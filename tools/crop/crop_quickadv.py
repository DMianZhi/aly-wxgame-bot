#!/usr/bin/env python
"""用例: 「快速进阶」模板裁剪（背包入口 / 列表页 / 详情页 / 数量面板 / 选料面板 / 二次确认）。

用法:
    uv run python tools/crop/crop_quickadv.py
产出:
    templates/qa_entry.png      背包页「快速进阶」绿键 (入口)
    templates/qa_title.png      列表页「选择快速进阶装备」标题 (列表页标志)
    templates/qa_tab_*.png      列表页四个页签: 战机 / 装甲 / 副武器 / 僚机
    templates/qa_dtitle.png     详情页标题「? 快速进阶」(含 ? 图标 → 与列表页标题区分)
    templates/qa_adj.png        详情页「调整数量」绿键
    templates/qa_pickexp.png    详情页「选择经验」绿键
    templates/qa_go.png         详情页「快速进阶」黄键
    templates/qa_ok.png         数量面板「确定」黄键
    templates/qa_mtitle.png     选料面板标题「选择材料」(选料面板标志)
    templates/qa_auto.png       选料面板「自动选择」蓝键
    templates/qa_mok.png        选料面板「确认」蓝键
    templates/qa_confirm.png    二次确认弹窗「确认」绿键
    shots/quickadv*_crops.csv / *_montage.png

坐标基于 814x1507 实测帧（同 845x1521 基准尺度，进代码前用 client_to_ref 归一）。

⚠ 不另裁的复用件（cross_check 里打印分数）:
   * 关闭 X（列表页/详情页/选料面板右上）= templates/sweep_close.png 实测 0.993；
   * 「恭喜获得」的「领取」= templates/claim_btn.png。

⚠ 数量面板的 **+ / − 按钮不裁模板，用颜色像素判状态**（实测）:
       + / − 可用(蓝)  = b>140 且 b-r>60
       + / − 禁用(灰)  = |r-g|<14 且 |g-b|<14 且 85<r<150
   实测要点（决定整条用例怎么写）:
       1) 「−」点到底停在 0，**不回绕**；
       2) 「+」封顶在持有数（绿 5 时点 4 次仍是 5）；
       3) 计数 Pill 上的数字不用 OCR —— 直接数「点几下 − 才变灰」即得数量。

⚠ 四列槽位实测: + 在 y=554、− 在 y=688，x 中心 114/211/307/403 (间距 ~96)。
   材料图标在两者之间 (y 578..664)，**绿装看图标边框色**（绿 5 的格子边框亮绿，
   旁边 4 号格子是白/灰边框、只是图面偏绿 —— 别被图面骗了）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb.croplab import SHOTS_DIR, TEMPLATES_DIR, _match_one, run_crop  # noqa: E402

BAG = "_qa_s2_bag.png"          # 背包页 (底部 快速进阶/经验合成/出售)
LIST = "_qa_s3_advance.png"     # 列表页「选择快速进阶装备」+ 四页签
DETAIL = "_qa_s4_row6.png"      # 详情页 (主装备 + 消耗装备/资源 + 快速进阶)
QTY = "_qa_s5_qty.png"          # 数量面板 (± 展开 + 确定)
MAT = "_qa_s9_exp.png"          # 选料面板「选择材料」(自动选择/确认)
DLG = "_qa_s12_done.png"        # 二次确认弹窗 (取消/确认)
RES = "_qa_s13_result.png"      # 「恭喜获得」结果页 (领取)

# (x, y, w, h) —— 814x1507 实测帧坐标
ENTRY = (378, 1283, 128, 58)    # 「快速进阶」绿键
TITLE = (268, 210, 290, 48)     # 「选择快速进阶装备」
TABS = {                        # 四个页签(只取字, 避开下方高亮条)
    "plane": (100, 1276, 84, 46),
    "armor": (248, 1276, 84, 46),
    "sub": (393, 1276, 84, 46),
    "wing": (543, 1276, 84, 46),
}
DTITLE = (308, 212, 246, 46)    # 「? 快速进阶」(含 ? 图标)
ADJ = (673, 579, 76, 78)        # 「调整数量」绿键
PICKEXP = (678, 801, 78, 73)    # 「选择经验」绿键
GO = (312, 1247, 206, 70)       # 「快速进阶」黄键
OK = (673, 579, 76, 78)         # 「确定」黄键 (与 ADJ 同位置)
MTITLE = (328, 212, 155, 46)    # 「选择材料」
AUTO = (647, 1197, 135, 60)     # 「自动选择」蓝键
MOK = (309, 1274, 197, 66)      # 「确认」蓝键
CONFIRM = (462, 866, 231, 72)   # 二次确认弹窗「确认」绿键

# 跨页核验: (模板, 帧, 说明, 期望命中[, 负样本上限])
CROSS = [
    ("qa_entry", BAG, "背包页入口(必须命中)", True),
    ("qa_entry", LIST, "列表页不该有背包入口", False),
    ("qa_title", LIST, "列表页标志(必须命中)", True),
    ("qa_title", DETAIL, "详情页不该有列表页标题", False),
    ("qa_dtitle", DETAIL, "详情页标志(必须命中)", True),
    ("qa_dtitle", LIST, "列表页不该有详情页标题(含 ? 图标才算数)", False),
    ("qa_go", DETAIL, "详情页黄键(必须命中)", True),
    ("qa_ok", QTY, "数量面板确定键(必须命中)", True),
    ("qa_ok", DETAIL, "详情页不该有数量面板确定键", False),
    ("qa_adj", DETAIL, "详情页调整数量(必须命中)", True),
    # qa_adj(调整数量, 绿) 与 确定(黄) 同位置同形状、只差字色 → 实测互命中 0.789。
    # 用例里查它是靠 0.90 阈值 + 先确认 qa_dtitle(详情页) 命中, 0.789 不会误点,
    # 所以这里只要求 <0.85（不要求到默认 0.70）。
    ("qa_adj", QTY, "数量面板开着时调整数量已变确定(实测 0.789, 靠 0.90 阈值拦)", False, 0.85),
    ("qa_pickexp", DETAIL, "详情页选择经验(必须命中)", True),
    ("qa_mtitle", MAT, "选料面板标志(必须命中)", True),
    ("qa_auto", MAT, "选料面板自动选择(必须命中)", True),
    ("qa_mok", MAT, "选料面板确认(必须命中)", True),
    ("qa_confirm", DLG, "二次确认弹窗确认(必须命中)", True),
    ("qa_confirm", DETAIL, "详情页不该有二次确认弹窗的确认", False),
    ("qa_go", LIST, "列表页不该有进阶黄键(列表页没有黄键)", False),
]
NEG_LIMIT = 0.70


def cross_check() -> int:
    """跨页区分度核验: 打印关键分数, 返回失败数。"""
    print("--- 跨页核验 ---")
    bad = 0
    for name, shot, note, want_hit, *lim in CROSS:
        img = cv2.imread(str(SHOTS_DIR / shot))
        score, cx, cy = _match_one(img, TEMPLATES_DIR / f"{name}.png")
        cap = lim[0] if lim else NEG_LIMIT
        ok = (score >= 0.90) if want_hit else (score <= cap)
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else '!!  '}] {name:12s} vs {shot:22s} {score:.4f} "
              f"center=({cx},{cy}) ({note})")
    for name in ("sweep_close", "claim_btn", "bag_title", "wh_bag"):
        for shot in (LIST, RES):
            img = cv2.imread(str(SHOTS_DIR / shot))
            if img is None:
                continue
            score, cx, cy = _match_one(img, TEMPLATES_DIR / f"{name}.png")
            print(f"[info] {name:12s} vs {shot:22s} {score:.4f} center=({cx},{cy}) (复用件)")
        break
    print("[info] ± 按钮状态用颜色像素判(蓝=可用/灰=禁用), 不做模板核验")
    return bad


def main() -> int:
    weak = 0
    weak += run_crop(
        {"qa_entry": (*ENTRY, "背包页「快速进阶」绿键")},
        tag="quickadv_bag", shot=BAG, reuse=["bag_title", "wh_bag", "bag_exp_syn"],
    )
    weak += run_crop(
        {"qa_title": (*TITLE, "列表页「选择快速进阶装备」标题(页面标志)"),
         **{f"qa_tab_{k}": (*v, f"列表页页签 {k}") for k, v in TABS.items()}},
        tag="quickadv_list", shot=LIST,
        # 不做 stations 区分度矩阵: qa_title(290x48) 比页签 zone 大,
        # matchTemplate 要求区域>=模板 → 直接 assert 炸。互斥交给 cross_check + 自检。
        reuse=["sweep_close", "stage_btn"],
    )
    weak += run_crop(
        {"qa_dtitle": (*DTITLE, "详情页标题「? 快速进阶」"),
         "qa_adj": (*ADJ, "详情页「调整数量」绿键"),
         "qa_pickexp": (*PICKEXP, "详情页「选择经验」绿键"),
         "qa_go": (*GO, "详情页「快速进阶」黄键")},
        tag="quickadv_detail", shot=DETAIL,
        reuse=["adjust_btn"],
    )
    weak += run_crop(
        {"qa_ok": (*OK, "数量面板「确定」黄键")},
        tag="quickadv_qty", shot=QTY, reuse=["qa_adj"],    )
    weak += run_crop(
        {"qa_mtitle": (*MTITLE, "选料面板标题「选择材料」"),
         "qa_auto": (*AUTO, "选料面板「自动选择」"),
         "qa_mok": (*MOK, "选料面板「确认」")},
        tag="quickadv_mat", shot=MAT,
    )
    weak += run_crop(
        {"qa_confirm": (*CONFIRM, "二次确认弹窗「确认」绿键")},
        tag="quickadv_dlg", shot=DLG,
    )
    bad = cross_check()
    print(f"=== 薄弱模板 {weak} / 跨页核验失败 {bad} ===")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
