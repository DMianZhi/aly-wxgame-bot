#!/usr/bin/env python
"""离线自检: claim_reward（奖励领取）—— 零消耗，不碰游戏窗口。

夹具(2026-10-10 实探真帧, 812x1518):
    HOME = "_rw3_step0_home.png"     首页(顶栏三图标带红点)
    PANEL = "_rw6_rw_panel.png"      奖励面板(6 行全橙可领)
    CLAIMED = "_rw7_after_claim.png" 领取后的面板(6 行全灰)

覆盖:
    ① 入口定位: rw_entry 在首页命中 (393,225)±8
    ② 可领检测: rw_claim 在奖励面板 find_all = 6 行, 第一行 (700,386)±8
    ③ 领完状态: 已领面板上 rw_claim **不得**命中(天然不可再领)
    ④ 无可领路径: run() 在已领面板上 → 不点领取、留证收工(不算失败)
    ⑤ dry 零点击零写盘; ⑥ 并发锁互斥

用法:
    uv run python tools/selftest/claim_reward_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from wb.selftest_kit import FakeRect  # noqa: E402
from tools.cases import claim_reward as cr  # noqa: E402

HOME = "_rw3_step0_home.png"
PANEL = "_rw6_rw_panel.png"
CLAIMED = "_rw7_after_claim.png"

C_ENTRY = (393, 225)                # rw_entry 命中中心(实测 1.000 @ 362,188 + 62/2,74/2)
C_CLAIM1 = (700, 386)               # 第 1 行领取按钮(实测)


def _frame(name: str, dry: bool = True) -> kit.Screen:
    img = cv2.imread(str(SHOTS_DIR / name))
    assert img is not None, f"缺夹具 {name}"
    h, w = img.shape[:2]
    sc = kit.Screen(FakeRect(0, 0, w, h), th=cr.TH, dry=dry, prefix="rw_")
    import wb.bot as _bot
    _bot.grab_window = lambda rect, _i=img: _i
    return sc


def case_entry(rp):
    """① 入口定位。"""
    sc = _frame(HOME)
    e = sc.find(cr.ENTRY_TPL)
    good = e is not None and abs(e[0] - C_ENTRY[0]) <= 8 and abs(e[1] - C_ENTRY[1]) <= 8
    return good, f"奖励图标={e and (e[0], e[1])} (期望 {C_ENTRY}±8)"


def case_rows(rp):
    """② 可领检测: 6 行, 第一行位置。"""
    sc = _frame(PANEL)
    hits = sc.find_all(cr.CLAIM_TPL, max_hits=8)
    ok1 = len(hits) == 6
    ok2 = (abs(hits[0][0] - C_CLAIM1[0]) <= 8 and abs(hits[0][1] - C_CLAIM1[1]) <= 8) if hits else False
    return ok1 and ok2, f"可领行={len(hits)}(期望 6) 第一行={hits and (hits[0][0], hits[0][1])}"


def case_claimed(rp):
    """③ 领完状态: 不可再命中。"""
    sc = _frame(CLAIMED)
    hits = sc.find_all(cr.CLAIM_TPL)
    return not hits, f"已领面板命中={len(hits)}(期望 0)"


def case_nothing(rp):
    """④ 无可领路径: 面板已开但无可领 → 不点领取, 留证收工(False)。"""
    sc = _frame(CLAIMED, dry=False)
    ok = cr._claim_in_panel(sc)
    clicks = list(rp.real_clicks)
    claim_clicks = [c for c in clicks if 600 <= c[0] <= 800 and 300 <= c[1] <= 1300]
    shots = str(rp.shots)
    good = "rw_nothing" in shots and not claim_clicks
    return good and (ok is False), (f"run={ok} 领取点击={claim_clicks}(期望空) "
                                    f"写盘含 rw_nothing={'rw_nothing' in shots}")


def case_dry(rp):
    """⑤ dry: 零点击零写盘。"""
    sc = _frame(HOME)
    sc2 = kit.Screen(sc.rect, th=cr.TH, dry=True, prefix="rw_")
    import wb.bot as _bot
    img = cv2.imread(str(SHOTS_DIR / HOME))
    _bot.grab_window = lambda rect, _i=img: _i
    ok = cr.run(sc2, kit.Args(dry=True))
    return ok and not rp.real_clicks and not rp.shots, \
        f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(_rp):
    """⑥ 并发锁互斥。"""
    name = "claim_reward_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("①入口定位(顶栏奖励图标)", [HOME], case_entry),
    ("②可领检测(6 行, 首行位置)", [PANEL], case_rows),
    ("③领完状态不可再命中", [CLAIMED], case_claimed),
    ("④无可领路径(留证收工不算失败)", [CLAIMED], case_nothing),
    ("⑤dry 零点击零写盘", [HOME], case_dry),
    ("⑥并发锁互斥", [HOME], case_lock),
]


def ensure_fixtures() -> bool:
    need = [HOME, PANEL, CLAIMED]
    missing = [f for f in need if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具: {missing}")
        return False
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("claim_reward 离线自检（入口/可领/已领/无可领路径）", SCENES)
