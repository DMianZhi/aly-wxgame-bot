"""从虚空裂隙页截图裁剪按钮模板。

产出: templates/rift_*.png + shots/rift_crops_montage.png + shots/rift_crops.csv
用法: uv run python tools/crop/crop_rift.py [截图文件名(可选,默认最新snap)]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb.croplab import run_crop  # noqa: E402

# name -> (x, y, w, h, label)  基于 845x1521 截图; 全句/图标避开流光与 NEW 角标
CROPS = {
    "rift_challenge": (35, 660, 590, 62,  "先锋挑战(大卡全句)"),
    "rift_rank":      (588, 648, 66, 50,  "先锋榜(金色奖杯)"),
    "rift_chest":     (108, 1084, 178, 46, "开启宝箱(全句)"),
    "rift_crush":     (566, 1066, 190, 50, "虚空讨伐(全句)"),
    "rift_module":    (88, 1334, 80, 48,   "超维模块(六边块)"),
    "rift_keyforge":  (106, 1434, 62, 48,  "秘钥工坊(钥匙图标)"),
    "rift_market":    (268, 1434, 56, 40,  "异度集市(购物篮)"),
}

if __name__ == "__main__":
    run_crop(CROPS, tag="rift", shot="snap_20261006_184910.png")
