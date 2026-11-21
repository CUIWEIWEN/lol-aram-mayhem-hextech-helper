"""
LOL 海克斯极地大乱斗 - 符文推荐助手 v2.0

安全设计（不被 WeGame 识别为外挂）:
  - 不使用全局热键（无 keyboard hook）
  - 不截屏 OCR（不读取游戏画面）
  - 不扫描进程（不遍历 system processes）
  - 不连接 2999 端口（不读取局内数据）
  - 只通过 lockfile 连接官方 LCU API（查询选人阶段英雄）
  - 纯数据查询工具，不修改/注入任何游戏文件

数据自动更新:
  - 启动时检查 GitHub 仓库最新数据
  - 自动下载更新，6小时检查一次
  - 本地缓存兜底，离线可用

打包:
  - PyInstaller 一键打包为独立 exe
  - 数据文件内嵌，无需外部依赖
"""
import os
import sys
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from collections import defaultdict
from thefuzz import process, fuzz
from pypinyin import lazy_pinyin
from datetime import datetime

# ==========================================
# 路径初始化（兼容 PyInstaller 打包）
# ==========================================

def get_app_dir():
    """获取应用根目录（兼容 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，数据在 _MEIPASS 或 exe 同级目录
        base = os.path.dirname(sys.executable)
        if os.path.exists(os.path.join(base, 'data')):
            return base
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()
DATA_DIR = os.path.join(APP_DIR, 'data')

# 用户数据目录（打包后可写的目录）
def get_user_data_dir():
    """获取用户可写的数据目录（打包后在 AppData 下）"""
    if getattr(sys, 'frozen', False):
        app_name = "LOLAramRuneHelper"
        appdata = os.environ.get('APPDATA') or os.environ.get('HOME') or os.path.expanduser('~')
        user_dir = os.path.join(appdata, app_name)
        os.makedirs(user_dir, exist_ok=True)
        os.makedirs(os.path.join(user_dir, 'data'), exist_ok=True)
        return user_dir
    return APP_DIR

USER_DIR = get_user_data_dir()
USER_DATA_DIR = os.path.join(USER_DIR, 'data')

# 导入模块
sys.path.insert(0, APP_DIR)

from scripts.rune_recommender import RuneRecommender
from scripts.team_analyzer import TeamAnalyzer, get_hero_profile
from scripts.safe_lcu_connector import SafeLCUConnector
from scripts.data_updater import DataUpdater
from scripts.ai_advisor import AIConfig, AIAdvisor, PROVIDER_PRESETS

# AI 配置文件路径
AI_CONFIG_PATH = os.path.join(USER_DIR, 'settings.json')


# ==========================================
# 配色 - 浅色主题
# ==========================================
class Theme:
    BG          = "#f5f6fa"
    BG_CARD     = "#ffffff"
    BG_INPUT    = "#ffffff"
    ACCENT      = "#4361ee"
    ACCENT_HVR  = "#3a56d4"
    SUCCESS     = "#2ecc71"
    WARNING     = "#f39c12"
    ERROR       = "#e74c3c"
    TEXT        = "#2c3e50"
    TEXT_DIM    = "#95a5a6"
    BORDER      = "#ecf0f1"
    PRISMATIC   = "#9b59b6"
    GOLD        = "#f1c40f"
    SILVER      = "#bdc3c7"


class App:
    """主应用"""

    FONT_TITLE  = ("Microsoft YaHei", 16, "bold")
    FONT_SUB    = ("Microsoft YaHei", 10)
    FONT_HERO   = ("Microsoft YaHei", 18, "bold")
    FONT_CARD   = ("Microsoft YaHei", 11, "bold")
    FONT_DETAIL = ("Microsoft YaHei", 9)
    FONT_TAG    = ("Microsoft YaHei", 8)

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("LOL 海克斯大乱斗符文推荐 v2.0")
        self.root.geometry("760x860")
        self.root.minsize(700, 720)
        self.root.configure(bg=Theme.BG)

        # 设置图标
        icon_path = os.path.join(APP_DIR, 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # ttk 样式
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except Exception:
            pass
        self._configure_styles()

        # 状态
        self.recommender = None
        self.lcu = None
        self.team_analyzer = TeamAnalyzer()
        self.current_hero = None
        self.auto_mode = False
        self._running = True
        self._lcu_thread = None
        self.updater = DataUpdater(
            on_progress=self._on_update_progress,
            on_log=self._on_update_log
        )

        # AI 配置
        self.ai_config = AIConfig(AI_CONFIG_PATH)
        self.ai_advisor = AIAdvisor(self.ai_config)

        # 构建 UI
        self._build_ui()

        # 启动数据加载（先更新后加载）
        self.root.after(100, self._init_data)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self):
        s = self.style
        s.configure('Accent.TButton',
                     background=Theme.ACCENT, foreground='white',
                     font=("Microsoft YaHei", 11, "bold"), padding=(16, 10), borderwidth=0)
        s.map('Accent.TButton', background=[('active', Theme.ACCENT_HVR)])
        s.configure('Secondary.TButton',
                     background=Theme.BG_CARD, foreground=Theme.TEXT,
                     font=("Microsoft YaHei", 10), padding=(12, 8), borderwidth=1)
        s.map('Secondary.TButton', background=[('active', '#e8eaf6')])
        s.configure('TNotebook', background=Theme.BG, borderwidth=0)
        s.configure('TNotebook.Tab',
                     background=Theme.BG_CARD, foreground=Theme.TEXT_DIM,
                     padding=(16, 8), font=("Microsoft YaHei", 10))
        s.map('TNotebook.Tab',
              background=[('selected', Theme.ACCENT)],
              foreground=[('selected', 'white')])
        s.configure('TCombobox', fieldbackground=Theme.BG_INPUT, background=Theme.BG_CARD)

    # ==========================================
    # UI 构建
    # ==========================================

    def _build_ui(self):
        main = tk.Frame(self.root, bg=Theme.BG, padx=20, pady=16)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- Header ----
        hdr = tk.Frame(main, bg=Theme.BG)
        hdr.pack(fill=tk.X, pady=(0, 12))

        tk.Label(hdr, text="⚡", font=("Segoe UI", 24), fg=Theme.ACCENT,
                 bg=Theme.BG).pack(side=tk.LEFT, padx=(0, 10))

        title_frame = tk.Frame(hdr, bg=Theme.BG)
        title_frame.pack(side=tk.LEFT)
        tk.Label(title_frame, text="海克斯大乱斗符文推荐",
                 font=self.FONT_TITLE, fg=Theme.TEXT, bg=Theme.BG).pack(anchor="w")
        tk.Label(title_frame, text="根据英雄 + 阵容智能推荐最佳海克斯",
                 font=self.FONT_SUB, fg=Theme.TEXT_DIM, bg=Theme.BG).pack(anchor="w")

        # 数据版本信息
        info_frame = tk.Frame(hdr, bg=Theme.BG)
        info_frame.pack(side=tk.RIGHT)
        self.data_info_label = tk.Label(info_frame, text="", font=self.FONT_DETAIL,
                                        fg=Theme.TEXT_DIM, bg=Theme.BG, anchor="e")
        self.data_info_label.pack()

        # ---- 英雄选择区 ----
        hero_frame = tk.Frame(main, bg=Theme.BG_CARD, padx=16, pady=12,
                              highlightbackground=Theme.BORDER, highlightthickness=1)
        hero_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(hero_frame, text="选择英雄", font=("Microsoft YaHei", 10, "bold"),
                 fg=Theme.TEXT_DIM, bg=Theme.BG_CARD).pack(anchor="w", pady=(0, 4))

        input_row = tk.Frame(hero_frame, bg=Theme.BG_CARD)
        input_row.pack(fill=tk.X)

        self.hero_var = tk.StringVar()
        self.hero_combo = ttk.Combobox(input_row, textvariable=self.hero_var,
                                       font=("Microsoft YaHei", 12), state='normal')
        self.hero_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.hero_combo.bind('<KeyRelease>', self._on_hero_search)
        self.hero_combo.bind('<<ComboboxSelected>>', self._on_hero_select)
        self.hero_combo.bind('<Return>', lambda e: self._do_recommend())

        ttk.Button(input_row, text="🔍 推荐", style='Accent.TButton',
                   command=self._do_recommend).pack(side=tk.RIGHT)

        auto_row = tk.Frame(hero_frame, bg=Theme.BG_CARD)
        auto_row.pack(fill=tk.X, pady=(8, 0))

        self.auto_btn = ttk.Button(auto_row, text="🎮 自动识别 (连接游戏客户端)",
                                   style='Secondary.TButton', command=self._toggle_auto_mode)
        self.auto_btn.pack(side=tk.LEFT)

        self.refresh_btn = ttk.Button(auto_row, text="🔄 检查更新",
                                      style='Secondary.TButton', command=self._manual_update)
        self.refresh_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.ai_btn = ttk.Button(auto_row, text="🤖 AI设置",
                                 style='Secondary.TButton', command=self._open_ai_settings)
        self.ai_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.status_label = tk.Label(auto_row, text="", font=self.FONT_DETAIL,
                                     fg=Theme.TEXT_DIM, bg=Theme.BG_CARD)
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))

        # ---- 阵容分析区 ----
        team_frame = tk.Frame(main, bg=Theme.BG_CARD, padx=16, pady=10,
                              highlightbackground=Theme.BORDER, highlightthickness=1)
        team_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(team_frame, text="阵容分析", font=("Microsoft YaHei", 10, "bold"),
                 fg=Theme.TEXT_DIM, bg=Theme.BG_CARD).pack(anchor="w")

        self.team_label = tk.Label(team_frame, text="未获取阵容 (手动选择英雄或开启自动识别)",
                                   font=self.FONT_DETAIL, fg=Theme.TEXT_DIM, bg=Theme.BG_CARD,
                                   wraplength=680, justify=tk.LEFT)
        self.team_label.pack(anchor="w", pady=(4, 0))

        # ---- 推荐结果区 ----
        result_frame = tk.Frame(main, bg=Theme.BG)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.notebook = ttk.Notebook(result_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: 综合推荐
        tab1 = tk.Frame(self.notebook, bg=Theme.BG)
        self.notebook.add(tab1, text="综合推荐")

        self.scroll_frame = tk.Frame(tab1, bg=Theme.BG)
        self.scroll_frame.pack(fill=tk.BOTH, expand=True)

        canvas1 = tk.Canvas(self.scroll_frame, bg=Theme.BG, highlightthickness=0)
        scrollbar1 = ttk.Scrollbar(self.scroll_frame, orient="vertical", command=canvas1.yview)
        self.recommend_canvas = canvas1
        self.recommend_inner = tk.Frame(canvas1, bg=Theme.BG)
        self.recommend_inner.bind(
            "<Configure>",
            lambda e: canvas1.configure(scrollregion=canvas1.bbox("all"))
        )
        canvas1.create_window((0, 0), window=self.recommend_inner, anchor="nw")
        canvas1.configure(yscrollcommand=scrollbar1.set)
        canvas1.pack(side="left", fill="both", expand=True)
        scrollbar1.pack(side="right", fill="y")

        # 鼠标滚轮
        def _on_mousewheel(event):
            canvas1.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas1.bind_all("<MouseWheel>", _on_mousewheel)
        canvas1.bind_all("<Button-4>", lambda e: canvas1.yview_scroll(-1, "units"))
        canvas1.bind_all("<Button-5>", lambda e: canvas1.yview_scroll(1, "units"))

        # Tab 2: 按等级分组
        tab2 = tk.Frame(self.notebook, bg=Theme.BG)
        self.notebook.add(tab2, text="按等级分组")

        self.tier_scroll = tk.Frame(tab2, bg=Theme.BG)
        self.tier_scroll.pack(fill=tk.BOTH, expand=True)

        canvas2 = tk.Canvas(self.tier_scroll, bg=Theme.BG, highlightthickness=0)
        scrollbar2 = ttk.Scrollbar(self.tier_scroll, orient="vertical", command=canvas2.yview)
        self.tier_canvas = canvas2
        self.tier_inner = tk.Frame(canvas2, bg=Theme.BG)
        self.tier_inner.bind(
            "<Configure>",
            lambda e: canvas2.configure(scrollregion=canvas2.bbox("all"))
        )
        canvas2.create_window((0, 0), window=self.tier_inner, anchor="nw")
        canvas2.configure(yscrollcommand=scrollbar2.set)
        canvas2.pack(side="left", fill="both", expand=True)
        scrollbar2.pack(side="right", fill="y")

        # Tab 3: AI 智能建议
        tab3 = tk.Frame(self.notebook, bg=Theme.BG)
        self.notebook.add(tab3, text="🤖 AI建议")

        ai_container = tk.Frame(tab3, bg=Theme.BG, padx=8, pady=8)
        ai_container.pack(fill=tk.BOTH, expand=True)

        # AI 状态提示
        ai_status_row = tk.Frame(ai_container, bg=Theme.BG)
        ai_status_row.pack(fill=tk.X, pady=(0, 8))
        self.ai_status_label = tk.Label(ai_status_row, text="", font=self.FONT_DETAIL,
                                        fg=Theme.TEXT_DIM, bg=Theme.BG)
        self.ai_status_label.pack(side=tk.LEFT)

        self.ai_ask_btn = ttk.Button(ai_status_row, text="询问AI建议",
                                     style='Accent.TButton', command=self._ask_ai)
        self.ai_ask_btn.pack(side=tk.RIGHT)

        # AI 回答展示区
        ai_canvas = tk.Canvas(ai_container, bg=Theme.BG, highlightthickness=0)
        ai_scrollbar = ttk.Scrollbar(ai_container, orient="vertical", command=ai_canvas.yview)
        self.ai_canvas = ai_canvas
        self.ai_inner = tk.Frame(ai_canvas, bg=Theme.BG)

        self.ai_inner.bind(
            "<Configure>",
            lambda e: ai_canvas.configure(scrollregion=ai_canvas.bbox("all"))
        )
        ai_canvas.create_window((0, 0), window=self.ai_inner, anchor="nw")
        ai_canvas.configure(yscrollcommand=ai_scrollbar.set)
        ai_canvas.pack(side="left", fill="both", expand=True)
        ai_scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮
        ai_canvas.bind_all("<MouseWheel>",
                           lambda e: ai_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._update_ai_status()
        self._show_ai_placeholder()

        self._show_placeholder("正在初始化，请稍候...")

    # ==========================================
    # 数据初始化和更新
    # ==========================================

    def _init_data(self):
        """初始化数据：先检查更新，再加载"""
        self.status_label.config(text="正在检查数据更新...", fg=Theme.WARNING)

        def _task():
            # 1. 检查更新（非阻塞，失败也不影响启动）
            try:
                result = self.updater.check_and_update(force=False)
                update_msg = ""
                if result.get("updated"):
                    update_msg = f"数据已更新 ({', '.join(result['files_updated'])})"
                elif result.get("skipped"):
                    update_msg = "数据已是最新"
                elif result.get("error"):
                    update_msg = "更新检查失败，使用本地数据"
                else:
                    update_msg = "数据已是最新"
            except Exception:
                update_msg = "更新检查失败，使用本地数据"

            # 2. 加载推荐引擎（使用用户数据目录的文件，没有则用内置的）
            self.root.after(0, lambda: self._load_recommender(update_msg))

        threading.Thread(target=_task, daemon=True).start()

    def _load_recommender(self, update_msg):
        """加载推荐引擎"""
        try:
            # 优先使用用户数据目录（更新后的数据）
            csv_path = os.path.join(USER_DATA_DIR, 'hero_augments.csv')
            champ_path = os.path.join(USER_DATA_DIR, 'champions.json')

            # 如果用户目录没有，回退到应用目录（内置数据）
            if not os.path.exists(csv_path):
                csv_path = os.path.join(DATA_DIR, 'hero_augments.csv')
            if not os.path.exists(champ_path):
                champ_path = os.path.join(DATA_DIR, 'champions.json')

            self.recommender = RuneRecommender(
                csv_path=csv_path,
                champions_json_path=champ_path
            )

            if self.recommender.hero_data:
                heroes = self.recommender.get_hero_list()
                self.hero_combo['values'] = heroes

                # 更新数据版本信息
                info = self.updater.get_data_info()
                version_text = f"数据版本: {info['version']}\n更新时间: {info['date']}\n英雄数: {len(heroes)}"
                self.data_info_label.config(text=version_text)

                self.status_label.config(
                    text=f"{update_msg} | 已加载 {len(heroes)} 个英雄",
                    fg=Theme.SUCCESS
                )
                self._show_placeholder("请在上方选择英雄，然后点击「推荐」按钮\n\n或点击「自动识别」连接游戏客户端")
            else:
                self.status_label.config(text="数据加载失败", fg=Theme.ERROR)
                messagebox.showerror("数据加载错误",
                    "海克斯数据加载失败。\n请检查网络连接后点击「检查更新」。")
        except Exception as e:
            self.status_label.config(text=f"加载失败: {e}", fg=Theme.ERROR)
            messagebox.showerror("加载错误", str(e))

    def _manual_update(self):
        """手动触发数据更新"""
        self.status_label.config(text="正在更新数据...", fg=Theme.WARNING)
        self.refresh_btn.config(state='disabled')

        def _task():
            try:
                result = self.updater.check_and_update(force=True)
                if result.get("updated"):
                    # 重新加载
                    self.root.after(0, lambda: self._load_recommender(
                        f"已更新: {', '.join(result['files_updated'])}"))
                elif result.get("error"):
                    self.root.after(0, lambda: self.status_label.config(
                        text=f"更新失败: {result['error']}", fg=Theme.ERROR))
                else:
                    self.root.after(0, lambda: self.status_label.config(
                        text="数据已是最新版本", fg=Theme.SUCCESS))
            except Exception as e:
                self.root.after(0, lambda: self.status_label.config(
                    text=f"更新异常: {e}", fg=Theme.ERROR))
            finally:
                self.root.after(0, lambda: self.refresh_btn.config(state='normal'))

        threading.Thread(target=_task, daemon=True).start()

    def _on_update_progress(self, current, total, message):
        pass  # 可扩展为进度条

    def _on_update_log(self, message):
        print(f"[DataUpdater] {message}")

    # ==========================================
    # 英雄搜索
    # ==========================================

    def _on_hero_search(self, event):
        if not self.recommender:
            return
        query = self.hero_var.get().strip().lower()
        if not query:
            return

        heroes = self.recommender.get_hero_list()
        matches = [h for h in heroes if query in h.lower() or query in ''.join(lazy_pinyin(h)).lower()]
        if not matches:
            results = process.extract(query, heroes, scorer=fuzz.partial_ratio, limit=10)
            matches = [r[0] for r in results if r[1] > 50]
        self.hero_combo['values'] = matches[:20]

    def _on_hero_select(self, event):
        self._do_recommend()

    # ==========================================
    # 推荐逻辑
    # ==========================================

    def _do_recommend(self):
        if not self.recommender:
            messagebox.showwarning("提示", "数据尚未加载完成")
            return

        hero = self.hero_var.get().strip()
        if not hero:
            messagebox.showwarning("提示", "请先选择或输入英雄名称")
            return

        if not self.recommender.has_hero(hero):
            heroes = self.recommender.get_hero_list()
            result = process.extractOne(hero, heroes, scorer=fuzz.ratio)
            if result and result[1] > 70:
                hero = result[0]
                self.hero_var.set(hero)
            else:
                messagebox.showwarning("未找到", f"未找到英雄 [{hero}]")
                return

        self.current_hero = hero
        team_heroes = [hero]

        if self.auto_mode and self.lcu and self.lcu.is_connected():
            team = self.lcu.get_team_champions()
            if team:
                team_heroes = team

        self.status_label.config(text=f"正在推荐 [{hero}]...", fg=Theme.WARNING)

        def _calc():
            try:
                result = self.recommender.recommend(hero, team_heroes=team_heroes, top_n=15)
                tier_result = self.recommender.recommend_by_tier(hero, team_heroes=team_heroes)
                self.root.after(0, lambda: self._show_result(result, tier_result))
            except Exception as e:
                self.root.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=_calc, daemon=True).start()

    def _show_result(self, result, tier_result):
        if result.get("error"):
            self.status_label.config(text=result["error"], fg=Theme.ERROR)
            self._show_placeholder(result["error"])
            return

        hero = result["hero"]
        recs = result["recommendations"]
        team = result.get("team_analysis")

        self.status_label.config(
            text=f"已推荐 {len(recs)} 个海克斯 · 当前: {hero}",
            fg=Theme.SUCCESS
        )

        if team and team.get("heroes"):
            self.team_label.config(text=self._format_team_analysis(team), fg=Theme.TEXT)
        else:
            self.team_label.config(text="无阵容数据 (按英雄单独推荐)", fg=Theme.TEXT_DIM)

        self._clear_recommendations()
        self._clear_tier_recommendations()

        # 更新 AI Tab 状态
        if self.ai_config.is_enabled and hero:
            self._show_ai_placeholder_with_hero(hero)
        else:
            self._show_ai_placeholder()

        if not recs:
            self._show_placeholder("该英雄暂无海克斯数据")
            return

        for i, rec in enumerate(recs):
            self._create_card(self.recommend_inner, rec, i + 1)

        groups = tier_result.get("groups", {})
        tier_order = ["棱彩", "黄金", "白银", "未知"]
        for tier in tier_order:
            if tier in groups:
                tier_recs = groups[tier]
                color = Theme.PRISMATIC if tier == "棱彩" else \
                        Theme.GOLD if tier == "黄金" else \
                        Theme.SILVER if tier == "白银" else Theme.TEXT_DIM
                tk.Label(self.tier_inner, text=f"◆ {tier} ({len(tier_recs)}个)",
                         font=("Microsoft YaHei", 12, "bold"), fg=color, bg=Theme.BG).pack(
                    anchor="w", pady=(8, 4) if tier != "棱彩" else (0, 4))
                for i, rec in enumerate(tier_recs[:8]):
                    self._create_card(self.tier_inner, rec, i + 1, show_team_score=False)

    def _format_team_analysis(self, team):
        heroes = team.get("heroes", [])
        damage = team.get("damage_type", "未知")
        ap = team.get("ap_count", 0)
        ad = team.get("ad_count", 0)
        cc = team.get("cc_total", 0)
        frontline = team.get("frontline_total", 0)
        sustain = team.get("sustain_total", 0)
        issues = team.get("issues", [])
        suggestions = team.get("suggestions", [])

        text = f"阵容: {' / '.join(heroes[:5])}\n"
        text += f"伤害类型: {damage} (AP:{ap} AD:{ad}) | 控制:{cc} | 前排:{frontline} | 续航:{sustain}\n"
        if issues:
            text += f"问题: {', '.join(issues)}\n"
        if suggestions:
            text += f"建议: {suggestions[0]}"
        return text

    def _create_card(self, parent, rec, rank, show_team_score=True):
        card = tk.Frame(parent, bg=Theme.BG_CARD, padx=12, pady=8,
                        highlightbackground=Theme.BORDER, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 6), padx=4)

        row1 = tk.Frame(card, bg=Theme.BG_CARD)
        row1.pack(fill=tk.X)

        rank_color = Theme.ERROR if rank <= 3 else Theme.WARNING if rank <= 6 else Theme.TEXT_DIM
        tk.Label(row1, text=f"#{rank}", font=("Microsoft YaHei", 12, "bold"),
                 fg=rank_color, bg=Theme.BG_CARD, width=4).pack(side=tk.LEFT)

        tk.Label(row1, text=rec["name"], font=("Microsoft YaHei", 11, "bold"),
                 fg=Theme.TEXT, bg=Theme.BG_CARD).pack(side=tk.LEFT, padx=(0, 8))

        tier = rec["tier"]
        tier_color = rec.get("tier_color", Theme.TEXT_DIM)
        tier_bg = tk.Frame(row1, bg=tier_color, padx=6, pady=1)
        tier_bg.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(tier_bg, text=tier, font=self.FONT_TAG, fg="white", bg=tier_color).pack()

        score = rec["final_score"]
        score_color = Theme.SUCCESS if score >= 70 else Theme.WARNING if score >= 50 else Theme.TEXT_DIM
        tk.Label(row1, text=f"评分 {score}", font=("Microsoft YaHei", 10, "bold"),
                 fg=score_color, bg=Theme.BG_CARD).pack(side=tk.RIGHT)

        row2 = tk.Frame(card, bg=Theme.BG_CARD)
        row2.pack(fill=tk.X, pady=(4, 0))

        detail_parts = [
            f"胜率排名 No.{rec['overall_rank']}",
            f"{rec['tier']}阶第{rec['t_rank']}位",
        ]
        if show_team_score:
            detail_parts.append(f"阵容匹配 {rec['team_score']}")

        tk.Label(row2, text=" | ".join(detail_parts), font=self.FONT_DETAIL,
                 fg=Theme.TEXT_DIM, bg=Theme.BG_CARD).pack(side=tk.LEFT)

        if rec.get("reason"):
            tk.Label(card, text=rec["reason"], font=self.FONT_DETAIL,
                     fg=Theme.TEXT_DIM, bg=Theme.BG_CARD, anchor="w").pack(
                fill=tk.X, pady=(2, 0))

    def _show_placeholder(self, text):
        self._clear_recommendations()
        tk.Label(self.recommend_inner, text=text, font=("Microsoft YaHei", 12),
                 fg=Theme.TEXT_DIM, bg=Theme.BG, justify=tk.LEFT).pack(pady=40)

    def _clear_recommendations(self):
        for w in self.recommend_inner.winfo_children():
            w.destroy()

    def _clear_tier_recommendations(self):
        for w in self.tier_inner.winfo_children():
            w.destroy()

    def _show_error(self, msg):
        self.status_label.config(text=f"错误: {msg}", fg=Theme.ERROR)
        messagebox.showerror("推荐失败", msg)

    # ==========================================
    # AI 设置和交互
    # ==========================================

    def _update_ai_status(self):
        """更新 AI 状态显示"""
        if self.ai_config.is_enabled:
            cfg = self.ai_config.get_effective_config()
            self.ai_status_label.config(
                text=f"✅ AI已启用 ({cfg['provider']}/{cfg['model']})",
                fg=Theme.SUCCESS
            )
            self.ai_ask_btn.config(state='normal')
        else:
            self.ai_status_label.config(
                text="未启用AI (点击「AI设置」配置API Key)",
                fg=Theme.TEXT_DIM
            )
            self.ai_ask_btn.config(state='disabled')

    def _open_ai_settings(self):
        """打开 AI 设置对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("AI 顾问设置")
        dialog.geometry("480x560")
        dialog.minsize(440, 520)
        dialog.configure(bg=Theme.BG)
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        content = tk.Frame(dialog, bg=Theme.BG, padx=24, pady=20)
        content.pack(fill=tk.BOTH, expand=True)

        # 标题
        tk.Label(content, text="🤖 AI 顾问配置", font=("Microsoft YaHei", 14, "bold"),
                 fg=Theme.TEXT, bg=Theme.BG).pack(anchor="w", pady=(0, 4))
        tk.Label(content, text="配置大语言模型 API，获得更智能的海克斯决策建议",
                 font=self.FONT_DETAIL, fg=Theme.TEXT_DIM, bg=Theme.BG).pack(anchor="w", pady=(0, 16))

        # 启用开关
        enable_frame = tk.Frame(content, bg=Theme.BG)
        enable_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(enable_frame, text="启用 AI 顾问", font=("Microsoft YaHei", 10),
                 fg=Theme.TEXT, bg=Theme.BG).pack(side=tk.LEFT)
        enable_var = tk.BooleanVar(value=self.ai_config.get("enabled", False))
        tk.Checkbutton(enable_frame, variable=enable_var, bg=Theme.BG,
                       activebackground=Theme.BG).pack(side=tk.LEFT, padx=(8, 0))

        # 提供商选择
        tk.Label(content, text="API 提供商", font=("Microsoft YaHei", 10),
                 fg=Theme.TEXT_DIM, bg=Theme.BG).pack(anchor="w", pady=(8, 2))

        provider_frame = tk.Frame(content, bg=Theme.BG)
        provider_frame.pack(fill=tk.X)

        current_provider = self.ai_config.get("provider", "deepseek")
        provider_var = tk.StringVar(value=current_provider)

        provider_combo = ttk.Combobox(provider_frame, textvariable=provider_var,
                                      state='readonly', font=("Microsoft YaHei", 10),
                                      width=30)
        provider_combo['values'] = list(PROVIDER_PRESETS.keys())
        provider_combo.pack(side=tk.LEFT)

        provider_desc_label = tk.Label(content, text="", font=self.FONT_DETAIL,
                                       fg=Theme.TEXT_DIM, bg=Theme.BG, wraplength=420, justify=tk.LEFT)
        provider_desc_label.pack(anchor="w", pady=(4, 0))

        def _on_provider_change(event=None):
            p = provider_var.get()
            desc = PROVIDER_PRESETS.get(p, {}).get("description", "")
            provider_desc_label.config(text=desc)

        provider_combo.bind('<<ComboboxSelected>>', _on_provider_change)
        _on_provider_change()

        # API Key
        tk.Label(content, text="API Key", font=("Microsoft YaHei", 10),
                 fg=Theme.TEXT_DIM, bg=Theme.BG).pack(anchor="w", pady=(12, 2))

        key_var = tk.StringVar(value=self.ai_config.get("api_key", ""))
        key_entry = tk.Entry(content, textvariable=key_var, show="*",
                             font=("Microsoft YaHei", 10), width=48)
        key_entry.pack(fill=tk.X, ipady=4)

        show_key_var = tk.BooleanVar(value=False)
        def _toggle_key_visibility():
            key_entry.config(show="" if show_key_var.get() else "*")
        tk.Checkbutton(content, text="显示Key", variable=show_key_var,
                       command=_toggle_key_visibility, bg=Theme.BG,
                       activebackground=Theme.BG).pack(anchor="w", pady=(4, 0))

        # 自定义 Base URL（仅 custom 提供商显示）
        url_frame = tk.Frame(content, bg=Theme.BG)
        url_frame.pack(fill=tk.X, pady=(8, 0))
        tk.Label(url_frame, text="自定义 API 地址 (可选)", font=("Microsoft YaHei", 10),
                 fg=Theme.TEXT_DIM, bg=Theme.BG).pack(anchor="w")
        url_var = tk.StringVar(value=self.ai_config.get("base_url", ""))
        url_entry = tk.Entry(url_frame, textvariable=url_var,
                             font=("Microsoft YaHei", 10), width=48)
        url_entry.pack(fill=tk.X, ipady=4)

        # 自定义模型名
        model_frame = tk.Frame(content, bg=Theme.BG)
        model_frame.pack(fill=tk.X, pady=(8, 0))
        tk.Label(model_frame, text="模型名 (可选，留空用默认)", font=("Microsoft YaHei", 10),
                 fg=Theme.TEXT_DIM, bg=Theme.BG).pack(anchor="w")
        model_var = tk.StringVar(value=self.ai_config.get("model", ""))
        model_entry = tk.Entry(model_frame, textvariable=model_var,
                               font=("Microsoft YaHei", 10), width=48)
        model_entry.pack(fill=tk.X, ipady=4)

        # 温度
        temp_frame = tk.Frame(content, bg=Theme.BG)
        temp_frame.pack(fill=tk.X, pady=(12, 0))
        tk.Label(temp_frame, text="温度 (0=严谨, 1=创意)", font=("Microsoft YaHei", 10),
                 fg=Theme.TEXT_DIM, bg=Theme.BG).pack(side=tk.LEFT)
        temp_var = tk.DoubleVar(value=self.ai_config.get("temperature", 0.7))
        temp_scale = ttk.Scale(temp_frame, from_=0, to=1, variable=temp_var,
                               orient=tk.HORIZONTAL, length=200)
        temp_scale.pack(side=tk.LEFT, padx=(12, 8))
        temp_val_label = tk.Label(temp_frame, text="0.7", font=self.FONT_DETAIL,
                                  fg=Theme.TEXT, bg=Theme.BG, width=4)
        temp_val_label.pack(side=tk.LEFT)
        def _on_temp_change(*_):
            temp_val_label.config(text=f"{temp_var.get():.1f}")
        temp_var.trace('w', _on_temp_change)

        # 按钮区
        btn_frame = tk.Frame(content, bg=Theme.BG)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        def _save():
            self.ai_config.update(
                enabled=enable_var.get(),
                provider=provider_var.get(),
                api_key=key_var.get().strip(),
                base_url=url_var.get().strip(),
                model=model_var.get().strip(),
                temperature=round(temp_var.get(), 2),
            )
            self.ai_advisor = AIAdvisor(self.ai_config)
            self._update_ai_status()
            dialog.destroy()
            if enable_var.get() and key_var.get().strip():
                messagebox.showinfo("已保存", "AI 配置已保存！\n点击「AI建议」标签页中的「询问AI建议」按钮使用。")

        def _cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text="取消", style='Secondary.TButton',
                   command=_cancel).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btn_frame, text="保存", style='Accent.TButton',
                   command=_save).pack(side=tk.RIGHT)

    def _ask_ai(self):
        """向 AI 请求建议"""
        if not self.ai_config.is_enabled:
            messagebox.showinfo("提示", "请先在「AI设置」中配置 API Key")
            return

        if not self.current_hero or not self.recommender:
            messagebox.showinfo("提示", "请先选择英雄并点击「推荐」")
            return

        # 获取当前推荐和阵容
        team_heroes = [self.current_hero]
        if self.auto_mode and self.lcu and self.lcu.is_connected():
            team = self.lcu.get_team_champions()
            if team:
                team_heroes = team

        result = self.recommender.recommend(self.current_hero, team_heroes=team_heroes, top_n=10)
        if result.get("error"):
            messagebox.showwarning("提示", result["error"])
            return

        local_recs = result.get("recommendations", [])
        team_analysis = result.get("team_analysis")

        # 显示加载状态
        self._show_ai_loading()

        def _task():
            response = self.ai_advisor.get_advice(
                hero_name=self.current_hero,
                team_heroes=team_heroes,
                local_recommendations=local_recs,
                team_analysis=team_analysis,
            )
            self.root.after(0, lambda: self._show_ai_result(response))

        threading.Thread(target=_task, daemon=True).start()

    def _show_ai_loading(self):
        """显示 AI 加载状态"""
        for w in self.ai_inner.winfo_children():
            w.destroy()
        tk.Label(self.ai_inner, text="🤔 AI 正在思考中...", font=("Microsoft YaHei", 12),
                 fg=Theme.ACCENT, bg=Theme.BG).pack(pady=40)
        self.ai_ask_btn.config(state='disabled')

    def _show_ai_result(self, response):
        """显示 AI 回复"""
        self.ai_ask_btn.config(state='normal')
        for w in self.ai_inner.winfo_children():
            w.destroy()

        if not response.get("success"):
            tk.Label(self.ai_inner, text=f"❌ AI请求失败\n\n{response.get('error', '未知错误')}",
                     font=("Microsoft YaHei", 10), fg=Theme.ERROR, bg=Theme.BG,
                     justify=tk.LEFT, wraplength=640).pack(pady=40, padx=16)
            return

        # AI 回复卡片
        card = tk.Frame(self.ai_inner, bg=Theme.BG_CARD, padx=16, pady=16,
                        highlightbackground=Theme.ACCENT, highlightthickness=2)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 8), padx=4)

        advice = response["advice"]
        # 按行展示
        for line in advice.split('\n'):
            if line.strip():
                # 检测标题行（含emoji或特殊符号开头）
                is_title = any(line.strip().startswith(e) for e in ['🎯', '📊', '⚔️', '##', '★', '◆'])
                font = ("Microsoft YaHei", 11, "bold") if is_title else ("Microsoft YaHei", 10)
                color = Theme.TEXT if is_title else Theme.TEXT
                tk.Label(card, text=line, font=font, fg=color, bg=Theme.BG_CARD,
                         anchor="w", justify=tk.LEFT, wraplength=620).pack(
                    fill=tk.X, pady=(1, 1))
            else:
                tk.Label(card, text="", bg=Theme.BG_CARD).pack(pady=(2, 2))

    def _show_ai_placeholder(self):
        """显示 AI 占位提示"""
        for w in self.ai_inner.winfo_children():
            w.destroy()
        if self.ai_config.is_enabled:
            text = "选择英雄并点击「推荐」后，\n再点击上方「询问AI建议」按钮获取智能建议"
        else:
            text = "AI 顾问未启用\n\n点击「AI设置」配置 API Key 即可启用\n支持 DeepSeek / OpenAI / 通义千问"
        tk.Label(self.ai_inner, text=text, font=("Microsoft YaHei", 11),
                 fg=Theme.TEXT_DIM, bg=Theme.BG, justify=tk.LEFT).pack(pady=40)

    def _show_ai_placeholder_with_hero(self, hero):
        """有英雄时的 AI 占位提示"""
        for w in self.ai_inner.winfo_children():
            w.destroy()
        text = f"当前英雄: {hero}\n\n点击上方「询问AI建议」按钮，\n让 AI 基于阵容给出更智能的推荐"
        tk.Label(self.ai_inner, text=text, font=("Microsoft YaHei", 11),
                 fg=Theme.ACCENT, bg=Theme.BG, justify=tk.LEFT).pack(pady=40)

    # ==========================================
    # 自动模式（安全版 LCU 连接）
    # ==========================================

    def _toggle_auto_mode(self):
        if not self.auto_mode:
            self._start_auto_mode()
        else:
            self._stop_auto_mode()

    def _start_auto_mode(self):
        if not self.recommender:
            messagebox.showwarning("提示", "数据尚未加载完成")
            return

        self.status_label.config(text="正在连接游戏客户端...", fg=Theme.WARNING)
        self.auto_btn.config(text="⏳ 连接中...")

        def _connect():
            try:
                champ_path = os.path.join(USER_DATA_DIR, 'champions.json')
                if not os.path.exists(champ_path):
                    champ_path = os.path.join(DATA_DIR, 'champions.json')

                lcu = SafeLCUConnector(champ_path)
                if lcu.connect():
                    self.lcu = lcu
                    self.auto_mode = True
                    self.root.after(0, lambda: self._on_auto_connected())
                else:
                    self.root.after(0, lambda: self._on_auto_failed(
                        "未检测到运行中的英雄联盟客户端\n\n"
                        "请确保:\n"
                        "1. 英雄联盟客户端已启动并登录\n"
                        "2. 游戏目录下存在 lockfile 文件\n\n"
                        "提示: 你也可以手动选择英雄进行推荐"))
            except Exception as e:
                self.root.after(0, lambda: self._on_auto_failed(str(e)))

        threading.Thread(target=_connect, daemon=True).start()

    def _on_auto_connected(self):
        self.status_label.config(text="已连接游戏客户端 · 选人后自动推荐", fg=Theme.SUCCESS)
        self.auto_btn.config(text="✅ 已连接 (点击断开)")
        self._lcu_thread = threading.Thread(target=self._poll_lcu, daemon=True)
        self._lcu_thread.start()

    def _on_auto_failed(self, msg):
        self.status_label.config(text="连接失败", fg=Theme.ERROR)
        self.auto_btn.config(text="🎮 自动识别 (连接游戏客户端)")
        messagebox.showinfo("连接提示", msg)

    def _poll_lcu(self):
        """后台轮询 LCU 状态（安全方式，只用 LCU API）"""
        last_hero = None
        poll_count = 0

        while self.auto_mode and self._running:
            try:
                if self.lcu and self.lcu.is_connected():
                    hero = self.lcu.get_current_champion()
                    if hero:
                        # 验证英雄名
                        validated = hero
                        if self.recommender and not self.recommender.has_hero(hero):
                            heroes = self.recommender.get_hero_list()
                            result = process.extractOne(hero, heroes, scorer=fuzz.ratio)
                            if result and result[1] > 70:
                                validated = result[0]

                        if validated != last_hero:
                            last_hero = validated
                            self.root.after(0, lambda h=validated: self._auto_set_hero(h))
                else:
                    # 每30次尝试重连一次
                    if poll_count % 30 == 0 and poll_count > 0:
                        self.lcu.reconnect()

                poll_count += 1
            except Exception:
                pass
            time.sleep(2)

    def _auto_set_hero(self, hero):
        self.hero_var.set(hero)
        self._do_recommend()

    def _stop_auto_mode(self):
        self.auto_mode = False
        if self.lcu:
            self.lcu.close()
            self.lcu = None
        self.auto_btn.config(text="🎮 自动识别 (连接游戏客户端)")
        self.status_label.config(text="已断开自动模式", fg=Theme.TEXT_DIM)

    # ==========================================
    # 关闭
    # ==========================================

    def _on_close(self):
        self._running = False
        self.auto_mode = False
        if self.lcu:
            self.lcu.close()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# ==========================================
# 入口
# ==========================================

def main():
    try:
        app = App()
        app.run()
    except Exception as e:
        try:
            messagebox.showerror("启动错误", f"程序启动时发生错误:\n\n{e}")
        except Exception:
            print(f"FATAL: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
