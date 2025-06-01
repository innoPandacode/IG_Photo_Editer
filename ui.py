# ui.py (v2.10 – 完整)
"""
Tkinter 介面
* 保留原始版面：左側控制面板 + 右側雙預覽。
* 預設勾選 Add Watermark 和 Add Border。
* CPU 執行緒數 = 約 80% 實體核心，避免 100% 滿載。
* 支援黑邊/白邊互斥，預覽與批量輸出一致。
* 兩階段多執行緒：先浮水印，再邊框；使用 ThreadPoolExecutor 限流。
"""

from __future__ import annotations

import os
import sys
import json
import queue
import threading
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import pillow_heif  # type: ignore
pillow_heif.register_heif_opener()

from image_processing import (
    correct_orientation,
    add_watermark,
    add_border_to_image,
)

# -------------------- 全域常數 -------------------- #
CONFIG_FILENAME = "config.json"
PREVIEW_W, PREVIEW_H = 400, 300
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".heic", ".heif")
FINAL_SIZE = 2048
CPU_POOL_SIZE = max(1, int((os.cpu_count() or 1) * 0.8))  # ≈80% CPU


class IGLogoApp(tk.Tk):
    VERSION = "v2.5"
    DEFAULT_WM_RATIO = 0.08575807
    DEFAULT_OFFSET_RATIO = 0.02447917

    def __init__(self):
        super().__init__()
        self.title("Image Processing Tool")

        # ---------- 動態狀態 ---------- #
        self.image_folder: str | None = None
        self.watermark_path: str = ""
        self.tasks: list[tuple[str, str, str]] = []
        self.total_tasks = 0
        self.done_wm = 0
        self.done_bd = 0
        self.stop_flag = False
        self.result_q: queue.Queue[tuple[str, str]] = queue.Queue()

        # ---------- Tk 變數 (預設勾選 watermark & border) ---------- #
        self.mode_var = tk.StringVar(value="general")
        self.wm_var = tk.BooleanVar(value=True)
        self.bd_var = tk.BooleanVar(value=True)
        self.black_var = tk.BooleanVar(value=False)
        self.size_var = tk.DoubleVar(value=self.DEFAULT_WM_RATIO)
        self.off_x = tk.DoubleVar(value=1 - self.DEFAULT_OFFSET_RATIO)
        self.off_y = tk.DoubleVar(value=1 - self.DEFAULT_OFFSET_RATIO)

        # ---------- 預覽快取 ---------- #
        self.samples: dict[str, str | None] = {"landscape": None, "portrait": None}
        self.base_previews: dict[str, Image.Image | None] = {"landscape": None, "portrait": None}
        self.preview_canvases: dict[str, tk.Canvas] = {}

        # 讀設定並建 UI
        self._load_config()
        self._build_ui()
        self.after(100, self._poll_q)

    # -------------------- 設定檔 -------------------- #
    def _cfg_path(self) -> str:
        base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
        return os.path.join(base, CONFIG_FILENAME)

    def _load_config(self):
        path = self._cfg_path()
        self.cfg: dict[str, str] = {}
        if os.path.exists(path):
            try:
                self.cfg = json.load(open(path, 'r', encoding='utf-8'))
            except Exception:
                self.cfg = {}
        self.watermark_path = self.cfg.get('watermark_path', '')

    def _save_config(self):
        self.cfg['watermark_path'] = self.watermark_path
        json.dump(self.cfg, open(self._cfg_path(), 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

    # -------------------- UI 組件 -------------------- #
    def _build_ui(self):
        self.columnconfigure(1, weight=1)

        # 左側控制面板
        ctrl = ttk.Frame(self, padding=10)
        ctrl.grid(row=0, column=0, sticky='ns')

        ttk.Label(ctrl, text='Mode:').grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(ctrl, text='General', variable=self.mode_var, value='general').grid(row=0, column=1)
        ttk.Radiobutton(ctrl, text='Advanced', variable=self.mode_var, value='advanced').grid(row=0, column=2)

        ttk.Checkbutton(ctrl, text='Add Watermark', variable=self.wm_var, command=self._refresh).grid(row=1, column=0, sticky='w')
        ttk.Checkbutton(ctrl, text='Add Border', variable=self.bd_var, command=self._refresh).grid(row=1, column=1, sticky='w')
        ttk.Checkbutton(ctrl, text='Black Border', variable=self.black_var, command=self._refresh).grid(row=1, column=2, sticky='w')

        ttk.Label(ctrl, text='Logo Size').grid(row=2, column=0, sticky='w')
        ttk.Scale(ctrl, from_=0.01, to=1.0, variable=self.size_var, orient='horizontal', command=lambda _e: self._refresh()).grid(row=2, column=1, columnspan=2, sticky='ew')

        ttk.Label(ctrl, text='Offset X').grid(row=3, column=0, sticky='w')
        ttk.Scale(ctrl, from_=0.0, to=1.0, variable=self.off_x, orient='horizontal', command=lambda _e: self._refresh()).grid(row=3, column=1, columnspan=2, sticky='ew')

        ttk.Label(ctrl, text='Offset Y').grid(row=4, column=0, sticky='w')
        ttk.Scale(ctrl, from_=0.0, to=1.0, variable=self.off_y, orient='horizontal', command=lambda _e: self._refresh()).grid(row=4, column=1, columnspan=2, sticky='ew')

        ttk.Button(ctrl, text='Reset Logo', command=self._reset_logo).grid(row=5, column=0, columnspan=3, sticky='ew', pady=4)

        ttk.Button(ctrl, text='Select Folder', command=self._sel_folder).grid(row=6, column=0, sticky='ew')
        self.folder_lbl = ttk.Label(ctrl, text='No folder', wraplength=150)
        self.folder_lbl.grid(row=6, column=1, columnspan=2)

        ttk.Button(ctrl, text='Select Watermark', command=self._sel_wm).grid(row=7, column=0, sticky='ew')
        self.wm_lbl = ttk.Label(ctrl, text=os.path.basename(self.watermark_path) or 'No watermark', wraplength=150)
        self.wm_lbl.grid(row=7, column=1, columnspan=2)

        self.start_btn = ttk.Button(ctrl, text='Start', command=self._start)
        self.start_btn.grid(row=8, column=0, sticky='ew')
        self.stop_btn = ttk.Button(ctrl, text='Stop', command=self._stop, state=tk.DISABLED)
        self.stop_btn.grid(row=8, column=1, sticky='ew')

        # 進度條 & 標籤
        self.wm_prog = ttk.Progressbar(ctrl, length=200)
        self.wm_prog.grid(row=9, column=0, columnspan=3, pady=(4,0))
        self.bd_prog = ttk.Progressbar(ctrl, length=200)
        self.bd_prog.grid(row=10, column=0, columnspan=3)
        self.wm_lbl_p = ttk.Label(ctrl, text='WM: 0/0')
        self.wm_lbl_p.grid(row=11, column=0, columnspan=3)
        self.bd_lbl_p = ttk.Label(ctrl, text='BD: 0/0')
        self.bd_lbl_p.grid(row=12, column=0, columnspan=3)

        self.log_txt = tk.Text(ctrl, width=40, height=20, font=('TkDefaultFont', 9))
        self.log_txt.grid(row=13, column=0, columnspan=3, pady=(4,0))
        ttk.Label(ctrl, text=f'Version {self.VERSION}').grid(row=14, column=0, columnspan=3, pady=2)

        # 右側預覽
        pv = ttk.Frame(self, padding=10)
        pv.grid(row=0, column=1, sticky='nsew')
        pv.columnconfigure(0, weight=1)
        ttk.Label(pv, text='Landscape').grid(row=0, column=0)
        self.preview_canvases['landscape'] = tk.Canvas(pv, width=PREVIEW_W, height=PREVIEW_H, bg='#ddd')
        self.preview_canvases['landscape'].grid(row=1, column=0, pady=4)
        ttk.Label(pv, text='Portrait').grid(row=2, column=0)
        self.preview_canvases['portrait'] = tk.Canvas(pv, width=PREVIEW_W, height=PREVIEW_H, bg='#ddd')
        self.preview_canvases['portrait'].grid(row=3, column=0, pady=4)

    # ==================== 日誌 & 輔助 ==================== #
    def _log(self, msg: str):
        self.log_txt.insert(tk.END, msg + "\n")
        self.log_txt.see(tk.END)

    def _reset_logo(self):
        self.size_var.set(self.DEFAULT_WM_RATIO)
        self.off_x.set(1 - self.DEFAULT_OFFSET_RATIO)
        self.off_y.set(1 - self.DEFAULT_OFFSET_RATIO)
        self._refresh()

    # ================ 資料夾 / 浮水印 選擇 ================ #
    def _sel_folder(self):
        p = filedialog.askdirectory()
        if not p:
            return
        self.image_folder = p
        self.folder_lbl.config(text=os.path.basename(p))
        self._load_samples()
        self._refresh()

    def _sel_wm(self):
        p = filedialog.askopenfilename(filetypes=[('Image', '*.png;*.jpg;*.jpeg;*.heic;*.heif')])
        if not p:
            return
        self.watermark_path = p
        self.wm_lbl.config(text=os.path.basename(p))
        self._save_config()
        self._refresh()

    # ==================== 預覽樣本 ==================== #
    def _load_samples(self):
        self.samples = {'landscape': None, 'portrait': None}
        if not self.image_folder:
            return
        for root, _dirs, fns in os.walk(self.image_folder):
            if 'IG_LOGO_Cropper' in root:
                continue
            for fn in sorted(fns):
                if not fn.lower().endswith(IMAGE_EXTS):
                    continue
                path = os.path.join(root, fn)
                try:
                    with Image.open(path) as im_raw:
                        im = correct_orientation(im_raw)
                        key = 'landscape' if im.width >= im.height else 'portrait'
                        if not self.samples[key]:
                            self.samples[key] = path
                        if all(self.samples.values()):
                            return
                except:
                    continue

    # ==================== 預覽刷新 ==================== #
    def _refresh(self):
        # 清除原本預覽
        for cv in self.preview_canvases.values():
            cv.delete('all')

        if not self.image_folder:
            return

        # 快取 base_previews
        for orient, path in self.samples.items():
            if not path:
                self.base_previews[orient] = None
                continue
            img = correct_orientation(Image.open(path)).convert('RGBA')
            r = min(PREVIEW_W / img.width, PREVIEW_H / img.height, 1.0)
            if r < 1.0:
                img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
            self.base_previews[orient] = img

        # Draw preview
        for orient, cv in self.preview_canvases.items():
            base = self.base_previews.get(orient)
            if base is None:
                continue
            iw, ih = base.size
            ox = oy = 0
            work = base.copy()

            # 邊框預覽
            if self.bd_var.get():
                square = max(iw, ih)
                color = 'black' if self.black_var.get() else 'white'
                bg = Image.new('RGBA', (square, square), color)
                ox = (square - iw) // 2
                oy = (square - ih) // 2
                bg.paste(work, (ox, oy))
                work = bg

            # 浮水印預覽
            if self.wm_var.get() and self.watermark_path:
                wm = Image.open(self.watermark_path).convert('RGBA')
                short = min(iw, ih)
                wm_sz = int(self.size_var.get() * short)
                wm = wm.resize((wm_sz, wm_sz), Image.LANCZOS)
                offset = int(self.DEFAULT_OFFSET_RATIO * short)
                dx = ox + iw - wm_sz - offset
                dy = oy + ih - wm_sz - offset
                work.paste(wm, (dx, dy), wm)

            tk_img = ImageTk.PhotoImage(work)
            cv.create_image((PREVIEW_W - work.width) // 2, (PREVIEW_H - work.height) // 2, anchor='nw', image=tk_img)
            cv.image_ref = tk_img

    # ==================== 批次處理 ==================== #
    def _start(self):
        if not self.image_folder:
            messagebox.showerror('Error', 'Select folder first')
            return
        if self.wm_var.get() and not self.watermark_path:
            messagebox.showerror('Error', 'Select watermark first')
            return

        # 清理舊輸出
        out_root = os.path.join(self.image_folder, 'IG_LOGO_Cropper')
        if os.path.isdir(out_root):
            shutil.rmtree(out_root)

        # 收集任務
        self.tasks.clear()
        if self.mode_var.get() == 'general':
            os.makedirs(out_root, exist_ok=True)
            for fn in os.listdir(self.image_folder):
                if fn.lower().endswith(IMAGE_EXTS):
                    self.tasks.append((self.image_folder, out_root, fn))
        else:
            for root, _dirs, fns in os.walk(self.image_folder):
                rel = os.path.relpath(root, self.image_folder)
                dst = os.path.join(out_root, rel)
                os.makedirs(dst, exist_ok=True)
                for fn in fns:
                    if fn.lower().endswith(IMAGE_EXTS):
                        self.tasks.append((root, dst, fn))

        self.total_tasks = len(self.tasks)
        if self.total_tasks == 0:
            messagebox.showinfo('Info', 'No images found')
            return

        # 重置進度條
        self.done_wm = self.done_bd = 0
        self.wm_prog.config(maximum=self.total_tasks, value=0)
        self.bd_prog.config(maximum=self.total_tasks, value=0)
        self.wm_lbl_p.config(text=f'WaterMark: 0/{self.total_tasks}')
        self.bd_lbl_p.config(text=f'Border: 0/{self.total_tasks}')

        self.stop_flag = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        # ---- 浮水印階段 ----
        if self.wm_var.get() and not self.stop_flag:
            with ThreadPoolExecutor(max_workers=CPU_POOL_SIZE) as ex:
                futures = {ex.submit(add_watermark, *t, wm_path=self.watermark_path, size_ratio=self.size_var.get(), off_ratio=self.DEFAULT_OFFSET_RATIO): t[2] for t in self.tasks}
                for fut in as_completed(futures):
                    if self.stop_flag:
                        break
                    fname = futures[fut]
                    try:
                        fut.result()
                    except Exception as e:
                        self.result_q.put(('err', f'[WM] {fname}: {e}'))
                    else:
                        self.result_q.put(('wm', fname))

        # ---- 邊框階段 ----
        if self.bd_var.get() and not self.stop_flag:
            border_color = 'black' if self.black_var.get() else 'white'
            with ThreadPoolExecutor(max_workers=CPU_POOL_SIZE) as ex:
                futures = {}
                for t in self.tasks:
                    src_root = t[1] if self.wm_var.get() else t[0]
                    futures[ex.submit(add_border_to_image, src_root, t[1], t[2], border_color, FINAL_SIZE)] = t[2]
                for fut in as_completed(futures):
                    if self.stop_flag:
                        break
                    fname = futures[fut]
                    try:
                        fut.result()
                    except Exception as e:
                        self.result_q.put(('err', f'[BD] {fname}: {e}'))
                    else:
                        self.result_q.put(('bd', fname))

        # 完成
        self.result_q.put(('done', ''))

    # ==================== UI 輪詢 ==================== #
    def _poll_q(self):
        try:
            while True:
                stage, msg = self.result_q.get_nowait()
                if stage == 'wm':
                    self.done_wm += 1
                    self.wm_prog['value'] = self.done_wm
                    self.wm_lbl_p.config(text=f'WM: {self.done_wm}/{self.total_tasks}')
                    self._log(f'Watermark OK: {msg}')
                elif stage == 'bd':
                    self.done_bd += 1
                    self.bd_prog['value'] = self.done_bd
                    self.bd_lbl_p.config(text=f'BD: {self.done_bd}/{self.total_tasks}')
                    self._log(f'Border OK: {msg}')
                elif stage == 'err':
                    self._log(msg)
                elif stage == 'done':
                    self._finish()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_q)

    def _stop(self):
        self.stop_flag = True
        self._log('Stop requested')

    def _finish(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._log('Processing complete')
        messagebox.showinfo('Done', 'Processing complete')


# -------------------- 入口 -------------------- #
def start_ui():
    app = IGLogoApp()
    app.mainloop()
