"""
符文/海克斯推荐引擎

结合英雄胜率数据 + 阵容分析结果，
给出综合推荐评分和排序。
"""
import csv
import os
import json
from collections import defaultdict
from scripts.config import DATA_DIR, CSV_FILE
from scripts.team_analyzer import TeamAnalyzer, match_hextach_to_team, get_hero_profile


class RuneRecommender:
    """海克斯符文推荐引擎"""

    # 等级优先级（棱彩 > 黄金 > 白银）
    TIER_PRIORITY = {"棱彩": 0, "黄金": 1, "白银": 2, "未知": 3}
    TIER_COLORS = {
        "棱彩": "#FF6BFF",   # 紫色
        "黄金": "#FFD700",   # 金色
        "白银": "#C0C0C0",   # 银色
        "未知": "#888888",
    }

    def __init__(self, csv_path=None, champions_json_path=None):
        self.csv_path = csv_path or CSV_FILE
        self.champions_json_path = champions_json_path or os.path.join(DATA_DIR, "champions.json")
        self.hero_data = {}        # {英雄名: {海克斯名: {tier, overall_rank, t_rank}}}
        self.cn_to_en = {}         # 中文名 -> 英文名
        self.en_to_cn = {}         # 英文名(小写) -> 中文名
        self._load_data()

    def _load_data(self):
        """加载 CSV 海克斯数据和英雄映射"""
        # 1. 加载英雄映射
        if os.path.exists(self.champions_json_path):
            try:
                with open(self.champions_json_path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                self.cn_to_en = mapping
                self.en_to_cn = {en.lower(): cn for cn, en in mapping.items()}
            except Exception as e:
                print(f"[WARN] champions.json 加载失败: {e}")

        # 2. 加载 CSV 海克斯数据
        if not os.path.exists(self.csv_path):
            print(f"[ERROR] CSV 文件不存在: {self.csv_path}")
            return

        try:
            with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                header = next(reader, None)

                for row in reader:
                    if not row or len(row) < 6:
                        continue
                    hero = row[0].strip()
                    tier = row[2].strip()
                    try:
                        overall_rank = int(row[3])
                    except (ValueError, IndexError):
                        overall_rank = 999
                    try:
                        t_rank = int(row[4])
                    except (ValueError, IndexError):
                        t_rank = 999
                    aug_name = row[5].strip()

                    if hero not in self.hero_data:
                        self.hero_data[hero] = {}
                    self.hero_data[hero][aug_name] = {
                        "tier": tier,
                        "overall_rank": overall_rank,
                        "t_rank": t_rank,
                    }

            print(f"[OK] 加载完成: {len(self.hero_data)} 个英雄的海克斯数据")
        except Exception as e:
            print(f"[ERROR] CSV 读取失败: {e}")

    def get_hero_list(self):
        """返回所有有数据的英雄名列表"""
        return sorted(self.hero_data.keys())

    def has_hero(self, hero_name):
        """检查英雄是否有数据"""
        return hero_name in self.hero_data

    def recommend(self, hero_name, team_heroes=None, tier_filter=None, top_n=10):
        """
        核心推荐方法：根据英雄 + 阵容推荐海克斯

        Args:
            hero_name: 当前英雄中文名
            team_heroes: 己方阵容英雄列表（含自己）
            tier_filter: 等级过滤 ["棱彩", "黄金", "白银"]，None=全部
            top_n: 返回前 N 个推荐

        Returns:
            dict: {
                "hero": str,
                "hero_profile": dict,
                "team_analysis": dict,
                "recommendations": [
                    {
                        "name": str,           # 海克斯名称
                        "tier": str,           # 等级
                        "overall_rank": int,   # 总排名
                        "t_rank": int,         # 等级内排名
                        "win_rate_score": int, # 胜率评分
                        "team_score": int,     # 阵容匹配评分
                        "final_score": int,    # 综合评分
                        "tier_color": str,     # 等级颜色
                        "tags": list,          # 属性标签
                        "reason": str,         # 推荐理由
                    },
                    ...
                ]
            }
        """
        if hero_name not in self.hero_data:
            return {
                "hero": hero_name,
                "hero_profile": get_hero_profile(hero_name),
                "team_analysis": None,
                "recommendations": [],
                "error": f"暂无 [{hero_name}] 的海克斯数据"
            }

        hero_augs = self.hero_data[hero_name]
        hero_profile = get_hero_profile(hero_name)

        # 阵容分析
        team_analysis = None
        if team_heroes:
            analyzer = TeamAnalyzer()
            team_analysis = analyzer.analyze_team(team_heroes)
        else:
            # 单英雄模式，只用英雄自身属性做基本分析
            team_analysis = {
                "heroes": [hero_name],
                "damage_type": hero_profile["damage_type"],
                "issues": [],
                "suggestions": ["按胜率排名推荐"],
                "frontline_total": hero_profile["frontline_score"],
                "cc_total": hero_profile["cc_level"],
            }

        # 遍历所有海克斯，计算综合评分
        recommendations = []
        for aug_name, aug_info in hero_augs.items():
            tier = aug_info.get("tier", "未知")
            overall_rank = aug_info.get("overall_rank", 999)
            t_rank = aug_info.get("t_rank", 999)

            # 等级过滤
            if tier_filter and tier not in tier_filter:
                continue

            # 胜率评分：排名越靠前分数越高
            # overall_rank 范围约 1-30+, 映射到 100-0
            win_rate_score = max(0, 100 - (overall_rank - 1) * 4) if overall_rank < 999 else 0

            # 阵容匹配评分
            team_score = match_hextach_to_team(aug_name, team_analysis) if team_analysis else 50

            # 综合评分: 胜率权重 60%, 阵容匹配权重 40%
            final_score = int(win_rate_score * 0.6 + team_score * 0.4)

            # 推荐理由
            reason = self._generate_reason(aug_name, tier, overall_rank, team_score, team_analysis)

            recommendations.append({
                "name": aug_name,
                "tier": tier,
                "overall_rank": overall_rank,
                "t_rank": t_rank,
                "win_rate_score": win_rate_score,
                "team_score": team_score,
                "final_score": final_score,
                "tier_color": self.TIER_COLORS.get(tier, "#888888"),
                "reason": reason,
            })

        # 按综合评分排序
        recommendations.sort(key=lambda x: (-x["final_score"], x["overall_rank"], x["t_rank"]))

        # 截取 top_n
        recommendations = recommendations[:top_n]

        return {
            "hero": hero_name,
            "hero_profile": hero_profile,
            "team_analysis": team_analysis,
            "recommendations": recommendations,
            "error": None,
        }

    def _generate_reason(self, aug_name, tier, overall_rank, team_score, team_analysis):
        """生成推荐理由文本"""
        parts = []

        # 胜率排名
        if overall_rank <= 3:
            parts.append(f"胜率极高(总No.{overall_rank})")
        elif overall_rank <= 10:
            parts.append(f"胜率较高(总No.{overall_rank})")
        elif overall_rank <= 20:
            parts.append(f"胜率一般(总No.{overall_rank})")
        else:
            parts.append(f"胜率较低(总No.{overall_rank})")

        # 等级
        if tier == "棱彩":
            parts.append("棱彩稀有")
        elif tier == "黄金":
            parts.append("黄金阶")

        # 阵容匹配
        if team_score >= 80 and team_analysis:
            issues = team_analysis.get("issues", [])
            for issue in issues:
                if issue != "阵容均衡":
                    parts.append(f"弥补「{issue}」")
                    break
            else:
                parts.append("阵容适配")
        elif team_score >= 65:
            parts.append("阵容较配")

        return " · ".join(parts)

    def recommend_by_tier(self, hero_name, team_heroes=None):
        """
        按等级分组推荐海克斯

        Returns:
            dict: {
                "棱彩": [...],
                "黄金": [...],
                "白银": [...],
            }
        """
        result = self.recommend(hero_name, team_heroes=team_heroes, top_n=999)
        if result.get("error"):
            return result

        grouped = defaultdict(list)
        for rec in result["recommendations"]:
            grouped[rec["tier"]].append(rec)

        # 每组内按 final_score 排序
        for tier in grouped:
            grouped[tier].sort(key=lambda x: -x["final_score"])

        return {
            "hero": hero_name,
            "hero_profile": result["hero_profile"],
            "team_analysis": result["team_analysis"],
            "groups": dict(grouped),
            "error": None,
        }
