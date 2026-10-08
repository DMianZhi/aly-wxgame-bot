"""用例: 裁剪闯关模式页按钮模板 (10 张)。

校准源: snap_20261006_160202.png 闯关页
用法: uv run python tools/crop/crop_stage.py
产出: templates/stage_*.png + shots/stage_crops_montage.png + shots/stage_crops.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb.croplab import run_crop  # noqa: E402

SHOT = "snap_20261006_160202.png"

# name -> (x, y, w, h, label)  基于 845x1521 截图
CROPS = {
    "stage_back":        (660, 1420, 180, 88, "返回"),
    "stage_warehouse":   (46, 1438, 118, 66, "仓库"),
    "stage_boss":        (252, 1422, 185, 64, "BOSS模式"),
    "stage_event_lv":    (432, 1424, 218, 62, "活动关卡"),
    "stage_sweep":       (12, 1300, 190, 76, "快速扫荡"),
    "stage_boss_island": (272, 1028, 88, 58, "BOSS岛(骷髅立方)"),
    "stage_deep":        (658, 416, 152, 62, "深空巡航(入口横幅)"),
    "stage_stair":       (622, 555, 220, 84, "逐星长阶(入口横幅)"),
    "stage_rift":        (624, 702, 192, 66, "虚空裂隙(入口横幅)"),
    "stage_diff_hero":   (600, 295, 240, 72, "英雄难度(骷髅图标)"),
}

# 尝试跨页复用的模板名（校验得分 >= REUSE_MIN 视为可复用）
REUSE = []


if __name__ == "__main__":
    raise SystemExit(run_crop(CROPS, tag="stage", shot=SHOT, reuse=REUSE))
