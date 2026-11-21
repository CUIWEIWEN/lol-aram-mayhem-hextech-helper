"""
安全版 LCU Connector - 不使用进程扫描，不使用全局热键，不截屏

防 WeGame/ACE 误报设计:
  1. 只通过读取 lockfile 连接 LCU API（官方提供的本地接口）
  2. 不使用 psutil 遍历进程（避免被标记为"进程扫描"行为）
  3. 不使用 keyboard 库（不 hook 全局键盘）
  4. 不使用 mss/opencv 截屏（不读取游戏画面）
  5. 不连接 2999 Live Client Data API（不读取局内数据）

LCU API 是 Riot 官方提供的本地客户端接口，
用于获取选人阶段的英雄信息，属于合法的客户端交互。
"""
import os
import json
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 英雄联盟安装路径（用于查找 lockfile）
# 只做文件读取，不做进程扫描
COMMON_INSTALL_PATHS = [
    r"C:\Riot Games\League of Legends",
    r"D:\Riot Games\League of Legends",
    r"E:\Riot Games\League of Legends",
    r"F:\Riot Games\League of Legends",
    r"C:\Program Files\Riot Games\League of Legends",
    r"D:\Program Files\Riot Games\League of Legends",
    r"E:\Program Files\Riot Games\League of Legends",
    r"C:\Games\Riot Games\League of Legends",
    r"D:\Games\Riot Games\League of Legends",
    r"C:\Riot Games\英雄联盟",
    r"D:\Riot Games\英雄联盟",
    r"E:\Riot Games\英雄联盟",
    r"D:\WeGameApps\英雄联盟",
    r"D:\WeGame\英雄联盟",
    r"E:\WeGame\英雄联盟",
    r"F:\WeGame\英雄联盟",
    r"D:\腾讯游戏\英雄联盟",
    r"E:\腾讯游戏\英雄联盟",
    r"F:\腾讯游戏\英雄联盟",
    r"D:\Program Files\WeGameApps\英雄联盟",
    r"E:\Program Files\WeGameApps\英雄联盟",
]

# 注册表中可能存储的路径（通过 Windows 注册表查询，比遍历进程安全得多）
def _find_install_path_from_registry():
    """从 Windows 注册表查找英雄联盟安装路径"""
    try:
        import winreg
        # 尝试多个注册表键
        reg_keys = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tencent\WeGame\apps\英雄联盟"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Riot Games\League of Legends"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Riot Games\League of Legends"),
        ]
        for hive, key_path in reg_keys:
            try:
                key = winreg.OpenKey(hive, key_path)
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                if install_path and os.path.isdir(install_path):
                    return install_path
            except (FileNotFoundError, OSError):
                continue
    except Exception:
        pass
    return None


def find_league_install_path():
    """查找英雄联盟安装路径"""
    # 1. 检查注册表
    reg_path = _find_install_path_from_registry()
    if reg_path:
        COMMON_INSTALL_PATHS.insert(0, reg_path)

    # 2. 遍历常见路径
    for path in COMMON_INSTALL_PATHS:
        lockfile = os.path.join(path, 'lockfile')
        if os.path.exists(lockfile):
            return path

    # 3. 在所有盘符根目录搜索（快速搜索，只搜2层）
    for drive in ['C', 'D', 'E', 'F', 'G']:
        for sub in [r'{}\League of Legends', r'{}\英雄联盟', r'{}\Riot Games\League of Legends',
                     r'{}\WeGameApps\英雄联盟', r'{}\腾讯游戏\英雄联盟', r'{}\Games\League of Legends']:
            p = sub.format(drive)
            if os.path.exists(os.path.join(p, 'lockfile')):
                return p

    return None


