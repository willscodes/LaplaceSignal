"""
laplace/config.py
配置管理模块 —— 使用 python-dotenv 从 .env 文件读取环境变量。

用法：
    from laplace.config import config
    print(config.OKX_API_KEY)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录（laplace/ 的上一级）
_ROOT = Path(__file__).resolve().parent.parent

# 优先加载项目根目录下的 .env；若不存在则静默跳过
load_dotenv(dotenv_path=_ROOT / ".env", override=False)


class Config:
    """全局配置，字段直接映射环境变量。

    访问方式：
        from laplace.config import config
        config.OKX_API_KEY
    """

    # ── OKX API 凭证 ──────────────────────────────────────────────
    OKX_API_KEY: str        = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET: str     = os.getenv("OKX_API_SECRET", "")
    OKX_API_PASSPHRASE: str = os.getenv("OKX_API_PASSPHRASE", "")

    # ── OKX REST 基础 URL ─────────────────────────────────────────
    OKX_BASE_URL: str       = os.getenv("OKX_BASE_URL", "https://www.okx.com")

    # ── Tavily 新闻搜索 ───────────────────────────────────────────
    TAVILY_KEY: str         = os.getenv("TAVILY_KEY", "")

    # ── Telegram 通知（可选）──────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str   = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── 运行模式 ──────────────────────────────────────────────────
    # "live"  → 实盘下单
    # "paper" → 仅记录信号，不下单
    RUN_MODE: str           = os.getenv("RUN_MODE", "paper")

    # ── 信号 / 权重存储路径 ───────────────────────────────────────
    SIGNALS_DIR: Path       = _ROOT / "signals"

    def __repr__(self) -> str:
        key_preview = self.OKX_API_KEY[:6] + "..." if self.OKX_API_KEY else "(unset)"
        return (
            f"Config(OKX_KEY={key_preview}, "
            f"RUN_MODE={self.RUN_MODE}, "
            f"SIGNALS_DIR={self.SIGNALS_DIR})"
        )


# 单例：整个应用共享同一个 Config 实例
config = Config()
