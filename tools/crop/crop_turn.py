"""用例: 寻宝页「转盘」tab 模板裁剪 (转盘: 12 格轮盘 + 中心免费/付费键)。

用法:
    uv run python tools/crop/crop_turn.py
产出:
    templates/turn_daily.png     中心「每日首次免费」键(免费态)
    templates/turn_paid.png      中心「购买 💎30」键(冷却态 —— 只用于识别, 永不点击)
    templates/turn_refresh.png   「立即刷新」键(转盘页标志)
    templates/turn_tab.png       底部「转盘」页签(未选中态, 从寻宝页裁)
    shots/turn*_crops.csv / *_montage.png

坐标基于 **812x1518 实测截图**(当前客户区真实画布): 游戏画布按高度等比渲染、宽度居中裁切,
812 客户区下的画布与模板基准 845x1521 同尺度(仅水平少露 15px), 故实测坐标可直接当基准坐标用。

⚠ 中心键两种形态必须**分别**裁剪且**只认免费态**:
  免费态「每日首次免费」/ 冷却态「购买 💎30」——背景金菱形一模一样, 靠**文字**区分;
  误点冷却态会白花 30 钻石。所以 turn_daily 裁得紧(只含文字), 并另裁 turn_paid 用于识别+护栏。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

from wb.croplab import run_crop  # noqa: E402

SHOT_TURN = "_rec_turn_page.png"        # 转盘页·免费态(未抽过)
SHOT_PAID = "_rec_turn_page_paid.png"   # 转盘页·冷却态(免费已用 → 中心变「购买💎30」)
SHOT_TREA = "_rec_treasure_page.png"    # 寻宝页(取底部未选中的「转盘」页签)

# 中心键: 两种形态同一坐标, 裁紧到文字
CENTER = (325, 776, 175, 46)
REFRESH = (630, 1268, 124, 52)
TAB = (210, 1398, 72, 84)


def main() -> int:
    weak = 0
    weak += run_crop(
        {"turn_daily": (*CENTER, "中心键·每日首次免费(免费态)"),
         "turn_refresh": (*REFRESH, "「立即刷新」键(转盘页标志)")},
        tag="turn", shot=SHOT_TURN, reuse=["nav_treasure"],
    )
    weak += run_crop(
        {"turn_paid": (*CENTER, "中心键·购买💎30(冷却态, 仅识别不点)")},
        tag="turn_paid", shot=SHOT_PAID, reuse=["turn_refresh"],
    )
    weak += run_crop(
        {"turn_tab": (*TAB, "底部「转盘」页签(未选中态)")},
        tag="turn_tab", shot=SHOT_TREA, reuse=["nav_treasure"],
    )
    print(f"=== 薄弱模板合计 {weak} ===")
    return weak


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
