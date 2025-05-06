import os
import sys
import json
import queue
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageOps, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import pillow_heif
from concurrent.futures import ThreadPoolExecutor, as_completed

# 專案自有模組
from image_processing import (
	correct_orientation,
	add_watermark,
	add_white_border_to_image,
)
from threading_executor import process_images_with_threads  # 若未使用可改自行實作

# 啟用 HEIF/HEIC 支援
pillow_heif.register_heif_opener()

# ---- 全域設定 ----
CONFIG_FILENAME = "config.json"
PREVIEW_WIDTH, PREVIEW_HEIGHT = 400, 300           # 右側預覽區大小
FINAL_SIZE = 2048                                   # 輸出正方形邊長
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".heif", ".heic")


class ImageProcessingApp:
	"""主 UI 與批次處理"""

	DEFAULT_WM_RATIO = 0.08575807    # logo / 圖片短邊
	DEFAULT_OFFSET_RATIO = 0.02447917
	VERSION = "v2.3"

	# ------------------------------------------------------------------ #
	# 初始化                                                              #
	# ------------------------------------------------------------------ #
	def __init__(self, master: tk.Tk):
		self.master = master
		master.title(f"Image Processing Tool")

		# 動態狀態 ------------------------------------------------------- #
		self.image_folder: str | None = None
		self.watermark_path: str = ""
		self.stop_flag = False
		self.result_q: queue.Queue[tuple[str, str]] = queue.Queue()

		# Tk 綁定變數
		self.mode_var = tk.StringVar(value="general")
		self.size_var = tk.DoubleVar(value=self.DEFAULT_WM_RATIO)
		self.off_x = tk.DoubleVar(value=1 - self.DEFAULT_OFFSET_RATIO)
		self.off_y = tk.DoubleVar(value=1 - self.DEFAULT_OFFSET_RATIO)
		self.wm_var = tk.BooleanVar(value=True)
		self.bd_var = tk.BooleanVar(value=True)

		# 預覽與樣本快取
		self.samples: dict[str, str | None] = {"landscape": None, "portrait": None}
		self.base_previews: dict[str, Image.Image | None] = {"landscape": None, "portrait": None}
		self.preview_canvases: dict[str, tk.Canvas] = {}

		# 批次任務
		self.tasks: list[tuple[str, str, str]] = []
		self.total_tasks = 0
		self.done_wm = 0
		self.done_bd = 0

		# 讀取設定、建 UI、啟動輪詢
		self._load_config()
		self._build_ui()
		self.master.after(100, self._poll_result_q)

	# ------------------------------------------------------------------ #
	# 設定檔 I/O                                                         #
	# ------------------------------------------------------------------ #
	def _load_config(self):
		"""讀取設定檔，若不存在則建立一份新的"""
		base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
		self.config_path = os.path.join(base_dir, CONFIG_FILENAME)

		if os.path.exists(self.config_path):
			try:
				with open(self.config_path, "r", encoding="utf-8") as f:
					self.config = json.load(f)
			except Exception:
				self.config = {}
		else:
			# 如果沒有就新建一份空的
			self.config = {}
			self._save_config()    # 順便保存一次

		self.watermark_path = self.config.get("watermark_path", "")

	def _save_config(self):
		self.config["watermark_path"] = self.watermark_path
		with open(self.config_path, "w", encoding="utf-8") as f:
			json.dump(self.config, f, ensure_ascii=False, indent=2)

	# ------------------------------------------------------------------ #
	# UI 組裝                                                            #
	# ------------------------------------------------------------------ #
	def _build_ui(self):
		self.master.columnconfigure(0, weight=0)
		self.master.columnconfigure(1, weight=1)

		# 左側控制面板 --------------------------------------------------- #
		ctrl = ttk.Frame(self.master, padding=10)
		ctrl.grid(row=0, column=0, sticky="ns")

		ttk.Label(ctrl, text="Mode:").grid(row=0, column=0, sticky="w")
		ttk.Radiobutton(ctrl, text="General", variable=self.mode_var, value="general").grid(row=0, column=1)
		ttk.Radiobutton(ctrl, text="Advanced", variable=self.mode_var, value="advanced").grid(row=0, column=2)

		ttk.Checkbutton(ctrl, text="Add Watermark", variable=self.wm_var, command=self._refresh_previews)\
			.grid(row=1, column=0, sticky="w")
		ttk.Checkbutton(ctrl, text="Add Border", variable=self.bd_var, command=self._refresh_previews)\
			.grid(row=1, column=1, sticky="w")

		# Logo Size 允許 1% ~ 100%（以短邊為基準）
		ttk.Label(ctrl, text="Logo Size").grid(row=2, column=0, sticky="w")
		ttk.Scale(
			ctrl, from_=0.01, to=1.0,      # ← 這裡改成 1.0
			variable=self.size_var, orient="horizontal",
			command=lambda _e: self._refresh_previews()
		).grid(row=2, column=1, columnspan=2, sticky="ew")

		# Offset X 允許 0% ~ 100%（相對可貼範圍）
		ttk.Label(ctrl, text="Offset X").grid(row=3, column=0, sticky="w")
		ttk.Scale(
			ctrl, from_=0.0, to=1.0,       # ← 這裡改成 1.0
			variable=self.off_x, orient="horizontal",
			command=lambda _e: self._refresh_previews()
		).grid(row=3, column=1, columnspan=2, sticky="ew")

		# Offset Y 同理
		ttk.Label(ctrl, text="Offset Y").grid(row=4, column=0, sticky="w")
		ttk.Scale(
			ctrl, from_=0.0, to=1.0,       # ← 這裡改成 1.0
			variable=self.off_y, orient="horizontal",
			command=lambda _e: self._refresh_previews()
		).grid(row=4, column=1, columnspan=2, sticky="ew")

		ttk.Button(ctrl, text="Reset Logo", command=self._reset_logo)\
			.grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)

		ttk.Button(ctrl, text="Select Folder", command=self._select_folder).grid(row=6, column=0, sticky="ew")
		self.folder_label = ttk.Label(ctrl, text="No folder selected", wraplength=150)
		self.folder_label.grid(row=6, column=1, columnspan=2)
		ttk.Button(ctrl, text="Select Watermark", command=self._select_watermark).grid(row=7, column=0, sticky="ew")
		self.wm_path_label = ttk.Label(ctrl, text=os.path.basename(self.watermark_path) or "No watermark", wraplength=150)
		self.wm_path_label.grid(row=7, column=1, columnspan=2)

		self.start_btn = ttk.Button(ctrl, text="Start", command=self._on_start)
		self.start_btn.grid(row=8, column=0, sticky="ew")
		self.stop_btn = ttk.Button(ctrl, text="Stop", command=self._on_stop, state=tk.DISABLED)
		self.stop_btn.grid(row=8, column=1, sticky="ew")

		self.wm_label = ttk.Label(ctrl, text="WM: 0/0")
		self.wm_label.grid(row=9, column=0)
		self.wm_prog = ttk.Progressbar(ctrl, orient="horizontal", length=120, mode="determinate")
		self.wm_prog.grid(row=9, column=1, columnspan=2)
		self.bd_label = ttk.Label(ctrl, text="BD: 0/0")
		self.bd_label.grid(row=10, column=0)
		self.bd_prog = ttk.Progressbar(ctrl, orient="horizontal", length=120, mode="determinate")
		self.bd_prog.grid(row=10, column=1, columnspan=2)

		ttk.Label(ctrl, text="Logs:").grid(row=11, column=1, sticky="w")
		self.log_txt = tk.Text(ctrl, height=30, width=40, font=("TkDefaultFont", 9))
		self.log_txt.grid(row=12, column=0, columnspan=3)

		ttk.Label(ctrl, text=f"Version: {self.VERSION}").grid(row=13, column=0, columnspan=3, pady=3)

		# 右側預覽 ------------------------------------------------------- #
		pv = ttk.Frame(self.master, padding=10)
		pv.grid(row=0, column=1, sticky="nsew")
		pv.columnconfigure(0, weight=1)
		ttk.Label(pv, text="橫幅預覽").grid(row=0, column=0)
		self.preview_canvases["landscape"] = tk.Canvas(pv, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, bg="#ddd")
		self.preview_canvases["landscape"].grid(row=1, column=0, pady=4)
		ttk.Label(pv, text="直幅預覽").grid(row=2, column=0)
		self.preview_canvases["portrait"] = tk.Canvas(pv, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, bg="#ddd")
		self.preview_canvases["portrait"].grid(row=3, column=0, pady=4)

	# ------------------------------------------------------------------ #
	# 小工具                                                             #
	# ------------------------------------------------------------------ #
	def _log(self, msg: str):
		self.log_txt.insert(tk.END, msg + "\n")
		self.log_txt.see(tk.END)

	def _reset_logo(self):
		"""將 Logo 相關滑桿歸回預設（右下角、原始比例）"""
		self.size_var.set(self.DEFAULT_WM_RATIO)
		# 右／下邊各保留 DEFAULT_OFFSET_RATIO 的邊距
		self.off_x.set(1 - self.DEFAULT_OFFSET_RATIO)
		self.off_y.set(1 - self.DEFAULT_OFFSET_RATIO)
		self._refresh_previews()


	# ------------------------------------------------------------------ #
	# 資料夾 / 檔案 選擇                                                 #
	# ------------------------------------------------------------------ #
	def _select_folder(self):
		folder = filedialog.askdirectory()
		if not folder:
			return
		self.image_folder = folder
		self.folder_label.config(text=os.path.basename(folder))
		self._load_samples()
		self._load_base_previews()
		self._refresh_previews()

	def _select_watermark(self):
		path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.heif;*.heic")])
		if not path:
			return
		self.watermark_path = path
		self.wm_path_label.config(text=os.path.basename(path))
		self._save_config()
		self._refresh_previews()

	# ------------------------------------------------------------------ #
	# 樣本載入與快取                                                     #
	# ------------------------------------------------------------------ #
	def _load_samples(self):
		"""從資料夾挑兩張(橫/直)作預覽樣本"""
		self.samples = {"landscape": None, "portrait": None}
		if not self.image_folder:
			return
		for root, _, files in os.walk(self.image_folder):
			if "IG_LOGO_Cropper" in root:
				continue
			for f in files:
				if not f.lower().endswith(IMAGE_EXTS):
					continue
				p = os.path.join(root, f)
				try:
					with Image.open(p) as img_raw:
						img = correct_orientation(img_raw)   # ⇐ 加入這行
						w, h = img.size    
					key = "landscape" if w >= h else "portrait"
					if not self.samples[key]:
						self.samples[key] = p
					if all(self.samples.values()):
						return
				except Exception:
					continue

	def _load_base_previews(self):
		"""把樣本圖縮好快取，滑桿變動即時 overlay"""
		for orient, path in self.samples.items():
			if path is None:
				self.base_previews[orient] = None
				continue
			img = correct_orientation(Image.open(path))
			w, h = img.size
			r = min(PREVIEW_WIDTH / w, PREVIEW_HEIGHT / h)
			new = img.resize((int(w * r), int(h * r)), Image.LANCZOS).convert("RGBA")
			self.base_previews[orient] = new

	# ------------------------------------------------------------------
	# 即時預覽刷新
	# ------------------------------------------------------------------
	def _refresh_previews(self):
		"""
		即時預覽：掃描第一張直幅與橫幅，並顯示（含白邊／浮水印選項）
		"""
		# 1. 清空所有 canvas
		for cv in self.preview_canvases.values():
			cv.delete("all")

		# 2. 快速找直幅與橫幅範例
		portrait_img = None
		landscape_img = None
		for fname in sorted(os.listdir(self.image_folder)):
			if not fname.lower().endswith(IMAGE_EXTS):
				continue
			fpath = os.path.join(self.image_folder, fname)
			try:
				with Image.open(fpath) as im_raw:
					im = correct_orientation(im_raw)  # ⇐ 加入這行
					w, h = im.size                   # ← 判斷正確方向
					if h > w and portrait_img is None:
						portrait_img = im.copy()
					elif w >= h and landscape_img is None:
						landscape_img = im.copy()
			except:
				continue
			if portrait_img and landscape_img:
				break

		# 3. 暫存到 base_previews
		self.base_previews["portrait"]  = portrait_img
		self.base_previews["landscape"] = landscape_img

		# 4. 產生並顯示縮圖（**一定要在這裡**）
		for orient, canvas in self.preview_canvases.items():
			base = self.base_previews.get(orient)
			if base is None:
				continue

			inner = base.copy()
			iw, ih = inner.size

			# 模擬白邊
			if self.bd_var.get():
				square = max(iw, ih)
				bg = Image.new("RGBA", (square, square), "white")
				ox = (square - iw)//2
				oy = (square - ih)//2
				bg.paste(inner, (ox, oy))
				work = bg
			else:
				work = inner

			# 疊浮水印
			if self.wm_var.get() and self.watermark_path:
				wm = Image.open(self.watermark_path).convert("RGBA")
				short = min(iw, ih)
				wm_w = int(self.size_var.get() * short)
				wm = wm.resize((wm_w, wm_w), Image.LANCZOS)
				offset = int(self.DEFAULT_OFFSET_RATIO * short)
				dx = ox + iw - wm_w - offset
				dy = oy + ih - wm_w - offset
				work.paste(wm, (dx, dy), wm)

			# 縮放到 canvas 再貼上
			ratio = min(PREVIEW_WIDTH/work.width, PREVIEW_HEIGHT/work.height, 1.0)
			if ratio < 1.0:
				work = work.resize((int(work.width*ratio),
									int(work.height*ratio)),
								   Image.LANCZOS)

			tkimg = ImageTk.PhotoImage(work)
			canvas.create_image(
				(PREVIEW_WIDTH - work.width)//2,
				(PREVIEW_HEIGHT - work.height)//2,
				anchor="nw", image=tkimg
			)
			canvas.image_ref = tkimg  # 防被 GC

	# ------------------------------------------------------------------ #
	# 批次處理                                                           #
	# ------------------------------------------------------------------ #
	def _on_start(self):
		if not self.image_folder:
			messagebox.showerror("Error", "Select folder first")
			return
		if self.wm_var.get() and not self.watermark_path:
			messagebox.showerror("Error", "Select watermark first")
			return

		# ---------- 1. 先清空舊輸出資料夾 ----------
		cropper_root = os.path.join(self.image_folder, "IG_LOGO_Cropper")
		if os.path.isdir(cropper_root):
			shutil.rmtree(cropper_root)

		# ---------- 2. 依「模式」收集處理清單 ----------
		self.tasks.clear()

		if self.mode_var.get() == "general":
			# 只處理最外層檔案，不深入子資料夾
			out_root = cropper_root                 # 輸出統一在 IG_LOGO_Cropper
			os.makedirs(out_root, exist_ok=True)

			for f in os.listdir(self.image_folder):
				if f.lower().endswith(IMAGE_EXTS):
					self.tasks.append((self.image_folder, out_root, f))

		else:   # advanced mode ─ 含所有子資料夾
			for root, _dirs, files in os.walk(self.image_folder):
				out_root = os.path.join(
					self.image_folder, "IG_LOGO_Cropper",
					os.path.relpath(root, self.image_folder)
				)
				os.makedirs(out_root, exist_ok=True)

				for f in files:
					if f.lower().endswith(IMAGE_EXTS):
						self.tasks.append((root, out_root, f))
		self.total_tasks = len(self.tasks)
		if not self.total_tasks:
			messagebox.showinfo("Info", "No images found")
			return

		# 進度條初始化
		self.done_wm = self.done_bd = 0
		self.wm_prog.configure(maximum=self.total_tasks, value=0)
		self.bd_prog.configure(maximum=self.total_tasks, value=0)
		self.wm_label.configure(text=f"WM: 0/{self.total_tasks}")
		self.bd_label.configure(text=f"BD: 0/{self.total_tasks}")

		self.stop_flag = False
		self.start_btn.config(state=tk.DISABLED)
		self.stop_btn.config(state=tk.NORMAL)
		threading.Thread(target=self._process_worker, daemon=True).start()

	# ------------------------------------------------------------------
	# 背景批次處理：限制執行緒 ≒ 80 % CPU
	# ------------------------------------------------------------------
	def _process_worker(self):
		"""實際進行批次處理（背景執行緒）"""

		# 計算「最多使用的執行緒數」= CPU 核心數 × 0.8
		max_threads = max(1, int((os.cpu_count() or 1) * 0.8))

		# ── 1. 浮水印 ────────────────────────────────────────────────
		if self.wm_var.get():
			with ThreadPoolExecutor(max_workers=max_threads) as ex:
				futures = [ex.submit(self._apply_watermark, t) for t in self.tasks]
				for fut in as_completed(futures):
					if self.stop_flag:
						break
					fname = fut.result()
					if fname:                           # 失敗時 _apply_watermark 會回傳 None
						self.result_q.put(("wm", fname))

		# ── 2. 白邊 ─────────────────────────────────────────────────
		if self.bd_var.get() and not self.stop_flag:
			with ThreadPoolExecutor(max_workers=max_threads) as ex:
				futures = [ex.submit(self._apply_border, t) for t in self.tasks]
				for fut in as_completed(futures):
					if self.stop_flag:
						break
					fname = fut.result()
					self.result_q.put(("bd", fname))

		# ── 3. 全部完成 ────────────────────────────────────────────
		self.result_q.put(("done", ""))

	# ------------------------------------------------------------------
	# 載入 → 加浮水印 → 存檔
	# ------------------------------------------------------------------
	def _apply_watermark(self, task: tuple[str, str, str]) -> str | None:
		# 一次正確拆解三個參數
		root, out_root, fname = task

		# 設定完整來源／輸出路徑
		src = os.path.join(root, fname)
		dst = os.path.join(out_root, fname)

		# 讀檔並修正方向
		try:
			img = correct_orientation(Image.open(src)).convert("RGBA")
		except Exception as e:
			self.result_q.put(("err", f"[Skip] {fname} ‒ {e}"))
			return None

		# 浮水印尺寸（短邊比例）
		short_side = min(img.width, img.height)
		wm_w       = int(self.size_var.get() * short_side)
		wm         = Image.open(self.watermark_path).convert("RGBA")
		wm         = wm.resize((wm_w, wm_w), Image.LANCZOS)

		# 固定 X/Y Offset = 0.02447917 × short_side
		offset_px  = int(0.02447917 * short_side)
		dest_x     = max(img.width  - wm_w - offset_px, 0)
		dest_y     = max(img.height - wm_w - offset_px, 0)

		# 貼浮水印並存檔
		img.paste(wm, (dest_x, dest_y), wm)
		img.convert("RGB").save(dst, quality=95)
		return fname
	
	def _apply_border(self, task: tuple[str, str, str]) -> str:
		"""
		給目前檔案加白邊（正方形 2048×2048）  
		回傳檔名供 UI 更新進度／日誌
		"""
		# 正確拆解三個元素
		root, out_root, fname = task

		# 直接以「來源資料夾」、「目的資料夾」、「檔名」呼叫
		add_white_border_to_image(root, out_root, fname)
		return fname

	# ------------------------------------------------------------------ #
	# 主執行緒輪詢 queue，更新 UI                                        #
	# ------------------------------------------------------------------ #
	def _poll_result_q(self):
		try:
			while True:
				stage, fname = self.result_q.get_nowait()
				if stage == "wm":
					self.done_wm += 1
					self.wm_prog["value"] = self.done_wm
					self.wm_label.configure(text=f"WM: {self.done_wm}/{self.total_tasks}")
					self._log(f"Watermark added: {fname}")
				elif stage == "bd":
					self.done_bd += 1
					self.bd_prog["value"] = self.done_bd
					self.bd_label.configure(text=f"BD: {self.done_bd}/{self.total_tasks}")
					self._log(f"Border added: {fname}")
				elif stage == "err":
					self._log(fname)		# fname 這裡其實是錯誤訊息字串
				elif stage == "done":
					self._finish()
		except queue.Empty:
			pass
		finally:
			self.master.after(100, self._poll_result_q)

	def _on_stop(self):
		self.stop_flag = True
		self._log("Stop requested")

	def _finish(self):
		self.start_btn.config(state=tk.NORMAL)
		self.stop_btn.config(state=tk.DISABLED)
		self._log("Processing complete")
		messagebox.showinfo("Done", "Processing complete")

# ---------------------------------------------------------------------- #
# 入口                                                                   #
# ---------------------------------------------------------------------- #
def resource_path(relative_path):
	"""打包後取得資源的正確路徑"""
	if hasattr(sys, '_MEIPASS'):
		return os.path.join(sys._MEIPASS, relative_path)
	return os.path.join(os.path.abspath("."), relative_path)

def start_ui():
	root = tk.Tk()
	# 這裡改用 resource_path 找 icon
	icon_path = resource_path('ig.ico')
	root.iconbitmap(icon_path)

	app = ImageProcessingApp(root)
	root.mainloop()
