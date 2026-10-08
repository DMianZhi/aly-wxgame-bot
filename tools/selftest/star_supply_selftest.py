#!/usr/bin/env python
"""离线自检: star_supply（逐星补给「领5次 + 领逐星信标×5」）—— 零消耗，不碰游戏窗口。

夹具: `_startest_*.png` 全部是**当天实探截下的真帧**（不是合成），天然构成最难场景 ——
    逐星补给面板是**半透明压暗**，底下的「逐星补给」入口在面板帧上仍 0.97 命中
    → 判层顺序写成「先长阶页后面板」就会在面板上瞎点，本自检专门钉这条。
    另有一张**旧美术**的闯关页真帧（snap_20261006_160202），用来钉「横幅美术轮换」后
    只裁文字的 stage_stair 是否仍能命中（0.891）。

覆盖:
    ① 判层专场: 7 张真帧逐一判对（含「面板压着长阶页」的歧义帧 + 两张恭喜获得覆盖层）
    ② ×5 装置两态: 可领(装置+红点, 0.98 命中) / 已领(**装置整个消失**, 0.59 不命中)
    ③ 全链路 10 点金标准: 首页→闯关→长阶→补给→领5次→领取→关面板→×5装置→领取→返回×2
    ④ 领5次「无覆盖层 + 计数未变」→ **不重试**（防重复消耗）→ 记为未达成(False)，无留证
    ⑤ ×5 装置丢点击重试到上限 → 报失败 + fail_beacon_noluck 留证
    ⑥ 未知页零点击中止（项目铁律）
    ⑦ dry 零点击零写盘；⑧ 并发锁互斥

用法:
    uv run python tools/selftest/star_supply_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from tools.cases import star_supply as ss  # noqa: E402

HOME = "_startest_home.png"           # 首页（闯关模式入口）
STAGE = "_startest_stage.png"         # 闯关页（**旧美术**，验文字版 stage_stair 兼容）
STAIR = "_startest_stair.png"         # 逐星长阶 已领态（×5 装置**已消失**）
CLAIM = "_startest_stair_claim.png"   # 逐星长阶 可领态（×5 装置 + 红点）
PANEL = "_startest_panel.png"         # 逐星补给面板（半透明压暗）
GIFT1 = "_startest_gift_supply.png"   # 恭喜获得: 黑匣密钥150 + 金币15000（领5次的产物）
GIFT2 = "_startest_gift_beacon.png"   # 恭喜获得: 逐星信标×5
UNKNOWN = "_startest_unknown.png"     # 合成: 纯深色（任何页面标志都不命中）
LAYERS = [HOME, STAGE, STAIR, CLAIM, PANEL, GIFT1, GIFT2]

# 金标准点击坐标（当天实探 + 同口径匹配算出的真值，容差 ±6）
C_STAGE = (620, 1383)    # 首页「闯关模式」
C_STAIR = (717, 614)     # 闯关页「逐星长阶」横幅
C_ENTRY = (137, 1073)    # 长阶页左下「逐星补给」
C_CLAIM5 = (587, 1002)   # 面板「领5次」橙键
C_GIFT = (416, 1288)     # 恭喜获得「领取」
C_CLOSE = (748, 419)     # 面板右上 X
C_BEACON = (432, 1046)   # 长阶页 ×5 装置
C_BACK1 = (727, 1448)    # 长阶页「返回」
C_BACK2 = (744, 1452)    # 闯关页「返回」

# ×5 装置右上红点区（**已不做判据**，仅作夹具状态旁证：可领=170 红像素 / 已领=0）
DOT = (415, 955, 490, 1035)


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=ss.TH, dry=dry, prefix="star_")


def _red(frame: str) -> int:
    """×5 装置右上红点区红像素数（直接读夹具真帧，与回放帧表无关）。"""
    img = cv2.imread(str(SHOTS_DIR / frame))
    x0, y0, x1, y1 = DOT
    reg = img[y0:y1, x0:x1].astype(int)
    b, g, r = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    return int(((r > 140) & (g < 100) & (b < 100)).sum())


def case_layers(rp):
    """① 判层专场 + 面板压暗歧义。"""
    sc = _sc()
    bad = []
    want = [ss.HOME, ss.STAGE, ss.STAIR, ss.STAIR, ss.PANEL, ss.GIFT, ss.GIFT]
    for i, (f, exp) in enumerate(zip(LAYERS, want)):
        rp.idx = i
        got = ss.state(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] {f[10:]:22s} -> {got:6s} (期望 {exp})")
        if got != exp:
            bad.append(f"{f}:{got}!={exp}")
    # 面板帧上「逐星补给」入口仍命中 → 判层顺序的歧义就在这一帧
    rp.idx = LAYERS.index(PANEL)
    amb = sc.look("ss_entry", "ss_claim5")
    e_ok = amb["ss_entry"] is not None and amb["ss_entry"][2] > 0.90
    print(f"  [{'ok  ' if e_ok else '!!  '}] 面板帧上 ss_entry 仍 {amb['ss_entry'][2]:.3f}"
          f"（面板=半透明压暗）却仍判成 PANEL（ss_claim5={amb['ss_claim5'][2]:.3f}）")
    if not e_ok:
        bad.append("panel-dim-ambiguity")
    return not bad, f"判层失败项={bad or '无'}"


def case_beacon_states(rp):
    """② ×5 装置两态（模板即判据，红点仅旁证）。"""
    sc = _sc()
    rp.idx = LAYERS.index(CLAIM)
    a = sc.find("ss_beacon", ss.TH_BEACON)
    rp.idx = LAYERS.index(STAIR)
    b = sc.find("ss_beacon", ss.TH_BEACON)
    ra, rb = _red(CLAIM), _red(STAIR)
    ok = a is not None and b is None and ra > 60 and rb == 0
    print(f"  [{'ok  ' if ok else '!!  '}] 可领: ss_beacon={a} 红点={ra}px | "
          f"已领: ss_beacon={b} 红点={rb}px（装置整个消失→模板不再命中）")
    return ok, f"可领命中={None if a is None else a[2]:.3f} 已领命中={b}"


def case_full_flow(rp):
    """③ 全链路 10 点金标准。"""
    ok = ss.run(_sc(), kit.Args(times=1))
    expect = [C_STAGE, C_STAIR, C_ENTRY, C_CLAIM5, C_GIFT, C_CLOSE, C_BEACON, C_GIFT,
              C_BACK1, C_BACK2]
    clicks_ok = st.check_clicks("全链路", rp.real_clicks, expect)
    n_gift = sum(1 for c in rp.real_clicks
                 if abs(c[0] - C_GIFT[0]) <= 6 and abs(c[1] - C_GIFT[1]) <= 6)
    print(f"[{'ok  ' if n_gift == 2 else '!!  '}] 「领取」只点 {n_gift} 次（补给1次 + 信标1次）")
    return ok and clicks_ok and n_gift == 2, f"run={ok} 点击={rp.real_clicks}"


def case_nocontent(rp):
    """④ 领5次无覆盖层 + 计数未变 → 不重试（防重复消耗）→ 未达成，无留证。"""
    ok = ss.run(_sc(), kit.Args(times=1))
    expect = [C_ENTRY, C_CLAIM5, C_CLOSE, C_BACK1, C_BACK2]
    clicks_ok = st.check_clicks("计数未变不重试", rp.real_clicks, expect)
    ok_ret = ok is False
    no_shot = not rp.shots
    print(f"[{'ok  ' if ok_ret else '!!  '}] 一次没领到返回 {ok}（期望 False: 目标未达成）")
    print(f"[{'ok  ' if no_shot else '!!  '}] 留证截图 {rp.shots}（期望空: 不是异常，只是没领到）")
    return ok_ret and clicks_ok and no_shot, f"run={ok} 点击={rp.real_clicks}"


def case_retry_limit(rp):
    """⑤ ×5 装置丢点击重试到上限 → 报失败 + 留证。"""
    ok = ss.run(_sc(), kit.Args(times=1))
    expect = [C_ENTRY, C_CLAIM5, C_GIFT, C_CLOSE, C_BEACON, C_BEACON, C_BEACON,
              C_BACK1, C_BACK2]
    clicks_ok = st.check_clicks("装置丢点击重试", rp.real_clicks, expect)
    shot_ok = [s for s in rp.shots if "fail_beacon_noluck" in s]
    print(f"[{'ok  ' if shot_ok else '!!  '}] 失败留证截图 {rp.shots}")
    return (not ok) and clicks_ok and bool(shot_ok), f"run={ok}(期望 False) 点击={rp.real_clicks}"


def case_unknown(rp):
    """⑥ 未知页零点击中止。"""
    ok = ss.run(_sc(), kit.Args(times=1))
    safe = not rp.real_clicks
    print(f"[{'ok  ' if safe else '!!  '}] 未知页点击 {len(rp.real_clicks)} 次 (期望 0)")
    return (not ok) and safe, f"run={ok}(期望 False) 点击={rp.real_clicks}"


def case_dry(rp):
    """⑦ dry: 零点击零写盘。"""
    ok = ss.run(_sc(dry=True), kit.Args(times=1, dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    name = "star_supply_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("判层专场(含面板压暗歧义)", LAYERS, case_layers),
    ("×5装置两态(可领/装置整个消失)", LAYERS, case_beacon_states),
    ("全链路(闯关→长阶→补给领5次→×5信标→返回)",
     [HOME, STAGE, STAIR, PANEL, GIFT1, PANEL, CLAIM, GIFT2, STAIR, STAGE, HOME], case_full_flow),
    ("领5次计数未变→不重试(防重复消耗)", [STAIR, PANEL, PANEL, STAIR, STAGE, HOME, HOME], case_nocontent),
    ("×5装置丢点击重试到上限→报失败",
     [CLAIM, PANEL, GIFT1, PANEL, CLAIM, CLAIM, CLAIM, CLAIM, STAGE, HOME], case_retry_limit),
    ("未知页中止(零点击)", [UNKNOWN], case_unknown),
    ("dry 零点击零写盘", [STAIR], case_dry),
    ("并发锁互斥", [STAIR], case_lock),
]


def ensure_fixtures() -> bool:
    """合成夹具按需生成（缺真帧则整份自检失去意义 → 直接跳过）。"""
    for f in LAYERS:
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
    st.run_one("star_supply 离线自检（真帧回放: 面板压着长阶页的判层顺序 + 计数未变不重试 + "
               "×5装置两态 + 丢点击重试）",
               SCENES)
