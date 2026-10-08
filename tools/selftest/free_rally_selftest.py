#!/usr/bin/env python
"""离线自检: free_rally（十年集结）判定逻辑回放 —— 零消耗，不碰游戏窗口。

做法: 实测帧当「每步画面」，点一下就切到下一帧（点击驱动状态机）；
      wb.bot 的取帧/点击、cv2 落盘、time.sleep 全部换成替身 →
      用例自身分支全跑一遍，且**点击序列逐点比对金标准坐标**。

金标准 (EXPECT_FULL) 来自 10-08 实跑：
    翻活动卡轮播 → 金卡 → 宝箱 → Lv15 → 领取 → 返回 → 发弹幕 → 发送 → 返回

用法:
    uv run python tools/selftest/free_rally_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st  # noqa: E402
from tools.cases import free_rally as fr  # noqa: E402

# 期望点击序列: (说明, x, y) —— 坐标是窗口内局部坐标，容差 ±4
EXPECT_FULL = [
    ("寻宝下方第一张卡(翻活动卡轮播)", 685, 340),
    ("「十年集结」金卡", 700, 476),
    ("右下宝箱(带红点)", 677, 1190),
    ("Lv15 大宝箱", 217, 672),
    ("领取(恭喜获得)", 416, 1288),
    ("返回(弹窗 → 集结页)", 727, 1448),
    ("发弹幕", 327, 1088),
    ("发送(第 1 条)", 687, 452),
    ("返回(集结页 → 首页)", 727, 1448),
]

HOME_F = "_rec_home_page.png"          # 首页(活动卡轮播在另一组，无金卡)
HOME_RALLY = "_rec_home_rally.png"     # 点了第一张卡 → 轮播翻页，金卡出现
RALLY_F = "_rec_rally_page.png"        # 集结页
CHEST_F = "_rec_rally_chest.png"       # 召集宝箱弹窗(Lv15 未领)
CLAIM_F = "_rec_rally_claim.png"       # 「恭喜获得」
CHEST_OPEN = "_rec_rally_chest_open.png"   # 箱盖已开(= 今日已领)
DANMU_F = "_rec_rally_danmu.png"       # 弹幕面板
SENT_F = "_ral_15_sent.png"            # 已发出(回集结页)
TREASURE_F = "_rec_treasure_page.png"  # 拿它当「未知页」

FRAMES_FULL = [HOME_F, HOME_RALLY, RALLY_F, CHEST_F, CLAIM_F,
               CHEST_OPEN, RALLY_F, DANMU_F, SENT_F, HOME_F]

ARGS = kit.Args()


def sc(*, dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=fr.TH, dry=dry, prefix="rally_")


def case_full(rp):
    """全链路: 9 次点击逐步比对金标准。"""
    ok = fr.run(sc(), ARGS)
    got = [(x, y) for x, y in rp.real_clicks]
    good = ok and st.check_clicks("全链路", got, [(x, y) for _, x, y in EXPECT_FULL], tol=4)
    good = good and st.expect_shot("全链路留证", rp, want=True)
    return good, f"run={ok} 点击 {len(got)}/{len(EXPECT_FULL)}"


def case_already_claimed(rp):
    """已领态: 起点在宝箱弹窗且箱盖已开 → 跳过开箱，只走返回+发弹幕。"""
    s = sc()
    st0 = fr.state(s)
    lv = s.find("ral_lv15", th=fr.TH)
    ok = fr.run(s, ARGS)
    got = rp.real_clicks
    expect = [(727, 1448), (327, 1088), (687, 452), (727, 1448)]
    good = (st0 == fr.CHEST) and (lv is None) and ok and st.check_clicks("已领跳过", got, expect, tol=4)
    return good, f"起点={st0}(期望 CHEST) lv15命中={lv} run={ok} 点击={got}"


def case_unknown(rp):
    """未知页面 → 中止，不盲点。"""
    s = sc()
    st0 = fr.state(s)
    ok = fr.run(s, ARGS)
    good = (st0 == fr.UNKNOWN) and (ok is False) and not rp.real_clicks
    return good, f"状态={st0}(期望 ?) run={ok}(期望 False) 点击={rp.real_clicks}(期望空)"


def case_dry(rp):
    """--dry: 只出计划，零点击零写盘。"""
    ok = fr.run(sc(dry=True), ARGS)
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_no_wish(rp):
    """--no-wish: 宝箱流程走完但不发弹幕。"""
    a = kit.Args(extra={"no_wish": True})
    ok = fr.run(sc(), a)
    got = rp.real_clicks
    expect = [(x, y) for _, x, y in EXPECT_FULL[:6]] + [(727, 1448)]   # + 最后「返回(集结页→首页)」
    good = ok and st.check_clicks("--no-wish", got, expect, tol=4)
    return good, f"run={ok} 点击={got} 期望(不含发弹幕)={expect}"


def case_lock(rp):
    """并发锁互斥。"""
    name = "free_rally_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("全链路(9 点，逐步比对金标准)", FRAMES_FULL, case_full),
    ("已领跳过(箱盖已开)", [CHEST_OPEN, RALLY_F, DANMU_F, SENT_F, HOME_F], case_already_claimed),
    ("未知页面中止", [TREASURE_F], case_unknown),
    ("dry 只出计划且零副作用", FRAMES_FULL, case_dry),
    ("--no-wish 跳过发弹幕", [HOME_F, HOME_RALLY, RALLY_F, CHEST_F, CLAIM_F, CHEST_OPEN, RALLY_F], case_no_wish),
    ("并发锁互斥", [HOME_F], case_lock),
]

if __name__ == "__main__":
    st.run_one("free_rally 离线自检（点击驱动状态机 + 金标准逐点比对）", SCENES)
