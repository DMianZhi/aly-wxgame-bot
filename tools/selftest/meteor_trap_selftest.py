#!/usr/bin/env python
"""离线自检: meteor_trap（陨石陷阱闪击）—— 零消耗，不碰游戏窗口。

夹具(2026-10-10 实探真帧, 812x1518):
    ACT = "_mt_actpage_full.png"   活动关卡页全页(三张卡都在)
    DLG = "_mt3_mt_dialog.png"     陨石陷阱的闪击对话框(只开未确认, 零消耗拍的)

覆盖:
    ① 判层: 活动页→actpage / 对话框→dialog(顺序陷阱: 对话框盖在活动页上必须先判)
    ② 闪击键: pick_flash 落在卡1橙钮 (564,588)±8 —— 锚点+偏移换算对不对就看这个
    ③ 极难页签: pick_hard 落在卡1页签 (740,307)±8 (共享 lm_hard 模板, 取离 ys_title 最近)
    ④ 跨卡不串台: ys_title 在卡2(激光迷宫)/卡3(导弹猎场)的标题区**不得** ≥0.86
    ⑤ dry 零点击零写盘; ⑥ 并发锁互斥

用法:
    uv run python tools/selftest/meteor_trap_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from wb.selftest_kit import FakeRect  # noqa: E402
from tools.cases import meteor_trap as mt  # noqa: E402

ACT = "_mt_actpage_full.png"        # 活动关卡页真帧(三张卡)
DLG = "_mt3_mt_dialog.png"          # 陨石陷阱闪击对话框真帧(只开未确认)

# 金标准(帧坐标 = 客户区坐标, 812x1518, 容差 ±8):
C_FLASH = (564, 588)                # 卡1橙「闪击」(实测橙块中心)
C_HARD = (740, 307)                 # 卡1「极难」页签(lm_hard 命中中心)
LM_TITLE_Y = 716                    # 卡2(激光迷宫)标题文字带中心
MH_TITLE_Y = 1084                   # 卡3(导弹猎场)标题文字带中心


def _sc_frame(name: str, dry: bool = True) -> kit.Screen:
    img = cv2.imread(str(SHOTS_DIR / name))
    assert img is not None, f"缺夹具 {name}"
    h, w = img.shape[:2]
    sc = kit.Screen(FakeRect(0, 0, w, h), th=mt.TH, dry=dry, prefix="mtrap_")
    import wb.bot as _bot
    _bot.grab_window = lambda rect, _i=img: _i     # 回放: grab 固定返回该帧
    return sc


def case_layers(rp):
    """① 判层: 活动页→actpage / 对话框→dialog。"""
    ok, bad = True, []
    for f, want in ((ACT, "actpage"), (DLG, "dialog")):
        got = mt.page(_sc_frame(f))
        okk = got == want
        ok &= okk
        if not okk:
            bad.append(f"{f}:{got}!={want}")
        print(f"  [{'ok  ' if okk else '!!  '}] {f} -> {got} (期望 {want})")
    return ok, f"判层失败项={bad or '无'}"


def case_flash(rp):
    """② pick_flash: 卡1的闪击键落点(锚点+偏移换算的金标准)。"""
    sc = _sc_frame(ACT)
    fl = mt.pick_flash(sc)
    good = fl is not None and abs(fl[0] - C_FLASH[0]) <= 8 and abs(fl[1] - C_FLASH[1]) <= 8
    return good, f"闪击键={fl and (fl[0], fl[1])} (期望 {C_FLASH}±8)"


def case_hard(rp):
    """③ click_hard: 卡1页签默认非选中(共享选中态模板只有 0.867) → 模板不中
    → 按标题锚定预测点直接点(幂等无消耗), 落点必须=页签位置 (740,307)±8。"""
    sc = _sc_frame(ACT, dry=False)   # dry=False: 回放层拦鼠标、记录点击 —— 预测点路径才走得到
    ok = mt.click_hard(sc)
    clicks = list(rp.real_clicks)
    good = (ok and len(clicks) == 1
            and abs(clicks[0][0] - C_HARD[0]) <= 8 and abs(clicks[0][1] - C_HARD[1]) <= 8)
    return good, f"通过={ok} 点击={clicks} (期望 [{list(C_HARD)}]±8)"


def case_no_cross(rp):
    """④ 跨卡不串台: ys_title 在卡2/卡3标题区必须 < 0.86。"""
    img = cv2.imread(str(SHOTS_DIR / ACT))
    tpl = cv2.imread(str(SHOTS_DIR.parent / "templates" / "ys_title.png"))
    bad = []
    for tag, y in (("卡2激光迷宫", LM_TITLE_Y), ("卡3导弹猎场", MH_TITLE_Y)):
        reg = cv2.cvtColor(img[y - 40:y + 40, 20:340], cv2.COLOR_BGR2GRAY)
        t = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        if reg.shape[0] < t.shape[0] or reg.shape[1] < t.shape[1]:
            continue
        s = float(cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED).max())
        print(f"  [{'ok  ' if s < 0.86 else '!!  '}] ys_title vs {tag}: {s:.3f}")
        if s >= 0.86:
            bad.append(tag)
    return not bad, f"串台={bad or '无'}"


def case_dry(rp):
    """⑤ dry: 零点击零写盘。"""
    sc = _sc_frame(ACT)
    sc2 = kit.Screen(sc.rect, th=mt.TH, dry=True, prefix="mtrap_")
    import wb.bot as _bot
    img = cv2.imread(str(SHOTS_DIR / ACT))
    _bot.grab_window = lambda rect, _i=img: _i
    ok = mt.run(sc2, kit.Args(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(_rp):
    """⑥ 并发锁互斥。"""
    name = "meteor_trap_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("①判层(活动页/对话框顺序)", [ACT, DLG], case_layers),
    ("②闪击键落点(锚点+偏移)", [ACT], case_flash),
    ("③极难页签落点(共享模板取最近)", [ACT], case_hard),
    ("④跨卡不串台(ys_title vs 卡2/卡3)", [ACT], case_no_cross),
    ("⑤dry 零点击零写盘", [ACT], case_dry),
    ("⑥并发锁互斥", [ACT], case_lock),
]


def ensure_fixtures() -> bool:
    need = [ACT, DLG]
    missing = [f for f in need if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具: {missing}")
        return False
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("meteor_trap 离线自检（判层/锚点几何/跨卡区分）", SCENES)
