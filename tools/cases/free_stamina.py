#!/usr/bin/env python
"""用例: 免费体力（体力入口 → 弹窗 → 免费 → 广告 → 循环到次数耗尽）。

实测链路（2026-10-07）:
    - 跳过卡弹窗「是否使用PC端广告跳过卡」: 偶现，点「不使用」走真实广告
    - 广告在游戏窗口内全屏播放(黑底广告卡)，领奖后左上角出现「已获得奖励」，
      右上角出现「关闭」按钮，点击后回到体力购买弹窗，「免费」按钮重现
    - 「免费」按钮消失 = 点击被游戏接受(进入广告流程)；按钮重现 = 本轮完成

    ⚠ 点「免费」后先等按钮消失(12s)确认点击生效，再等 ad_rewarded(55s)
    ⚠ 弹窗已在场时不重复点入口(避免把弹窗点掉)
    ⚠ 次数用尽特征: 弹窗开着但没有「免费」按钮 → 收尾关弹窗(别留给下一个用例)

用法:
    uv run python tools/cases/free_stamina.py [--max=4] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

MAX_ROUNDS = 4            # 每日免费次数上限
ROUND_TIMEOUT = 75.0      # 单轮(含广告)超时秒数
JUMP_WAIT = 8.0           # 点免费后等跳过卡弹窗出现的秒数

PLAN = """[dry] 计划:
  首页 --(stamina_entry 体力入口)--> 体力购买弹窗(stamina_close)
  --> 点「免费」(stamina_free) --> [偶现跳卡弹窗 → 不使用(jump_no)]
  --> 等「免费」消失(点击被接受) --> 广告 → ad_rewarded + 关闭(ad_close)
  --> 等「免费」重现 = 本轮完成；最多 4 轮
  ⚠ 点击生效的判据是「免费」按钮消失，不是页面变化
  ⚠ 次数用尽特征: 弹窗开着但没有「免费」按钮 → 关弹窗收尾
  ⚠ 弹窗已在场则不重复点入口(否则会把弹窗点掉)"""


def goto_popup(sc: kit.Screen, idx: int) -> bool:
    """确保体力弹窗开着；已在场则不再点入口。"""
    if sc.find("stamina_close") is not None:
        return True
    entry = sc.find("stamina_entry")
    if entry is None:
        log(f"第{idx}轮: 找不到体力入口，放弃")
        return False
    sc.click(entry, "体力入口(stamina_entry)")
    if not sc.wait("stamina_close", 6):
        log(f"第{idx}轮: 弹窗没开出来")
        sc.shot(f"fs_fail_entry{idx}")
        return False
    return True


def close_popup(sc: kit.Screen) -> None:
    """收尾关弹窗(别把弹窗留给下一个用例)。"""
    x = sc.find("stamina_close")
    if x is not None:
        sc.click(x, "关闭弹窗(收尾)")


def one_round(sc: kit.Screen, idx: int) -> bool:
    log(f"== 第 {idx} 轮 ==")
    if not goto_popup(sc, idx):
        return False
    log("弹窗已开")

    free = sc.find("stamina_free")
    if free is None:
        log("没有「免费」按钮(次数用尽?) → 收尾")
        close_popup(sc)
        return False

    sc.click(free, "免费")
    if sc.dry:
        return True

    jno = sc.wait("jump_no", JUMP_WAIT)          # 跳过卡弹窗偶现
    if jno is not None:
        log("跳过卡弹窗出现 → 点「不使用」")
        sc.click(jno, "不使用(跳过卡)")
    else:
        log("无跳过卡弹窗，直接等广告结束")

    if not sc.wait_gone("stamina_free", 12):     # 按钮消失 = 点击被游戏接受
        log("点击后「免费」未消失 → 点击未生效")
        sc.shot(f"fs_stuck{idx}")
        return False

    adr = sc.wait("ad_rewarded", 55)
    if adr is not None:
        log("广告奖励到账 → 点「关闭」")
        x = sc.wait("ad_close", 10)
        if x is not None:
            sc.click(x, "广告关闭")
        else:
            log("没找到「关闭」按钮，等广告自动结束")
    else:
        log("未见广告奖励标记(可能直接回弹窗)")

    if sc.wait("stamina_free", ROUND_TIMEOUT):
        log("「免费」按钮重现，本轮完成 ✓")
        return True

    log("超时未重现(次数耗尽?)，收尾")
    close_popup(sc)
    sc.shot(f"fs_timeout{idx}")
    return False


def run(sc: kit.Screen, args: kit.Args) -> bool:
    rounds = min(max(1, args.max), MAX_ROUNDS)
    if sc.dry:
        entry = sc.find("stamina_entry")
        log(f"[dry] 计划: 体力入口({'已找到' if entry else '当前页未找到'}) → 免费 → "
            f"[跳卡弹窗/广告] → 等「免费」重现 × 最多 {rounds} 轮（上限 {MAX_ROUNDS}）")
        return True

    ok = 0
    for i in range(1, rounds + 1):
        if one_round(sc, i):
            ok += 1
            kit.nap(1.2)                          # 领取动画缓冲
        else:
            break                                 # 次数用尽或异常 → 停
    log(f"完成: 成功 {ok} 轮")
    return ok > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_stamina", "免费体力（最多 4 轮）", run,
        plan=PLAN, prefix="fs_", lock_ttl=600, default_max=1,
    ))
