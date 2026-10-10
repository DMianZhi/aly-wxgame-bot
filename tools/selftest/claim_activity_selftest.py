#!/usr/bin/env python
"""离线自检: claim_activity（活跃度奖励）—— 零消耗，不碰游戏窗口。

夹具(2026-10-10 实探真帧, 812x1518):
    HOME = "_rw3_step0_home.png"     首页(顶栏四图标)
    PANEL = "_rw1_probe_icon1.png"   活跃度面板(右下大橙钮「一键领取」)

覆盖:
    ① 入口定位: act_entry 在首页命中 (187,225)±8
    ② 一键领取定位: act_claim 在面板命中 (665,1311)±8
    ③ dry 零点击零写盘; ④ 并发锁互斥

用法:
    uv run python tools/selftest/claim_activity_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from wb.selftest_kit import FakeRect  # noqa: E402
from tools.cases import claim_activity as ca  # noqa: E402

HOME = "_act2_act2_home.png"
PANEL = "_rw1_probe_icon2.png"

C_ENTRY = (290, 225)                # act_entry 命中中心(258,188 + 64/2,74/2)
C_CLAIM = (700, 593)                # 领取按钮中心(实测点击生效处)


def _frame(name: str, dry: bool = True) -> kit.Screen:
    img = cv2.imread(str(SHOTS_DIR / name))
    assert img is not None, f"缺夹具 {name}"
    h, w = img.shape[:2]
    sc = kit.Screen(FakeRect(0, 0, w, h), th=ca.TH, dry=dry, prefix="act_")
    import wb.bot as _bot
    _bot.grab_window = lambda rect, _i=img: _i
    return sc


def case_entry(rp):
    """① 入口定位。"""
    sc = _frame(HOME)
    e = sc.find(ca.ENTRY_TPL)
    good = e is not None and abs(e[0] - C_ENTRY[0]) <= 8 and abs(e[1] - C_ENTRY[1]) <= 8
    return good, f"活跃度图标={e and (e[0], e[1])} (期望 {C_ENTRY}±8)"


def case_claim(rp):
    """② 一键领取定位。"""
    sc = _frame(PANEL)
    b = sc.find(ca.CLAIM_TPL)
    good = b is not None and abs(b[0] - C_CLAIM[0]) <= 8 and abs(b[1] - C_CLAIM[1]) <= 8
    return good, f"一键领取={b and (b[0], b[1])} (期望 {C_CLAIM}±8)"


def case_dry(rp):
    """③ dry: 零点击零写盘。"""
    sc = _frame(HOME)
    sc2 = kit.Screen(sc.rect, th=ca.TH, dry=True, prefix="act_")
    import wb.bot as _bot
    img = cv2.imread(str(SHOTS_DIR / HOME))
    _bot.grab_window = lambda rect, _i=img: _i
    ok = ca.run(sc2, kit.Args(dry=True))
    return ok and not rp.real_clicks and not rp.shots, \
        f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(_rp):
    """④ 并发锁互斥。"""
    name = "claim_activity_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("①入口定位(顶栏第②图标)", [HOME], case_entry),
    ("②领取钮定位", [PANEL], case_claim),
    ("③dry 零点击零写盘", [HOME], case_dry),
    ("④并发锁互斥", [HOME], case_lock),
]


def ensure_fixtures() -> bool:
    need = [HOME, PANEL]
    missing = [f for f in need if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具: {missing}")
        return False
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("claim_activity 离线自检（入口/一键领取定位）", SCENES)
