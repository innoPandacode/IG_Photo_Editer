import os
import sys
import time
from colorama import init, Fore, Style
from PIL import Image, ExifTags
from concurrent.futures import ThreadPoolExecutor
import threading

# 初始化 colorama
init()

def add_watermark(input_folder, output_folder, watermark_path, image_filename):
    try:
       # 讀取浮水印
        watermark = Image.open(watermark_path)

        # 讀取圖片
        image_path = os.path.join(input_folder, image_filename)
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

        # 计算浮水印的目标宽度，根据照片的短边的0.08575807倍来计算
        target_width = int(0.08575807 * min(img.width, img.height))
        target_height = target_width  # 保持正方形比例

        
        # 计算照片的长边和短边长度
        long_edge_length = max(img.width, img.height)
        short_edge_length = min(img.width, img.height)

        # 计算浮水印距离照片边缘的固定偏移值
        if img.height > img.width:  # 如果照片是直幅
            offset_percentage = short_edge_length * 0.02447917
        else:  # 如果照片是横幅
            offset_percentage = short_edge_length * 0.02447917

        # 计算浮水印的相对位置
        x_offset = int(offset_percentage)
        y_offset = int(offset_percentage)

        # 计算浮水印的相对位置
        x = img.width - target_width - x_offset
        y = img.height - target_height - y_offset

        # 缩放浮水印
        watermark_resized = watermark.resize((target_width, target_height))

        # 在照片上粘贴浮水印
        img.paste(watermark_resized, (x, y), watermark_resized)

        # 将带有浮水印的照片保存到输出文件夹
        output_path = os.path.join(output_folder, image_filename)
        img.save(output_path)

        print(f"Watermark added to {image_filename}")

    except Exception as e:
        print(f"An error occurred while processing {image_filename}: {str(e)}")

def add_white_border_to_image(input_image_path, output_image_path):
    try:
        img = Image.open(input_image_path)
        
        # 如果寬度或高度為奇數，進行等比放大一像素
        width, height = img.size
        if width % 2 != 0:
            width += 3
        if height % 2 != 0:
            height += 3
        
        # 計算白邊尺寸
        max_size = max(width, height)
        scale = 2048 / max_size

        new_width = int(width * scale)
        new_height = int(height * scale)

        # 調整圖片大小
        resized_image = img.resize((int(new_width), int(new_height)), Image.LANCZOS)

        # 創建新的白邊圖片
        new_img = Image.new("RGB", (2048, 2048), "white")

        # 計算圖片的居中位置
        x_offset = (2048 - new_width) // 2
        y_offset = (2048 - new_height) // 2

        # 將調整大小後的圖片粘貼到新圖片上
        new_img.paste(resized_image, (x_offset, y_offset))

        # 保存帶有白邊的圖片
        new_img.save(output_image_path)

        print(f"White border added to {output_image_path}")

    except Exception as e:
        print(f"An error occurred while adding white border to {input_image_path}: {str(e)}")


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

def process_image(input_folder, output_folder, watermark_path, image_filename):
    add_watermark(input_folder, output_folder, watermark_path, image_filename)

def setup_environment():
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

    # Manually input the input folder location
    input_folder = input("Enter the image folder path: ")

    # 检查输入文件夹是否存在
    if not os.path.exists(input_folder):
        print("Error: The specified folder does not exist.")
        input("Press Enter to exit.")
        exit()

    # 列出輸入文件夾中的圖片文件
    image_files = [f for f in os.listdir(input_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    # 如果沒有圖片文件，顯示錯誤消息並等待用戶輸入後退出
    if not image_files:
        print("Error: No image files found in the input folder.")
        input("Press Enter to exit.")
        exit()

    # 显示图片数量（用绿色文本）并等待一秒
    #print(f"\033[92mTotal number of images: {len(image_files)}\033[0m")
    print(f"{Fore.GREEN}Total number of images: {len(image_files)}{Style.RESET_ALL}")
    time.sleep(1)

    # Create the output folder
    output_folder = os.path.join(input_folder, "IG_LOGO_Cropper")
    os.makedirs(output_folder, exist_ok=True)

    return watermark_path, input_folder, output_folder, image_files

def main():
    watermark_path, input_folder, output_folder, image_files = setup_environment()

    selected_logo = select_logo(watermark_path)

    # 設定最大同時運行的線程數，您可以根據需要進行調整
    max_threads = 20

    with ThreadPoolExecutor(max_threads) as executor:
        # 使用 submit 方法提交任務，每個圖片處理任務都是一個線程
        for image_filename in image_files:
            executor.submit(process_image, input_folder, output_folder, selected_logo, image_filename)

    add_white_border_option = input("Do you want to add a white border? (Enter 'y' or 'n'): ").lower()

    if add_white_border_option == "y":
        with ThreadPoolExecutor(max_threads) as executor:
            for image_filename in image_files:
                input_image_path = os.path.join(output_folder, image_filename)
                output_image_path = os.path.join(output_folder, f"{image_filename}")

                executor.submit(add_white_border_to_image, input_image_path, output_image_path)

if __name__ == "__main__":
    main()

print("All processing completed.")
input("Press Enter to exit.")
exit()