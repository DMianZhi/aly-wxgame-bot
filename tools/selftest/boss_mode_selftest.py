#!/usr/bin/env python
"""离线自检: boss_mode（BOSS 闪击）—— 零消耗，不碰游戏窗口。

夹具: `_bossmode_*.png` / `_boss_*.png` / `ref_boss_prompt.png` 全部是**实跑截下的真帧**；
      局内战斗的三张（复活/装备UP/结算）是**合成**的 —— 用 templates/ 里的真模板贴在深底上
      （那三个弹窗只在战斗中一闪而过，历史上没留过图）。合成只为验**状态机的判定顺序**。

覆盖:
    ① 判页专场: 12 张真帧逐一判对（含「次数耗尽提示叠在列表/站内页上」→ prompt 优先）
    ② 导航状态机: 首页→关卡页→BOSS列表→站内，点击逐步比对
    ③ 已在别站: 先按「返回」回列表，再选目标站
    ④ 次数用尽: 点闪击 → 弹提示 → 确认关闭 → 跳过本站（不误判成失败）
    ⑤ 局内状态机: 点技能 → 阵亡复活 → 装备UP确认 → 结算继续（判定优先级: 复活>装备UP>结算）
    ⑥ 站内页停留 2 次**不算**打完（防战斗间隙误判）/ 连续 3 次才算打完
    ⑦ dry 零点击零写盘；⑧ 并发锁互斥

用法:
    uv run python tools/selftest/boss_mode_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR, TEMPLATE_PATH  # noqa: E402
from tools.cases import boss_mode as bm  # noqa: E402

# ---- 真帧（磁盘上确实存在）----
LIST0 = "_bossmode_stuck_prompt_pegasus.png"     # BOSS 列表页
STN_CYG = "_bossmode_noflash_cygnus.png"         # 副武器站内页(次数用尽, 无闪击)
STN_AND = "_bossmode_noflash_andro.png"          # 僚机站内页
STN_END = "_boss_strike_final.png"               # 站内页(闪击收尾)
STN_REF = "_boss_ref_scale.png"                  # 站内页(缩放参考)
STN_OLD = "_bossmode_unknown_cygnus.png"         # 站内页(曾被判 unknown)
EQP = "_bossmode_fight_timeout.png"              # 站内 + 装备UP选择弹窗
PRM_PEG = "_bossmode_nodialog_pegasus.png"       # 次数耗尽提示(叠在列表页)
PRM_DRA = "_bossmode_nodialog_drago.png"         # 次数耗尽提示(装甲站)
PRM_REF = "ref_boss_prompt.png"                  # 次数耗尽提示(参考图)
UNK0 = "_boss_unknown_state.png"                 # 非 BOSS 页面
UNK1 = "_diag_now.png"                           # 扫荡面板+背包已满(非 BOSS 页面)

# ---- 合成帧（局内战斗，用真模板贴深底）----
IDLE = "_ts_fight_idle.png"                      # 局内空白(→点技能)
REVIVE = "_ts_fight_revive.png"                  # 阵亡复活弹窗
EQUIPUP = "_ts_fight_equipup.png"                # 装备UP选择弹窗
RESULT = "_ts_fight_result.png"                  # 结算页

# 判页期望: 文件名 -> (可接受页面集, 期望弹窗, 说明)
# 注: 弹窗带遮罩时背后站内页会被压暗, boss_flash/boss_equipup_btn 不命中属正常，
#     此时页面判为 unknown 不影响流程(流程先判弹窗，站内页判定只用于收尾)。
PAGE_CASES = [
    (LIST0, {"bosslist"}, None, "BOSS 列表页(4空间站)"),
    (STN_CYG, {"station"}, None, "副武器站内页(次数用尽, 无闪击)"),
    (STN_AND, {"station"}, None, "僚机站内页(周BOSS 噩梦, 无闪击)"),
    (STN_END, {"station"}, None, "站内页(闪击收尾)"),
    (STN_REF, {"station"}, None, "站内页(缩放标定参考)"),
    (STN_OLD, {"station"}, None, "站内页(曾被判 unknown 那次)"),
    (EQP, {"station"}, "boss_equipup_title", "站内+装备UP选择弹窗"),
    (PRM_PEG, {"prompt"}, "boss_noattempts", "次数耗尽提示(叠在列表页上)"),
    (PRM_DRA, {"prompt"}, "boss_noattempts", "次数耗尽提示(装甲站)"),
    (PRM_REF, {"prompt"}, "boss_noattempts", "次数耗尽提示(参考图)"),
    (UNK0, {"unknown"}, None, "非 BOSS 页面(未知态)"),
    (UNK1, {"unknown"}, None, "扫荡面板+背包已满(非 BOSS 页面)"),
]
DIALOGS = ("boss_revive_diamond", "boss_equipup_title", "boss_result_next",
           "boss_noattempts", "boss_confirm_ok")

# 金标准坐标全部**从夹具帧实测**（不是手填）:
#   stage_btn@home(620,1383) / stage_boss@snap_20261008_091133(328,1450)
#   boss_stn_pegasus@列表页(256,1097) / boss_flash@站内(308,1418)
#   boss_back@STN_CYG(726,1457) / boss_confirm_ok@提示层(418,913)
STAGE_PAGE = "snap_20261008_091133.png"          # 真帧: 关卡页(stage_boss, 无 stage_btn)
C_STAGE = (620, 1383)
C_BOSS = (328, 1450)
C_PEGASUS = (256, 1097)
C_FLASH = (308, 1418)
C_BACK = (726, 1457)
C_CONFIRM = (418, 913)
C_SKILL = (740, 1300)


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=bm.TH, dry=dry, prefix="bossmode_")


def _paste_dark(name: str, tpl: str, cx: int, cy: int) -> None:
    """深底 + 贴一个真模板（局内弹窗合成）。"""
    img = np.full((1518, 812, 3), 16, np.uint8)
    t = cv2.imread(str(TEMPLATE_PATH(tpl)))
    h, w = t.shape[:2]
    x0, y0 = max(0, cx - w // 2), max(0, cy - h // 2)
    img[y0:y0 + h, x0:x0 + w] = t
    cv2.imwrite(str(SHOTS_DIR / name), img)


def ensure_fixtures() -> bool:
    for f in (LIST0, STN_CYG, STN_AND, STN_END, STN_REF, STN_OLD, EQP,
              PRM_PEG, PRM_DRA, PRM_REF, UNK0, UNK1):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}")
            return False
    made = []
    for name, tpl, cx, cy in (
        (IDLE, None, 0, 0),
        (REVIVE, "boss_revive_diamond", 200, 420),
        (EQUIPUP, "boss_equipup_title", 200, 700),
        (RESULT, "boss_result_next", 200, 520),
    ):
        p = SHOTS_DIR / name
        if p.is_file():
            continue
        if tpl is None:
            cv2.imwrite(str(p), np.full((1518, 812, 3), 16, np.uint8))
        else:
            _paste_dark(name, tpl, cx, cy)
        made.append(name)
    if (SHOTS_DIR / EQUIPUP).is_file() and not (SHOTS_DIR / "_ts_equipup_ok.note").is_file():
        _paste_dark("_ts_tmp_ok.png", "boss_equipup_ok", 200, 900)
        base = cv2.imread(str(SHOTS_DIR / EQUIPUP))
        t = cv2.imread(str(SHOTS_DIR / "_ts_tmp_ok.png"))
        base = np.where(t > 20, t, base)          # 把「确认」键也贴上去
        cv2.imwrite(str(SHOTS_DIR / EQUIPUP), base)
        (SHOTS_DIR / "_ts_equipup_ok.note").write_text("equipup_ok 已合成", encoding="utf-8")
        (SHOTS_DIR / "_ts_tmp_ok.png").unlink()
        made.append("equipup_ok 补丁")
    if made:
        print(f"[生成] 合成夹具 {', '.join(made)}（深底 + 真模板）")
    return True


def _dialog(sc: kit.Screen, want: str | None):
    for d in DIALOGS:
        if d == "boss_confirm_ok" and want != d:
            continue                      # 确认键只在指定场景检查
        hit = _find_soft(sc, d)
        if hit is not None:
            return d
    return None


def _find_soft(sc: kit.Screen, name: str):
    try:
        return sc.find(name)
    except FileNotFoundError:
        return None


def case_pages(rp):
    """① 判页专场：12 张真帧逐一判定（真匹配、真代码路径）。"""
    sc = _sc()
    bad = []
    for i, (f, want_pages, want_dlg, label) in enumerate(PAGE_CASES):
        rp.idx = i                       # 直接指定帧（不靠点击推进）
        got_page = bm.page(sc)           # ← 生产代码本体，不是副本
        got_dlg = _dialog(sc, want_dlg)
        ok = got_page in want_pages and (want_dlg is None or got_dlg == want_dlg)
        print(f"  [{'ok  ' if ok else '!!  '}] {label:30s} 页面 {got_page:8s}"
              f"(期望 {'/'.join(want_pages)}) 弹窗 {str(got_dlg):20s}(期望 {want_dlg})")
        if not ok:
            bad.append(label)
    return not bad, f"判页失败项={bad or '无'}"


def case_nav(rp):
    """② 导航状态机：首页→关卡页→BOSS列表→站内。"""
    ok = bm.goto_station(_sc(), "pegasus")
    clicks_ok = st.check_clicks("导航", rp.real_clicks, [C_STAGE, C_BOSS, C_PEGASUS])
    return ok and clicks_ok, f"到达={ok} 点击={rp.real_clicks}"


def case_nav_from_other_station(rp):
    """③ 已在别站：先「返回」回列表，再选目标站。"""
    ok = bm.goto_station(_sc(), "pegasus")
    clicks_ok = st.check_clicks("别站兜回", rp.real_clicks, [C_BACK, C_PEGASUS])
    return ok and clicks_ok, f"到达={ok} 点击={rp.real_clicks}"


def case_no_attempts(rp):
    """④ 次数用尽：点闪击 → 弹「今日可攻打次数已耗尽」→ 确认关闭 → 跳过本站。"""
    ok = not bm.one_station(_sc(), "pegasus")
    clicks_ok = st.check_clicks("次数用尽", rp.real_clicks,
                                [C_PEGASUS, C_FLASH, C_CONFIRM])
    return ok and clicks_ok, f"跳过={ok} 点击={rp.real_clicks}"


def case_fight_flow(rp):
    """⑤ 局内状态机：点技能 → 复活 → 装备UP确认 → 结算继续，判定优先级。"""
    bm.FIGHT_TIMEOUT = 90          # 预算给足：真匹配耗时也算进循环预算，给窄了会 flaky
    ok, rounds, revives = bm.fight(_sc())
    clicks_ok = st.check_clicks("局内", rp.real_clicks,
                                [C_SKILL, (200, 420), (200, 900), (200, 520)])
    return ok and clicks_ok and rounds == 1 and revives == 1, \
        f"跑完={ok} 复活={revives} 结算={rounds} 点击={rp.real_clicks}"


def case_station_hits_not_enough(rp):
    """⑥a 站内页停留次数不够**不算**打完（战斗间隙会短暂回站内页）。

    预算取 2s：真匹配耗时也算进循环预算，所以实际只够 1 轮 —— 只要**没能**凑满
    连续 3 次就必须返回 False（正是要防的「战斗间隙误判成打完」）。
    """
    bm.FIGHT_TIMEOUT = 2
    ok, _r, _v = bm.fight(_sc())
    shot = "shot:_bossmode_fight_timeout.png" in rp.shots
    return (not ok) and shot, f"提前判完成={ok}(期望 False) 超时留证={shot} 点击={rp.real_clicks}"


def case_station_hits_enough(rp):
    """⑥b 连续 3 次停留 = 闪击真正打完（预算给足，避免真匹配耗时导致 flaky）。"""
    bm.FIGHT_TIMEOUT = 90
    ok, _r, _v = bm.fight(_sc())
    return ok and not rp.real_clicks, f"判完成={ok}(期望 True) 零点击={not rp.real_clicks}"


def case_dry(rp):
    """⑦ dry: 零点击零写盘。"""
    ok = bm.run(_sc(dry=True), kit.Args(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    name = "boss_mode_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("判页专场(12 张真帧，含提示层优先)", [c[0] for c in PAGE_CASES], case_pages),
    ("导航: 首页→关卡→BOSS列表→站内", ["_guildtest_home.png", STAGE_PAGE, LIST0, STN_END], case_nav),
    ("已在别站: 先返回列表再选站", [STN_CYG, LIST0, STN_END], case_nav_from_other_station),
    ("次数用尽: 提示层确认关闭后跳过本站", [LIST0, STN_END, PRM_PEG, LIST0, STN_END], case_no_attempts),
    ("局内状态机: 技能→复活→装备UP→结算", [IDLE, REVIVE, EQUIPUP, RESULT, STN_END, STN_END, STN_END],
     case_fight_flow),
    ("站内停留 2 次不算打完(防间隙误判)", [STN_END], case_station_hits_not_enough),
    ("站内停留 3 次算打完", [STN_END], case_station_hits_enough),
    ("dry 零点击零写盘", [STN_END], case_dry),
    ("并发锁互斥", [STN_END], case_lock),
]

if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("boss_mode 离线自检（真帧回放：判页/导航/局内状态机）", SCENES)
