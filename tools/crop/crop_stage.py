"""用例: 裁剪闯关模式页按钮模板 (10 张)。

校准源: snap_20261006_160202.png 闯关页（845x1521 基准；另见下方 stage_stair 注）
用法: uv run python tools/crop/crop_stage.py
产出: templates/stage_*.png + shots/stage_crops_montage.png + shots/stage_crops.csv

⚠ stage_stair「逐星长阶」横幅**美术会轮换**（10-08 实测：旧「整横幅」模板在新美术上只
  0.589）→ 所以**只裁文字**（162x72，避开横幅边框与红点），实测在 10-06/10-08 三种美术上
  均 0.89+、实时 0.959、非闯关页 ≤0.6。源图为当次美术（10-08 用的是 snap_20261008_091133.png，
  原始 812x1518 → 需先拉伸到 845x1521 基准再按本表坐标裁，否则尺度差 4%）。
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
    # ⚠ 「快速扫荡」右侧紧贴**驾驶员头像**（玩家可换），旧版 190 宽把头像框进去了
    #    → 换头像后模板永远配不上（2026-10-09 实测只剩 0.897，卡在用例 0.90 门槛外，
    #    导航直接失败）。故只裁**按钮本体**（143x62，右边界停按钮面内）。
    #    实测: 本页 0.990、首页 0.672、星外探索弹窗 0.698 → 门槛 0.90 下余量充足。
    #    校准源为 snap_20261009_124742.png（810x1514，按 ref 845x1521 换算）。
    "stage_sweep":       (25, 1306, 143, 62, "快速扫荡(只裁按钮本体, 避开右侧头像)"),
    "stage_boss_island": (272, 1028, 88, 58, "BOSS岛(骷髅立方)"),
    "stage_deep":        (658, 416, 152, 62, "深空巡航(入口横幅)"),
    "stage_stair":       (648, 578, 162, 72, "逐星长阶(入口横幅·只裁文字)"),
    "stage_rift":        (624, 702, 192, 66, "虚空裂隙(入口横幅)"),
    "stage_diff_hero":   (600, 295, 240, 72, "英雄难度(骷髅图标)"),
}

# 尝试跨页复用的模板名（校验得分 >= REUSE_MIN 视为可复用）
REUSE = []


if __name__ == "__main__":
    raise SystemExit(run_crop(CROPS, tag="stage", shot=SHOT, reuse=REUSE))
