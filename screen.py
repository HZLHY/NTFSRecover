from tkinter import *
from tkinter import messagebox
from tkinter import ttk
from tkinter.filedialog import askdirectory
from NTFS_recover import *


def get_drives():
    ori_drives = win32api.GetLogicalDriveStrings()
    split_drive = ori_drives.split("\x00")
    drives = []
    for drive in split_drive:
        if drive:
            drives.append(drive[0] + ":\\")
    return drives


class SCREEN:

    def __init__(self):
        self.recover_mft = None
        self.delete_file = []
        self.root_window = Tk()  # 创建窗口对象的背景色
        self.root_window.geometry('450x300')  # 设置窗口大小
        self.root_window.title("NTFS文件系统-文件恢复")  # 设置title
        self.file_list_box = Listbox(self.root_window)  # 文件列表
        self.select_disk_label = Label(self.root_window, text="盘符选择：", font=('微软雅黑', 15))  # 标签
        self.select_disk_button = Button(self.root_window, text="确定", width=10, command=self.select_disk)
        self.scan_disk_button = Button(self.root_window, text="扫描文件", width=10, command=self.scan_disk)
        self.resume_file_button = Button(self.root_window, text="恢复文件", width=10, command=self.resume_file)
        self.disk_cbox = ttk.Combobox(self.root_window)  # 创建 列表组件
        self.disk_cbox['value'] = get_drives()  # 设置下拉菜单中的值
        self.disk_cbox.current(0)  # 通过 current() 设置下拉菜单选项的默认值
        self.path = StringVar()
        self.path_label = Label(self.root_window, text="选择保存路径:")
        self.path_entry = Entry(self.root_window, textvariable=self.path)
        self.path_button = Button(self.root_window, text="路径选择", command=self.select_path)

    # 按钮
    def select_disk(self):
        select_disk_value = self.disk_cbox.get()[0]
        # 要恢复的磁盘
        recover_drive = BPB_info(select_disk_value)
        start_position = recover_drive.return_start_position()
        self.recover_mft = MFT(start_position, select_disk_value, recover_drive.sector_per_cluster, recover_drive.bytes_per_sector)

        # 刷新界面组件
        self.select_disk_label.destroy()
        self.disk_cbox.destroy()
        self.select_disk_button.destroy()
        self.path_label.place(relx=0.1, rely=0.1)
        self.path_entry.place(relx=0.3, rely=0.1)
        self.path_button.place(relx=0.7, rely=0.1)
        self.scan_disk_button.place(relx=0.7, rely=0.3)
        self.resume_file_button.place(relx=0.7, rely=0.6)
        self.file_list_box.place(relx=0, rely=0.3, height=300, width=300)

    def scan_disk(self):
        file_list = []
        self.delete_file = self.recover_mft.find_delete_file_list()
        self.file_list_box.delete(0, len(self.delete_file))
        for i in self.delete_file:
            file_list.append(i[2])
        for i in file_list:
            self.file_list_box.insert("end", i)

    def resume_file(self):
        select_index = self.file_list_box.curselection()
        target_path = self.path_entry.get()
        if target_path:
            tuple_file = self.delete_file[select_index[0]]
            self.recover_mft.recover_file(tuple_file[0], tuple_file[1], tuple_file[2], target_path)
            messagebox.showinfo("消息", "恢复文件成功！")

        else:
            messagebox.showinfo("消息", "保存路径不能为空！")
        pass

    # 保存路径
    def select_path(self):
        self.path.set(askdirectory())

    # 将控件放入主页面

    def start(self):
        self.select_disk_label.grid(row=0, column=0, padx=10, pady=15)
        self.disk_cbox.grid(row=1, column=1)
        self.select_disk_button.grid(row=1, column=2, padx=10, pady=5)
        self.root_window.mainloop()


if __name__ == "__main__":
    screen = SCREEN()
    screen.start()