class SafeLCUConnector:
    """
    安全版 LCU 连接器

    只通过 lockfile 方式连接，不扫描进程，不截屏，不 hook 键盘。
    LCU API 是 Riot 官方提供的本地客户端 REST API，
    用于查询选人阶段的英雄和队伍信息。
    """

    LCU_TIMEOUT = 3.0

    def __init__(self, champions_json_path):
        self.port = None
        self.auth_token = None
        self.base_url = None
        self._connected = False
        self._summoner_id = None
        self.session = requests.Session()

        # 加载英雄映射
        self.champions_json_path = champions_json_path
        self.cn_to_en = {}
        self.en_to_cn = {}
        self.id_to_cn = {}
        self._load_champions_map()

    def _load_champions_map(self, path=None):
        """加载 champions.json 构建中英文映射"""
        path = path or self.champions_json_path
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            self.cn_to_en = mapping
            self.en_to_cn = {en.lower(): cn for cn, en in mapping.items()}
        except Exception:
            pass

    def _resolve_champion_name(self, raw_name):
        """解析英雄名为标准中文名"""
        if not raw_name:
            return None
        cleaned = raw_name.strip()
        if cleaned in self.cn_to_en:
            return cleaned
        if cleaned.startswith("game_character_displayname_"):
            cleaned = cleaned.replace("game_character_displayname_", "").strip()
            if cleaned in self.cn_to_en:
                return cleaned
        lower = cleaned.lower()
        if lower in self.en_to_cn:
            return self.en_to_cn[lower]
        no_space = lower.replace(" ", "").replace("_", "").replace("'", "")
        if no_space in self.en_to_cn:
            return self.en_to_cn[no_space]
        return None

    # ==========================================
    # 连接
    # ==========================================

    def connect(self):
        """通过 lockfile 连接 LCU API（安全方式，不扫描进程）"""
        install_path = find_league_install_path()
        if not install_path:
            return False

        lockfile_path = os.path.join(install_path, 'lockfile')
        if not os.path.exists(lockfile_path):
            return False

        try:
            with open(lockfile_path, 'r') as f:
                content = f.read().strip()
            parts = content.split(':')
            if len(parts) >= 5:
                self.port = parts[2]
                self.auth_token = parts[3]
                self.base_url = f"https://127.0.0.1:{self.port}"
                self._connected = True
                self._build_champion_id_map()
                self._cache_summoner_id()
                return True
        except Exception:
            pass
        return False

    def is_connected(self):
        """检查连接是否有效"""
        if not self._connected:
            return False
        # 快速测试连接
        try:
            resp = self.session.get(
                f"{self.base_url}/lol-summoner/v1/current-summoner",
                auth=('riot', self.auth_token),
                verify=False, timeout=2.0
            )
            return resp.status_code == 200
        except Exception:
            self._connected = False
            return False

    def reconnect(self):
        """重新连接"""
        self._connected = False
        return self.connect()

    def _request(self, method, endpoint, **kwargs):
        """向 LCU API 发送请求"""
        if not self.base_url or not self.auth_token:
            return None
        try:
            resp = self.session.request(
                method, f"{self.base_url}{endpoint}",
                auth=('riot', self.auth_token),
                verify=False, timeout=self.LCU_TIMEOUT, **kwargs
            )
            return resp
        except Exception:
            return None

    def _build_champion_id_map(self):
        """构建英雄 ID -> 中文名映射"""
        resp = self._request('GET', '/lol-game-data/assets/v1/champion-summary.json')
        if not resp or resp.status_code != 200:
            return
        try:
            for champ in resp.json():
                cid = champ.get('id')
                alias = champ.get('alias', '')
                if cid is None or cid == -1:
                    continue
                cn_name = self.en_to_cn.get(alias.lower())
                if cn_name:
                    self.id_to_cn[cid] = cn_name
        except Exception:
            pass

    def _cache_summoner_id(self):
        """缓存当前召唤师 ID"""
        resp = self._request('GET', '/lol-summoner/v1/current-summoner')
        if resp and resp.status_code == 200:
            try:
                self._summoner_id = resp.json().get('summonerId')
            except Exception:
                pass

    # ==========================================
    # 获取游戏阶段和英雄
    # ==========================================

    def get_gameflow_phase(self):
        """获取当前游戏阶段"""
        if not self._connected:
            return None
        resp = self._request('GET', '/lol-gameflow/v1/gameflow-phase')
        if resp and resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                pass
        return None

    def get_current_champion(self):
        """获取当前选中的英雄（选人阶段）"""
        if not self._connected:
            return None

        phase = self.get_gameflow_phase()

        if phase == "ChampSelect":
            return self._get_champselect_champion()

        if phase in ("InProgress", "GameStart"):
            return self._get_gameflow_champion()

        return None

    def _get_champselect_champion(self):
        """从选人阶段获取当前英雄"""
        resp = self._request('GET', '/lol-champ-select/v1/session')
        if not resp or resp.status_code != 200:
            return None
        try:
            data = resp.json()
            local_cell_id = data.get('localPlayerCellId')
            if local_cell_id is None:
                return None
            for player in data.get('myTeam', []):
                if player.get('cellId') == local_cell_id:
                    cid = player.get('championId', 0)
                    if cid and cid > 0:
                        return self.id_to_cn.get(cid)
        except Exception:
            pass
        return None

    def _get_gameflow_champion(self):
        """从 gameflow 获取英雄（加载/游戏中阶段）"""
        resp = self._request('GET', '/lol-gameflow/v1/session')
        if not resp or resp.status_code != 200:
            return None
        try:
            data = resp.json()
            game_data = data.get('gameData', {})
            all_players = game_data.get('teamOne', []) + game_data.get('teamTwo', [])
            for player in all_players:
                if player.get('summonerId') == self._summoner_id:
                    cid = player.get('championId', 0)
                    if cid and cid > 0:
                        return self.id_to_cn.get(cid)
            # 备选
            selections = game_data.get('playerChampionSelections', [])
            for sel in selections:
                if sel.get('summonerId') == self._summoner_id:
                    cid = sel.get('championId', 0)
                    if cid and cid > 0:
                        return self.id_to_cn.get(cid)
        except Exception:
            pass
        return None

    # ==========================================
    # 获取队伍阵容（新增 - 阵容分析所需）
    # ==========================================

    def get_team_champions(self):
        """
        获取己方阵容的英雄列表

        Returns:
            list[str]: 英雄中文名列表
        """
        if not self._connected:
            return []

        # 选人阶段：从 ChampSelect session 获取全队
        team = self._get_champselect_team()
        if team:
            return team

        # 加载/游戏中阶段：从 gameflow 获取
        team = self._get_gameflow_team()
        if team:
            return team

        return []

    def _get_champselect_team(self):
        """从 ChampSelect session 获取己方阵容"""
        resp = self._request('GET', '/lol-champ-select/v1/session')
        if not resp or resp.status_code != 200:
            return []
        try:
            data = resp.json()
            my_team = data.get('myTeam', [])
            team_heroes = []
            for player in my_team:
                cid = player.get('championId', 0)
                if cid and cid > 0:
                    cn_name = self.id_to_cn.get(cid)
                    if cn_name:
                        team_heroes.append(cn_name)
            return team_heroes
        except Exception:
            return []

    def _get_gameflow_team(self):
        """从 gameflow session 获取己方阵容"""
        resp = self._request('GET', '/lol-gameflow/v1/session')
        if not resp or resp.status_code != 200:
            return []
        try:
            data = resp.json()
            game_data = data.get('gameData', {})
            # 查找自己所在的队伍
            team_one = game_data.get('teamOne', [])
            team_two = game_data.get('teamTwo', [])

            my_team = None
            for player in team_one:
                if player.get('summonerId') == self._summoner_id:
                    my_team = team_one
                    break
            if my_team is None:
                for player in team_two:
                    if player.get('summonerId') == self._summoner_id:
                        my_team = team_two
                        break

            if my_team is None:
                my_team = team_one or team_two

            team_heroes = []
            for player in my_team:
                cid = player.get('championId', 0)
                if cid and cid > 0:
                    cn_name = self.id_to_cn.get(cid)
                    if cn_name:
                        team_heroes.append(cn_name)
            return team_heroes
        except Exception:
            return []

    def close(self):
        """关闭连接"""
        try:
            self.session.close()
        except Exception:
            pass
        self._connected = False
