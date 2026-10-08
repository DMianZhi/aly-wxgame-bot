"""配置加载：config.toml -> BotConfig。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "templates"
SHOTS_DIR = APP_DIR / "shots"


@dataclass
class BotConfig:
    title_keyword: str
    process_name: str
    trim_top: int
    trim_rest: int
    threshold: float
    jitter_px: int
    delay_min: float
    delay_max: float
    step_timeout: float
    retry_interval: float
    dry_run: bool


def load(path: Path | None = None) -> BotConfig:
    p = path or (APP_DIR / "config.toml")
    with open(p, "rb") as f:
        d = tomllib.load(f)
    w = d["window"]
    b = d["bot"]
    return BotConfig(
        title_keyword=str(w["title_keyword"]),
        process_name=str(w.get("process_name", "")),
        trim_top=int(w["trim_top"]),
        trim_rest=int(w["trim_rest"]),
        threshold=float(b["threshold"]),
        jitter_px=int(b["jitter_px"]),
        delay_min=float(b["delay_min"]),
        delay_max=float(b["delay_max"]),
        step_timeout=float(b["step_timeout"]),
        retry_interval=float(b["retry_interval"]),
        dry_run=bool(b["dry_run"]),
    )


def TEMPLATE_PATH(name: str) -> Path:
    """模板图片路径: templates/<name>.png"""
    return TEMPLATES_DIR / f"{name}.png"


# 全局配置单例：导入即加载，启动时尽早暴露配置错误
CONF = load()
