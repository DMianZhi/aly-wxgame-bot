#!/usr/bin/env python
"""离线自检: clear_stamina（体力清空）—— 零消耗，不碰游戏窗口。

覆盖
    ① 药丸判据: 超上限真帧 → True（黄占比 ≥0.35）
    ② 药丸判据: 上限内真帧 → False（黄占比 ≤0.10）—— 两档分得开才敢用
    ③ **压暗免疫**: 扫荡面板态真帧（背景被压暗到 ~0.26 倍亮度）→ 仍判 True
       —— 这是「面板里就地回读、不用每轮进出面板」的前提（用户 2026-10-13 提速要求）
    ④ **不超就不动**: 上限内首页帧回放 → run() 返回 True 且**零点击**
    ⑤ **硬约束**: 用例源码里不存在对 sweep_double（双倍奖励）的 click
       —— 用户口径「没有看广告双倍奖励」，这条是回归护栏（改坏了立刻红）

为什么用「药丸底色」而不是 OCR
    顶部「292/120」是第 5 套字形（与既有 4 套都不同源，归一后仅 0.18~0.46）。
    超上限时药丸是**亮黄**、上限内是**暗棕**（实测 45% vs 4%）→ 判布尔量足够。

夹具（真帧，零成本可复现：跑一次用例会自动留证）
    _cs_pill_over.png  首页体力药丸**亮黄**（超上限）
    _cs_pill_ok.png    首页体力药丸**暗棕**（上限内）
    _cs_panel.png      扫荡面板态（背景被压暗）——验「面板里也能读」

用法
    uv run python tools/selftest/clear_stamina_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st, stamina as stam  # noqa: E402
from tools.cases import clear_stamina as cs  # noqa: E402

OVER = "_cs_pill_over.png"
OK = "_cs_pill_ok.png"
PANEL = "_cs_panel.png"


def _pill(sc) -> tuple[float | None, bool | None]:
    hit = sc.find("stamina_entry", stam.ENTRY_TH)
    if hit is None:
        return None, None
    return stam.yellow_frac(sc.grab(), hit[0], hit[1]), stam.over_cap(sc)


def scene_over(rp):
    """① 超上限真帧：黄占比高 + over_cap=True。"""
    sc = kit.open_screen(th=0.86, prefix="_cs_self")
    fr, got = _pill(sc)
    ok = (got is True) and (fr is not None) and fr >= 0.35
    return ok, (f"黄占比={fr if fr is None else round(fr, 4)} over_cap={got}"
                f"（期望 True，黄占比 ≥0.35 = 亮黄药丸）")


def scene_ok(rp):
    """② 上限内真帧：黄占比低 + over_cap=False。"""
    sc = kit.open_screen(th=0.86, prefix="_cs_self")
    fr, got = _pill(sc)
    ok = (got is False) and (fr is not None) and fr <= 0.10
    return ok, (f"黄占比={fr if fr is None else round(fr, 4)} over_cap={got}"
                f"（期望 False，黄占比 ≤0.10 = 暗棕药丸）")


def scene_panel(rp):
    """③ 压暗免疫：面板态（背景压暗）仍须读出「超上限」。"""
    sc = kit.open_screen(th=0.86, prefix="_cs_self")
    fr, got = _pill(sc)
    ok = (got is True) and (fr is not None) and fr >= 0.35
    return ok, (f"面板态 黄占比={fr if fr is None else round(fr, 4)} over_cap={got}"
                f"（期望 True —— 压暗不改色相/饱和度，读数应与首页一致）")


def scene_noop(rp):
    """④ 不超就不动：整条用例在上限内首页上应当**一次都不点**。"""
    sc = kit.open_screen(th=0.86, prefix="_cs_self")
    res = cs.run(sc, kit.Args())
    clicks = list(rp.real_clicks)
    ok = (res is True) and not clicks
    return ok, (f"run()={res}（期望 True）点击={clicks}（期望空：体力没超上限就什么都不点）")


def scene_no_ad(rp):
    """⑤ 硬约束：源码里不许出现对「双倍奖励」的点击。"""
    src = Path(cs.__file__).read_text(encoding="utf-8")
    bad = [ln.strip() for ln in src.splitlines()
           if "sweep_double" in ln and "click" in ln and not ln.strip().startswith("#")]
    plan_ok = ("不点" in cs.PLAN) and ("双倍奖励" in cs.PLAN)
    ok = (not bad) and plan_ok
    return ok, ("源码/计划均无「点双倍奖励」，PLAN 明示不点" if ok
                else f"发现点击双倍奖励: {bad} / PLAN 说明缺失")


if __name__ == "__main__":
    st.run_one("clear_stamina 体力清空自检", [
        ("① 超上限真帧 → over_cap=True", [OVER], scene_over),
        ("② 上限内真帧 → over_cap=False", [OK], scene_ok),
        ("③ 面板压暗态 → 仍判超上限", [PANEL], scene_panel),
        ("④ 不超上限 → 零点击", [OK], scene_noop),
        ("⑤ 硬约束：绝不点双倍奖励", [], scene_no_ad),
    ])
