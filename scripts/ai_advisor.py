"""
AI 顾问模块

接入大语言模型 API，在本地规则推荐的基础上提供更智能的决策建议。

支持的 API 提供商:
  1. OpenAI (GPT-4o / GPT-4o-mini)
  2. DeepSeek (deepseek-chat)
  3. 通义千问 (qwen-plus / qwen-turbo)
  4. 任意 OpenAI 兼容 API (自定义 base_url)

配置方式:
  - 在 settings.json 中填入 api_key 和 provider
  - 或在 GUI 设置界面中填写
"""
import os
import json
import time
import requests

# ==========================================
# 默认配置
# ==========================================

DEFAULT_CONFIG = {
    "enabled": False,
    "provider": "deepseek",       # openai / deepseek / qwen / custom
    "api_key": "",
    "base_url": "",               # 自定义 API 地址（留空则用 provider 默认地址）
    "model": "",                  # 模型名（留空则用 provider 默认模型）
    "max_tokens": 800,            # 最大返回 token 数
    "temperature": 0.7,           # 温度（0=严谨, 1=创意）
}

# 各提供商默认配置
PROVIDER_PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "description": "DeepSeek (国内可直连, 性价比高)",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "description": "OpenAI (需要代理, 效果最好)",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "description": "通义千问 (阿里云, 国内直连)",
    },
    "custom": {
        "base_url": "",
        "model": "",
        "description": "自定义 (任意 OpenAI 兼容 API)",
    },
}


# ==========================================
# 配置管理
# ==========================================

class AIConfig:
    """AI 配置管理器"""

    def __init__(self, config_path):
        self.config_path = config_path
        self.config = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        """从文件加载配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                # 合并配置（保留新字段的默认值）
                self.config.update(saved)
            except Exception:
                pass

    def save(self):
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def update(self, **kwargs):
        self.config.update(kwargs)
        self.save()

    @property
    def is_enabled(self):
        return self.config.get("enabled", False) and bool(self.config.get("api_key"))

    def get_effective_config(self):
        """获取生效配置（合并 provider 预设）"""
        provider = self.config.get("provider", "deepseek")
        preset = PROVIDER_PRESETS.get(provider, {})

        base_url = self.config.get("base_url") or preset.get("base_url", "")
        model = self.config.get("model") or preset.get("model", "")

        return {
            "enabled": self.is_enabled,
            "provider": provider,
            "api_key": self.config.get("api_key", ""),
            "base_url": base_url,
            "model": model,
            "max_tokens": self.config.get("max_tokens", 800),
            "temperature": self.config.get("temperature", 0.7),
        }


# ==========================================
# AI 顾问
# ==========================================

class AIAdvisor:
    """AI 决策顾问"""

    def __init__(self, config):
        """
        Args:
            config: AIConfig 实例
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

    def is_available(self):
        """检查 AI 是否可用"""
        return self.config.is_enabled

    def get_advice(self, hero_name, team_heroes, local_recommendations, team_analysis=None):
        """
        向 AI 请求智能决策建议

        Args:
            hero_name: 当前英雄中文名
            team_heroes: 己方阵容英雄列表
            local_recommendations: 本地引擎的推荐结果列表
            team_analysis: 阵容分析结果 (dict)

        Returns:
            dict: {
                "success": bool,
                "advice": str,       # AI 建议文本
                "error": str | None, # 错误信息
            }
        """
        if not self.is_available():
            return {"success": False, "advice": "", "error": "AI 未启用或未配置 API Key"}

        cfg = self.config.get_effective_config()

        # 构建 prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(hero_name, team_heroes, local_recommendations, team_analysis)

        # 调用 API
        try:
            response = self._call_api(cfg, system_prompt, user_prompt)
            if response.get("success"):
                advice = response["content"]
                return {"success": True, "advice": advice, "error": None}
            else:
                return {"success": False, "advice": "", "error": response.get("error", "API 调用失败")}
        except Exception as e:
            return {"success": False, "advice": "", "error": str(e)}

    def _build_system_prompt(self):
        """构建系统提示词"""
        return (
            "你是一个英雄联盟海克斯极地大乱斗（ARAM Mayhem）的专家顾问。\n"
            "你的任务是根据英雄特性、阵容组成和海克斯胜率数据，给出最优的海克斯选择建议。\n\n"
            "回答要求：\n"
            "1. 简洁有力，不超过 300 字\n"
            "2. 先给出最推荐的 3 个海克斯（按优先级排序）\n"
            "3. 说明推荐理由（结合阵容分析）\n"
            "4. 指出需要注意的对局要点\n"
            "5. 使用中文回答\n\n"
            "格式：\n"
            "🎯 最优推荐：\n1. [海克斯名] - 理由\n2. [海克斯名] - 理由\n3. [海克斯名] - 理由\n\n"
            "📊 阵容分析：\n（简述阵容优劣势）\n\n"
            "⚔️ 对局要点：\n（1-2 条关键建议）"
        )

    def _build_user_prompt(self, hero_name, team_heroes, local_recs, team_analysis):
        """构建用户提示词"""
        lines = []
        lines.append(f"当前英雄: {hero_name}")
        lines.append(f"己方阵容: {' / '.join(team_heroes)}")

        if team_analysis:
            lines.append(f"阵容伤害类型: {team_analysis.get('damage_type', '未知')}")
            lines.append(f"前排指数: {team_analysis.get('frontline_total', 0)}/15")
            lines.append(f"控制指数: {team_analysis.get('cc_total', 0)}/15")
            lines.append(f"续航指数: {team_analysis.get('sustain_total', 0)}/15")
            issues = team_analysis.get("issues", [])
            if issues:
                lines.append(f"阵容问题: {', '.join(issues)}")

        lines.append("\n本地胜率排名 Top 5:")
        for i, rec in enumerate(local_recs[:5]):
            lines.append(
                f"  {i+1}. [{rec['tier']}] {rec['name']} "
                f"(总排名No.{rec['overall_rank']}, 评分{rec['final_score']})"
            )

        lines.append("\n请基于以上信息，给出你的最优海克斯推荐和对局建议。")
        return "\n".join(lines)

    def _call_api(self, cfg, system_prompt, user_prompt):
        """调用 OpenAI 兼容 API"""
        url = f"{cfg['base_url']}/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {cfg['api_key']}",
        }
        payload = {
            'model': cfg['model'],
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'max_tokens': cfg['max_tokens'],
            'temperature': cfg['temperature'],
        }

        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                content = data['choices'][0]['message']['content']
                return {"success": True, "content": content}
            else:
                error_msg = f"HTTP {resp.status_code}"
                try:
                    err_data = resp.json()
                    if 'error' in err_data:
                        error_msg = err_data['error'].get('message', error_msg)
                except Exception:
                    pass
                return {"success": False, "content": "", "error": error_msg}

        except requests.exceptions.Timeout:
            return {"success": False, "content": "", "error": "请求超时（30秒）"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "content": "", "error": "网络连接失败，请检查网络或代理设置"}
        except Exception as e:
            return {"success": False, "content": "", "error": str(e)}
