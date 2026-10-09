#!/usr/bin/env python
"""用例: 「战队 BOSS 征讨」模板裁剪（战队页入口 / 征讨页 / 结算页）。

用法:
    uv run python tools/crop/crop_guildboss.py
产出:
    templates/gb_entry.png  战队页「BOSS征讨」卡标题 (避开卡片右上红点与「挑战中」状态字)
    templates/gb_max.png    征讨页「奖励等级 MAX」行 (⭐ 用例前提判据: 只有真是 MAX 才命中)
    templates/gb_go.png     征讨页底部「出击」大键 (也当征讨页标志)
    templates/gb_done.png   结算页「挑战完成」大标题 (局内退出判据)
    templates/gb_ok.png     结算页「确定」键 (点它回征讨页)
    shots/guildboss*_crops.csv / *_montage.png

坐标基于 814x1507 实测帧（同 845x1521 基准尺度，进代码前用 client_to_ref 归一）。

⚠ 不另裁的复用件:
   * 恭喜获得弹层的「领取」键 = templates/claim_btn.png (实测 0.976)，与战队捐献同款；
   * 征讨页右下「返回」= wc_res_back (0.992) / 战队页「返回」= ral_back (0.930)。

⚠ 50M 奖励槽的**三态判据不用模板，用颜色像素**（实测，见 guild_boss.py::reward_state）:
       未领取 = 槽右上角红点(r>190,g<80,b<80) 65 像素        → 可领，点它
       已领取 = 图标被绿勾盖住(g>r+40,g>b+40) 459 像素       → 今日已领完，收工
       都没有 = 伤害未达 50M                                 → 继续出击
   模板判三态不可行: 领完的图标被绿勾覆盖，未领取态裁的模板必然退化。

⚠ 出击键必须按颜色量 bbox 再裁，不能目测（沿用战队捐献的教训）:
   橙黄渐变 (r>210,g 130..215,b<110) 实测 bbox=(263,1345,312,57) 中心=(420,1372)；
   结算页「确定」同法实测 bbox=(282,1353,280,87) 中心=(422,1394)。

⚠ 旧模板 gb 前缀没有冲突；但**橙色大键互相很像**这事在本页已踩到:
   sel_go 在「出击」上 0.923、boss_flash_go 0.866、fdlg_go 0.839，
   反过来 wc_settle_go 会在「奖励等级 100%」进度条上 0.970 假命中 →
   gb_ok 必须核验它不会在征讨页假命中（见 cross_check 与自检）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb.croplab import SHOTS_DIR, TEMPLATES_DIR, _match_one, run_crop  # noqa: E402

GUILD = "_expl_expl_guildpage.png"      # 战队页 (BOSS征讨 卡片在中间偏上)
PAGE = "_expl_expl_after_ok.png"        # 征讨页·未领取态 (今日伤害 191.5M + 三槽红点)
DONE = "_expl_expl_w6.png"              # 结算页「挑战完成」+ 确定

# (x, y, w, h) —— 814x1507 实测帧坐标
ENTRY = (410, 578, 198, 46)             # 「BOSS征讨」白字 + 紫底(状态字「挑战中」在 y>=624，不含)
MAXROW = (50, 375, 212, 32)             # 「奖励等级 MAX」(默认号旁边的礼盒 icon 也含在内)
GO = (300, 1348, 240, 62)               # 「出击」键(橙块 bbox 内取含字区)
DONE_TITLE = (165, 252, 490, 106)       # 「挑战完成」金色大标题
OK_BTN = (290, 1358, 265, 78)           # 结算页「确定」键

# 跨页核验: (模板, 帧, 说明, 期望命中[, 负样本上限])
# 默认负样本上限 NEG_LIMIT；gb_max 例外: 结算页有「MAX 100%」进度条，实测 0.79 假命中。
# 但用例里 gb_max 只在 **已确认是征讨页**(gb_go 命中) 后才查、且阈值抬到 0.90 → 0.79 无害。
CROSS = [
    ("gb_go",     GUILD, "战队页不该有出击键", False),
    ("gb_ok",     PAGE,  "征讨页不该有结算页确定键(必躲开 100% 进度条)", False),
    ("gb_done",   PAGE,  "征讨页不该有挑战完成标题", False),
    ("gb_max",    DONE,  "结算页不该有奖励等级行(有 MAX 100% 进度条, 容忍到 0.90)", False, 0.90),
    ("gb_entry",  PAGE,  "征讨页不该有战队页入口卡标题", False),
    ("gb_go",     PAGE,  "征讨页标志(必须命中)", True),
    ("gb_done",   DONE,  "结算页标志(必须命中)", True),
]
NEG_LIMIT = 0.70                        # 负样本上限(默认)


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
        print(f"[{'ok  ' if ok else '!!  '}] {name:10s} vs {shot:26s} {score:.4f} "
              f"center=({cx},{cy}) ({note})")
    for name, shot in (("claim_btn", "_expl_expl_claim1.png"),
                       ("wc_res_back", PAGE), ("ral_back", GUILD)):
        img = cv2.imread(str(SHOTS_DIR / shot))
        if img is None:
            continue
        score, cx, cy = _match_one(img, TEMPLATES_DIR / f"{name}.png")
        print(f"[info] {name:12s} vs {shot:26s} {score:.4f} center=({cx},{cy}) (复用件)")
    print("[info] 50M 槽三态用颜色像素判(红点/绿勾), 不做模板核验")
    return bad


def main() -> int:
    weak = 0
    weak += run_crop(
        {"gb_entry": (*ENTRY, "战队页「BOSS征讨」卡标题(避开红点/状态字)")},
        tag="guildboss_guild", shot=GUILD, reuse=["ral_back", "nav_home"],
    )
    weak += run_crop(
        {"gb_max": (*MAXROW, "征讨页「奖励等级 MAX」(用例前提判据)"),
         "gb_go": (*GO, "征讨页底部「出击」大键(也是页面标志)")},
        tag="guildboss_page", shot=PAGE,
        stations=["gb_max", "gb_go"], reuse=["wc_res_back", "boss_warehouse"],
    )
    weak += run_crop(
        {"gb_done": (*DONE_TITLE, "结算页「挑战完成」大标题(局内退出判据)"),
         "gb_ok": (*OK_BTN, "结算页「确定」键")},
        tag="guildboss_done", shot=DONE,
        # 不做 stations 区分度矩阵: gb_done(490x106) 比 gb_ok 的 zone 还大，
        # cv2.matchTemplate 要求 区域>=模板 → 直接 assert 炸(两个尺寸差太大的模板不能互查)。
        # 这两张的互斥改由 cross_check + 自检覆盖。
        reuse=["wc_settle_go"],
    )
    bad = cross_check()
    print(f"=== 薄弱模板 {weak} / 跨页核验失败 {bad} ===")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
