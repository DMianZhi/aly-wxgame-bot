#!/usr/bin/env python
"""离线自检: free_turn（转盘·每日首次免费）判定逻辑回放 —— 零消耗，不碰游戏窗口。

做法: 实测帧当「每步画面」，点一下就切到下一帧（点击驱动状态机）；
      wb.bot 的取帧/点击、cv2 落盘、time.sleep 全部换成替身 →
      用例自身分支（导航、已在页、免费/冷却两形态护栏、抽奖→领取、dry、并发锁）全跑一遍。

用法:
    uv run python tools/selftest/free_turn_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st  # noqa: E402
from tools.cases import free_turn as ft  # noqa: E402

# 夹具（实测帧）—— 缺哪个该场景就 SKIP，不计入分母
F = {
    "home": "_rec_home_page.png",          # 首页
    "treasure": "_rec_treasure_page.png",  # 寻宝页
    "free": "_rec_turn_page.png",          # 转盘页·中心键=每日首次免费
    "paid": "_rec_turn_page_paid.png",     # 转盘页·中心键=购买💎30（冷却）
    "claim": "_rec_turn_claim.png",        # 「恭喜获得」+ 领取
}


def sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, dry=dry, prefix="turn_")


def case_goto(rp):
    ok = ft.goto_turn_page(sc())
    good = ok and st.check_clicks("导航", rp.real_clicks, [(685, 218), (246, 1440)])
    return good, f"导航 ok={ok} 点击={rp.real_clicks}"


def case_already(rp):
    """已在转盘页 → 直接返回，一次都不点。"""
    ok = ft.goto_turn_page(sc())
    good = ok and not rp.real_clicks
    return good, f"已在转盘页直接返回={ok} 点击={rp.real_clicks}(期望空)"


def case_turn_free(rp):
    ok = ft.one_turn(sc())
    got = rp.real_clicks
    good = ok and len(got) == 2 and got[0][1] > 700 and got[1][1] > 1200
    return good, f"ok={ok} 点击(中心键→领取)={got}"


def case_turn_paid_guard(rp):
    """冷却态：必须一次都不点（点错白花 30 钻石）。"""
    ok = ft.one_turn(sc())
    good = (ok is False) and not rp.real_clicks
    return good, f"返回={ok}(期望 False) 点击={rp.real_clicks}(期望空 → 没白花钻石)"


def case_turn_dry(rp):
    ok = ft.one_turn(sc(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry 返回={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_claim(rp):
    ok = ft.claim_if_any(sc())
    got = rp.real_clicks
    good = ok and len(got) == 1 and got[0][1] > 1200
    return good, f"点到领取={ok} 点击={got}"


def case_lock(rp):
    """并发锁：第二个实例拿不到锁；释放后可再拿。"""
    name = "free_turn_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


if __name__ == "__main__":
    st.run_one("free_turn 离线自检（点击驱动状态机，不消耗次数）", [
        ("首页→寻宝→转盘 导航", [F["home"], F["treasure"], F["free"]], case_goto),
        ("已在转盘页不重复点", [F["free"]], case_already),
        ("免费态→抽奖→领取", [F["free"], F["claim"], F["paid"]], case_turn_free),
        ("冷却态护栏（不许点）", [F["paid"]], case_turn_paid_guard),
        ("dry 只出计划且零副作用", [F["free"]], case_turn_dry),
        ("恭喜获得→点领取", [F["claim"], F["paid"]], case_claim),
        ("并发锁互斥", [F["free"]], case_lock),
    ])
