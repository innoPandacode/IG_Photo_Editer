from PIL import Image
import os


def resize_and_fill(image_path, target_size):
    # 打开图像
    image = Image.open(image_path)

    # 计算缩放比例
    width, height = image.size
    max_size = max(width, height)
    scale = target_size / max_size

    # 计算缩放后的宽度和高度
    new_width = int(width * scale)
    new_height = int(height * scale)

    # 缩放图像
    resized_image = image.resize((new_width, new_height))

    # 创建新的空白图像
    new_image = Image.new("RGB", (target_size, target_size), "white")

    # 计算图像居中的位置
    x_offset = (target_size - new_width) // 2
    y_offset = (target_size - new_height) // 2

    # 将缩放后的图像粘贴到新图像上
    new_image.paste(resized_image, (x_offset, y_offset))

    # 返回处理后的图像
    return new_image


def process_images(folder_path):
    # 检查目录是否存在
    if not os.path.isdir(folder_path):
        print("文件路徑不存在")
        return

    # 创建保存调整后图像的文件夹
    save_folder = os.path.join(folder_path, "resize_for_IG")
    os.makedirs(save_folder, exist_ok=True)

    # 遍历目录下的所有文件
    for filename in os.listdir(folder_path):
        # 检查文件是否为图像文件
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            # 构建完整的文件路径
            image_path = os.path.join(folder_path, filename)

            # 调整图像大小并填充
            resized_image = resize_and_fill(image_path, 2048)

            # 构建保存路径
            save_path = os.path.join(save_folder, filename)

            # 保存处理后的图像
            resized_image.save(save_path)
            print(f"已保存處理後的圖像: {save_path}")


# 获取用户输入的文件夹路径
folder_path = input("輸入想要Resize的圖片資料夾路徑：")
# 处理图像
process_images(folder_path)
# 等待用户关闭窗口
input("處理完成。請關閉窗口退出...")

