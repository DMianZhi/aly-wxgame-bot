#!/usr/bin/env python
"""用例: 活跃度奖励（首页顶栏「活跃度」→ 一键领取）。

链路(2026-10-10 实测定版):
    首页 --(act_entry 顶栏第②个图标「活跃度」)--> 活跃度面板(宽橙条=活跃度进度条)
    --(act_claim 面板「领取」钮 (700,593))--> 恭喜弹窗(claim_btn 领取) → 关面板 → 回首页

    ⚠ 顶栏四图标实测定版(2026-10-10): ①每日任务 ②活跃度 ③每日奖励 ④贵族 ——
      之前把①当活跃度是**错的**(①的面板标题 4-5 字, 且用户确认②才是; 面板帧比对
      ②面板 vs 用户手开面板差异仅 0.9 实锤)
    ⚠ 活跃度面板顶部那条 570px 宽橙条是**进度条**(等距斜刻度纹理), 不是按钮!
    ⚠ 无可领时「领取」钮变灰 → act_claim 不命中 → 留证收工(**不算失败**)
    ⚠ 恭喜弹窗可能连续多个 → 逐个领取, 最多 4 个

    模板标定(2026-10-10, 812x1518 实帧):
      act_entry  自匹配 1.000 / 次高 0.573
      act_claim  自匹配 1.000 / 次高 0.585

用法:
    uv run python tools/cases/claim_activity.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86
ENTRY_TPL = "act_entry"     # 顶栏「活跃度」图标(第①个)
CLAIM_TPL = "act_claim"     # 面板「一键领取」大橙钮
PLAN = """[dry] 计划:
  首页 --(act_entry 顶栏「活跃度」第②个图标)--> 活跃度面板
  --(act_claim 「领取」钮)--> 恭喜弹窗(claim_btn 领取) → 关面板 → 回首页
  无可领: 领取钮变灰(act_claim 不命中) → 留证收工(不算失败)"""


def claim_once(sc: kit.Screen) -> bool:
    """打开活跃度面板并一键领取; 返回是否领到了。"""
    entry = sc.find(ENTRY_TPL)
    if entry is None:
        log("首页找不到「活跃度」图标(act_entry)")
        sc.shot("act_no_entry")
        return False
    sc.click(entry, "顶栏「活跃度」图标")
    if sc.dry:
        return False
    kit.nap(2.5)
    btn = sc.find(CLAIM_TPL)
    if btn is None:
        log("「一键领取」不可点(无可领/已领完) → 留证收工")
        sc.shot("act_nothing")
        x = sc.find("sweep_close", 0.90)
        if x:
            sc.click(x, "关面板")
        return False
    sc.click(btn, "一键领取")
    kit.nap(3.0)
    claimed = 0
    for _ in range(4):
        c = sc.find("claim_btn")
        if c is None:
            break
        sc.click(c, "恭喜获得-领取")
        claimed += 1
        kit.nap(2.0)
    x = sc.find("sweep_close", 0.90)
    if x:
        sc.click(x, "关面板")
        kit.nap(1.2)
    log(f"一键领取完成 (恭喜弹窗领取 {claimed} 次)")
    return True


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if sc.dry:
        e = sc.find(ENTRY_TPL)
        log(f"[dry] 计划: 首页顶栏「活跃度」({'已找到' if e else '当前页未找到'}) "
            f"→ 面板「一键领取」→ 恭喜领取 → 关面板")
        return True
    if not kit.is_home(sc):
        kit.goto_home(sc)
    ok = claim_once(sc)
    if not kit.is_home(sc):
        kit.goto_home(sc)
    return ok


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "claim_activity", "活跃度奖励（顶栏「活跃度」→ 一键领取）", run,
        plan=PLAN, prefix="act_", lock_ttl=300, th=TH,
    ))
