import win32api


def get_drives():
    ori_drives = win32api.GetLogicalDriveStrings()
    split_drive = ori_drives.split("\x00")
    drives = []
    for drive in split_drive:
        if drive:
            drives.append(drive[0])
    return drives


class BPB_info:

    def __init__(self, drive_name):
        self.drive_name = drive_name
        self.disk_read = open(r'\\.\\' + drive_name + ':', 'rb')

        self.disk_read.read(3)
        self.disk_read.seek(0x0B)
        self.bytes_per_sector = int.from_bytes(self.disk_read.read(2), byteorder='little')  # 扇区大小

        self.disk_read.seek(0x0d)
        self.sector_per_cluster = int.from_bytes(self.disk_read.read(1), byteorder='little')  # 每簇扇区数

        self.disk_read.seek(0x30)
        self.mft_start_cluster = int.from_bytes(self.disk_read.read(8), byteorder='little')  # MFT起始簇号

        self.disk_read.seek(0x40)
        self.cluster_per_mft = int.from_bytes(self.disk_read.read(4), byteorder='little')

    def return_start_position(self):
        return self.mft_start_cluster * self.sector_per_cluster * self.bytes_per_sector


# MFT头部56字节
# 非常驻属性，属性头64字节；常驻属性，属性头24字节
class MFT:
    file_list = []  # 扫描获得的已删除的文件列表及其对应的MFT序号
    MFT_section_array = []  # 记录每个MFT段的起始位置和簇数

    def __init__(self, position, drive_name, sector_per_cluster, bytes_per_sector):
        self.drive_name = drive_name
        self.start_position = position
        self.sector_per_cluster = sector_per_cluster
        self.bytes_per_sector = bytes_per_sector
        self.disk_read = open(r'\\.\\' + drive_name + ':', 'rb')

    # 获取已删除的文件名和对应MFT位置index
    # 整个MFT以FF FF FF FF 结尾，大小1024字节，占两个扇区
    # MFT文件的第一个记录就是描述他自己的，这样可以确定扫描范围
    def find_delete_file_list(self):
        self.file_list = []
        self.MFT_section_array = []
        self.disk_read = open(r'\\.\\' + self.drive_name + ':', 'rb')
        self.disk_read.read(1)  # 好像要先读取一下，seek才能用，每次单参数seek都是相对最开始
        self.disk_read.seek(self.start_position)  # 移动到MFT起始位置
        # MFT_node = self.disk_read.read(1024)
        # 本来以为FF结尾，直接判断遍历即可，FF是在实际结尾处的
        # 要用到80h属性中的runlist了
        # 第一个属性偏移地址0x14
        self.disk_read.read(1)
        self.disk_read.seek(self.start_position + 20)
        first_attribute_position = int.from_bytes(self.disk_read.read(2), byteorder='little')

        self.disk_read.seek(self.start_position + first_attribute_position)
        attribute_type = hex(int.from_bytes(self.disk_read.read(4), byteorder='little'))  # 第一个一般为0x10

        # 循环属性，寻找80h属性
        while attribute_type != '0x80':
            attribute_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
            self.disk_read.seek(attribute_length - 8, 1)
            # 这里需要注意，hex()返回的是字符串
            attribute_type = hex(int.from_bytes(self.disk_read.read(4), byteorder='little'))

        # 找到80属性后，因该寻找运行列表runlist
        # 判断是否为常驻属性,0为常驻属性，1为非常驻属性
        attribute_type80_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
        is_resident_attribute = int.from_bytes(self.disk_read.read(1), 'little')
        attribute_header_length = 64 if is_resident_attribute else 24

        # 因为MFT的第一个文件记录就是描述他自己的，现在我们对其进行解析，特别是留意0x80属性的runlist
        # 判断是否为非常驻属性
        if is_resident_attribute:
            runlist_length = 0
            self.disk_read.seek(attribute_header_length - 9, 1)
            # 获取高低位
            info_byte = self.disk_read.read(1)
            info_byte_num = int.from_bytes(info_byte, byteorder='little')
            # low表示紧接着low个字节为簇流的簇数，high表示后high个字节为簇流起始
            info_byte_high, info_byte_low = info_byte_num >> 4, info_byte_num & 0x0f
            # 解释后面字节
            runlist_cluster_num = int.from_bytes(self.disk_read.read(info_byte_low), byteorder='little')
            runlist_start_cluster = int.from_bytes(self.disk_read.read(info_byte_high), byteorder='little', signed=True)

            self.MFT_section_array.append((runlist_start_cluster * self.sector_per_cluster * self.bytes_per_sector, runlist_cluster_num))
            pre_mft_start_cluster = runlist_start_cluster
            runlist_length += info_byte_high + info_byte_low
            # 非常驻属性中，分为一个运行列表和多个运行列表，需要分开讨论
            # 判断是否有对多个流标志
            have_next = int.from_bytes(self.disk_read.read(1), byteorder='little')
            if have_next:
                while have_next:
                    # 下一runlist的压缩字节
                    next_high, next_low = have_next >> 4, have_next & 0x0f
                    next_runlist_cluster_num = int.from_bytes(self.disk_read.read(next_low), byteorder='little')
                    next_runlist_start_cluster = int.from_bytes(self.disk_read.read(next_high), byteorder='little', signed=True)
                    now_mft_start_cluster = pre_mft_start_cluster + next_runlist_start_cluster
                    mft_section_start = now_mft_start_cluster * self.sector_per_cluster * self.bytes_per_sector
                    self.MFT_section_array.append((mft_section_start, next_runlist_cluster_num))
                    pre_mft_start_cluster = now_mft_start_cluster

                    runlist_length += (next_low + next_high)
                    if runlist_length >= attribute_type80_length - attribute_header_length:
                        break
                    have_next = int.from_bytes(self.disk_read.read(1), byteorder='little')

        self.disk_read.close()
        self.disk_read = open(r'\\.\\' + self.drive_name + ':', 'rb')

        section_index = 0  # MFT分区的序号
        for mft_section in self.MFT_section_array:  # 遍历不同的MFT段
            self.disk_read.seek(mft_section[0])  # 移动到对应的MFT段开头
            mft_num = (mft_section[1] * self.sector_per_cluster) // 2  # 每个MFT段的mft文件记录的数目
            for mft in range(mft_num):  # 遍历一个MFT段的文件记录
                FILE_flag = self.disk_read.read(4)  # 获取FILE标志
                self.disk_read.seek(0x12, 1)
                delete_flag = int.from_bytes(self.disk_read.read(2), byteorder='little')  # 是否为删除文件标志
                # 找到被删除的MFT项添加到列表中
                if FILE_flag == b'FILE' and delete_flag == 0:
                    return_filename = self.find_file_name(mft_section[0], mft)
                    if return_filename:
                        self.file_list.append((section_index, mft, return_filename))  # 以元组的形式加入列表，将MFT序号对应其文件名
                        # print("第{}个MFT段".format(section_index), mft, ":", return_filename)
                    else:
                        break
                self.disk_read.seek(mft_section[0] + (mft + 1) * 1024)
            section_index += 1
        self.disk_read.close()
        return self.file_list

    # 根据表项序号获取文件名字
    def find_file_name(self, mft_section_start, mft_index):
        self.disk_read = open(r'\\.\\' + self.drive_name + ':', 'rb')
        # 移动到对应MFT项起始位置
        find_name_start = mft_section_start + mft_index * 1024
        self.disk_read.seek(find_name_start)
        self.disk_read.read(4)
        self.disk_read.seek(0x10, 1)
        first_attribute_postion = int.from_bytes(self.disk_read.read(2), byteorder='little')
        self.disk_read.seek(find_name_start + first_attribute_postion)
        find_name_attribute_type = hex(int.from_bytes(self.disk_read.read(4), byteorder='little'))
        # 寻找0x30属性
        if find_name_attribute_type != '0xffffffff':  # 表示一个文件记录结束
            while find_name_attribute_type != '0x30':
                attribute_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
                self.disk_read.seek(attribute_length - 8, 1)
                find_name_attribute_type = hex(int.from_bytes(self.disk_read.read(4), byteorder='little'))

            attribute_type30_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
            is_resident_attribute = int.from_bytes(self.disk_read.read(1), 'little')
            attribute_header_length = 64 if is_resident_attribute else 24
            self.disk_read.seek(attribute_header_length - 9 + 64, 1)
            name_length = int.from_bytes(self.disk_read.read(1), byteorder='little')
            name_space = int.from_bytes(self.disk_read.read(1), byteorder='little')  # 这个一直是零
            file_name = self.disk_read.read(2 * name_length).decode('utf-16')
            return file_name
        else:
            return None

    # 根据MFT分区序号和mft文件记录项的序号恢复文件
    def recover_file(self, re_mft_section_index, re_mft_index, re_file_name, re_output_path):
        re_file_byte_data = b''
        runlist_array = []
        self.disk_read = open(r'\\.\\' + self.drive_name + ':', 'rb')
        re_file_start = self.MFT_section_array[re_mft_section_index][0] + re_mft_index * 1024
        self.disk_read.seek(re_file_start)
        self.disk_read.read(1)
        self.disk_read.seek(0x13, 1)  # 移动到第一个属性位置
        first_attribute_position = int.from_bytes(self.disk_read.read(2), byteorder='little')

        self.disk_read.seek(re_file_start + first_attribute_position)
        attribute_type = hex(int.from_bytes(self.disk_read.read(4), byteorder='little'))  # 第一个一般为0x10
        # 循环属性，寻找80h属性
        while attribute_type != '0x80':
            attribute_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
            # 难道是转换格式问题...hex()返回的是字符...所以之前一直错
            self.disk_read.seek(attribute_length - 8, 1)
            attribute_type = hex(int.from_bytes(self.disk_read.read(4), byteorder='little'))
        # 找到80属性后，应该寻找运行列表runlist
        # 判断是否为常驻属性,0为常驻属性，1为非常驻属性
        attribute_type80_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
        is_resident_attribute = int.from_bytes(self.disk_read.read(1), 'little')
        attribute_header_length = 64 if is_resident_attribute else 24
        # 若为非常驻属性
        if is_resident_attribute:
            runlist_length = 0
            self.disk_read.seek(39, 1)
            real_size = int.from_bytes(self.disk_read.read(8), byteorder='little')
            self.disk_read.seek(attribute_header_length - 56, 1)
            # 获取高低位
            info_byte = self.disk_read.read(1)
            info_byte_num = int.from_bytes(info_byte, byteorder='little')
            # low表示紧接着low个字节为簇流的簇数，high表示后high个字节为簇流起始
            info_byte_high, info_byte_low = info_byte_num >> 4, info_byte_num & 0x0f
            # 解释后面字节
            runlist_cluster_num = int.from_bytes(self.disk_read.read(info_byte_low), byteorder='little')
            runlist_start_cluster = int.from_bytes(self.disk_read.read(info_byte_high), byteorder='little', signed=True)
            # print(runlist_start_cluster, runlist_cluster_num)
            runlist_length += info_byte_high + info_byte_low

            runlist_array.append((runlist_start_cluster, runlist_cluster_num))
            pre_start = runlist_start_cluster
            # 判断是否有对多个流标志
            have_next = int.from_bytes(self.disk_read.read(1), byteorder='little')
            if have_next:
                while have_next:
                    # 下一runlist的压缩字节
                    next_high, next_low = have_next >> 4, have_next & 0x0f
                    next_runlist_cluster_num = int.from_bytes(self.disk_read.read(next_low), byteorder='little')
                    next_runlist_start_cluster = int.from_bytes(self.disk_read.read(next_high), byteorder='little', signed=True)
                    now_start = pre_start + next_runlist_start_cluster
                    runlist_array.append((now_start, next_runlist_cluster_num))
                    pre_start = now_start

                    runlist_length += (next_low + next_high)
                    if runlist_length >= attribute_type80_length - attribute_header_length:
                        break
                    have_next = int.from_bytes(self.disk_read.read(1), byteorder='little')
            # print(runlist_array)
            # 只有一个runlist
            if len(runlist_array) == 1:
                runlist_ptr = runlist_array[0][0] * self.sector_per_cluster * self.bytes_per_sector
                self.disk_read.seek(runlist_ptr)
                re_file_byte_data = self.disk_read.read(real_size)
            else:
                for runlist_index in range(len(runlist_array) - 1):
                    # runlist的起始位置
                    runlist_ptr = runlist_array[runlist_index][0] * self.sector_per_cluster * self.bytes_per_sector
                    self.disk_read.seek(runlist_ptr)
                    # 每个runlist要读取的字节数
                    runlist_byte_num = runlist_array[runlist_index][1] * self.sector_per_cluster * self.sector_per_cluster
                    re_file_byte_data += self.disk_read.read(runlist_byte_num)
                    # 每个runlist不一定全都能读完，所以要依靠真实大小realsize
                    real_size -= runlist_byte_num
                last_runlist_ptr = runlist_array[len(runlist_array) - 1][0] * self.sector_per_cluster * self.bytes_per_sector
                self.disk_read.seek(last_runlist_ptr)
                re_file_byte_data += self.disk_read.read(real_size)
        else:  # 常驻数据
            self.disk_read.read(1)
            attribute_offset = int.from_bytes(self.disk_read.read(2), byteorder='little')
            self.disk_read.seek(4, 1)
            re_file_data_length = int.from_bytes(self.disk_read.read(4), byteorder='little')
            self.disk_read.seek(attribute_header_length - attribute_offset + 4, 1)
            re_file_byte_data = self.disk_read.read(re_file_data_length)
        # 读取数据后创建文件写入
        with open(re_output_path + '\\' + re_file_name, 'ba') as f:
            f.write(re_file_byte_data)
        self.disk_read.close()


# if __name__ == '__main__':
#     h_disk = get_drives()[3]
#     recover_drive = BPB_info(h_disk)
#     print(recover_drive.bytes_per_sector, recover_drive.sector_per_cluster, recover_drive.mft_start_cluster)
#     start_position = recover_drive.mft_start_cluster * recover_drive.sector_per_cluster * recover_drive.bytes_per_sector
#     recover_mft = MFT(start_position, h_disk, recover_drive.sector_per_cluster, recover_drive.bytes_per_sector)
#     recover_mft.find_delete_file_list()
    # recover_mft.recover_file(0, 39, recover_mft.find_file_name(recover_mft.MFT_section_array[0][0], 39), "D:\\")
