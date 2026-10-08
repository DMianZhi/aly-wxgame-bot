#!/usr/bin/env python
"""离线自检: guild_donate（战队捐献）—— 零消耗，不碰游戏窗口。

夹具: `_guildtest_*.png` 全部是**当天实跑截下的真帧**，它们恰好构成最难的场景 ——
    四层同底半透明遮罩: 确认弹窗 / 「次数不足」提示层底下，捐献页标志照样满血
    (gd_title 1.00、gd_gold_btn 0.99) → 判层顺序错了就会在模态弹窗上瞎点。
  唯一合成的是 `_ts_unknown_page.png`（纯深色，任何页面标志都不命中）→ 验「未知页零点击」。

覆盖:
    ① 判层专场: 7 张真帧逐一判对（含「遮罩底下满血」的两层）
    ② 勾选框颜色判态: 未勾(靛蓝)=False / 已勾(黄)=True / 无弹窗(深底)=None
    ③ 全链路: 首页→战队→捐献→金币(直接)→钻石(确认弹窗+勾选)→领取→收尾，点击逐步比对金标准
    ④ 丢点击重试: 点后帧不变=没生效 → 重试；**领取只点 1 次**(重试绝不重复捐)
       + 次数用尽提示层收掉后立即停手 + 留证截图
    ⑤ 未知页中止: 零点击
    ⑥ dry 零点击零写盘；⑦ 并发锁互斥

用法:
    uv run python tools/selftest/guild_donate_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from tools.cases import guild_donate as gd  # noqa: E402

H = "_guildtest_home.png"
G = "_guildtest_guild.png"
D = "_guildtest_donate.png"
P = "_guildtest_popup.png"
DLG = "_guildtest_dialog.png"          # 确认弹窗 + 勾选框**未勾**(靛蓝)
DLG_CHK = "_guildtest_dialog_chk.png"  # 确认弹窗 + 勾选框**已勾**(黄)
NOCNT = "_guildtest_nocnt.png"         # 「次数不足」提示层(绿确认键)
UNKNOWN = "_ts_unknown_page.png"       # 合成: 纯深色
LAYERS = [H, G, D, P, DLG, DLG_CHK, NOCNT]

# 金标准点击坐标（来自实跑，容差 ±6）
C_GUILD = (699, 1058)
C_DONATE = (700, 1008)
C_GOLD = (226, 1129)
C_DIAMOND = (612, 1129)
C_CLAIM = (416, 1289)
C_CHK = (348, 808)
C_OK = (527, 900)
C_CLOSE = (760, 346)
C_BACK = (727, 1448)
C_NOCNT_OK = (412, 907)


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=gd.TH, dry=dry, prefix="guild_")


def case_layers(rp):
    """① 判层专场 + ② 勾选框颜色判态：7 张真帧逐一判定。"""
    sc = _sc()
    bad = []
    want = [gd.HOME, gd.GUILD, gd.DONATE, gd.POPUP, gd.DIALOG, gd.DIALOG, gd.NOCNT]
    for i, (f, exp) in enumerate(zip(LAYERS, want)):
        rp.idx = i                       # 直接指定帧（不靠点击推进）
        got = gd.state(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] {f:28s} -> {got:7s} (期望 {exp})")
        if got != exp:
            bad.append(f"{f}:{got}!={exp}")
    for name, idx, exp in (("未勾(靛蓝)", 4, False), ("已勾(黄)", 5, True), ("无弹窗(深底)", 2, None)):
        rp.idx = idx
        got = gd._chk_checked(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] 勾选框 {name:14s} 已勾选={got} (期望 {exp})")
        if got != exp:
            bad.append(f"chk:{name}")
    return not bad, f"判层/判态失败项={bad or '无'}"


def case_full_flow(rp):
    """③ 全链路：金币 1 次 + 钻石 1 次(走确认弹窗并勾选) → 收尾回首页。"""
    ok = gd.run(_sc(), kit.Args(type="both", times=1))
    expect = [C_GUILD, C_DONATE, C_GOLD, C_CLAIM,
              C_DIAMOND, C_CHK, C_OK, C_CLAIM, C_CLOSE, C_BACK]
    clicks_ok = st.check_clicks("全链路", rp.real_clicks, expect)
    return ok and clicks_ok, f"run={ok} 点击={rp.real_clicks}"


def case_retry_nocnt(rp):
    """④ 丢点击重试 + 次数用尽：重试不重复捐，提示层收掉后停手。"""
    ok = gd.run(_sc(), kit.Args(type="gold", times=2))
    expect = [C_GUILD, C_DONATE, C_GOLD, C_GOLD, C_CLAIM, C_GOLD, C_NOCNT_OK, C_CLOSE, C_BACK]
    clicks_ok = st.check_clicks("丢点击重试/次数用尽", rp.real_clicks, expect)
    n_claim = sum(1 for c in rp.real_clicks
                  if abs(c[0] - C_CLAIM[0]) <= 6 and abs(c[1] - C_CLAIM[1]) <= 6)
    once = n_claim == 1
    print(f"[{'ok  ' if once else '!!  '}] 领取键只点 {n_claim} 次 —— 重试没有造成重复捐献")
    shot_ok = "shot:_guild_nocnt_gold.png" in rp.shots
    print(f"[{'ok  ' if shot_ok else '!!  '}] 次数用尽留证截图 {rp.shots}")
    return ok and clicks_ok and once and shot_ok, f"run={ok} 点击={rp.real_clicks}"


def case_unknown(rp):
    """⑤ 未知页中止：零点击。"""
    ok = not gd.run(_sc(), kit.Args(type="gold", times=1))
    safe = not rp.real_clicks
    print(f"[{'ok  ' if safe else '!!  '}] 未知页点击 {len(rp.real_clicks)} 次 (期望 0)")
    return ok and safe, f"run={ok}(期望 False) 点击={rp.real_clicks}"


def case_dry(rp):
    """⑥ dry: 零点击零写盘。"""
    ok = gd.run(_sc(dry=True), kit.Args(type="both", times=1, dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    name = "guild_donate_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("判层专场 + 勾选框颜色判态", LAYERS, case_layers),
    ("全链路(金币/钻石各 1，含确认弹窗+勾选)", [H, G, D, P, D, DLG, DLG_CHK, P, D, G, H], case_full_flow),
    ("丢点击重试 / 次数用尽", [H, G, D, D, P, D, NOCNT, D, G, H], case_retry_nocnt),
    ("未知页中止(零点击)", [UNKNOWN], case_unknown),
    ("dry 零点击零写盘", [D], case_dry),
    ("并发锁互斥", [D], case_lock),
]


def ensure_fixtures() -> bool:
    """合成夹具按需生成（缺真帧则整份自检失去意义 → 直接跳过）。"""
    for f in (H, G, D, P, DLG, DLG_CHK, NOCNT):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}")
            return False
    p = SHOTS_DIR / UNKNOWN
    if not p.is_file():
        cv2.imwrite(str(p), np.full((1518, 812, 3), 16, np.uint8))
        print(f"[生成] {UNKNOWN}（合成: 纯深色，不含任何页面标志）")
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("guild_donate 离线自检（真帧回放：四层遮罩判层 + 丢点击重试）", SCENES)
