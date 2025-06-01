# image_processing.py
import os
import datetime
from PIL import Image, ExifTags

# --------------------------------------------------------------------- #
# 共用小工具                                                             #
# --------------------------------------------------------------------- #
def log_message(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def correct_orientation(img: Image.Image) -> Image.Image:
    """
    依 EXIF 方向值自動旋轉；若無 EXIF 則原圖輸出
    """
    try:
        orient_key = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
        exif = img.getexif()
        orient = exif.get(orient_key, 1) if exif else 1
        if orient == 3:
            img = img.rotate(180, expand=True)
        elif orient == 6:
            img = img.rotate(270, expand=True)
        elif orient == 8:
            img = img.rotate(90, expand=True)
    except Exception as e:
        log_message(f"[Warn] EXIF rotate failed: {e}")
    return img

# --------------------------------------------------------------------- #
# 浮水印                                                                 #
# --------------------------------------------------------------------- #
DEFAULT_WM_RATIO   = 0.08575807     # 浮水印邊長 / 圖片短邊
DEFAULT_OFFSET_R   = 0.02447917     # 浮水印離右下角距離 / 圖片短邊

def add_watermark(src_root: str, dst_root: str, fname: str,
                  wm_path: str,
                  size_ratio: float = DEFAULT_WM_RATIO,
                  off_ratio: float = DEFAULT_OFFSET_R) -> None:
    """
    於 src_root/fname 加浮水印 → 存 dst_root/fname（PNG 透明 OK）
    """
    try:
        src = os.path.join(src_root, fname)
        dst = os.path.join(dst_root, fname)
        img = correct_orientation(Image.open(src)).convert("RGBA")

        wm  = Image.open(wm_path).convert("RGBA")
        short = min(img.width, img.height)
        wm_sz = int(short * size_ratio)
        wm   = wm.resize((wm_sz, wm_sz), Image.LANCZOS)

        offset = int(short * off_ratio)
        dx = img.width  - wm_sz - offset
        dy = img.height - wm_sz - offset
        img.paste(wm, (dx, dy), wm)

        img.convert("RGB").save(dst, quality=95)
        log_message(f"Watermark OK → {fname}")
    except Exception as e:
        log_message(f"[Err] Watermark {fname}: {e}")
        raise

# --------------------------------------------------------------------- #
# 邊框（白或黑）                                                         #
# --------------------------------------------------------------------- #
def add_border_to_image(src_root: str,
                        dst_root: str,
                        fname: str,
                        border_color: str = "white",
                        target_size: int = 2048) -> None:
    """
    於 src_root/fname 加正方形『白／黑』邊 → 存 dst_root/fname
    """
    try:
        src = os.path.join(src_root, fname)
        dst = os.path.join(dst_root, fname)

        img = correct_orientation(Image.open(src))
        w, h = img.size
        scale = target_size / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        canvas = Image.new("RGB", (target_size, target_size), border_color)
        ox = (target_size - new_w) // 2
        oy = (target_size - new_h) // 2
        canvas.paste(resized, (ox, oy))

        canvas.save(dst, quality=95)
        log_message(f"Border({border_color}) OK → {fname}")
    except Exception as e:
        log_message(f"[Err] Border {fname}: {e}")
        raise
