"""用例: 寻宝页「兑换」模板裁剪 (兑换页: 星辉商店 + 每日免费「四角金币」)。

用法:
    uv run python tools/crop/crop_exchange.py
产出:
    templates/ex_coin.png     红点四角金币(星辉)本体 —— 裁到红点之外
    templates/ex_coin_v2.png  四角金币 + 红点整体(红点在时更稳; 两者命中任一即可)
    templates/ex_shoptext.png 「每周一0点重置星辉商店兑换次数」= 兑换页标志
    templates/ex_tab.png      底部「兑换」页签(未选中态, 从寻宝页裁)
    shots/exchange*_crops.csv / *_montage.png

坐标基于 812x1518 实测截图(同 845x1521 基准尺度)。

⚠ 红点会随「已领」消失, 所以金币模板必须给两版:
   v1 只含金币本体(红点没了也认), v2 含红点(红点在时更独特)。`_template_variants` 会自动都试。
⚠ 底栏红点位置会变(转盘红点=免费次数可用, 领完即消失) → 页签模板一律裁到 x<=434 避开红点。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

from wb.croplab import run_crop  # noqa: E402

SHOT_EX = "_rec_exchange_page.png"      # 兑换页·红点四角金币在场(未领)
SHOT_TREA = "_rec_treasure_page.png"    # 寻宝页(取未选中的「兑换」页签)

COIN = (405, 452, 58, 68)          # 金币六边形本体(红点 x>=465, 已避开)
COIN_V2 = (400, 425, 105, 100)     # 金币 + 红点整体
SHOPTEXT = (28, 748, 505, 30)      # 「每周一0点重置星辉商店兑换次数」
TAB = (360, 1402, 74, 92)          # 底部「兑换」页签(未选中态; 红点 x>=440 已避开)


def main() -> int:
    weak = 0
    weak += run_crop(
        {"ex_coin": (*COIN, "红点四角金币(星辉)本体"),
         "ex_coin_v2": (*COIN_V2, "四角金币+红点整体"),
         "ex_shoptext": (*SHOPTEXT, "兑换页标志文字")},
        tag="exchange", shot=SHOT_EX, reuse=["nav_treasure", "treasure_help"],
    )
    weak += run_crop(
        {"ex_tab": (*TAB, "底部「兑换」页签(未选中态)")},
        tag="exchange_tab", shot=SHOT_TREA, reuse=["nav_treasure"],
    )
    print(f"=== 薄弱模板合计 {weak} ===")
    return weak


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
