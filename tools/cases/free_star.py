#!/usr/bin/env python
"""用例: 寻宝 → 兑换 → 每日免费「红点四角金币」= 星辉。

链路(10-08 实测):
    寻宝页底部「兑换」页签 → 兑换页(星辉商店, 标志=「每周一0点重置星辉商店兑换次数」)
    → 左上插画里**带红点的四角金币**(星辉) → 点击 → 「恭喜获得 星辉」+ 领取
    → 回兑换页: 星辉 1089→1090、金币与红点**一起消失**

⚠ 判定用「金币在场」而不是「红点在场」: 实测领取后金币整颗消失(不是只掉红点)，
   所以金币检测做成双模板 —— ex_coin(本体, 无红点也认) + ex_coin_v2(含红点, 红点在时更独特)，
   任一变体命中即算未领。实测区分度: 未领 0.999 / 已领实机 0.443、0.366(阈值 0.85)。
⚠ 底栏「转盘」的红点 = 免费转盘次数可用(领完即消失)，与兑换/星辉无关，别被它带偏 ——
   本用例只看金币模板，不看红点。
⚠ 页面标志只能用 ex_shoptext: treasure_help(「说明」)在寻宝/转盘/兑换三页都有，区分不了。

用法:
    uv run python tools/cases/free_star.py [--max=1] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

CLAIM_TIMEOUT = 90
COIN_NAMES = ("ex_coin", "ex_coin_v2")   # 本体优先(红点没了也认)

PLAN = """[dry] 计划:
  首页 --(nav_treasure 寻宝)--> 寻宝页 --(ex_tab 底部页签)--> 兑换页(星辉商店)
  --> 插画里带红点的四角金币(ex_coin / ex_coin_v2, 本体优先) --> 「恭喜获得 星辉」--> 领取
  --> 校验: 金币+红点一起消失、仍在兑换页(still ex_shoptext)
  ⚠ 判「金币在场」而不是「红点在场」: 领取后整颗金币消失
  ⚠ 底栏「转盘」的红点与本用例无关"""


def goto_exchange_page(sc: kit.Screen) -> bool:
    """首页 → 寻宝 → 底部「兑换」页签；已在兑换页则直接返回。"""
    if sc.find("ex_shoptext") is not None:
        log("已在兑换页")
        return True

    if sc.find("treasure_help") is None:            # 不在寻宝系页面 → 先点首页「寻宝」
        nav = sc.find("nav_treasure")
        if nav is None:
            log("既不在兑换页，也找不到首页「寻宝」入口")
            return False
        if sc.dry:
            log("[dry] 计划: 点首页「寻宝」→ 等寻宝页 → 点底部「兑换」页签")
            return True
        sc.click(nav, "首页·寻宝")
        kit.nap(2.5)
        if sc.find("treasure_help") is None:
            log("点「寻宝」后没进寻宝页")
            return False

    tab = sc.find("ex_tab")
    if tab is None:
        log("寻宝页上找不到底部「兑换」页签")
        return False
    if sc.dry:
        log("[dry] 计划: 点底部「兑换」页签 → 进兑换页")
        return True
    sc.click(tab, "底部·兑换页签")
    kit.nap(2.5)
    ok = sc.find("ex_shoptext") is not None
    log("已进入兑换页" if ok else "未进入兑换页")
    return ok


def one_claim(sc: kit.Screen) -> bool:
    """一次领取。返回是否真的领到。"""
    coin, which = sc.find_any(COIN_NAMES)
    if coin is None:
        on_page = sc.find("ex_shoptext") is not None
        log(f"没找到红点四角金币(ex_shoptext={on_page}) → "
            f"{'今日已领/红点已清' if on_page else '不在兑换页?'}, 不点, 收工")
        return False
    if sc.dry:
        log(f"[dry] 计划: 点 {which} @({coin[0]},{coin[1]}) (score={coin[2]:.3f}) "
            f"→ 等「恭喜获得 星辉」→ 点领取 → 校验金币消失")
        return True

    sc.click(coin, f"红点四角金币({which})")
    if kit.ad_flow(sc, page="ex_shoptext", timeout=CLAIM_TIMEOUT) == "timeout":
        log("未等到「恭喜获得」/未点到领取 → 判定未成功")
        sc.shot("star_fail_noclaim")
        return False

    after = sc.look("ex_coin", "ex_coin_v2", "ex_shoptext")
    gone = after["ex_coin"] is None and after["ex_coin_v2"] is None
    if gone and after["ex_shoptext"] is not None:
        log("领取成功: 金币+红点已消失、仍在兑换页(星辉 +1) ✓")
        return True
    if gone:
        log("金币已消失, 但页面标志也丢了(可能弹出别的界面?) → 留证")
        sc.shot("star_after_unknown")
        return True
    log(f"⚠ 领取后金币仍在(ex_coin={after['ex_coin']}) → 可能未成功")
    sc.shot("star_after_still_there")
    return False


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if not goto_exchange_page(sc):
        log("未就绪到兑换页")
        sc.shot("star_fail_nav")
        return False
    done = 0
    for _ in range(max(1, args.max)):
        if one_claim(sc):
            done += 1
        else:
            break
        kit.nap(1.5)
    log(f"收尾: 完成 {done} 次; 状态={'兑换页' if sc.find('ex_shoptext') else '非兑换页'}")
    return done > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_star", "寻宝·兑换星辉（每日免费）", run,
        plan=PLAN, prefix="ex_", lock_ttl=600,
    ))
