#!/usr/bin/env python
"""离线自检: redeem_code（兑换码）—— 零消耗，不碰游戏窗口。

夹具: `_redeemtest_*.png` 全部是**当天实跑截下的真帧**（826x1503），构成全链路四种画面:
    panel = 设置面板 + 兑换码弹窗（输入框 + 绿「兑换」）
    input = 游戏内「输入文字」弹窗（码已填，含「完成」）
    ok    = 兑换成功「恭喜获得」全屏页（含「领取」claim_btn）
    bad   = 「无效兑换码」弹层（rd_invalid_tag）

覆盖:
    ① 成功路径: 输入框→完成→兑换→**领取**，两张留证
    ② 失败路径: 「无效兑换码」→ 点「确认」(与兑换同槽位)，返回 False 且不炸
    ③ 失败文案②: 「无法重复使用同一个兑换码」(两张提示层图不同) → 同样要点掉
    ④ 残层清理: 开局就停在残留弹层 → redeem_one 开头先清掉再走流程
    ⑤ 多码不中断: 成功/失败/成功 三码跑完，计数 2（单个失败不中断整轮）
    ⑥ 收尾顺序: 先关兑换码弹窗 X、再关设置面板 X（反了会被遮罩吃掉）
    ⑦ dry 零点击零写盘；⑧ 剪贴板原文 / --codes 直传 解析；⑨ 并发锁互斥

⚠ 打字/清空/切输入法是**真实副作用**（pyautogui 敲键 + Win32 换输入语言）→ 自检里
  全部打桩，只验用例的点击与分支，绝不真敲键盘、绝不真改系统输入法语言。

⚠ 弹层是半透明遮罩 → 底下的 stage_btn 照样命中（实测 0.971 vs 正常 0.996）→
  用 stage_btn 判「已回首页」会把残留弹层误判成已收尾（close_panel 已避开这个坑）。

用法:
    uv run python tools/selftest/redeem_code_selftest.py
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot, kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from tools.cases import redeem_code as rc  # noqa: E402

GAME_W, GAME_H = 826, 1503      # 夹具真帧尺寸（= 用例坐标基准，故坐标换算恒等）

PANEL = "_redeemtest_panel.png"
INPUT = "_redeemtest_input.png"
OK = "_redeemtest_ok.png"
BAD = "_redeemtest_bad.png"            # 「无效兑换码」
REPEAT = "_redeemtest_repeat.png"      # 「无法重复使用同一个兑换码」
HOME = "_redeemtest_home.png"

C_INPUT = rc.XY_INPUT            # (422, 766) 输入框
C_DONE = rc.XY_INPUT_DONE        # (316, 864) 输入弹窗「完成」
C_CONFIRM = rc.XY_CONFIRM        # (424, 895) 绿「兑换」/「确认」(同槽位)
C_CLAIM = (423, 1277)            # ok 帧上 claim_btn 命中坐标（本机实测）
C_DLG_X = rc.XY_DLG_X            # (724, 665) 兑换码弹窗 X
C_PANEL_X = rc.XY_PANEL_X        # (750, 347) 设置面板 X


def _sc(dry: bool = False) -> kit.Screen:
    """夹具帧是 826x1503 → 用同尺寸假窗口，坐标换算恒等（与实跑一致）。"""
    return kit.Screen(st.FakeRect(0, 0, GAME_W, GAME_H), dry=dry, prefix="redeem_")


@contextlib.contextmanager
def _stub_typing():
    """打字/清空/切输入法全打桩（否则自检会真敲键盘、真改系统输入法语言）。"""
    with mock.patch.object(bot, "clear_text"), \
         mock.patch.object(bot, "type_text"), \
         mock.patch.object(bot, "ime_english", return_value=True):
        yield


def case_success(rp):
    """① 成功路径：点完「兑换」出现「恭喜获得」→ 点「领取」。"""
    with _stub_typing():
        ok = rc.redeem_one(_sc(), "TESTOK", 1)
    clicks_ok = st.check_clicks("成功路径", rp.real_clicks,
                                [C_INPUT, C_DONE, C_CONFIRM, C_CLAIM])
    want = ["shot:_redeem_redeem_1_TESTOK_result.png",
            "shot:_redeem_redeem_1_TESTOK_after.png"]
    shots_ok = all(w in rp.shots for w in want)
    print(f"[{'ok  ' if shots_ok else '!!  '}] 留证截图(结果层+收尾) {rp.shots}")
    return ok and clicks_ok and shots_ok, f"ok={ok} 点击={rp.real_clicks}"


def case_fail(rp):
    """② 失败路径：「无效兑换码」→ 点「确认」，返回 False 但不抛异常。"""
    with _stub_typing():
        ok = rc.redeem_one(_sc(), "TESTBAD", 1)
    clicks_ok = st.check_clicks("失败路径", rp.real_clicks,
                                [C_INPUT, C_DONE, C_CONFIRM, C_CONFIRM])
    return (not ok) and clicks_ok, f"ok={ok}(期望 False) 点击={rp.real_clicks}"


def case_multi(rp):
    """③ 多码不中断：成功 → 失败 → 成功，计数 2。"""
    got = []
    with _stub_typing():
        for i, code in enumerate(("AAA111", "BBB222", "CCC333"), 1):
            got.append(rc.redeem_one(_sc(), code, i))
    expect = [C_INPUT, C_DONE, C_CONFIRM, C_CLAIM,          # 码1 成功
              C_INPUT, C_DONE, C_CONFIRM, C_CONFIRM,        # 码2 失败(不中断)
              C_INPUT, C_DONE, C_CONFIRM, C_CLAIM]          # 码3 成功
    clicks_ok = st.check_clicks("三码连跑", rp.real_clicks, expect)
    count_ok = got == [True, False, True]
    print(f"[{'ok  ' if count_ok else '!!  '}] 结果序列 {got} (期望 [True, False, True])")
    return clicks_ok and count_ok, f"点击={rp.real_clicks}"


def case_fail_repeat(rp):
    """③ 失败文案②：「无法重复使用同一个兑换码」（与「无效兑换码」是两层不同的图）。"""
    with _stub_typing():
        ok = rc.redeem_one(_sc(), "DUPTEST", 1)
    clicks_ok = st.check_clicks("失败文案②", rp.real_clicks,
                                [C_INPUT, C_DONE, C_CONFIRM, C_CONFIRM])
    return (not ok) and clicks_ok, f"ok={ok}(期望 False) 点击={rp.real_clicks}"


def case_clear_residual(rp):
    """④ 残层清理：开局帧就是残留弹层 → redeem_one 开头先关掉它，再正常走完。"""
    with _stub_typing():
        ok = rc.redeem_one(_sc(), "AFTERDUP", 1)
    clicks_ok = st.check_clicks("残层清理", rp.real_clicks,
                                [C_CONFIRM, C_INPUT, C_DONE, C_CONFIRM, C_CONFIRM])
    return (not ok) and clicks_ok, f"ok={ok}(期望 False) 点击={rp.real_clicks}"


def case_close_panel(rp):
    """⑥ 收尾顺序：先关兑换码弹窗 X → 再关设置面板 X，且复查不误点。"""
    rc.close_panel(_sc())
    clicks_ok = st.check_clicks("收尾顺序", rp.real_clicks, [C_DLG_X, C_PANEL_X])
    return clicks_ok, f"点击={rp.real_clicks}"


def case_dry(rp):
    """④ dry：只规划不点击、不落盘。"""
    with _stub_typing():
        out = rc.redeem_one(_sc(dry=True), "DRY001", 1)
    good = bool(out) and not rp.real_clicks and not rp.shots
    return good, f"dry={out} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_parse(rp):
    """⑤ 解析：小程序剪贴板原文（带「兑换码」标记）与 --codes 直传纯列表。"""
    clip = "今日失效兑换码： 8SJFTSTY, pN1ZOCiC, CFDBhm4q, 58MGdUqo"
    got_clip = rc.parse_codes(clip)
    want_clip = ["8SJFTSTY", "pN1ZOCiC", "CFDBhm4q", "58MGdUqo"]
    got_direct = rc.codes_from_text("AAA111, BBB222 CCC333")
    want_direct = ["AAA111", "BBB222", "CCC333"]
    no_mark = rc.parse_codes("一堆没有标记的文字 ABCDEF") == []
    dedup = rc.codes_from_text("兑换码：AAAA11, AAAA11, BBBB22") == ["AAAA11", "BBBB22"]
    print(f"  剪贴板={got_clip} / 直传={got_direct} / 无标记={no_mark} / 去重={dedup}")
    return (got_clip == want_clip and got_direct == want_direct
            and no_mark and dedup), f"clip={got_clip} direct={got_direct}"


def case_lock(rp):
    """⑥ 并发锁互斥。"""
    name = "redeem_code_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


FOUR = [PANEL, INPUT, PANEL, OK, OK]
SCENES = [
    ("成功: 输入框→完成→兑换→领取", FOUR, case_success),
    ("失败①: 「无效兑换码」→确认", [PANEL, INPUT, PANEL, BAD, BAD], case_fail),
    ("失败②: 「无法重复使用同一个兑换码」→确认", [PANEL, INPUT, PANEL, REPEAT, REPEAT],
     case_fail_repeat),
    ("残层清理: 开局带残留弹层", [REPEAT, PANEL, INPUT, PANEL, BAD], case_clear_residual),
    ("多码不中断: 成功/失败/成功", [PANEL, INPUT, PANEL, OK,
                                   PANEL, INPUT, PANEL, BAD,
                                   PANEL, INPUT, PANEL, OK], case_multi),
    ("收尾顺序: 弹窗X → 面板X", [PANEL, PANEL, HOME], case_close_panel),
    ("dry 零点击零写盘", [PANEL], case_dry),
    ("解析: 剪贴板原文 / --codes 直传", [PANEL], case_parse),
    ("并发锁互斥", [PANEL], case_lock),
]


def ensure_fixtures() -> bool:
    for f in (PANEL, INPUT, OK, BAD, REPEAT, HOME):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}")
            return False
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("redeem_code 离线自检（真帧回放：两种失败文案 + 残层清理 + 收尾顺序）", SCENES)
