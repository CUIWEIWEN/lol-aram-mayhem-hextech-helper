"""
阵容分析模块

通过 LCU API 获取选人阶段和游戏中的双方阵容，
分析阵容特征（AP/AD比例、控制量、前排厚度、续航能力等），
为符文/海克斯推荐提供上下文依据。
"""
import json
import os

# ==========================================
# 英雄角色/定位数据
# 用于判断阵容的 AP/AD 分布、前排厚度、控制量等
# 数据来源：官方英雄定位 + 手动标注大乱斗常见特征
# ==========================================

# 伤害类型: "AD" / "AP" / "混合" / "真伤"
# 定位: "坦克" / "战士" / "刺客" / "法师" / "射手" / "辅助"
# 控制量: 1-3 (1=少控, 2=中等, 3=多控)
# 前排指数: 0-3 (0=脆皮, 3=纯肉)

# 核心英雄属性表（覆盖大乱斗常见英雄）
# 格式: 中文名 -> {damage_type, role, cc_level, frontline_score, sustain}
HERO_PROFILES = {
    # === 坦克 ===
    "牛头酋长":     {"damage_type": "AP", "role": "坦克", "cc_level": 3, "frontline_score": 3, "sustain": 2},
    "殇之木乃伊":   {"damage_type": "AP", "role": "坦克", "cc_level": 3, "frontline_score": 3, "sustain": 2},
    "虚空恐惧":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 3},
    "弗雷尔卓德之心": {"damage_type": "AD", "role": "坦克/辅助", "cc_level": 3, "frontline_score": 3, "sustain": 2},
    "曙光女神":     {"damage_type": "AP", "role": "坦克/辅助", "cc_level": 3, "frontline_score": 3, "sustain": 1},
    "熔岩巨兽":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "树精卫士":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "深海泰坦":     {"damage_type": "AP", "role": "坦克/辅助", "cc_level": 3, "frontline_score": 3, "sustain": 2},
    "雪人骑士":     {"damage_type": "AD", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 3},
    "披甲龙龟":     {"damage_type": "AD", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "加里奥":       {"damage_type": "AP", "role": "坦克/法师", "cc_level": 3, "frontline_score": 2, "sustain": 1},
    "波比":         {"damage_type": "AD", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "酒桶":         {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},

    # === 战士 ===
    "暗裔剑魔":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 2, "sustain": 2},
    "诺克萨斯之手": {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 2, "sustain": 2},
    "德玛西亚之力": {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 2, "sustain": 1},
    "武器大师":     {"damage_type": "混合", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "荒漠屠夫":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "疾风剑豪":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "封魔剑魂":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "海洋之灾":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 1},
    "铁血狼母":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "青钢影":       {"damage_type": "AD", "role": "战士/刺客", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "机械公敌":     {"damage_type": "混合", "role": "战士/法师", "cc_level": 1, "frontline_score": 2, "sustain": 1},
    "海兽祭司":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 2, "sustain": 2},
    "迷失之子":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 1},
    "圣锤之毅":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "德邦总管":     {"damage_type": "AD", "role": "战士/刺客", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "狂厄蔷薇":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "腕豪":         {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "齐天大圣":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "牧魂人":       {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 2, "sustain": 1},
    "不灭狂雷":     {"damage_type": "AP", "role": "战士/坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "翠神":         {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 1, "sustain": 1},

    # === 刺客 ===
    "离群之刺":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "潮汐海灵":     {"damage_type": "AP", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "卡特琳娜":     {"damage_type": "AP", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "影流之主":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "傲之追猎者":   {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "不祥之刃":     {"damage_type": "AP", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "虚无之眼":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},

    # === 法师 ===
    "九尾妖狐":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "冰晶凤凰":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "黑暗之女":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "寒冰射手":     {"damage_type": "AD", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "沙漠皇帝":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "复仇焰魂":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "魔蛇之拥":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "虚空先知":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "末日使者":     {"damage_type": "AP", "role": "法师", "cc_level": 3, "frontline_score": 0, "sustain": 1},
    "光辉女郎":     {"damage_type": "AP", "role": "法师/辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "季分之仙":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "堕落天使":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "爆破鬼才":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "机械先驱":     {"damage_type": "混合", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "邪恶小法师":   {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "猩红收割者":   {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 1, "sustain": 3},
    "远古巫灵":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "蜘蛛女皇":     {"damage_type": "AP", "role": "法师/刺客", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "皎月女神":     {"damage_type": "AP", "role": "法师/战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "发条魔灵":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "荆棘之兴":     {"damage_type": "AP", "role": "法师/辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "岩雀":         {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "星界游神":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "铸星龙王":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "佐伊":         {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "辛德拉":       {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "双界灵兔":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "异画师":       {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "斯莫德":       {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},

    # === 射手 ===
    "皮城女警":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "英勇投弹手":   {"damage_type": "混合", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "荣耀行刑官":   {"damage_type": "AD", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "探险家":       {"damage_type": "混合", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "赏金猎人":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "暴走萝莉":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "麦林炮手":     {"damage_type": "AD", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "惩戒之箭":     {"damage_type": "AD", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "圣枪游侠":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 2},
    "戏命师":       {"damage_type": "AD", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "逆羽":         {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "残月之肃":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "虚空之女":     {"damage_type": "AD", "role": "射手/刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "沙漠玫瑰":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "愁云使者":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "尼菈":         {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 1, "sustain": 2},

    # === 辅助 ===
    "蒸汽机器人":   {"damage_type": "AP", "role": "辅助/坦克", "cc_level": 3, "frontline_score": 2, "sustain": 1},
    "星籁歌姬":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 2},
    "仙灵女巫":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "唤潮鲛姬":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 2},
    "琴瑟仙女":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "风暴之怒":     {"damage_type": "AP", "role": "辅助", "cc_level": 3, "frontline_score": 0, "sustain": 1},
    "幻翎":         {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "血港鬼影":     {"damage_type": "AP", "role": "辅助/刺客", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "魂锁典狱长":   {"damage_type": "AP", "role": "辅助/坦克", "cc_level": 3, "frontline_score": 2, "sustain": 1},
    "万花通灵":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "影哨":         {"damage_type": "AD", "role": "射手/刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "迷雾女巫":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},

    # === 补充英雄档案 ===
    # 战士/坦克类
    "上古领主":     {"damage_type": "AD", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "不屈之枪":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "不破之誓":     {"damage_type": "AD", "role": "战士/坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "亡灵战神":     {"damage_type": "AD", "role": "坦克", "cc_level": 1, "frontline_score": 3, "sustain": 2},
    "刀锋舞者":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "北地之怒":     {"damage_type": "AD", "role": "战士/坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "德玛西亚皇子": {"damage_type": "AD", "role": "战士/坦克", "cc_level": 3, "frontline_score": 2, "sustain": 1},
    "战争之影":     {"damage_type": "AD", "role": "战士/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "放逐之刃":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "无双剑姬":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "无极剑圣":     {"damage_type": "AD", "role": "战士/刺客", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "无畏战车":     {"damage_type": "AD", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 1},
    "未来守护者":   {"damage_type": "混合", "role": "战士/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "正义巨像":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 1},
    "永恒梦魇":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "永猎双子":     {"damage_type": "AD", "role": "战士/刺客", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "狂战士":       {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "狂暴之心":     {"damage_type": "AP", "role": "战士", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "皮城执法官":   {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "盲僧":         {"damage_type": "AD", "role": "战士/刺客", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "破败之王":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "祖安怒兽":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 2, "sustain": 2},
    "祖安狂人":     {"damage_type": "AP", "role": "坦克/战士", "cc_level": 1, "frontline_score": 2, "sustain": 3},
    "蛮族之王":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "暮光之眼":     {"damage_type": "AP", "role": "坦克/战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "暴怒骑士":     {"damage_type": "AD", "role": "战士/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "河流之王":     {"damage_type": "AP", "role": "坦克/辅助", "cc_level": 2, "frontline_score": 3, "sustain": 1},
    "深渊巨口":     {"damage_type": "混合", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "炼金术士":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 2, "sustain": 3},
    "生化魔人":     {"damage_type": "AP", "role": "坦克/战士", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "痛苦之拥":     {"damage_type": "AP", "role": "刺客/法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "祖安花火":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "不羁之悦":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "不落魔锋":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "影流之镰":     {"damage_type": "AD", "role": "刺客/战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "明烛":         {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "灰烬驱魔人":   {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "百裂冥犬":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 1, "sustain": 2},
    "纳祖芒荣耀":   {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "镕铁少女":     {"damage_type": "AP", "role": "坦克/辅助", "cc_level": 3, "frontline_score": 3, "sustain": 1},
    "龙血武姬":     {"damage_type": "混合", "role": "战士/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 2},

    # 法师类
    "冰霜女巫":     {"damage_type": "AP", "role": "法师", "cc_level": 3, "frontline_score": 1, "sustain": 1},
    "元素女皇":     {"damage_type": "AP", "role": "法师/刺客", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "奥术先驱":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 1, "sustain": 1},
    "暗黑元首":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "死亡颂唱者":   {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "符文法师":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "解脱者":       {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "诡术妖姬":     {"damage_type": "AP", "role": "刺客/法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "诺克萨斯统领": {"damage_type": "AP", "role": "法师/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "虚空之眼":     {"damage_type": "AP", "role": "法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "虚空女皇":     {"damage_type": "AD", "role": "战士/刺客", "cc_level": 2, "frontline_score": 1, "sustain": 2},
    "虚空掠夺者":   {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "虚空行者":     {"damage_type": "AP", "role": "刺客/法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "虚空遁地兽":   {"damage_type": "混合", "role": "战士/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "远古恐惧":     {"damage_type": "AP", "role": "法师", "cc_level": 3, "frontline_score": 0, "sustain": 1},
    "时光守护者":   {"damage_type": "AP", "role": "辅助/法师", "cc_level": 2, "frontline_score": 0, "sustain": 2},
    "铁铠冥魂":     {"damage_type": "AP", "role": "法师/战士", "cc_level": 2, "frontline_score": 1, "sustain": 2},
    "流光镜影":     {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "山隐之焰":     {"damage_type": "AD", "role": "坦克/辅助", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "炼金男爵":     {"damage_type": "AP", "role": "法师/辅助", "cc_level": 2, "frontline_score": 0, "sustain": 2},

    # 射手/刺客类
    "刀锋之影":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "卡牌大师":     {"damage_type": "混合", "role": "法师/射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "复仇之矛":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "暗夜猎手":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "法外狂徒":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 1, "sustain": 1},
    "瘟疫之源":     {"damage_type": "AD", "role": "射手/刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},

    # 辅助类
    "众星之子":     {"damage_type": "AP", "role": "辅助", "cc_level": 1, "frontline_score": 0, "sustain": 2},
    "天启者":       {"damage_type": "AP", "role": "辅助", "cc_level": 2, "frontline_score": 0, "sustain": 2},
    "魔法猫咪":     {"damage_type": "AP", "role": "辅助", "cc_level": 1, "frontline_score": 0, "sustain": 2},
    "涤魂圣枪":     {"damage_type": "AP", "role": "辅助/射手", "cc_level": 2, "frontline_score": 0, "sustain": 2},

    # 其他
    "兽灵行者":     {"damage_type": "AD", "role": "战士", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "含羞蓓蕾":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "德玛西亚之翼": {"damage_type": "AD", "role": "射手", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "恶魔小丑":     {"damage_type": "AD", "role": "刺客", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "战争女神":     {"damage_type": "AD", "role": "射手/战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "扭曲树精":     {"damage_type": "AP", "role": "坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "时间刺客":     {"damage_type": "AD", "role": "刺客/战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "暮光星灵":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "正义天使":     {"damage_type": "混合", "role": "射手/法师", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "沙漠死神":     {"damage_type": "AD", "role": "战士/坦克", "cc_level": 1, "frontline_score": 2, "sustain": 2},
    "灵罗娃娃":     {"damage_type": "AD", "role": "战士", "cc_level": 1, "frontline_score": 1, "sustain": 2},
    "瓦洛兰之盾":   {"damage_type": "AP", "role": "坦克/辅助", "cc_level": 2, "frontline_score": 3, "sustain": 1},
    "迷失之牙":     {"damage_type": "混合", "role": "战士/坦克", "cc_level": 2, "frontline_score": 2, "sustain": 1},
    "雪原双子":     {"damage_type": "AP", "role": "坦克/辅助", "cc_level": 2, "frontline_score": 2, "sustain": 2},
    "巨魔之王":     {"damage_type": "AD", "role": "战士/坦克", "cc_level": 2, "frontline_score": 3, "sustain": 2},
    "狂野女猎手":   {"damage_type": "AP", "role": "法师/刺客", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "迅捷斥候":     {"damage_type": "AP", "role": "射手/法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
    "炽炎雏龙":     {"damage_type": "AD", "role": "射手", "cc_level": 1, "frontline_score": 0, "sustain": 1},
    "大发明家":     {"damage_type": "AP", "role": "法师", "cc_level": 2, "frontline_score": 0, "sustain": 1},
}


def get_hero_profile(hero_name):
    """获取英雄属性档案，找不到的返回默认值"""
    default = {"damage_type": "混合", "role": "未知", "cc_level": 1, "frontline_score": 1, "sustain": 1}
    return HERO_PROFILES.get(hero_name, default)


class TeamAnalyzer:
    """阵容分析器"""

    def __init__(self, lcu_connector=None):
        self.lcu = lcu_connector

    def get_team_composition(self):
        """
        获取当前己方阵容的英雄列表。
        优先从 LCU ChampSelect 获取，备选从 Live Client Data API 获取。

        Returns:
            list[str]: 己方英雄中文名列表，失败返回空列表
        """
        if not self.lcu or not self.lcu.is_connected():
            return []

        # 方式1: 从 ChampSelect session 获取全队英雄
        team = self._get_champselect_team()
        if team:
            return team

        # 方式2: 从 Live Client Data API 获取
        team = self._get_live_team()
        if team:
            return team

        return []

    def _get_champselect_team(self):
        """从 ChampSelect session 获取己方阵容"""
        try:
            resp = self.lcu._request('GET', '/lol-champ-select/v1/session')
            if not resp or resp.status_code != 200:
                return []

            data = resp.json()
            my_team = data.get('myTeam', [])
            team_heroes = []
            for player in my_team:
                cid = player.get('championId', 0)
                if cid and cid > 0:
                    cn_name = self.lcu.id_to_cn.get(cid)
                    if cn_name:
                        team_heroes.append(cn_name)
            return team_heroes
        except Exception:
            return []

    def _get_live_team(self):
        """从 Live Client Data API 获取己方阵容"""
        try:
            resp = self.lcu.live_session.get(
                'https://127.0.0.1:2999/liveclientdata/playerlist',
                verify=False, timeout=self.lcu.LIVE_API_TIMEOUT
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            # allPlayers 中 team 字段为 "ORDER" (蓝方) / "CHAOS" (红方)
            # 找到当前玩家的队伍
            my_team_name = None
            team_heroes = []
            for p in data:
                champ_raw = p.get('championName', '') or p.get('rawChampionName', '')
                cn = self.lcu._resolve_champion_name(champ_raw)
                if not cn:
                    continue
                team_name = p.get('team', '')
                if my_team_name is None:
                    my_team_name = team_name
                    team_heroes.append(cn)
                elif team_name == my_team_name:
                    team_heroes.append(cn)
            return team_heroes
        except Exception:
            return []

    def analyze_team(self, team_heroes):
        """
        分析阵容特征

        Args:
            team_heroes: 英雄中文名列表

        Returns:
            dict: 阵容分析结果
            {
                "heroes": [...],           # 英雄列表
                "damage_type": "AP"/"AD"/"混合",  # 主要伤害类型
                "ap_count": int,           # AP英雄数量
                "ad_count": int,           # AD英雄数量
                "cc_total": int,           # 控制总量
                "frontline_total": int,    # 前排总量
                "sustain_total": int,      # 续航总量
                "issues": [...],           # 阵容问题
                "suggestions": [...],      # 推荐方向
            }
        """
        if not team_heroes:
            return self._empty_analysis()

        profiles = [get_hero_profile(h) for h in team_heroes]
        ap_count = sum(1 for p in profiles if p["damage_type"] == "AP")
        ad_count = sum(1 for p in profiles if p["damage_type"] == "AD")
        hybrid_count = sum(1 for p in profiles if p["damage_type"] == "混合")

        cc_total = sum(p["cc_level"] for p in profiles)
        frontline_total = sum(p["frontline_score"] for p in profiles)
        sustain_total = sum(p["sustain"] for p in profiles)

        # 判断主要伤害类型
        if ap_count > ad_count + hybrid_count:
            main_damage = "AP"
        elif ad_count > ap_count + hybrid_count:
            main_damage = "AD"
        else:
            main_damage = "混合"

        # 阵容问题诊断
        issues = []
        suggestions = []

        # 前排不足
        if frontline_total < 4:
            issues.append("前排不足")
            suggestions.append("优先选择生存/坦克类海克斯增强前排能力")

        # 控制不足
        if cc_total < 5:
            issues.append("控制不足")
            suggestions.append("考虑选择控制增强类海克斯补充控制链")

        # 伤害类型单一
        if ap_count >= 4 and ad_count <= 1:
            issues.append("全AP阵容")
            suggestions.append("对面可能堆魔抗，选择法穿/混合伤害海克斯")
        elif ad_count >= 4 and ap_count <= 1:
            issues.append("全AD阵容")
            suggestions.append("对面可能堆护甲，选择破甲/真伤海克斯")

        # 续航不足
        if sustain_total < 5:
            issues.append("续航不足")
            suggestions.append("选择回复/吸血类海克斯提升续航")

        # 脆皮过多
        squishy_count = sum(1 for p in profiles if p["frontline_score"] <= 0)
        if squishy_count >= 4:
            issues.append("阵容过脆")
            suggestions.append("选择防御/减伤类海克斯弥补脆皮缺陷")

        if not issues:
            issues.append("阵容均衡")
            suggestions.append("按胜率排序选择最优海克斯即可")

        return {
            "heroes": team_heroes,
            "damage_type": main_damage,
            "ap_count": ap_count,
            "ad_count": ad_count,
            "hybrid_count": hybrid_count,
            "cc_total": cc_total,
            "frontline_total": frontline_total,
            "sustain_total": sustain_total,
            "squishy_count": squishy_count,
            "issues": issues,
            "suggestions": suggestions,
        }

    def _empty_analysis(self):
        return {
            "heroes": [],
            "damage_type": "未知",
            "ap_count": 0,
            "ad_count": 0,
            "hybrid_count": 0,
            "cc_total": 0,
            "frontline_total": 0,
            "sustain_total": 0,
            "squishy_count": 0,
            "issues": ["无法获取阵容"],
            "suggestions": ["请确保游戏客户端正在运行"],
        }


# ==========================================
# 海克斯属性标签
# 用于将海克斯与阵容需求匹配
# ==========================================
HEXTACH_TAGS = {
    # 生存/坦克类
    "歌利亚巨人": ["生存", "坦克"],
    "巨像的勇气": ["生存", "坦克"],
    "自适应防护": ["生存", "防御"],
    "最终形态": ["生存", "全能"],
    "超负荷": ["生存", "全能"],
    "坦克引擎": ["生存", "坦克"],
    "屹立不倒": ["生存", "防御"],
    "质变：棱彩阶": ["强化"],
    "热舞怪兽": ["生存", "坦克"],

    # 回复/吸血类
    "贪欲束缚": ["吸血", "续航"],
    "吸元秘术": ["吸血", "续航"],
    "渴血": ["吸血", "续航"],

    # 控制类
    "惊惧": ["控制"],

    # 伤害增强类 - AD
    "命运之武器": ["AD", "增伤"],
    "强化!": ["AD", "增伤"],
    "重型": ["AD", "增伤"],
    "虚幻武器": ["AD", "增伤"],
    "罪恶快感！": ["AD", "增伤"],

    # 伤害增强类 - AP
    "珠光护手": ["AP", "增伤"],
    "升级：焚天": ["混合", "增伤"],

    # 通用增伤
    "大力": ["增伤", "通用"],
    "循环往复": ["冷却", "通用"],
    "单曲红人": ["增伤", "通用"],
    "鼓声暴起 低音轰鸣": ["增伤", "通用"],
    "前进时间到": ["冷却", "通用"],
    "逃跑计划": ["机动", "通用"],

    # 升级类
    "升级：死亡之舞": ["装备升级"],
    "升级：贪欲九头蛇": ["装备升级"],

    # 终极海克斯
    "终极九头蛇": ["终极", "增伤"],
}


def get_hextach_tags(hextach_name):
    """获取海克斯的属性标签"""
    return HEXTACH_TAGS.get(hextach_name, ["通用"])


def match_hextach_to_team(hextach_name, team_analysis):
    """
    判断某个海克斯是否匹配当前阵容需求

    Returns:
        int: 匹配度评分 (0-100)
    """
    tags = get_hextach_tags(hextach_name)
    issues = team_analysis.get("issues", [])
    score = 50  # 基础分

    # 根据阵容问题匹配标签
    if "前排不足" in issues or "阵容过脆" in issues:
        if "生存" in tags or "坦克" in tags or "防御" in tags:
            score += 30

    if "续航不足" in issues:
        if "吸血" in tags or "续航" in tags:
            score += 30

    if "控制不足" in issues:
        if "控制" in tags:
            score += 30

    if "全AP阵容" in issues:
        if "AP" in tags or "法穿" in tags:
            score += 15
        if "混合" in tags:
            score += 20  # 混合伤害弥补全AP

    if "全AD阵容" in issues:
        if "AD" in tags or "破甲" in tags:
            score += 15
        if "混合" in tags:
            score += 20  # 混合伤害弥补全AD

    if "阵容均衡" in issues:
        score += 10  # 均衡阵容任何海克斯都还行

    return min(score, 100)
