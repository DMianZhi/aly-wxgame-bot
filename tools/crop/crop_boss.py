"""用例: 裁剪 BOSS 模式(副本选择)页面按钮模板 -> templates/。

源截图: shots/snap_20261006_163018.png (845x1521)
坐标基于该截图实测; 超限模式避开右上红点; 四块空间站铭牌须过区分度矩阵校验。

用法:
    uv run python tools/crop/crop_boss.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb.croplab import run_crop  # noqa: E402

SHOT = "snap_20261006_163018.png"

# name -> (x, y, w, h, label)
CROPS = {
    "boss_hyper":       (330, 1408, 220, 52, "超限模式(金字)"),
    "boss_stn_drago":   (170, 597, 205, 36, "天龙座空间站(装甲)"),
    "boss_stn_cygnus":  (563, 767, 220, 36, "白鸟座空间站(副武器)"),
    "boss_stn_pegasus": (170, 1080, 205, 36, "天马座空间站(战机)"),
    "boss_stn_andro":   (563, 1232, 220, 36, "仙女座空间站(僚机)"),
    "boss_warehouse":   (60, 1440, 130, 60, "仓库(本页样式)"),
}

# 从其他页面复用的模板（仅校验本页可得分，不落盘）
REUSE = ["stage_back"]

# 需要做 N×N 区分度矩阵校验的模板（防串台）
STATIONS = [n for n in CROPS if n.startswith("boss_stn_")]


def main() -> int:
    return run_crop(
        CROPS,
        tag="boss",
        shot=SHOT,
        stations=STATIONS,
        reuse=REUSE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
