#!/usr/bin/env python
"""离线自检: missile_hunt（导弹猎场闪击）—— 零消耗，不碰游戏窗口。

夹具: `__mhmh**.png` 全部是**实跑截下的真机真帧**（601x1143 小窗口那批）——
      判页/导航/归属/降级都在真帧上跑；只有「局内」两张是合成的
      （845 灰底 + 真模板，让 match_adaptive 走 identity 单候选，快）。

覆盖:
    ① 判页专场: 7 张真帧逐一判对（含「次数已耗尽提示叠在活动关卡页上」→ prompt 优先；
       局内帧必须判 unknown，不许误认成页面）
    ② 闪击键归属: 两张活动卡「闪击」键同款(0.998/0.978) → 取离卡标题最近的那张
    ③ 导航: 首页→关卡页→活动关卡页，点击逐步比对真帧实测坐标
    ④ 次数用尽: 点闪击 → 弹「次数已耗尽」→ 只点绿确认关掉 → 跳过(不算失败)
    ⑤ 残留对话框: 上来就是闪击对话框 → 不重找卡片，直接闪击进局
    ⑥ 局内: 真局内帧不算结束（且技能走**真模板**命中 546,977）+
       回到活动关卡页连续 3 次才算结束
    ⑦ dry 零点击零写盘；⑧ 并发锁互斥

用法:
    uv run python tools/selftest/missile_hunt_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import battle, kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR, TEMPLATE_PATH  # noqa: E402
from tools.cases import missile_hunt as mh  # noqa: E402

# ---- 真帧（实跑截下，601x1143）----
HOME0 = "__mhmh00_home.png"          # 首页
STAGE0 = "__mhmh01_stage.png"        # 关卡页(stage_event_lv 活动关卡入口)
ACTPAGE = "__mhmh05_actpage.png"     # 活动关卡页(陨石陷阱 + 导弹猎场 两张卡)
DLG = "__mhmh06_flashdlg.png"        # 闪击对话框
BATTLE = "__mhmh08_state_-.png"      # 局内
END = "__mhmh09_end.png"             # 闪击完回到活动关卡页
PROMPT = "__mhmh10_dlg0.png"         # 次数已耗尽提示(叠在活动关卡页上)

# ---- 合成帧（845x1521，identity 路径）----
IDLE845 = "_ts_mh_idle845.png"       # 局内空帧 + 真技能模板(验模板可用)
ACT845 = "_ts_mh_act845.png"         # 活动关卡页(贴真卡标题) — 收尾判据

# 金标准坐标: 全部**从夹具帧实测**，不是手填
C_STAGE_BTN = (462, 1045)    # stage_btn @ 首页(601x1143)
C_ACT_ENTRY = (391, 1095)    # stage_event_lv @ 关卡页（实测 0.979）
C_FLASH_MH = (421, 1003)     # mh_flash @ 活动关卡页 → 导弹猎场那张卡(靠下的)
C_FLASH_OTHER = (421, 455)   # 同款按键 @ 陨石陷阱那张卡(靠上的) → 必须**不**选它
C_CONFIRM = (313, 696)       # boss_confirm_ok @ 次数耗尽提示
C_DLG_GO = (313, 862)        # mh_dlg_go @ 闪击对话框
C_SKILL = (546, 977)         # battle_skill @ 601 局内真帧(真模板命中 0.986)

# 判页期望: 文件名 -> (可接受页面集, 说明)
PAGE_CASES = [
    (HOME0, {"home"}, "首页"),
    (STAGE0, {"stage"}, "关卡页(有活动关卡入口)"),
    (ACTPAGE, {"actpage"}, "活动关卡页"),
    (END, {"actpage"}, "闪击完回到活动关卡页"),
    (DLG, {"dialog"}, "闪击对话框(背后那张卡仍能命中闪击键)"),
    (PROMPT, {"prompt"}, "次数已耗尽提示(叠在活动关卡页上)"),
    (BATTLE, {"unknown"}, "局内帧 → 不是任何页面"),
]


def _sc(rp, dry: bool = False) -> kit.Screen:
    """按**当前帧的真实尺寸**建 Screen。

    真帧是 601x1143、合成帧是 845x1521 —— 混用会让「锚点+偏移」按错误的尺寸缩放，
    所以每个场景都从帧本身取尺寸（st.RECT 是固定 812，对真帧不适用）。
    """
    h, w = rp.imgs[min(rp.idx, len(rp.imgs) - 1)].shape[:2]
    return kit.Screen((0, 0, w, h), th=mh.TH, dry=dry, prefix="missile_")


def _paste(name: str, tpl: str, cx: int, cy: int, size=(845, 1521), base=16) -> None:
    """灰底 + 贴一个真模板（合成帧）。"""
    w, h = size
    img = np.full((h, w, 3), base, np.uint8)
    t = cv2.imread(str(TEMPLATE_PATH(tpl)))
    th, tw = t.shape[:2]
    x0, y0 = max(0, cx - tw // 2), max(0, cy - th // 2)
    img[y0:y0 + th, x0:x0 + tw] = t
    cv2.imwrite(str(SHOTS_DIR / name), img)


def ensure_fixtures() -> bool:
    for f in (HOME0, STAGE0, ACTPAGE, DLG, BATTLE, END, PROMPT):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}")
            return False
    made = []
    if not (SHOTS_DIR / IDLE845).is_file():
        _paste(IDLE845, "battle_skill", 755, 1296)
        made.append(IDLE845)
    if not (SHOTS_DIR / ACT845).is_file():
        _paste(ACT845, "mh_title", 420, 800)
        made.append(ACT845)
    if made:
        print(f"[生成] 合成夹具 {', '.join(made)}（灰底 + 真模板）")
    return True


def case_pages(rp):
    """① 判页专场：7 张真帧逐一判定（跑生产 page() 本体）。"""
    bad = []
    for i, (f, want, label) in enumerate(PAGE_CASES):
        rp.idx = i                       # 直接指定帧（不靠点击推进）
        got = mh.page(_sc(rp))           # ← 生产代码本体
        ok = got in want
        print(f"  [{'ok  ' if ok else '!!  '}] {label:34s} 页面 {got:8s}(期望 {'/'.join(want)})")
        if not ok:
            bad.append(label)
    return not bad, f"判页失败项={bad or '无'}"


def case_flash_pick(rp):
    """② 闪击键归属：两张卡同款按键(0.998/0.978) → 取离导弹猎场卡标题最近的。"""
    rp.idx = PAGE_CASES.index(next(c for c in PAGE_CASES if c[0] == ACTPAGE))
    fl = mh.pick_flash(_sc(rp))
    got = fl[:2] if fl else None
    good = got == C_FLASH_MH
    return good, (f"选中 {got}(期望 {C_FLASH_MH}=导弹猎场那张) "
                  f"—— 同款按键 {C_FLASH_OTHER} 是另一张卡，必须不选")


def case_nav(rp):
    """③ 导航：首页→关卡页→活动关卡页。"""
    ok = mh.goto_actpage(_sc(rp))
    clicks_ok = st.check_clicks("导航", rp.real_clicks, [C_STAGE_BTN, C_ACT_ENTRY])
    return ok and clicks_ok, f"到达={ok} 点击={rp.real_clicks}"


def case_no_attempts(rp):
    """④ 次数用尽：点闪击 → 弹提示 → 只点绿确认关掉 → 跳过(不算失败)。"""
    ok = mh.one_round(_sc(rp))
    clicks_ok = st.check_clicks("次数用尽", rp.real_clicks, [C_FLASH_MH, C_CONFIRM])
    return ok and clicks_ok, f"跳过={ok}(期望 True) 点击={rp.real_clicks}"


def case_resume_dialog(rp):
    """⑤ 残留对话框：上来就在闪击对话框 → 不重找卡片，直接闪击进局。

    只钉第一下(对话框上的闪击键): 后面的技能点击发生在**合成 845 帧**上，坐标落在
    合成帧空间(755,1296)，跟真帧预注释的 6a 期望值不同 —— 混帧尺寸下不比坐标。
    """
    mh.FIGHT_TIMEOUT = 600        # 帧序列走完就结束，不会真等这么久
    ok = mh.one_round(_sc(rp))
    clicks_ok = st.check_clicks("残留对话框", rp.real_clicks[:1], [C_DLG_GO])
    return ok and clicks_ok, f"跑完={ok} 点击={rp.real_clicks}(首下应为对话框的闪击键)"


def case_battle_not_end(rp):
    """⑥a 局内真帧**不算**回到活动关卡页（不许提前收工），且技能走真模板。

    夹具是 601 真局内帧: battle_skill 真模板命中 (546,977) → 技能点击不是坐标兜底。
    （本场景就是要等超时: 退不出去才对，所以预算给小）
    """
    mh.FIGHT_TIMEOUT = 4
    ok, _r, _v = mh.fight(_sc(rp))
    used_tpl = C_SKILL in rp.real_clicks
    good = (not ok) and used_tpl
    return good, (f"提前收工={ok}(期望 False) 技能命中真模板={used_tpl}"
                  f" 点击={rp.real_clicks}(期望含 {C_SKILL})")


def case_actpage_end(rp):
    """⑥b 回到活动关卡页连续 3 次才算闪击打完（防战斗间隙误判）。"""
    mh.FIGHT_TIMEOUT = 600
    ok, _r, _v = mh.fight(_sc(rp))
    return ok and not rp.real_clicks, f"判完成={ok}(期望 True) 零点击={not rp.real_clicks}"


def case_dry(rp):
    """⑦ dry: 零点击零写盘。"""
    ok = mh.run(_sc(rp, dry=True), kit.Args(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(_rp):
    name = "missile_hunt_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("判页专场(7 张真帧，含提示层优先/局内帧不误判)", [c[0] for c in PAGE_CASES], case_pages),
    ("闪击键归属(两卡同款→取导弹猎场那张)", [ACTPAGE], case_flash_pick),
    ("导航: 首页→关卡页→活动关卡页", [HOME0, STAGE0, ACTPAGE], case_nav),
    ("次数用尽: 关掉提示即跳过(不算失败)", [ACTPAGE, PROMPT, ACTPAGE], case_no_attempts),
    ("残留对话框: 直接闪击进局", [DLG, IDLE845, ACT845, ACT845, ACT845], case_resume_dialog),
    ("局内真帧不算结束 + 技能走真模板", [BATTLE], case_battle_not_end),
    ("回到活动关卡页连续 3 次才算打完", [ACT845], case_actpage_end),
    ("dry 零点击零写盘", [ACTPAGE], case_dry),
    ("并发锁互斥", [ACTPAGE], case_lock),
]

if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("missile_hunt 离线自检（真帧回放：判页/归属/降级/局内）", SCENES)
