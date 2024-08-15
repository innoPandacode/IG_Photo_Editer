import os
import sys
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
from image_processing import add_watermark, add_white_border_to_image
import threading
from threading_executor import process_images_with_threads

class ImageProcessingApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Image Processing Tool")
        
        self.image_folder = None
        self.watermark_path = None
        self.stop_processing = False  # 用於控制處理是否中止
        
        # 版本號
        self.version = "2.1"
        
        # 主框架
        main_frame = tk.Frame(master)
        main_frame.pack(padx=10, pady=10)

        # 左側面板（處理選項）
        left_pane = tk.Frame(main_frame)
        left_pane.grid(row=0, column=0, sticky="n")

        # 模式選擇
        self.mode_var = tk.StringVar(value="general")
        tk.Label(left_pane, text="Select Mode:").pack(anchor="w", padx=10, pady=(10, 0))
        tk.Radiobutton(left_pane, text="General Mode", variable=self.mode_var, value="general").pack(anchor="w", padx=20)
        tk.Radiobutton(left_pane, text="Advanced Batch Mode", variable=self.mode_var, value="advanced").pack(anchor="w", padx=20)
        
        # 圖片處理選項
        self.add_watermark_var = tk.BooleanVar(value=True)
        self.add_border_var = tk.BooleanVar(value=False)
        tk.Label(left_pane, text="Image Processing Options:").pack(anchor="w", padx=10, pady=(10, 0))
        tk.Checkbutton(left_pane, text="Add Watermark", variable=self.add_watermark_var, command=self.toggle_watermark_option).pack(anchor="w", padx=20)
        tk.Checkbutton(left_pane, text="Add White Border", variable=self.add_border_var).pack(anchor="w", padx=20)
        
        # 選擇資料夾按鈕
        self.select_folder_button = tk.Button(left_pane, text="Select Image Folder", command=self.select_folder)
        self.select_folder_button.pack(pady=10)
        
        # 顯示所選資料夾路徑
        self.folder_path_label = tk.Label(left_pane, text="")
        self.folder_path_label.pack(pady=5)
        
        # 選擇水印按鈕
        self.select_watermark_button = tk.Button(left_pane, text="Select Watermark", command=self.select_watermark, state=tk.NORMAL)
        self.select_watermark_button.pack(pady=10)
        
        # 開始處理按鈕
        self.start_button = tk.Button(left_pane, text="Start Processing", command=self.start_processing)
        self.start_button.pack(pady=10)

        # 停止處理按鈕
        self.stop_button = tk.Button(left_pane, text="Stop Processing", command=self.stop_processing_command, state=tk.DISABLED)
        self.stop_button.pack(pady=10)
        
        # 初始化進度條和標籤（先初始化浮水印進度條，再初始化白邊進度條）
        self.watermark_progress_label = tk.Label(left_pane, text="Watermark Progress: 0/0")
        self.watermark_progress = ttk.Progressbar(left_pane, orient="horizontal", length=300, mode="determinate")

        self.border_progress_label = tk.Label(left_pane, text="Border Progress: 0/0")
        self.border_progress = ttk.Progressbar(left_pane, orient="horizontal", length=300, mode="determinate")
        
        # 記錄日誌區域
        tk.Label(left_pane, text="Logs:").pack(anchor="w", padx=10, pady=(10, 0))
        self.log_text = tk.Text(left_pane, height=10, width=50, state=tk.DISABLED)
        self.log_text.pack(pady=10)

        # 右側面板（預覽與設置）
        right_pane = tk.Frame(main_frame)
        right_pane.grid(row=0, column=1, padx=20)

        # 水印預覽
        self.preview_label = tk.Label(right_pane, text="Watermark Preview:")
        self.preview_label.pack(pady=(20, 5))
        self.preview_canvas = tk.Canvas(right_pane, width=200, height=200, bg="#808080")  # 中性灰背景
        self.preview_canvas.pack()

        # 水印設置參數
        tk.Label(right_pane, text="Watermark Settings:").pack(anchor="w", padx=10, pady=(10, 0))
        tk.Label(right_pane, text="Transparency:").pack(anchor="w", padx=20)
        self.transparency_var = tk.DoubleVar(value=0.5)
        self.transparency_scale = tk.Scale(right_pane, from_=0, to=1, resolution=0.1, orient="horizontal", variable=self.transparency_var, state=tk.DISABLED)
        self.transparency_scale.pack(anchor="w", padx=20)
        
        tk.Label(right_pane, text="Position Offset:").pack(anchor="w", padx=20)
        self.position_var = tk.DoubleVar(value=0.05)
        self.position_scale = tk.Scale(right_pane, from_=0, to=0.5, resolution=0.01, orient="horizontal", variable=self.position_var, state=tk.DISABLED)
        self.position_scale.pack(anchor="w", padx=20)

        # 版本號標籤
        version_label = tk.Label(main_frame, text=f"Version: {self.version}")
        version_label.grid(row=1, column=0, sticky="w", padx=10, pady=10)
    
    def toggle_watermark_option(self):
        """根據水印選項的選擇狀態，啟用或禁用水印相關設置。"""
        if self.add_watermark_var.get():
            self.select_watermark_button.config(state=tk.NORMAL)
        else:
            self.select_watermark_button.config(state=tk.DISABLED)
            self.watermark_path = None
            self.preview_canvas.delete("all")
            self.log("Watermark option disabled, skipping watermark selection.")
    
    def select_folder(self):
        """選擇要處理的圖像資料夾。"""
        self.image_folder = filedialog.askdirectory(title="Select Image Folder")
        if self.image_folder:
            self.folder_path_label.config(text=f"Selected folder: {self.image_folder}")
            self.log(f"Selected folder: {self.image_folder}")
            self.start_button.config(state=tk.NORMAL)
        else:
            self.log("No folder selected.")

    def select_watermark(self):
        """選擇水印圖片文件，默認打開在當前目錄下的 Logopath 資料夾。"""
        # 判斷是否為 PyInstaller 打包的可執行文件
        if hasattr(sys, '_MEIPASS'):
            # 使用 sys.executable 獲取可執行文件所在的目錄
            base_path = os.path.dirname(sys.executable)
        else:
            # 否則使用腳本當前所在的目錄
            base_path = os.path.dirname(os.path.abspath(__file__))

        # 定義 Logopath 目錄
        logopath_directory = os.path.join(base_path, "Logopath")

        # 如果 Logopath 目錄不存在，則創建它
        if not os.path.exists(logopath_directory):
            os.makedirs(logopath_directory)
            self.log(f"Created Logopath directory: {logopath_directory}")

        # 打開文件對話框，默認目錄設置為 Logopath
        self.watermark_path = filedialog.askopenfilename(
            initialdir=logopath_directory,
            title="Select Watermark Image", 
            filetypes=(("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*"))
        )

        if self.watermark_path:
            self.log(f"Selected watermark: {self.watermark_path}")
            self.display_preview()
        else:
            self.log("No watermark selected.")

    def display_preview(self):
        """顯示所選水印的預覽。"""
        if self.watermark_path:
            img = Image.open(self.watermark_path)
            img.thumbnail((200, 200))
            img_tk = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image(100, 100, image=img_tk)
            self.preview_canvas.image = img_tk  # 保持引用以避免垃圾回收

    def log(self, message):
        """將信息寫入日誌區域，並統一格式化路徑。"""
        formatted_message = message.replace("\\", "/")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, formatted_message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)
    
    def start_processing(self):
        """啟動圖片處理流程。"""
        # 重置停止標誌
        self.stop_processing = False
        
        # 檢查是否有必要顯示進度條並初始化
        if self.add_watermark_var.get() and not self.watermark_path:
            messagebox.showerror("Error", "Watermark selected but no watermark image chosen.")
            return

        # 禁用開始按鈕並啟用停止按鈕
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # 重置日誌區域
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        # 隱藏所有進度條
        self.watermark_progress_label.pack_forget()
        self.watermark_progress.pack_forget()
        self.border_progress_label.pack_forget()
        self.border_progress.pack_forget()

        # 根據選項顯示進度條
        if self.add_watermark_var.get() and not self.add_border_var.get():
            # 只選擇了加浮水印
            self.watermark_progress_label.config(text="Watermark Progress: 0/0")
            self.watermark_progress["maximum"] = len(os.listdir(self.image_folder))
            self.watermark_progress["value"] = 0
            self.watermark_progress_label.pack(pady=5)
            self.watermark_progress.pack(pady=10)
        elif self.add_border_var.get() and not self.add_watermark_var.get():
            # 只選擇了加白邊
            self.border_progress_label.config(text="Border Progress: 0/0")
            self.border_progress["maximum"] = len(os.listdir(self.image_folder))
            self.border_progress["value"] = 0
            self.border_progress_label.pack(pady=5)
            self.border_progress.pack(pady=10)
        elif self.add_watermark_var.get() and self.add_border_var.get():
            # 兩者都選擇了
            self.watermark_progress_label.config(text="Watermark Progress: 0/0")
            self.watermark_progress["maximum"] = len(os.listdir(self.image_folder))
            self.watermark_progress["value"] = 0
            self.watermark_progress_label.pack(pady=5)
            self.watermark_progress.pack(pady=10)

            self.border_progress_label.config(text="Border Progress: 0/0")
            self.border_progress["maximum"] = len(os.listdir(self.image_folder))
            self.border_progress["value"] = 0
            self.border_progress_label.pack(pady=5)
            self.border_progress.pack(pady=10)

        # 啟動新線程來處理圖片，以避免阻塞主UI線程
        processing_thread = threading.Thread(target=self.process_images)
        processing_thread.start()

    def stop_processing_command(self):
        """用戶請求停止處理圖片。"""
        self.stop_processing = True
        self.log("Processing stopped by user.")
        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)

    def process_images(self):
        """實際執行圖片處理的功能，根據用戶選擇的設置加水印或加白邊，且不修改原圖。"""
        if not self.image_folder:
            messagebox.showerror("Error", "Image folder not selected.")
            return

        if self.add_watermark_var.get() and not self.watermark_path:
            messagebox.showerror("Error", "Watermark selected but no watermark image chosen.")
            return

        output_root_folder = os.path.join(self.image_folder, "IG_LOGO_Cropper")

        if os.path.exists(output_root_folder):
            shutil.rmtree(output_root_folder)
            self.log(f"Deleted existing folder: {output_root_folder}")

        os.makedirs(output_root_folder, exist_ok=True)

        # 確認模式
        if self.mode_var.get() == "advanced":
            # 在進階模式下，計算所有需要處理的圖片數量，並初始化進度條
            total_images = self.count_images(self.image_folder)
            self.init_progress_bars(total_images)
            # 遞迴處理資料夾中的所有圖片
            self.process_folder_recursively(self.image_folder, output_root_folder)
        else:
            # 在一般模式下，只處理當前資料夾中的圖片
            image_files = [f for f in os.listdir(self.image_folder) if os.path.isfile(os.path.join(self.image_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            total_images = len(image_files)
            self.init_progress_bars(total_images)
            self.process_single_folder(self.image_folder, output_root_folder)

        if not self.stop_processing:
            self.log("Processing completed successfully.")
            messagebox.showinfo("Completed", "Image processing completed successfully.")

        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)

    def count_images(self, folder):
        """遞迴計算資料夾中所有圖片的總數量，排除 IG_LOGO_Cropper 資料夾。"""
        total_images = 0
        for root, dirs, files in os.walk(folder):
            if "IG_LOGO_Cropper" in root:
                continue
            total_images += len([f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
        return total_images

    def init_progress_bars(self, total_images):
        """初始化進度條。"""
        
        # 隱藏所有進度條
        self.watermark_progress_label.pack_forget()
        self.watermark_progress.pack_forget()
        self.border_progress_label.pack_forget()
        self.border_progress.pack_forget()

        # 根據選項顯示並初始化進度條
        if self.add_watermark_var.get():
            self.watermark_progress["maximum"] = total_images
            self.watermark_progress["value"] = 0
            self.watermark_progress_label.config(text=f"Watermark Progress: 0/{total_images}")
            self.watermark_progress_label.pack(pady=5)
            self.watermark_progress.pack(pady=10)

        if self.add_border_var.get():
            self.border_progress["maximum"] = total_images
            self.border_progress["value"] = 0
            self.border_progress_label.config(text=f"Border Progress: 0/{total_images}")
            self.border_progress_label.pack(pady=5)
            self.border_progress.pack(pady=10)

    def process_folder_recursively(self, input_folder, output_folder):
        """Advanced Mode: 遞迴處理資料夾中的所有圖片，並保持相同的資料夾結構。"""
        for root, dirs, files in os.walk(input_folder):
            relative_path = os.path.relpath(root, input_folder)
            output_dir = os.path.join(output_folder, relative_path)
            
            # 跳過 IG_LOGO_Cropper 資料夾
            if "IG_LOGO_Cropper" in relative_path:
                continue
            
            os.makedirs(output_dir, exist_ok=True)
            
            image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

            # 步驟1：加水印
            if self.add_watermark_var.get():
                for image_filename in image_files:
                    if self.stop_processing:
                        self.log("Processing stopped by user.")
                        return

                    input_image_path = os.path.join(root, image_filename)
                    output_image_path = os.path.join(output_dir, image_filename)

                    add_watermark(root, output_dir, self.watermark_path, image_filename)

                    # 更新水印進度條
                    self.watermark_progress["value"] += 1
                    self.watermark_progress_label.config(text=f"Watermark Progress: {self.watermark_progress['value']}/{self.watermark_progress['maximum']}")
                    self.master.update_idletasks()

            # 步驟2：加白邊
            if self.add_border_var.get():
                for image_filename in image_files:
                    if self.stop_processing:
                        self.log("Processing stopped by user.")
                        return

                    input_image_path = os.path.join(output_dir, image_filename) if self.add_watermark_var.get() else os.path.join(root, image_filename)
                    output_image_path = os.path.join(output_dir, image_filename)

                    add_white_border_to_image(input_image_path, output_image_path)

                    # 更新白邊進度條
                    self.border_progress["value"] += 1
                    self.border_progress_label.config(text=f"Border Progress: {self.border_progress['value']}/{self.border_progress['maximum']}")
                    self.master.update_idletasks()

    def process_single_folder(self, input_folder, output_folder):
        """General Mode: 處理單一資料夾中的所有圖片，不遞迴。"""
        image_files = [f for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg'))]

        for image_filename in image_files:
            if self.stop_processing:
                self.log("Processing stopped by user.")
                return

            input_image_path = os.path.join(input_folder, image_filename)
            output_image_path = os.path.join(output_folder, image_filename)

            # 如果只選擇了加浮水印
            if self.add_watermark_var.get() and not self.add_border_var.get():
                add_watermark(input_folder, output_folder, self.watermark_path, image_filename)
                self.watermark_progress["value"] += 1
                self.watermark_progress_label.config(text=f"Watermark Progress: {self.watermark_progress['value']}/{self.watermark_progress['maximum']}")
                self.master.update_idletasks()

            # 如果只選擇了加白邊
            elif self.add_border_var.get() and not self.add_watermark_var.get():
                add_white_border_to_image(input_image_path, output_image_path)
                self.border_progress["value"] += 1
                self.border_progress_label.config(text=f"Border Progress: {self.border_progress['value']}/{self.border_progress['maximum']}")
                self.master.update_idletasks()

            # 如果兩者都選擇了
            elif self.add_watermark_var.get() and self.add_border_var.get():
                add_watermark(input_folder, output_folder, self.watermark_path, image_filename)
                add_white_border_to_image(output_image_path, output_image_path)
                self.watermark_progress["value"] += 1
                self.watermark_progress_label.config(text=f"Watermark Progress: {self.watermark_progress['value']}/{self.watermark_progress['maximum']}")
                self.border_progress["value"] += 1
                self.border_progress_label.config(text=f"Border Progress: {self.border_progress['value']}/{self.border_progress['maximum']}")
                self.master.update_idletasks()

def start_ui():
    """啟動應用的主UI。"""
    root = tk.Tk()
    app = ImageProcessingApp(root)
    root.mainloop()

if __name__ == "__main__":
    start_ui()
