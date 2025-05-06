import subprocess
import sys
import os
import shutil

APP_NAME = "IG_Photo_Editer"
MAIN_SCRIPT = "main.py"
ICON_FILE = "ig.ico"

def clean_old_build():
    """刪除舊的 build/ dist/ .spec 檔案"""
    for folder in ("build", "dist"):
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"Deleted old folder: {folder}")
    
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)
        print(f"Deleted old file: {spec_file}")

def build_exe():
    """呼叫 PyInstaller 打包"""
    try:
        command = [
            sys.executable, '-m', 'PyInstaller',
            '--onefile',
            '--windowed',
            f'--icon={ICON_FILE}',
            f'--name={APP_NAME}',
            f'--add-data={ICON_FILE};.',   # ★★★ 加這行 ★★★
            MAIN_SCRIPT,
        ]
        subprocess.run(command, check=True)
        print("\n✅ Build completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed: {e}")
        sys.exit(1)

def open_dist_folder():
    """打開 dist 資料夾方便快速拿到 EXE"""
    dist_path = os.path.join(os.getcwd(), "dist")
    if os.path.exists(dist_path):
        if sys.platform.startswith('win'):
            os.startfile(dist_path)
        else:
            subprocess.run(['open', dist_path])

def main():
    # 1. 確認 PyInstaller 是否安裝
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Please install it first by running:")
        print("pip install pyinstaller")
        sys.exit(1)
    
    # 2. 確認 icon 檔案存在
    if not os.path.exists(ICON_FILE):
        print(f"❌ Icon file '{ICON_FILE}' not found!")
        sys.exit(1)

    # 3. 開始流程
    print("🧹 Cleaning old builds...")
    clean_old_build()

    print("\n🔨 Building EXE...")
    build_exe()

    print("\n📂 Opening dist folder...")
    open_dist_folder()

if __name__ == "__main__":
    main()
