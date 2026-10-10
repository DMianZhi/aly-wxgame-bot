#!/usr/bin/env python
"""用例: 奖励领取（首页顶栏「奖励」→ 一键领取全部可领奖励，是体力的补给渠道之一）。

链路(2026-10-10 实测定版):
    首页 --(rw_entry 顶栏第③个图标)--> 奖励面板(sweep_close X 在 752,235)
    --(rw_claim 面板内任一行「领取」，x=700 列)-->
      游戏**自动领取全部**可领奖励(实测: 6 行全橙, 点第 1 行 → 6 行全部变灰+恭喜弹窗)
    --(claim_btn 恭喜获得-领取)→ 关面板 → 回首页

    ⚠ 前提: 基础任务完成后才有可领项(用户口述)。无可领时 rw_claim 不命中 →
      留证收工(**不算失败**)—— 可能是任务没做完，也可能真领完了
    ⚠ 「点一个=全领」是游戏机制(实测), 所以只点 find_all 的**第一个**
    ⚠ 顶栏三个图标都带红点(①任务②邮件③奖励, 都探过: ①②不是奖励面板),
      入口用图标本体模板 rw_entry(不含红点, 红点有无不影响命中)

    模板标定(2026-10-10, 812x1518 实帧):
      rw_entry  自匹配 1.000 / 次高 0.582
      rw_claim  自匹配 1.000 (6 行按钮全橙时; 领完变灰 0.00~0.18 → 天然不可再命中)

用法:
    uv run python tools/cases/claim_reward.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86
ENTRY_TPL = "rw_entry"      # 顶栏「奖励」图标(第③个)
CLAIM_TPL = "rw_claim"      # 面板内「领取」按钮(行式, 同款)
PLAN = """[dry] 计划:
  首页 --(rw_entry 顶栏「奖励」)--> 奖励面板
  --(rw_claim 找到可领行 → 点第一个)--> 游戏自动领取全部 → 恭喜弹窗(claim_btn 领取)
  → 关面板 → 回首页
  无可领: rw_claim 不命中 → 留证收工(不算失败; 前提=基础任务已完成)"""


def _claim_in_panel(sc: kit.Screen) -> bool:
    """奖励面板**已开**的前提下领取(离线自检也从这进)。返回是否领到了。"""
    # max_hits=8: 面板实测 6 行可领, find_all 默认上限 4 会少报
    hits = sc.find_all(CLAIM_TPL, max_hits=8)
    if not hits:
        log("无可领取的奖励(基础任务未完成?) → 留证收工")
        sc.shot("rw_nothing")
        x = sc.find("sweep_close", 0.90)
        if x:
            sc.click(x, "关面板")
        return False
    sc.click(hits[0], f"领取(第 1 行, 共 {len(hits)} 行可领)")
    kit.nap(3.0)
    # 恭喜弹窗(可能连续多个) → 逐个领取, 最多 4 个
    claimed = 0
    for _ in range(4):
        c = sc.find("claim_btn")
        if c is None:
            break
        sc.click(c, "恭喜获得-领取")
        claimed += 1
        kit.nap(2.0)
    # 关面板
    x = sc.find("sweep_close", 0.90)
    if x:
        sc.click(x, "关奖励面板")
        kit.nap(1.2)
    log(f"领取完成 (恭喜弹窗领取 {claimed} 次)")
    return True


def claim_once(sc: kit.Screen) -> bool:
    """打开奖励面板并领取; 返回是否领到了东西。"""
    entry = sc.find(ENTRY_TPL)
    if entry is None:
        log("首页找不到「奖励」图标(rw_entry)")
        sc.shot("rw_no_entry")
        return False
    sc.click(entry, "顶栏「奖励」图标")
    if sc.dry:
        return False
    kit.nap(2.5)
    if sc.find_all(CLAIM_TPL, max_hits=8) or sc.find("sweep_close", 0.90):
        return _claim_in_panel(sc)
    log("奖励面板没开(领取键与 X 都不在) → 再点一次入口")
    sc.click(entry, "顶栏「奖励」图标(重试)")
    kit.nap(2.5)
    if sc.find_all(CLAIM_TPL, max_hits=8) or sc.find("sweep_close", 0.90):
        return _claim_in_panel(sc)
    log("面板还是没开 → 留证放弃")
    sc.shot("rw_no_panel")
    return False


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if sc.dry:
        e = sc.find(ENTRY_TPL)
        log(f"[dry] 计划: 首页顶栏「奖励」({'已找到' if e else '当前页未找到'}) "
            f"→ 面板内点第一个可领行 → 自动全领 → 恭喜领取 → 关面板")
        return True
    if not kit.is_home(sc):
        kit.goto_home(sc)
    ok = claim_once(sc)
    if not kit.is_home(sc):
        kit.goto_home(sc)
    return ok


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "claim_reward", "奖励领取（顶栏「奖励」→ 一键领取全部可领）", run,
        plan=PLAN, prefix="rw_", lock_ttl=300, th=TH,
    ))
