"""
PyInstaller 打包脚本 v2.0

将 app.py 打包为独立运行的 exe 程序，
内嵌所有 Python 运行时、依赖库和数据文件。

使用方法:
  python build.py

生成:
  dist/LOLAramRuneHelper/ 目录下的 exe 文件

注意:
  - 需要 Python 3.10~3.12
  - 首次打包约需 3-5 分钟
  - 打包后的 exe 约 60-80MB（已排除不需要的重型依赖）
"""
import os
import sys
import shutil
import subprocess

# ==========================================
# 配置
# ==========================================

APP_NAME = "LOLAramRuneHelper"
APP_ENTRY = "app.py"
ICON_FILE = "assets/icon.ico"

# 需要内嵌的数据文件/目录
DATA_DIRS = ["data"]
DATA_FILES = ["assets/icon.ico"]

# 打包输出目录
DIST_DIR = "dist"
BUILD_DIR = "build"
SPEC_FILE = f"{APP_NAME}.spec"


def check_environment():
    """检查打包环境"""
    print("=" * 50)
    print("  LOL 海克斯大乱斗符文推荐 - 打包脚本")
    print("=" * 50)
    print()

    version = sys.version_info
    print(f"Python 版本: {version.major}.{version.minor}.{version.micro}")

    if version >= (3, 13):
        print("❌ 错误: Python 3.13+ 不兼容")
        print("   请使用 Python 3.10~3.12")
        return False

    if version < (3, 10):
        print("❌ 错误: Python 版本过低，需要 3.10+")
        return False

    print("✅ Python 版本兼容")
    return True


def check_dependencies():
    """检查并安装所需依赖"""
    required = ["requests", "thefuzz", "pypinyin", "Pillow", "pyinstaller"]
    missing = []

    for pkg in required:
        try:
            __import__(pkg.replace("-", "_").lower())
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"正在安装缺失依赖: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + missing
        )

    print("✅ 依赖检查完成")


def clean_old_build():
    """清理旧的构建文件"""
    print("清理旧构建...")
    for path in [DIST_DIR, BUILD_DIR, SPEC_FILE]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    print("✅ 清理完成")


def build():
    """执行打包"""
    print()
    print("开始打包...")
    print()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--onedir",   # onedir 启动更快，比 onefile 启动快 3-5 倍
        "--windowed", # 无控制台窗口
    ]

    # 图标
    if os.path.exists(ICON_FILE):
        cmd.extend(["--icon", ICON_FILE])

    # 内嵌数据目录
    for data_dir in DATA_DIRS:
        if os.path.exists(data_dir):
            cmd.extend(["--add-data", f"{data_dir}{os.pathsep}{data_dir}"])

    # 内嵌数据文件
    for data_file in DATA_FILES:
        if os.path.exists(data_file):
            target_dir = os.path.dirname(data_file)
            if not target_dir:
                target_dir = "."
            cmd.extend(["--add-data", f"{data_file}{os.pathsep}{target_dir}"])

    # 排除不需要的重型依赖（安全版不需要这些，大幅减小体积）
    excludes = [
        "selenium",
        "webdriver_manager",
        "mss",
        "cv2",
        "opencv",
        "rapidocr_onnxruntime",
        "onnxruntime",
        "numpy",
        "keyboard",
        "psutil",
        "pystray",
    ]
    for excl in excludes:
        cmd.extend(["--exclude-module", excl])

    # 入口文件
    cmd.append(APP_ENTRY)

    print("PyInstaller 命令:")
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print()
        print("=" * 50)
        print("✅ 打包成功!")
        print("=" * 50)
        print()
        exe_path = os.path.join(DIST_DIR, APP_NAME, f"{APP_NAME}.exe")
        print(f"输出目录: {os.path.join(DIST_DIR, APP_NAME)}/")
        print(f"EXE 文件: {exe_path}")
        print()
        print("使用方法:")
        print(f"  1. 将 {DIST_DIR}/{APP_NAME}/ 整个目录复制到任意位置")
        print(f"  2. 双击 {APP_NAME}.exe 运行")
        print(f"  3. 无需安装 Python 或任何依赖")
        print()
        print("注意事项:")
        print("  - 首次启动会自动检查 GitHub 数据更新")
        print("  - 更新后的数据保存在 %APPDATA%/LOLAramRuneHelper/data/")
        print("  - 如需连接游戏客户端，请以管理员身份运行")
        print("  - 本程序不修改/注入游戏文件，不会被 WeGame 识别为外挂")
    else:
        print()
        print("❌ 打包失败!")
        print(f"   返回码: {result.returncode}")
        return False

    return True


def main():
    if not check_environment():
        sys.exit(1)

    # 切换到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"工作目录: {os.getcwd()}")
    print()

    check_dependencies()
    clean_old_build()

    if build():
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
