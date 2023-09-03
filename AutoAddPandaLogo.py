import os
import sys
import time
from colorama import init, Fore, Style
from PIL import Image, ExifTags
# 初始化 colorama
init()

def add_watermark(input_folder, output_folder, watermark_path):
    try:
        # Step 2: Read the watermark and scale it proportionally
        watermark = Image.open(watermark_path)

        # Resize the watermark
        new_width = int(watermark.width * 0.7779)
        new_height = int(watermark.height * 0.7779)
        watermark = watermark.resize((new_width, new_height))

        # Iterate through image files in the input folder and add watermark
        for filename in os.listdir(input_folder):
            if filename.lower().endswith((".jpg", ".jpeg", ".png")):
                print("Processing image:", filename)
                image_path = os.path.join(input_folder, filename)
                img = Image.open(image_path)

                # Clear the image's orientation information
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                if hasattr(img, '_getexif'):
                    exif = dict(img._getexif().items())
                    if orientation in exif:
                        if exif[orientation] == 3:
                            img = img.rotate(180, expand=True)
                        elif exif[orientation] == 6:
                            img = img.rotate(270, expand=True)
                        elif exif[orientation] == 8:
                            img = img.rotate(90, expand=True)

                # Calculate watermark position
                x = img.width - watermark.width - 142
                y = img.height - watermark.height - 142

                # Paste the watermark onto the image
                img.paste(watermark, (x, y), watermark)

                # Save the image with watermark to the output folder
                output_path = os.path.join(output_folder, filename)
                img.save(output_path)

        print("Watermarking completed!")

    except Exception as e:
        print("An error occurred:", str(e))


def add_white_border(input_folder):
    # Iterate through image files in the input folder and add white border
    for filename in os.listdir(input_folder):
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            print("Processing image:", filename)
            image_path = os.path.join(input_folder, filename)
            img = Image.open(image_path)

            # Calculate scaling ratio
            width, height = img.size
            max_size = max(width, height)
            scale = 2048 / max_size

            # Calculate the width and height after scaling
            new_width = int(width * scale)
            new_height = int(height * scale)

            # Resize the image
            resized_image = img.resize((new_width, new_height))

            # Create a new blank image
            new_img = Image.new("RGB", (2048, 2048), "white")

            # Calculate the centered position for the image
            x_offset = (2048 - new_width) // 2
            y_offset = (2048 - new_height) // 2

            # Paste the resized image onto the new image
            new_img.paste(resized_image, (x_offset, y_offset))

            # Save the image with white border to the output folder
            output_path = os.path.join(output_folder, filename)
            new_img.save(output_path)

    print("White border added!")


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

def setup_environment():
    # Get the path to the watermark directory in the same directory as the script
    if getattr(sys, 'frozen', False):
        # Running as a compiled .exe file
        script_directory = os.path.dirname(sys.executable)
    else:
        # Running as a script
        script_directory = os.path.dirname(__file__)

    watermark_path = os.path.join(script_directory, "LOGOPATH")

    # 如果LOGOPATH文件夹不存在，创建它并提醒用户
    if not os.path.exists(watermark_path):
        os.makedirs(watermark_path)
        print("The LOGOPATH folder was created, but it doesn't contain any LOGO files.")
        input("Press Enter to exit.")
        exit()
    else:
        # 检查LOGOPATH文件夹内是否有LOGO文件，如果没有，提示用户
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

    # 列出输入文件夹中的图片文件
    image_files = [f for f in os.listdir(input_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    # 如果没有图片文件，显示错误消息并等待用户输入后退出
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

    return watermark_path, input_folder, output_folder

if __name__ == "__main__":
    watermark_path, input_folder, output_folder = setup_environment()

    # Automatically select a watermark logo from watermark_path
    selected_logo = select_logo(watermark_path)

    # Perform watermarking
    add_watermark(input_folder, output_folder, selected_logo)

    # Ask whether to add white border
    while True:
        add_white_border_option = input("Do you want to add a white border? (Enter 'y' or 'n'): ").lower()
        if add_white_border_option in ['y', 'n']:
            break
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

    if add_white_border_option == "y":
        add_white_border(output_folder)

input("Press Enter to exit.")
exit()