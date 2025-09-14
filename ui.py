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
    VERSION = "v2.6"
    DEFAULT_WM_RATIO = 0.08575807
    DEFAULT_OFFSET_RATIO = 0.02447917

    def __init__(self):
        super().__init__()
        self.title("Image Processing Tool")

        # --- 先備好設定與預設值，並讀取 config.json（exe/腳本所在資料夾） ---
        self.cfg: dict[str, str] = {}
        self.watermark_path: str = ""   # 先給預設，_load_config 會覆蓋
        self._load_config()             # 讀完後可從 self.cfg 取值

        # ---------- 動態狀態 ---------- #
        self.image_folder: str | None = None
        self.tasks: list[tuple[str, str, str]] = []
        self.total_tasks = 0
        self.done_wm = 0
        self.done_bd = 0
        self.stop_flag = False
        self.result_q: queue.Queue[tuple[str, str]] = queue.Queue()

        # ---------- Tk 變數 (預設勾選 watermark & border) ---------- #
        self.mode_var  = tk.StringVar(value="general")
        self.wm_var    = tk.BooleanVar(value=True)
        self.bd_var    = tk.BooleanVar(value=True)
        self.black_var = tk.BooleanVar(value=False)
        self.size_var  = tk.DoubleVar(value=self.DEFAULT_WM_RATIO)
        self.off_x     = tk.DoubleVar(value=1 - self.DEFAULT_OFFSET_RATIO)
        self.off_y     = tk.DoubleVar(value=1 - self.DEFAULT_OFFSET_RATIO)
        self.out_size  = tk.IntVar(value=int(self.cfg.get('out_size', 2048)))

        # ---------- 預覽快取 ---------- #
        self.samples: dict[str, str | None] = {"landscape": None, "portrait": None}
        self.base_previews: dict[str, Image.Image | None] = {"landscape": None, "portrait": None}
        self.preview_canvases: dict[str, tk.Canvas] = {}

        # 建 UI（此時 self.watermark_path / self.out_size 已就緒）
        self._build_ui()
        self.after(100, self._poll_q)

    # -------------------- 設定檔 -------------------- #
    def _cfg_path(self) -> str:
        # 打包後（frozen）→ EXE 所在夾；開發期 → 此 .py 檔所在夾
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent
        return str(base_dir / CONFIG_FILENAME)  # CONFIG_FILENAME 例如 "config.json"


    def _load_config(self):
        path = self._cfg_path()
        self.cfg = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.cfg = json.load(f)
            except Exception as e:
                # 此時 UI 尚未建好，先用 print 避免 _log 崩潰
                print(f"[Config] load failed: {e}")
                self.cfg = {}

        # 套用到成員
        self.watermark_path = self.cfg.get('watermark_path', '')
        try:
            v = int(self.cfg.get('out_size', 2048))
            if 512 <= v <= 8192:
                if hasattr(self, 'out_size'):
                    self.out_size.set(v)
                else:
                    self.cfg['out_size'] = v
        except Exception:
            pass

    def _save_config(self):
        try:
            self.cfg['watermark_path'] = self.watermark_path
            if hasattr(self, 'out_size'):
                self.cfg['out_size'] = int(self.out_size.get())
            with open(self._cfg_path(), 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # 這時 UI 已存在，才安全用 _log
            self._log(f"[Config] save failed: {e}")

    # -------------------- UI 組件 -------------------- #
    def _build_ui(self):
        self.columnconfigure(1, weight=1)

        # ==== 左側控制面板 ====
        ctrl = ttk.Frame(self, padding=10)
        ctrl.grid(row=0, column=0, sticky='ns')
        ctrl.columnconfigure(0, weight=0)
        ctrl.columnconfigure(1, weight=1)
        ctrl.columnconfigure(2, weight=0)

        # 小工具：建立水平滑桿（帶即時刷新）
        def make_scale(row, label, var, lo, hi):
            ttk.Label(ctrl, text=label).grid(row=row, column=0, sticky='w')
            ttk.Scale(
                ctrl, from_=lo, to=hi, orient='horizontal',
                variable=var, command=lambda _e: self._refresh()
            ).grid(row=row, column=1, columnspan=2, sticky='ew')

        # 模式
        ttk.Label(ctrl, text='Mode:').grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(ctrl, text='General',  variable=self.mode_var, value='general').grid(row=0, column=1, sticky='w')
        ttk.Radiobutton(ctrl, text='Advanced', variable=self.mode_var, value='advanced').grid(row=0, column=2, sticky='w')

        # 勾選項
        ttk.Checkbutton(ctrl, text='Add Watermark', variable=self.wm_var, command=self._refresh).grid(row=1, column=0, sticky='w')
        ttk.Checkbutton(ctrl, text='Add Border',    variable=self.bd_var, command=self._refresh).grid(row=1, column=1, sticky='w')
        ttk.Checkbutton(ctrl, text='Black Border',  variable=self.black_var, command=self._refresh).grid(row=1, column=2, sticky='w')

        # Logo 相關
        make_scale(2, 'Logo Size', self.size_var, 0.01, 1.0)
        make_scale(3, 'Offset X',  self.off_x,    0.0,  1.0)
        make_scale(4, 'Offset Y',  self.off_y,    0.0,  1.0)
        ttk.Button(ctrl, text='Reset Logo', command=self._reset_logo).grid(row=5, column=0, columnspan=3, sticky='ew', pady=4)

        # Output size（使用 row=6，避免與 row=5 衝突）
        out_row = 6
        rowf = ttk.Frame(ctrl)
        rowf.grid(row=out_row, column=0, columnspan=3, sticky='ew', pady=(4, 6))
        rowf.columnconfigure(0, weight=1)

        ttk.Label(rowf, text='Output size (px)').grid(row=0, column=0, sticky='w')

        val_frame = ttk.Frame(rowf)
        val_frame.grid(row=0, column=1, sticky='e')

        val_lbl = ttk.Label(val_frame, text=f'{self.out_size.get()} px', width=8)
        val_lbl.pack(side='left', padx=(0, 4))

        def _reset_out_size():
            self.out_size.set(2048)
            val_lbl.config(text='2048 px')
            self._save_config()  # 想即時記憶

        ttk.Button(val_frame, text='Reset', width=5, command=_reset_out_size).pack(side='right')

        scale = ttk.Scale(
            rowf, from_=512, to=8192, orient='horizontal',
            variable=self.out_size
        )
        scale.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(2, 0))

        # 吸附到 128 並更新顯示
        def _on_out_size(v):
            val = int(round(float(v) / 128) * 128)
            val = max(512, min(8192, val))
            if val != self.out_size.get():
                self.out_size.set(val)
            val_lbl.config(text=f'{val} px')
        scale.configure(command=_on_out_size)

        # （可選）變更就自動存設定
        # self.out_size.trace_add('write', lambda *_: self._save_config())

        # 檔案/浮水印選擇
        ttk.Button(ctrl, text='Select Folder',    command=self._sel_folder).grid(row=7, column=0, sticky='ew')
        self.folder_lbl = ttk.Label(ctrl, text='No folder', wraplength=150)
        self.folder_lbl.grid(row=7, column=1, columnspan=2, sticky='w')

        ttk.Button(ctrl, text='Select Watermark', command=self._sel_wm).grid(row=8, column=0, sticky='ew')
        self.wm_lbl = ttk.Label(ctrl, text=os.path.basename(self.watermark_path) or 'No watermark', wraplength=150)
        self.wm_lbl.grid(row=8, column=1, columnspan=2, sticky='w')

        # Start / Stop
        self.start_btn = ttk.Button(ctrl, text='Start', command=self._start)
        self.start_btn.grid(row=9, column=0, sticky='ew')
        self.stop_btn  = ttk.Button(ctrl, text='Stop',  command=self._stop, state=tk.DISABLED)
        self.stop_btn.grid(row=9, column=1, sticky='ew')

        # 進度與日誌
        self.wm_prog = ttk.Progressbar(ctrl, length=200)
        self.wm_prog.grid(row=10, column=0, columnspan=3, pady=(4, 0))
        self.bd_prog = ttk.Progressbar(ctrl, length=200)
        self.bd_prog.grid(row=11, column=0, columnspan=3)
        self.wm_lbl_p = ttk.Label(ctrl, text='WM: 0/0')
        self.wm_lbl_p.grid(row=12, column=0, columnspan=3)
        self.bd_lbl_p = ttk.Label(ctrl, text='BD: 0/0')
        self.bd_lbl_p.grid(row=13, column=0, columnspan=3)

        self.log_txt = tk.Text(ctrl, width=40, height=20, font=('TkDefaultFont', 9))
        self.log_txt.grid(row=14, column=0, columnspan=3, pady=(4, 0))
        ttk.Label(ctrl, text=f'Version {self.VERSION}').grid(row=15, column=0, columnspan=3, pady=2)

        # ==== 右側預覽 ====
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
        preview_target = min(PREVIEW_W, PREVIEW_H)
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
            work = base.copy()

            if self.bd_var.get():
                # 與最終輸出一致的思路：先把 work 縮到預覽的固定邊長，再貼到正方形畫布
                color = 'black' if self.black_var.get() else 'white'
                scale = preview_target / max(iw, ih)
                new_w, new_h = int(iw * scale), int(ih * scale)
                resized = work.resize((new_w, new_h), Image.LANCZOS)

                bg = Image.new('RGBA', (preview_target, preview_target), color)
                ox = (preview_target - new_w) // 2
                oy = (preview_target - new_h) // 2
                bg.paste(resized, (ox, oy))
                work = bg
                # 之後的 wm 貼圖，會用 ox/oy 當「內容相對畫布」的基準點

                # 覆蓋 iw, ih 為「內容尺寸」（方便後續 wm 計算）
                iw, ih = new_w, new_h

            # 浮水印預覽（維持和成品一致，offset 採短邊比例）
            if self.wm_var.get() and self.watermark_path:
                wm = Image.open(self.watermark_path).convert('RGBA')
                short = min(iw, ih)
                wm_sz = int(self.size_var.get() * short)
                wm = wm.resize((wm_sz, wm_sz), Image.LANCZOS)

                # 如果有邊框，ox/oy 是內容的左上角相對正方形畫布的偏移
                # 沒邊框時，ox=oy=0
                offset = int(self.DEFAULT_OFFSET_RATIO * short)
                # 將 wm 貼在內容的右下角（不壓到邊）
                if work.width == preview_target and work.height == preview_target and self.bd_var.get():
                    # 有邊框時，內容右下角 = (ox+iw, oy+ih)
                    dx = (preview_target - (preview_target - iw) // 2) - wm_sz - offset
                    dy = (preview_target - (preview_target - ih) // 2) - wm_sz - offset
                    dx = (preview_target - iw) // 2 + iw - wm_sz - offset
                    dy = (preview_target - ih) // 2 + ih - wm_sz - offset
                else:
                    # 無邊框時直接用內容尺寸
                    dx = iw - wm_sz - offset
                    dy = ih - wm_sz - offset

                work.paste(wm, (dx, dy), wm)

            tk_img = ImageTk.PhotoImage(work)
            cv.create_image((PREVIEW_W - work.width) // 2,
                            (PREVIEW_H - work.height) // 2,
                            anchor='nw', image=tk_img)
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
                future_to_name = {}
                for t in self.tasks:
                    f = ex.submit(
                        add_watermark,
                        *t,
                        wm_path=self.watermark_path,
                        size_ratio=self.size_var.get(),
                        off_ratio=self.DEFAULT_OFFSET_RATIO
                    )
                    future_to_name[f] = t[2]  # 檔名

                for fut in as_completed(list(future_to_name.keys())):
                    if self.stop_flag:
                        break
                    fname = future_to_name.pop(fut, None)
                    try:
                        fut.result()
                    except Exception as e:
                        self.result_q.put(('err', f'[WM] {fname or "?"}: {e}'))
                    else:
                        if fname:
                            self.result_q.put(('wm', fname))

        # ---- 邊框階段 ----
        if self.bd_var.get() and not self.stop_flag:
            border_color = 'black' if self.black_var.get() else 'white'
            target_size = int(max(512, min(8192, self.out_size.get())))
            with ThreadPoolExecutor(max_workers=CPU_POOL_SIZE) as ex:
                future_to_name = {}
                for t in self.tasks:
                    src_root = t[1] if self.wm_var.get() else t[0]
                    f = ex.submit(
                        add_border_to_image,
                        src_root, t[1], t[2],
                        border_color,
                        target_size
                    )
                    future_to_name[f] = t[2]

                for fut in as_completed(list(future_to_name.keys())):
                    if self.stop_flag:
                        break
                    fname = future_to_name.pop(fut, None)
                    try:
                        fut.result()
                    except Exception as e:
                        self.result_q.put(('err', f'[BD] {fname or "?"}: {e}'))
                    else:
                        if fname:
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
