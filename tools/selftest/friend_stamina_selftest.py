#!/usr/bin/env python
"""离线自检: friend_stamina（好友体力「一键收赠」）—— 零消耗，不碰游戏窗口。

夹具: `_friendtest_*.png` 全部是**当天实探截下的真帧**（不是合成），天然构成最难场景 ——
    回礼弹窗**只压中屏**，好友页标志在弹窗底下照样满血（fr_counter / fr_onekey 仍 1.000）
    → 判层顺序写成「先页面后弹窗」就会在弹窗上瞎点，本自检专门钉这条。

覆盖:
    ① 判层专场: 4 张真帧逐一判对（含「弹窗压着好友页」的歧义帧）
    ② 红角标颜色判态三态: 有(917 红像素) / 收赠后无(0) / 弹窗压暗无(0)
    ③ 全链路: 首页→小人 icon→一键收赠→回礼弹窗→绿「确认」→返回，点击逐步比对金标准
    ④ 静默无效降级: 残留弹窗先收掉 → 今日已满(30/30)点后**无弹层** → 视为已完成不报错
    ⑤ 丢点击重试: 点后帧不变且红角标仍在 → 重试到上限 → 报失败 + 留证
    ⑥ 未知页零点击中止（项目铁律）
    ⑦ dry 零点击零写盘；⑧ 并发锁互斥

用法:
    uv run python tools/selftest/friend_stamina_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from tools.cases import friend_stamina as fs  # noqa: E402

H = "_friendtest_home.png"        # 首页（小人 icon 在「无尽模式」正上排最左）
PG = "_friendtest_page.png"       # 好友页 0/30，键上**有**红角标
GIFT = "_friendtest_gift.png"     # 回礼弹窗 ⚡+150 + 绿确认 + 右上 X
CAP = "_friendtest_capped.png"    # 收赠后好友页 30/30，角标消失
UNKNOWN = "_friendts_unknown.png"  # 合成: 纯深色（任何页面标志都不命中）
LAYERS = [H, PG, GIFT, CAP]

# 金标准点击坐标（当天实跑真值，容差 ±6）
C_FRIEND = (111, 1242)
C_ONEKEY = (510, 1430)
C_OK = (412, 965)
C_BACK = (731, 1475)


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=fs.TH, dry=dry, prefix="friend_")


def case_layers(rp):
    """① 判层专场 + ② 红角标三态。"""
    sc = _sc()
    bad = []
    want = [fs.HOME, fs.FRIEND, fs.GIFT, fs.FRIEND]
    for i, (f, exp) in enumerate(zip(LAYERS, want)):
        rp.idx = i
        got = fs.state(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] {f:28s} -> {got:7s} (期望 {exp})")
        if got != exp:
            bad.append(f"{f}:{got}!={exp}")
    # 弹窗帧上好友页标志仍满血 → 判层顺序的歧义就在这一帧
    rp.idx = 2
    on_gift = sc.look("fr_counter", "fr_onekey")
    print(f"  [{'ok  ' if all(v is not None for v in on_gift.values()) else '!!  '}]"
          f" 弹窗帧上 fr_counter={on_gift['fr_counter']} fr_onekey={on_gift['fr_onekey']}"
          f" —— 两者都命中却仍判成 GIFT")
    for i, (f, exp) in enumerate(zip([PG, CAP, GIFT], [True, False, False])):
        rp.idx = [H, PG, GIFT, CAP].index(f)
        got = fs.has_badge(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] 红角标 {f:28s} -> {got} (期望 {exp})")
        if got != exp:
            bad.append(f"badge:{f}:{got}")
    return not bad, f"判层/判态失败项={bad or '无'}"


def case_full_flow(rp):
    """③ 全链路：首页→好友页→一键收赠→回礼→确认→返回。"""
    ok = fs.run(_sc(), kit.Args(times=1))
    expect = [C_FRIEND, C_ONEKEY, C_OK, C_BACK]
    clicks_ok = st.check_clicks("全链路", rp.real_clicks, expect)
    n_ok = sum(1 for c in rp.real_clicks
               if abs(c[0] - C_OK[0]) <= 6 and abs(c[1] - C_OK[1]) <= 6)
    once = n_ok == 1
    print(f"[{'ok  ' if once else '!!  '}] 「确认」只点 {n_ok} 次")
    return ok and clicks_ok and once, f"run={ok} 点击={rp.real_clicks}"


def case_capped(rp):
    """④ 残留弹窗先收掉 + 今日已满(30/30)静默无效 → 视为已完成，不报错。"""
    ok = fs.run(_sc(), kit.Args(times=1))
    expect = [C_OK, C_ONEKEY, C_BACK]
    clicks_ok = st.check_clicks("残留弹窗+静默降级", rp.real_clicks, expect)
    ok_ret = ok is True
    print(f"[{'ok  ' if ok_ret else '!!  '}] 静默无效返回 {ok} (期望 True: 今日已无待收不算失败)")
    return ok and clicks_ok, f"run={ok} 点击={rp.real_clicks}"


def case_retry(rp):
    """⑤ 丢点击重试：红角标一直在 → 连点 3 次 → 报失败 + 留证。"""
    ok = fs.run(_sc(), kit.Args(times=1))
    expect = [C_ONEKEY, C_ONEKEY, C_ONEKEY, C_BACK]
    clicks_ok = st.check_clicks("丢点击重试", rp.real_clicks, expect)
    shot_ok = [s for s in rp.shots if "fail_noluck" in s]
    print(f"[{'ok  ' if shot_ok else '!!  '}] 失败留证截图 {rp.shots}")
    return (not ok) and clicks_ok and bool(shot_ok), f"run={ok}(期望 False) 点击={rp.real_clicks}"


def case_unknown(rp):
    """⑥ 未知页零点击中止。"""
    ok = fs.run(_sc(), kit.Args(times=1))
    safe = not rp.real_clicks
    print(f"[{'ok  ' if safe else '!!  '}] 未知页点击 {len(rp.real_clicks)} 次 (期望 0)")
    return (not ok) and safe, f"run={ok}(期望 False) 点击={rp.real_clicks}"


def case_dry(rp):
    """⑦ dry: 零点击零写盘。"""
    ok = fs.run(_sc(dry=True), kit.Args(times=1, dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    name = "friend_stamina_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("判层专场 + 红角标判态三态", LAYERS, case_layers),
    ("全链路(首页→收赠→回礼→确认→返回)", [H, PG, GIFT, PG, H], case_full_flow),
    ("残留弹窗先收掉 + 今日已满静默降级", [GIFT, CAP, CAP, H], case_capped),
    ("丢点击重试到上限 → 报失败", [PG, PG, PG, PG, H], case_retry),
    ("未知页中止(零点击)", [UNKNOWN], case_unknown),
    ("dry 零点击零写盘", [PG], case_dry),
    ("并发锁互斥", [CAP], case_lock),
]


def ensure_fixtures() -> bool:
    """合成夹具按需生成（缺真帧则整份自检失去意义 → 直接跳过）。"""
    for f in (H, PG, GIFT, CAP):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}（当天实探帧，需重新实探补齐）")
            return False
    p = SHOTS_DIR / UNKNOWN
    if not p.is_file():
        cv2.imwrite(str(p), np.full((1518, 812, 3), 16, np.uint8))
        print(f"[生成] {UNKNOWN}（合成: 纯深色，不含任何页面标志）")
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("friend_stamina 离线自检（真帧回放: 弹窗压着好友页的判层顺序 + 静默降级 + 丢点击重试）",
               SCENES)
