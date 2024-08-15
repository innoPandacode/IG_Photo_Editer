from PIL import Image, ExifTags
import os
import datetime

def log_message(message):
    """
    格式化日誌輸出，包含時間戳與信息內容。
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def correct_orientation(img):
    """
    根據 EXIF 資訊來糾正圖片的方向。
    """
    try:
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
    except Exception as e:
        log_message(f"An error occurred while correcting orientation: {str(e)}")
    return img

def add_watermark(input_folder_path, output_folder_path, watermark_path, image_filename):
    try:
        # 讀取浮水印
        watermark = Image.open(watermark_path)

        # 讀取圖片
        image_path = os.path.join(input_folder_path, image_filename)
        img = Image.open(image_path)

        # 糾正圖片方向
        img = correct_orientation(img)
        
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
        log_message(f"Watermark added to {image_filename}")

    except FileNotFoundError:
        log_message(f"File not found: {image_filename}")
    except Exception as e:
        log_message(f"An error occurred while processing {image_filename}: {str(e)}")

def add_white_border_to_image(input_image_path, output_image_path):
    try:
        # 取得檔案名稱以一致格式
        image_filename = os.path.basename(input_image_path)
        
        img = Image.open(input_image_path)
        img = correct_orientation(img)

        width, height = img.size
        
        # 計算縮放比例，限制長邊為 target_size 像素
        target_size = 2048
        if width > height:
            scale = target_size / width
        else:
            scale = target_size / height

        new_width = int(width * scale)
        new_height = int(height * scale)

        # 計算白邊大小
        white_border_x = max(0, (target_size - new_width) // 2)
        white_border_y = max(0, (target_size - new_height) // 2)

        # 調整大小
        resized_image = img.resize((new_width, new_height), Image.LANCZOS)

        # 創建帶白邊的新圖片
        new_img = Image.new("RGB", (target_size, target_size), "white")

        # 粘貼調整大小後的圖片到新圖片上
        new_img.paste(resized_image, (white_border_x, white_border_y))

        # 保存帶有白邊的圖片
        new_img.save(output_image_path)
        log_message(f"White border added to {image_filename}")

    except FileNotFoundError:
        log_message(f"File not found: {image_filename}")
    except Exception as e:
        log_message(f"An error occurred while processing {image_filename}: {str(e)}")
