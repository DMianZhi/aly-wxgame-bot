#!/usr/bin/env python
"""用例: 商城免费礼包（首页 → 商城 → 礼包页 → 免费 → 领取）。

实测两种形态都要兼容:
    A. 免广告直发: 点免费 → 立即弹「恭喜获得」→ 点领取 → 到账
    B. 看广告形态: 点免费 → [跳过卡弹窗→不使用] → 广告页(ad_close/ad_rewarded) → 关闭
       → 恭喜弹窗 → 领取

成功判据: 领取后回到礼包页且 gift_free 消失(→ 0/1)。
每日限购 1/1，当天再跑会走「已领完」分支（不点任何东西）。

用法:
    uv run python tools/cases/free_gift.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

FLOW_TIMEOUT = 120      # 点免费后的总超时(广告最长 30s + 缓冲)

PLAN = """[dry] 计划:
  首页 --(shop 商城)--> 商城页 --(gift_tab 礼包页签)--> 礼包页(gift_page)
  --> 免费按钮(gift_free) --> 形态A: 立即「恭喜获得」 / 形态B: 广告(ad_rewarded+ad_close)
  --> 点领取(claim_btn) --> 校验 gift_free 消失(→0/1)
  ⚠ 领取后免费按钮消失 = 成功；按钮还在 = 未成功
  ⚠ 每日限购 1/1，已领完则不走流程"""


def goto_gift_page(sc: kit.Screen) -> bool:
    """从任意状态导航到礼包页；已在礼包页直接返回 True。"""
    if sc.find("gift_page") is not None:
        log("已在礼包页")
        return True

    if sc.find("gift_tab") is None:                 # 不在商城页 → 从首页进商城
        shop = sc.wait("shop", 10)
        if shop is None:
            log("找不到商城入口，可能不在首页")
            return False
        sc.click(shop, "商城入口(shop)")
        if not sc.wait("gift_tab", 15):
            log("未进入商城/找不到礼包页签")
            return False

    tab = sc.find("gift_tab")
    if tab is None:
        log("找不到礼包页签(gift_tab)")
        return False
    sc.click(tab, "礼包页签")
    if not sc.wait("gift_page", 15):
        log("未进入礼包页")
        return False
    log("礼包页就绪")
    return True


def one_round(sc: kit.Screen) -> bool:
    if not goto_gift_page(sc):
        log("未能就绪到礼包页")
        sc.shot("gift_fail_nav")
        return False

    free = sc.find("gift_free")
    if free is None:
        if sc.find("gift_page") is not None:
            log("已在礼包页，但免费按钮不存在 → 今日免费礼包已领完(0/1)")
        else:
            log("未找到免费按钮")
        return False

    if sc.dry:
        log(f"[dry] 计划: 点免费礼包 {free} → 等广告/恭喜弹窗 → 领取 → 校验 gift_free 消失")
        return True

    sc.click(free, "免费")
    res = kit.ad_flow(sc, page="gift_page", timeout=FLOW_TIMEOUT)
    if res == "timeout":
        log("流程超时")
        sc.shot("gift_fail_timeout")
        return False

    sc.wait_gone("claim_btn", 6)
    if sc.find("gift_free") is None and sc.find("ad_close") is None:
        log("领取完成，免费按钮消失(→0/1) ✓")
        return True
    log("⚠ 已点领取，但免费按钮仍在 → 可能未成功")
    sc.shot("gift_afterclaim")
    return False


def run(sc: kit.Screen, args: kit.Args) -> bool:
    ok = one_round(sc)
    log(("成功" if ok else "未完成") + " / 免费礼包每日限购 1/1")
    return ok


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_gift", "商城免费礼包（每日 1/1）", run,
        plan=PLAN, prefix="gift_", lock_ttl=300,
    ))
