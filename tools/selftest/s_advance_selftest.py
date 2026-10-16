"""s_advance（快速进阶-S 装升蓝）离线自检 —— 列表页预筛判据的回归。

2026-10-16 用户一次实跑暴露的判据/坐标 bug（全部零消耗可复现）：
  ① S 徽标扫描区错用**材料格**列（LIST_AREA，基准 x 180~500），而 S 徽标贴在
     **主图格左上角**（基准 x≈65）→ 徽标整体在 ROI 之外，永远扫不到；
     日志里那条「列表页 y=275/276: S 行但无绿/白材料格」其实是材料格橙色被误当徽标。
  ② 白材料格还有一种「**大字牌**」（bbox 51x51、亮像素 area 仅 146~217）——
     牌面大部是深色底，mn>140 命中的只是亮缘/数字 → 被旧的 area>=250 + bbox<=48
     双重排除 → **白品质 S 装整行白丢**（用户原话：「第四行就是 S 白装啊」）。
  ③ s_rows 返回**徽标 y** 而非行中心 y（徽标在行顶，拿去点主图偏上 ~24px）。
 ④ 详情页「白材料槽」判据的取样带落在格子外（tile_rect 的格子实测在**上方 ~23px**）
    → 有白材料的槽也算 0.05 → 进了详情页立刻「本行已无绿/白材料 → 收手」。

夹具 = 2026-10-16 实跑时用户提供的 3 张页签真帧 + 1 张详情页真帧（存 shots/，不入库）；
缺夹具时本自检整体 SKIP（沿用 selftest_kit 的约定）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import selftest_kit as st  # noqa: E402
from tools.cases import s_advance as sa  # noqa: E402


class _Sc:
    """最小 Screen 替身：s_rows 只用到 w/h 与 grab()（不点击、不写盘）。"""

    def __init__(self, img):
        self.img = img
        self.w, self.h = img.shape[1], img.shape[0]

    def grab(self):
        return self.img


def _case(expect: list[int], label: str):
    def fn(rp):
        got = sa.s_rows(_Sc(rp.imgs[0]), None)
        return got == expect, f"页签「{label}」s_rows={got} 期望={expect}"
    return fn


def _case_detail(rp):
    """详情页材料槽判据(2026-10-16 用户实跑: 旧「数字牌中段 pill」取样带落在格子外
    → 有白材料的槽也全判无材料 → 刚进详情页就收手)。"""
    img = rp.imgs[0]
    g, w = sa.quality_cols(_Sc(img), img)
    return (g, w) == ([], [0]), f"详情页 quality_cols=(绿{g}, 白{w}) 期望=(绿[], 白[0])"


def _case_go(expect: bool, label: str):
    """详情页「快速进阶」黄键在场性(2026-10-16: 灰键=「当前指定消耗的装备已无法进阶」)。"""
    def fn(rp):
        img = rp.imgs[0]
        s = sa.go_ready(_Sc(img), img)
        return (s >= sa.GO_YELLOW_MIN) == expect, (
            f"{label}: 黄像素占比 {s:.2f} (阈值 {sa.GO_YELLOW_MIN}) 期望"
            + ("可进阶" if expect else "灰键不可进阶"))
    return fn


TABS = [
    ("战机", "_sadv_user_tab_zhanji.png", [752],
     "仅第 4 行(白材料大字牌) —— 修复前返回 []"),
    ("副武器", "_sadv_user_tab_fuwuqi.png", [307, 462, 746, 909],
     "4 行(2 白 + 2 绿) —— 修复前 0 行且点不进详情页"),
    ("僚机", "_sadv_user_tab_liaoji.png", [302, 453, 616],
     "3 行(2 白 + 1 绿) —— 修复前 0 行"),
]

if __name__ == "__main__":
    st.run_one("s_advance 离线自检（列表页预筛 + 详情页判料，零消耗）",
               [(f"页签「{lb}」{note}", [fr], _case(ex, lb))
                for lb, fr, ex, note in TABS]
               + [("详情页第 1 槽白材料判识", ["_sadv_user_detail.png"], _case_detail),
                  ("详情页「快速进阶」黄键在场→受得进阶", ["_sadv_user_detail.png"],
                   _case_go(True, "黄键源图")),
                  ("详情页灰键→判不可进阶(提前收手)", ["_sadv_user_detail2.png"],
                   _case_go(False, "灰键源图(当前指定消耗的装备已无法进阶)"))])
