# image_processing.py
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
        for orientation in ExifTags.TAGS:
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = img._getexif() if hasattr(img, '_getexif') else None
        if exif and orientation in exif:
            orient = exif[orientation]
            if orient == 3:
                img = img.rotate(180, expand=True)
            elif orient == 6:
                img = img.rotate(270, expand=True)
            elif orient == 8:
                img = img.rotate(90, expand=True)
    except Exception as e:
        log_message(f"Error correcting orientation: {e}")
    return img

def add_watermark(input_folder_path, output_folder_path, watermark_path, image_filename):
    try:
        watermark = Image.open(watermark_path)
        image_path = os.path.join(input_folder_path, image_filename)
        img = Image.open(image_path)
        img = correct_orientation(img)
        
        target_width = int(0.08575807 * min(img.width, img.height))
        target_height = target_width
        x_offset = int(0.02447917 * min(img.width, img.height))
        y_offset = x_offset
        x = img.width - target_width - x_offset
        y = img.height - target_height - y_offset

        watermark_resized = watermark.resize((target_width, target_height))
        img.paste(watermark_resized, (x, y), watermark_resized)

        output_path = os.path.join(output_folder_path, image_filename)
        img.save(output_path)
        
        log_message(f"Watermark added: {image_filename}")
        return f"Watermark added: {image_filename}"

    except FileNotFoundError:
        error_msg = f"File not found: {image_filename}"
        log_message(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An error occurred while processing {image_filename}: {str(e)}"
        log_message(error_msg)
        return error_msg


# image_processing.py
def add_white_border_to_image(
        input_folder_path,
        output_folder_path,
        image_filename,
        target_size=2048
):
    """
    讀 input_folder_path/image_filename
    只在短邊留下白邊後，存到 output_folder_path/image_filename
    """
    try:
        input_image_path  = os.path.join(input_folder_path, image_filename)
        output_image_path = os.path.join(output_folder_path, image_filename)

        img = Image.open(input_image_path)
        img = correct_orientation(img)

        w, h = img.size
        scale = target_size / max(w, h)           # 長邊縮到 target_size
        new_w, new_h = int(w * scale), int(h * scale)
        new_w += new_w % 2                         # 轉成偶數，避免日後壓縮取半像素
        new_h += new_h % 2

        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas  = Image.new("RGB", (target_size, target_size), "white")

        # 只會在短邊方向留下白邊
        x = (target_size - new_w) // 2
        y = (target_size - new_h) // 2
        canvas.paste(resized, (x, y))

        canvas.save(output_image_path)
        log_message(f"Border added: {image_filename}")
        return f"Border added: {image_filename}"

    except Exception as e:
        err = f"Border error [{image_filename}]: {e}"
        log_message(err)
        return err

    except FileNotFoundError:
        error_msg = f"File not found: {image_filename}"
        log_message(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An error occurred while processing {image_filename}: {str(e)}"
        log_message(error_msg)
        return error_msg
