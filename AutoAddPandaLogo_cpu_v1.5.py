import os
import sys
import time
import cv2
import numpy as np
from colorama import init, Fore, Style
from PIL import Image, ExifTags
from concurrent.futures import ThreadPoolExecutor
import threading
import shutil
def add_watermark(input_folder_path, output_folder_path, watermark_path, image_filename):
    try:
        # 讀取浮水印
        watermark = Image.open(watermark_path)

        # 讀取圖片
        image_path = os.path.join(input_folder_path, image_filename)
        img = Image.open(image_path)

        # 清除圖片的方向信息
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        if hasattr(img, '_getexif') and img._getexif() is not None:
            exif = dict(img._getexif().items())
            if orientation in exif:
                if exif[orientation] == 3:
                    img = img.rotate(180, expand=True)
                elif exif[orientation] == 6:
                    img = img.rotate(270, expand=True)
                elif exif[orientation] == 8:
                    img = img.rotate(90, expand=True)
        
        # 計算浮水印的目標寬度和高度，保持正方形比例
        target_width = int(0.08575807 * min(img.width, img.height))
        target_height = target_width
  
        # 計算浮水印的位置
        x_offset = int(0.02447917 * min(img.width, img.height))
        y_offset = x_offset
        x = img.width - target_width - x_offset
        y = img.height - target_height - y_offset

        # 調整浮水印大小
        watermark_resized = watermark.resize((target_width, target_height))

        # 在圖片上添加浮水印
        img.paste(watermark_resized, (x, y), watermark_resized)

        # 保存帶有浮水印的圖片
        output_path = os.path.join(output_folder_path, image_filename)
        img.save(output_path)
        print(f"Watermark added to {image_filename}")

    except Exception as e:
        print(f"An error occurred while processing {image_filename}: {str(e)}")

    time.sleep(1)

