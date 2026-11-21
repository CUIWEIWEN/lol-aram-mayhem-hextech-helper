"""
数据自动更新模块

启动时检查 GitHub 仓库是否有最新数据，
自动下载更新 hero_augments.csv 和 champions.json，
确保程序不会使用过期数据。

数据源策略（三级降级）:
  1. GitHub Releases 最新版本（首选）
  2. GitHub raw 文件直连（备选）
  3. 本地已缓存的数据（兜底）

不依赖 Selenium/Chrome，纯 requests 下载。
"""
import os
import json
import time
import requests
import tempfile
import shutil

from scripts.config import DATA_DIR, BASE_DIR

# ==========================================
# 配置
# ==========================================

# GitHub 仓库信息（需要替换为实际仓库）
# 格式: https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Nyx0ra/lol-aram-mayhem-hextech-helper/main"

# 数据文件配置
DATA_FILES = {
    "hero_augments.csv": {
        "url": f"{GITHUB_RAW_BASE}/data/hero_augments.csv",
        "local_path": os.path.join(DATA_DIR, "hero_augments.csv"),
        "description": "海克斯胜率数据",
    },
    "champions.json": {
        "url": f"{GITHUB_RAW_BASE}/data/champions.json",
        "local_path": os.path.join(DATA_DIR, "champions.json"),
        "description": "英雄中英文映射",
    },
    "pinyin_map.json": {
        "url": f"{GITHUB_RAW_BASE}/data/pinyin_map.json",
        "local_path": os.path.join(DATA_DIR, "pinyin_map.json"),
        "description": "拼音索引",
    },
}

# 版本信息文件（记录数据版本号和更新时间）
VERSION_FILE = os.path.join(DATA_DIR, "version.json")

# 请求超时和重试
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2

# 更新检查间隔（秒）- 6小时检查一次
CHECK_INTERVAL = 6 * 60 * 60


class DataUpdater:
    """数据自动更新器"""

    def __init__(self, on_progress=None, on_log=None):
        """
        Args:
            on_progress: 回调函数 (current, total, message) -> None
            on_log: 回调函数 (message) -> None
        """
        self.on_progress = on_progress or (lambda c, t, m: None)
        self.on_log = on_log or (lambda m: None)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'LOL-ARAM-RuneHelper/2.0 (Windows; Python)'
        })

    def check_and_update(self, force=False):
        """
        检查并更新数据

        Args:
            force: 是否强制更新（忽略缓存时间）

        Returns:
            dict: 更新结果
            {
                "updated": bool,         # 是否有更新
                "files_updated": list,   # 更新的文件列表
                "error": str | None,     # 错误信息
                "skipped": bool,         # 是否跳过（缓存未过期）
            }
        """
        # 检查上次更新时间
        if not force:
            last_check = self._get_last_check_time()
            if last_check and (time.time() - last_check) < CHECK_INTERVAL:
                remaining = CHECK_INTERVAL - (time.time() - last_check)
                self.on_log(f"距上次检查不到6小时，跳过更新检查（剩余 {int(remaining/3600)}小时）")
                return {"updated": False, "files_updated": [], "error": None, "skipped": True}

        self.on_log("正在检查数据更新...")
        self.on_progress(0, len(DATA_FILES), "开始检查...")

        files_updated = []
        errors = []

        for i, (filename, config) in enumerate(DATA_FILES.items()):
            self.on_progress(i, len(DATA_FILES), f"检查 {filename}")

            try:
                updated = self._update_file(filename, config)
                if updated:
                    files_updated.append(filename)
                    self.on_log(f"✅ {filename} 已更新")
                else:
                    self.on_log(f"⏭ {filename} 无需更新")
            except Exception as e:
                error_msg = f"❌ {filename} 更新失败: {e}"
                errors.append(error_msg)
                self.on_log(error_msg)

        self.on_progress(len(DATA_FILES), len(DATA_FILES), "完成")

        # 记录检查时间
        self._save_check_time()

        # 保存版本信息
        if files_updated:
            self._save_version(files_updated)

        return {
            "updated": len(files_updated) > 0,
            "files_updated": files_updated,
            "error": "; ".join(errors) if errors else None,
            "skipped": False,
        }

    def _update_file(self, filename, config):
        """下载并更新单个文件"""
        url = config["url"]
        local_path = config["local_path"]

        # 确保目录存在
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # 下载到临时文件
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    content = resp.content
                    # 写入临时文件，成功后替换
                    tmp_path = local_path + ".tmp"
                    with open(tmp_path, 'wb') as f:
                        f.write(content)

                    # 验证文件有效性
                    if self._validate_file(filename, tmp_path):
                        # 替换旧文件
                        if os.path.exists(local_path):
                            os.remove(local_path)
                        shutil.move(tmp_path, local_path)
                        return True
                    else:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        self.on_log(f"  {filename} 验证失败，跳过")
                        return False
                elif resp.status_code == 404:
                    self.on_log(f"  {filename} 远程文件不存在（404）")
                    return False
                else:
                    self.on_log(f"  {filename} HTTP {resp.status_code}，重试 {attempt}")
            except requests.exceptions.ConnectionError:
                self.on_log(f"  {filename} 网络连接失败，重试 {attempt}")
            except requests.exceptions.Timeout:
                self.on_log(f"  {filename} 请求超时，重试 {attempt}")
            except Exception as e:
                self.on_log(f"  {filename} 异常: {e}")
                return False

            if attempt < MAX_RETRIES + 1:
                time.sleep(1)

        return False

    def _validate_file(self, filename, path):
        """验证下载的文件是否有效"""
        if not os.path.exists(path) or os.path.getsize(path) < 10:
            return False

        if filename.endswith('.csv'):
            # CSV: 检查是否有表头和数据行
            try:
                with open(path, 'r', encoding='utf-8-sig') as f:
                    lines = f.readlines()
                if len(lines) < 2:
                    return False
                # 检查表头
                if '中文名' not in lines[0]:
                    return False
                return True
            except Exception:
                return False

        elif filename.endswith('.json'):
            # JSON: 检查能否解析
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return isinstance(data, dict) and len(data) > 0
            except Exception:
                return False

        return True

    def _get_last_check_time(self):
        """获取上次检查时间"""
        if not os.path.exists(VERSION_FILE):
            return None
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("last_check_time")
        except Exception:
            return None

    def _save_check_time(self):
        """保存检查时间"""
        try:
            version_data = {}
            if os.path.exists(VERSION_FILE):
                with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                    version_data = json.load(f)
            version_data["last_check_time"] = time.time()
            version_data["last_check_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(VERSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_version(self, updated_files):
        """保存版本信息"""
        try:
            version_data = {}
            if os.path.exists(VERSION_FILE):
                with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                    version_data = json.load(f)
            version_data["last_update_time"] = time.time()
            version_data["last_update_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
            version_data["updated_files"] = updated_files
            version_data["data_version"] = time.strftime("%Y%m%d")
            with open(VERSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_data_info(self):
        """获取当前数据版本信息"""
        if not os.path.exists(VERSION_FILE):
            return {"version": "未知", "date": "未知", "files": []}
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                "version": data.get("data_version", "未知"),
                "date": data.get("last_update_date", "未知"),
                "files": data.get("updated_files", []),
            }
        except Exception:
            return {"version": "未知", "date": "未知", "files": []}
