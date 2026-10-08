#!/usr/bin/env python
"""用例: 寻宝 → 转盘 → 每日首次免费抽奖。

链路:
    首页 --(nav_treasure)--> 寻宝页 --(turn_tab 底部页签)--> 转盘页
    → 中心键「每日首次免费」→ 轮盘转 ~5s → 「恭喜获得」+ 领取 → 回转盘页
    → 中心键变为「购买 💎30」+ 右下倒计时（冷却开始，实测约 5h 一轮）

⚠ 安全红线: 中心键有两种形态且**背景金菱形完全相同**，只靠文字区分 ——
    「每日首次免费」= 可白嫖;  「购买 💎30」= 冷却中，点了白花 30 钻石。
    实测区分度: 免费态 turn_daily 0.978 / turn_paid 0.466；冷却态 0.450 / 0.991。
    所以只在 turn_daily 命中且**明显高于** turn_paid 时才点，否则一律只记录不乱动。

用法:
    uv run python tools/cases/free_turn.py                 # 抽每日首次免费
    uv run python tools/cases/free_turn.py --max=2         # 最多试 2 轮（第 2 轮会被冷却态挡住）
    uv run python tools/cases/free_turn.py --dry           # 只出计划、零点击
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

FLOW_TIMEOUT = 90          # 单次抽奖（点击 → 动画 → 领取）总超时

PLAN = """[dry] 计划:
  首页 --(nav_treasure 寻宝)--> 寻宝页 --(turn_tab 底部页签)--> 转盘页
  --> 中心键「每日首次免费」(turn_daily) --> 轮盘转运 ~5s --> 「恭喜获得」--> 领取
  --> 回转盘页(中心键变 turn_paid 付费态 = 免费次数 -1，冷却开始)
  ⚠ 中心键两形态美术相同: turn_daily=免费可嫖 / turn_paid=购买💎30(冷却期，绝不点)
  ⚠ 付费态更高分或两形态同时命中 → 保守放弃，一次都不点"""


def goto_turn_page(sc: kit.Screen) -> bool:
    """首页 → 寻宝 → 底部「转盘」页签；已在转盘页则直接返回。"""
    if sc.find("turn_refresh") is not None:
        log("已在转盘页")
        return True

    if sc.find("treasure_help") is None:            # 不在寻宝系页面 → 先点首页「寻宝」
        nav = sc.find("nav_treasure")
        if nav is None:
            log("既不在转盘页，也找不到首页「寻宝」入口")
            return False
        if sc.dry:
            log("[dry] 计划: 点首页「寻宝」→ 点底部「转盘」页签")
            return True
        sc.click(nav, "首页·寻宝")
        kit.nap(2.0)

    tab = sc.find("turn_tab")
    if tab is None:
        log("寻宝页上找不到「转盘」页签")
        return False
    if sc.dry:
        log("[dry] 计划: 点底部「转盘」页签 → 进转盘页")
        return True
    sc.click(tab, "底部·转盘页签")
    kit.nap(2.5)
    ok = sc.find("turn_refresh") is not None
    log("已进入转盘页" if ok else "未进入转盘页")
    return ok


def claim_if_any(sc: kit.Screen, timeout: float = FLOW_TIMEOUT) -> bool:
    """等「恭喜获得」→ 点领取（顺带兜住跳过卡弹窗/看广告形态）。返回是否领到。"""
    r = kit.ad_flow(sc, page="turn_refresh", timeout=timeout)
    if r == "timeout":
        log("未等到「恭喜获得」/未点到领取")
        return False
    return True


def one_turn(sc: kit.Screen) -> bool:
    """一轮抽奖。返回是否真的把免费次数用掉。"""
    st = sc.look("turn_daily", "turn_paid")
    daily, paid = st["turn_daily"], st["turn_paid"]
    log(f"中心键: turn_daily={'%.3f' % daily[2] if daily else None}  "
        f"turn_paid={'%.3f' % paid[2] if paid else None}")

    if daily is None:
        if paid is not None:
            log(f"冷却中（中心键=购买💎30 score={paid[2]:.3f}，距下次免费见右下倒计时）→ 不点，收工")
        else:
            log("中心键两种形态都没命中 → 页面未就绪，不点")
        return False
    if paid is not None and paid[2] > daily[2]:
        log(f"⚠ 两形态同时命中且付费态更高（daily={daily[2]:.3f} paid={paid[2]:.3f}）→ 保守放弃")
        return False
    if sc.dry:
        log(f"[dry] 计划: 点中心键「每日首次免费」@({daily[0]},{daily[1]}) → 等「恭喜获得」→ 点领取")
        return True

    sc.click(daily, "中心键·每日首次免费")
    if not claim_if_any(sc):
        sc.shot("turn_fail_noclaim")
        return False

    after = sc.look("turn_daily", "turn_paid", "turn_refresh")
    if after["turn_paid"] is not None and after["turn_daily"] is None:
        log(f"抽奖完成: 中心键已变付费态({after['turn_paid'][2]:.3f})，免费次数 -1，冷却开始 ✓")
        return True
    if after["turn_daily"] is not None:
        log(f"⚠ 领取后中心键仍是免费态({after['turn_daily'][2]:.3f}) → 可能未成功")
        sc.shot("turn_after_claim_still_free")
        return False
    log("领取后中心键判不出形态（动画/弹窗遮罩?），记留证")
    sc.shot("turn_after_claim_unknown")
    return True


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if not goto_turn_page(sc):
        log("未就绪到转盘页")
        sc.shot("turn_fail_nav")
        return False
    done = 0
    for _ in range(max(1, args.max)):
        if one_turn(sc):
            done += 1
        else:
            break
        kit.nap(1.5)
    log(f"收尾: 完成 {done} 次; 状态={'转盘页' if sc.find('turn_refresh') else '非转盘页'}")
    return done > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_turn", "寻宝·转盘（每日首次免费）", run,
        plan=PLAN, prefix="turn_", lock_ttl=600,
    ))
