"""用例: 寻宝页模板裁剪 (寻宝入口页: 顶部大转盘 + 装备宝箱/高级装备宝箱两张卡)。

用法:
    uv run python tools/crop/crop_treasure.py
产出:
    templates/treasure_*.png
    shots/treasure_crops.csv / shots/treasure_crops_montage.png

坐标基于 **812x1518 实测截图**(shots/_rec_treasure_page.png, 即当前客户区真实画布)。
说明: 本页模板按实测画布坐标裁剪 —— 游戏画布按高度等比渲染、宽度居中裁切,
      812 客户区下的画布与模板基准 845x1521 **同尺度**(仅水平少露 15px),
      所以实测坐标与基准坐标可以 1:1 混用; 运行期由 match_adaptive 的原像素候选命中。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

from wb.croplab import run_crop  # noqa: E402

SHOT = "_rec_treasure_page.png"  # 实测校准源(寻宝页)

# name -> (x, y, w, h, 中文说明)
# 免费广告 icon 裁剪要点: **整条避开左上角红色「!」角标**——实测角标占 x100..133 / y1190..1223,
# 而图标本体是 x69..116 / y1222..1265, 角标瓞在图标右上角上。所以从 y=1226 起裁:
# 丢掉图标顶部 4px(不影响辨认), 完全不含角标 → 用户用掉后角标消失也不影响匹配。
CROPS = {
    "treasure_help": (696, 292, 96, 34, "「说明」按钮(寻宝页标志)"),
    "treasure_tab":  (55, 1406, 95, 44, "底部「寻宝」页签(高亮态)"),
    "treasure_free": (69, 1226, 48, 40, "宝箱·免费广告icon(胶片+▶, 不含红角标)"),
}


def main() -> int:
    return run_crop(
        CROPS,
        tag="treasure",
        shot=SHOT,
        reuse=["nav_treasure", "nav_home"],  # 顶部导航在本页仍可见
    )


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