def add_white_border_to_image(input_image_path, output_image_path):
    try:
        img = Image.open(input_image_path)

        width, height = img.size
        
        # 計算縮放比例，限制長邊為 2048 像素
        if width > height:
            new_width = 2048
            scale = new_width / width
            new_height = int(height * scale)
        else:
            new_height = 2048
            scale = new_height / height
            new_width = int(width * scale)

        # 計算白邊大小
        white_border_x = max(0, (2048 - new_width) // 2)
        white_border_y = max(0, (2048 - new_height) // 2)

        # 調整大小
        resized_image = img.resize((new_width, new_height), Image.LANCZOS)

        # 創建帶白邊的新圖片
        new_img = Image.new("RGB", (2048, 2048), "white")

        # 粘貼調整大小後的圖片到新圖片上
        x_offset = white_border_x
        y_offset = white_border_y
        new_img.paste(resized_image, (x_offset, y_offset))

        # 保存帶有白邊的圖片
        new_img.save(output_image_path)
        print(f"White border added to {output_image_path}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

    time.sleep(1)

def select_logo(watermark_path):
    # List all files in the watermark directory
    logo_files = os.listdir(watermark_path)

    print("Select a logo style:")
    for i, logo in enumerate(logo_files, 1):
        print(f"{i}. {logo}")

    while True:
        try:
            choice = int(input("Enter the number of the logo you want to use: "))
            if 1 <= choice <= len(logo_files):
                selected_logo = os.path.join(watermark_path, logo_files[choice - 1])
                return selected_logo
            else:
                print("Invalid choice. Please enter a valid number.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def setup_logo_environment():
    # Get the path to the watermark directory in the same directory as the script
    if getattr(sys, 'frozen', False):
        # Running as a compiled .exe file
        script_directory = os.path.dirname(sys.executable)
    else:
        # Running as a script
        script_directory = os.path.dirname(__file__)

    watermark_path = os.path.join(script_directory, "LOGOPATH")

    # 如果LOGOPATH文件夾不存在，創建它並提醒用戶
    if not os.path.exists(watermark_path):
        os.makedirs(watermark_path)
        print("The LOGOPATH folder was created, but it doesn't contain any LOGO files.")
        input("Press Enter to exit.")
        exit()
    else:
        # 檢查LOGOPATH文件夾內是否有LOGO文件，如果沒有，提示用戶
        logo_files = os.listdir(watermark_path)
        if not any(filename.lower().endswith((".png", ".jpg", ".jpeg")) for filename in logo_files):
            print("The LOGOPATH folder exists, but it doesn't contain any LOGO files.")
            input("Press Enter to exit.")
            exit()

    return watermark_path

def count_images(folder_path):
    image_extensions = ('.png', '.jpg', '.jpeg')
    image_count = 0

    for root, dirs, files in os.walk(folder_path):
        image_count += len([file for file in files if file.lower().endswith(image_extensions)])

    return image_count

def initialize_environment():
    # 手动输入输入文件夹路径
    input_folder_path = input("Enter the image folder path: ")
    
    # 检查输入文件夹是否存在
    if not os.path.exists(input_folder_path):
        print("Error: The specified folder does not exist.")
        input("Press Enter to exit.")
        exit()

    # 创建输出文件夹路徑
    output_folder_path = os.path.join(input_folder_path, "IG_LOGO_Cropper")

     # 检查输出文件夹是否存在，如果存在则删除
    if os.path.exists(output_folder_path):
        print("Deleting existing output folder...")
        shutil.rmtree(output_folder_path)

    # 列出输入文件夹中的图片文件
    image_files = [f for f in os.listdir(input_folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    '''
    # 如果没有图片文件，显示错误消息并等待用户输入后退出
    if not image_files:
        print("Error: No image files found in the input folder.")
        input("Press Enter to exit.")
        exit()
        '''
    total_images = count_images(input_folder_path)
    # 显示图片数量（用绿色文本）并等待一秒
    print(f"{Fore.GREEN}Total number of images: {total_images}{Style.RESET_ALL}")
    time.sleep(1)
    return input_folder_path, output_folder_path, image_files

def check_empty_folders(input_folder_path):
    empty_folders = []
    subfolders = [f for f in os.listdir(input_folder_path) if os.path.isdir(os.path.join(input_folder_path, f))]
    for subfolder in subfolders:
        subfolder_path = os.path.join(input_folder_path, subfolder)
        if not os.listdir(subfolder_path):
            empty_folders.append(subfolder)
    return empty_folders

def copy_folder_structure(source_folder, destination_folder):
    empty_folders = check_empty_folders(source_folder)

    for item in os.listdir(source_folder):
        source_item_path = os.path.join(source_folder, item)
        destination_item_path = os.path.join(destination_folder, item)

        if os.path.isdir(source_item_path):
            if item not in empty_folders:  # 跳过空文件夹
                os.makedirs(destination_item_path, exist_ok=True)
                copy_folder_structure(source_item_path, destination_item_path)  # 递归复制文件夹内的内容
        else:
            shutil.copy2(source_item_path, destination_item_path)  # 复制文件

def general_mode(watermark_path):

    input_folder_path, output_folder_path, image_files = initialize_environment()

    while True:
        # 根據 CPU 線程數計算最大線程數（假設使用 80% 的 CPU 線程）
        max_threads = int(os.cpu_count() * 0.8)
        print(f"Max CPU threads set to: {max_threads}")

        print("Select option:")
        print("1. Add watermark")
        print("2. Add white border")
        print("3. Add watermark and then add white border")

        user_choice = input("Enter your choice (1, 2, or 3): ")

        # 創建輸出文件夾
        os.makedirs(output_folder_path, exist_ok=True)

        with ThreadPoolExecutor(max_threads) as executor:
            if user_choice == "1":
                # 只加水印
                selected_logo = select_logo(watermark_path)
                for image_filename in image_files:
                    executor.submit(add_watermark, input_folder_path, output_folder_path, selected_logo, image_filename)
                break
            elif user_choice == "2":
                # 只加白邊
                for image_filename in image_files:
                    input_image_path = os.path.join(input_folder_path, image_filename)
                    output_image_path = os.path.join(output_folder_path, image_filename)
                    executor.submit(add_white_border_to_image, input_image_path, output_image_path)
                break
            elif user_choice == "3":
                # 先加水印，然後等1秒，再加白邊
                selected_logo = select_logo(watermark_path)
                for image_filename in image_files:
                    executor.submit(add_watermark, input_folder_path, output_folder_path, selected_logo, image_filename)
                time.sleep(1)
                for image_filename in image_files:
                    input_image_path = os.path.join(output_folder_path, image_filename)
                    output_image_path = os.path.join(output_folder_path, image_filename)
                    executor.submit(add_white_border_to_image, input_image_path, output_image_path)
                break
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

def advanced_batch_mode(watermark_path):
    input_folder_path, output_folder_path, image_files = initialize_environment()
    empty_folders = check_empty_folders(input_folder_path)
    print("destination_folder : " + output_folder_path)
    if empty_folders:
        print(f"{Fore.GREEN}Empty folders found:{Style.RESET_ALL}")
        for folder in empty_folders:
            print(folder)

        skip_empty_folders = input("Skip empty folders? (Enter 'y' or 'n'): ").lower()

        while skip_empty_folders not in ['y', 'n']:
            print("Invalid input. Please enter 'y' or 'n'.")
            skip_empty_folders = input("Skip empty folders? (Enter 'y' or 'n'): ").lower()

        if skip_empty_folders != 'y':
            print("Processing aborted.")
            exit()

    copy_folder_structure(input_folder_path, output_folder_path)
    
    # 根據 CPU 線程數計算最大線程數（假設使用 80% 的 CPU 線程）
    max_threads = int(os.cpu_count() * 0.8)
    print(f"Max CPU threads set to: {max_threads}")
    
    while True:
        user_choice = input("Enter your choice (1: Add watermark, 2: Add white border, 3: Add both): ")
        if user_choice in ["1", "2", "3"]:
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

    if user_choice == "1" or user_choice == "3":
        selected_logo = select_logo(watermark_path)
    else:
        selected_logo = None

    with ThreadPoolExecutor(max_threads) as executor:
        for root, dirs, files in os.walk(output_folder_path):
            for file in files:
                if user_choice == "1":
                    executor.submit(add_watermark, root, root, selected_logo, file)
                elif user_choice == "2":
                    executor.submit(add_white_border_to_image, os.path.join(root, file), os.path.join(root, file))
                elif user_choice == "3":
                    executor.submit(add_watermark, root, root, selected_logo, file)
                    time.sleep(1)  # 等待1秒
                    executor.submit(add_white_border_to_image, os.path.join(root, file), os.path.join(root, file))

def main():
    watermark_path = setup_logo_environment()
    print("Select mode:")
    print("1. General_mode")
    print("2. Advanced Batch Mode")
    
    while True:
        try:
            mode_choice = int(input("Enter your choice: "))
            
            if mode_choice in [1, 2]:
                break
            else:
                print("Invalid choice. Please enter 1 or 2.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    if mode_choice == 1:
        # 执行标准模式的逻辑
        general_mode(watermark_path)
    elif mode_choice == 2:
        # 执行高级批次模式的逻辑
        advanced_batch_mode(watermark_path)
    print(f"\n{Fore.GREEN}------------------- All processing completed -------------------{Style.RESET_ALL}")
    print(f"\n{Fore.GREEN}Press Enter to exit{Style.RESET_ALL}")
    input()  # 等待使用者輸入Enter鍵
    exit()

if __name__ == "__main__":
    main()

