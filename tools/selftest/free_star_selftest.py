#!/usr/bin/env python
"""离线自检: free_star（兑换星辉）判定逻辑回放 —— 零消耗，不碰游戏窗口。

做法: 实测帧当「每步画面」，点一下就切到下一帧（点击驱动状态机）；
      wb.bot 的取帧/点击、cv2 落盘、time.sleep 全部换成替身 →
      用例自身分支（导航、已在页、金币→领取→校验、已领护栏、dry、并发锁）全跑一遍。

用法:
    uv run python tools/selftest/free_star_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st  # noqa: E402
from tools.cases import free_star as fs  # noqa: E402

# 夹具（实测帧）—— 缺哪个该场景就 SKIP，不计入分母
F = {
    "home": "_rec_home_page.png",              # 首页
    "treasure": "_rec_treasure_page.png",      # 寻宝页
    "free": "_rec_exchange_page.png",          # 兑换页·金币在场（星辉未领）
    "claim": "_rec_exchange_claim.png",        # 「恭喜获得 星辉」+ 领取
    "done": "_rec_exchange_claimed.png",       # 已领：金币+红点消失，仍在兑换页
}


def sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, dry=dry, prefix="ex_")


def case_goto(rp):
    ok = fs.goto_exchange_page(sc())
    got = rp.real_clicks
    exp = [(685, 218), (397, 1448)]        # nav_treasure → ex_tab
    good = ok and len(got) == 2 and all(abs(g[0] - e[0]) <= 8 and abs(g[1] - e[1]) <= 8
                                        for g, e in zip(got, exp))
    return good, f"导航 ok={ok} 点击={got} 期望≈{exp}"


def case_already(rp):
    """已在兑换页 → 直接返回，一次都不点。"""
    ok = fs.goto_exchange_page(sc())
    good = ok and not rp.real_clicks
    return good, f"已在兑换页直接返回={ok} 点击={rp.real_clicks}(期望空)"


def case_claim(rp):
    """金币在场 → 点金币 → 「恭喜获得」→ 领取 → 校验金币消失。"""
    ok = fs.one_claim(sc())
    got = rp.real_clicks
    good = ok and len(got) == 2 and got[0][1] < 700 and got[1][1] > 1200
    return good, f"ok={ok} 点击(金币→领取)={got}"


def case_done_guard(rp):
    """已领态：金币没了 → 必须一次都不点（重复点无收益）。"""
    ok = fs.one_claim(sc())
    got = rp.real_clicks
    good = (ok is False) and not got
    return good, f"返回={ok}(期望 False) 点击={got}(期望空 → 已领不乱点)"


def case_dry(rp):
    ok = fs.one_claim(sc(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry 返回={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    """并发锁：第二个实例拿不到锁；释放后可再拿。"""
    name = "free_star_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


if __name__ == "__main__":
    st.run_one("free_star 离线自检（点击驱动状态机，不消耗次数）", [
        ("首页→寻宝→兑换 导航", [F["home"], F["treasure"], F["free"]], case_goto),
        ("已在兑换页不重复点", [F["free"]], case_already),
        ("金币→抽奖→领取→校验", [F["free"], F["claim"], F["done"]], case_claim),
        ("已领护栏（金币不在不乱点）", [F["done"]], case_done_guard),
        ("dry 只出计划且零副作用", [F["free"]], case_dry),
        ("并发锁互斥", [F["free"]], case_lock),
    ])
