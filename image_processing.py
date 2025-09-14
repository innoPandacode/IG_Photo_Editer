# image_processing.py (cleaned)
import os
import datetime
from typing import Dict, Any, Tuple
from PIL import Image, ExifTags, PngImagePlugin

# --------------------------------------------------------------------- #
# 共用小工具                                                             #
# --------------------------------------------------------------------- #
def log_message(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def correct_orientation(img: Image.Image) -> Image.Image:
    """依 EXIF 方向值自動旋轉；若無 EXIF 則原圖輸出"""
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

def _extract_meta(src_img: Image.Image, out_format: str) -> Dict[str, Any]:
    """
    從來源影像抽出需要寫回的 metadata，並將 Orientation 正規化為 1。
    回傳可直接展開給 PIL save() 的 kwargs。
    """
    out_format = (out_format or src_img.format or "").upper()
    kwargs: Dict[str, Any] = {}

    # --- EXIF：用可編輯的 Exif 物件，把 Orientation 設為 1，避免檢視器二次旋轉 ---
    try:
        exif = src_img.getexif()  # editable
        if exif is not None:
            orient_key = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
            exif[orient_key] = 1
            exif_bytes = exif.tobytes()
            if exif_bytes:
                kwargs["exif"] = exif_bytes
    except Exception:
        # fallback：若上面失敗，盡量帶回原始 bytes
        exif_bytes_fallback = src_img.info.get("exif")
        if exif_bytes_fallback:
            kwargs["exif"] = exif_bytes_fallback

    # --- ICC profile：維持色彩一致 ---
    icc = src_img.info.get("icc_profile")
    if icc:
        kwargs["icc_profile"] = icc

    # --- PNG 文字型 metadata（選用） ---
    if out_format == "PNG":
        pnginfo = PngImagePlugin.PngInfo()
        for k in ("XML:com.adobe.xmp", "Comment"):
            if k in src_img.info:
                pnginfo.add_text(k, src_img.info[k])
        if pnginfo.text:
            kwargs["pnginfo"] = pnginfo

    return kwargs

def _ensure_rgb_for_jpeg(img: Image.Image) -> Image.Image:
    """若輸出為 JPEG 且影像有 alpha，鋪白底轉成 RGB。"""
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    if img.mode == "P":
        return img.convert("RGB")
    return img

def _save_with_meta(result_img: Image.Image,
                    src_img: Image.Image,
                    dst: str,
                    quality: int = 95) -> None:
    """依據副檔名自動選擇格式，寫回 EXIF/ICC 等 metadata。"""
    fmt_hint = os.path.splitext(dst)[1].lower()
    is_jpeg = fmt_hint in (".jpg", ".jpeg")
    out_img = _ensure_rgb_for_jpeg(result_img) if is_jpeg else result_img
    save_kwargs = _extract_meta(src_img, out_img.format or "")
    if is_jpeg:
        save_kwargs.setdefault("quality", quality)
        save_kwargs.setdefault("subsampling", 0)
    out_img.save(dst, **save_kwargs)

# --------------------------------------------------------------------- #
# 浮水印                                                                 #
# --------------------------------------------------------------------- #
DEFAULT_WM_RATIO = 0.08575807   # 浮水印邊長 / 圖片短邊
DEFAULT_OFFSET_R = 0.02447917   # 浮水印離右下角距離 / 圖片短邊

def add_watermark(src_root: str,
                  dst_root: str,
                  fname: str,
                  wm_path: str,
                  size_ratio: float = DEFAULT_WM_RATIO,
                  off_ratio: float = DEFAULT_OFFSET_R) -> None:
    """於 src_root/fname 加浮水印 → 存 dst_root/fname（PNG 透明 OK）"""
    try:
        src = os.path.join(src_root, fname)
        dst = os.path.join(dst_root, fname)

        with Image.open(src) as im_src:
            img = correct_orientation(im_src).convert("RGBA")

            with Image.open(wm_path).convert("RGBA") as wm:
                short = min(img.width, img.height)
                wm_sz = int(short * size_ratio)
                wm = wm.resize((wm_sz, wm_sz), Image.LANCZOS)

                offset = int(short * off_ratio)
                dx = img.width  - wm_sz - offset
                dy = img.height - wm_sz - offset

                img.paste(wm, (dx, dy), wm)

            _save_with_meta(img.convert("RGB"), im_src, dst)
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
    """於 src_root/fname 加正方形『白／黑』邊 → 存 dst_root/fname"""
    try:
        src = os.path.join(src_root, fname)
        dst = os.path.join(dst_root, fname)

        with Image.open(src) as im_src:
            img = correct_orientation(im_src)
            w, h = img.size
            scale = target_size / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            resized = img.resize((new_w, new_h), Image.LANCZOS)

            canvas = Image.new("RGB", (target_size, target_size), border_color)
            ox = (target_size - new_w) // 2
            oy = (target_size - new_h) // 2
            canvas.paste(resized, (ox, oy))

            _save_with_meta(canvas, im_src, dst)
        log_message(f"Border({border_color}) OK → {fname}")

    except Exception as e:
        log_message(f"[Err] Border {fname}: {e}")
        raise
