# LOL 海克斯极地大乱斗 - 符文推荐助手 v2.0

![Python](https://img.shields.io/badge/Python-3.10~3.12-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![License](https://img.shields.io/badge/License-MIT-green)

> 基于 [Nyx0ra/lol-aram-mayhem-hextech-helper](https://github.com/Nyx0ra/lol-aram-mayhem-hextech-helper) 二次开发

## ✨ 功能特性

- **英雄选择**：搜索/下拉选择任意英雄，即时查看海克斯推荐
- **阵容分析**：自动获取己方阵容，分析 AP/AD 分布、控制量、前排厚度、续航能力
- **智能推荐**：综合胜率数据 (60%) + 阵容匹配度 (40%) 给出最佳海克斯推荐
- **按等级分组**：棱彩 / 黄金 / 白银 分类展示
- **自动识别**：通过官方 LCU API 连接客户端，选人后自动推荐
- **数据自动更新**：启动时检查 GitHub 最新数据，6小时检查一次
- **独立 exe**：PyInstaller 打包，无需安装 Python
- **安全设计**：不被 WeGame 识别为外挂

## 📦 快速开始

### 方式一：下载 exe（推荐新手）

1. 前往 Releases 页面下载最新版 `LOLAramRuneHelper.zip`
2. 解压到任意目录
3. 双击 `LOLAramRuneHelper.exe` 运行
4. 无需安装任何东西

### 方式二：从源码运行

```bash
git clone https://github.com/your-repo/lol-aram-rune-helper.git
cd lol-aram-rune-helper
pip install -r requirements.txt
python app.py
```

### 方式三：自行打包 exe

```bash
python build.py
# 输出在 dist/LOLAramRuneHelper/
```

## 🛡️ 安全设计（防 WeGame 误报）

本程序**不会**被 WeGame/腾讯反作弊 (ACE) 识别为外挂：

| 行为 | 本程序 | 说明 |
|------|--------|------|
| 全局热键 hook | ❌ 不使用 | 不 hook 键盘 |
| 截屏 OCR | ❌ 不使用 | 不读取游戏画面 |
| 进程扫描 | ❌ 不使用 | 不遍历 system processes |
| 连接 2999 端口 | ❌ 不使用 | 不读取局内数据 |
| 读取 lockfile | ✅ | 只读文件，不侵入进程 |
| LCU API 查询 | ✅ | Riot 官方本地接口 |
| 修改游戏文件 | ❌ | 从不修改 |
| 注入游戏进程 | ❌ | 从不注入 |

**核心原则**：本程序是纯粹的"数据查询工具"，只通过 Riot 官方 LCU API 获取选人阶段的英雄信息，不涉及游戏内存读取、画面截取或进程注入。

## 🔄 数据自动更新

- 启动时自动检查 GitHub 仓库最新数据
- 6小时内不重复检查
- 更新数据保存在 `%APPDATA%/LOLAramRuneHelper/data/`
- 网络不可用时使用内置数据，离线可用
- 可手动点击「检查更新」按钮强制刷新

## 🧠 推荐算法

```
综合评分 = 胜率评分 × 60% + 阵容匹配评分 × 40%
```

| 阵容问题 | 匹配海克斯标签 | 加分 |
|---------|--------------|------|
| 前排不足 | 生存/坦克/防御 | +30 |
| 续航不足 | 吸血/续航 | +30 |
| 控制不足 | 控制 | +30 |
| 全 AP 阵容 | 混合伤害 | +20 |
| 全 AD 阵容 | 混合伤害 | +20 |

## 📂 项目结构

```
lol-aram-rune-helper/
├── app.py                       # 主程序（新手 GUI）
├── build.py                     # PyInstaller 打包脚本
├── start.bat                    # 一键启动（源码模式）
├── requirements.txt             # Python 依赖
│
├── scripts/
│   ├── safe_lcu_connector.py    # 安全版 LCU 连接器（不用进程扫描）
│   ├── data_updater.py          # 数据自动更新
│   ├── rune_recommender.py      # 符文推荐引擎
│   ├── team_analyzer.py         # 阵容分析
│   ├── config.py                # 路径配置
│   ├── lcu_connector.py         # 原版 LCU 连接器（保留）
│   ├── hero_scraper.py          # OP.GG 爬虫（保留）
│   └── ...
│
├── data/
│   ├── hero_augments.csv        # 海克斯胜率数据
│   ├── champions.json           # 英雄映射
│   └── pinyin_map.json          # 拼音索引
│
└── assets/
    └── icon.ico                 # 图标
```

## 📄 License

MIT License
