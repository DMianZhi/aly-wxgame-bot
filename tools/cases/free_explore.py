#!/usr/bin/env python
"""用例: 星际探索（快速探索免费/看广告领取，默认 3 轮）。

链路:
    首页 → 点星际探索(star_explore) → 打开面板(exp_close)
    → 若已探索满: 点绿色领取(exp_claim) → 恭喜弹窗(claim_btn) 领取
    → 点快速探索(exp_quick) → 快速探索弹窗
    → 弹窗内领取按钮两种形态:
          第1次: 绿色「免费领取」(exp_free) → 直接弹恭喜获得
          之后:  蓝色「▶领取」(exp_video)  → 播广告 → ad_rewarded → ad_close → 恭喜获得
    → 点恭喜弹窗领取(claim_btn) → 回弹窗(次数-1) → 重复 n 次
    → 关弹窗(exp_popup_close) → 关面板(exp_close) → 回首页

    ⚠ 阈值 0.90 起步: exp_claim(绿「领取」) 在「免费领取」上有 0.86 误匹配 → 抬到 0.93
    ⚠ 次数耗尽的特征: 弹窗开着但没有领取按钮 → 判定 exhausted 而不是失败

用法:
    uv run python tools/cases/free_explore.py [--max=3] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.90               # 本用例整页阈值高于默认 0.86
CLAIM_TH = 0.93         # exp_claim 需高阈值(与「免费领取」区分)
REWARD_TIMEOUT = 120    # 点领取后等广告+恭喜的最长时间(广告约 40s)

PLAN = """[dry] 计划:
  首页 --(star_explore 星际探索)--> 面板(exp_close)
  --> 若已探索满: exp_claim 领取 → 恭喜(claim_btn)
  --> exp_quick 快速探索 → 弹窗 → 绿 exp_free(直接发) / 蓝 exp_video(看广告) → 恭喜领取
  --> 重复 n 轮(默认 3) → 关弹窗(exp_popup_close) → 关面板(exp_close) → 回首页
  ⚠ exp_claim 阈值须 ≥0.93（在「免费领取」上会 0.86 误匹配）
  ⚠ 弹窗开着但无领取按钮 = 次数耗尽（不是失败）"""


def claim_button(sc: kit.Screen):
    """弹窗内当前领取按钮: 绿「免费领取」或 蓝「看广告领取」→ (名字, 命中)。

    ⚠ find_any 返回的是 (命中, 名字)，本函数按调用方约定换成 (名字, 命中)。
    2026-10-09 实跑事故: 返回顺序写反 → 调用方拿到 name=(x,y,score)、hit="exp_free"，
    `if hit is None` 判不出、随后 sc.click(hit) 把字符串当命中结果 → ValueError 崩溃。
    """
    hit, name = sc.find_any(("exp_free", "exp_video"))
    return name, hit


def handle_reward(sc: kit.Screen, idx: int) -> bool:
    """等广告/恭喜弹窗并完成领取。"""
    t0 = kit.time.time()
    closed_ad = False
    while kit.time.time() - t0 < REWARD_TIMEOUT:
        jno, adr, adc, cbtn = sc.look("jump_no", "ad_rewarded", "ad_close", "claim_btn").values()
        log(f"  第{idx}轮 t={kit.time.time() - t0:5.1f} 跳过卡={jno is not None} "
            f"已获奖励={adr is not None} 广告关闭={adc is not None} 恭喜领取={cbtn is not None}")

        if cbtn is not None:
            sc.click(cbtn, "恭喜弹窗-领取")
            return True
        if jno is not None:
            sc.click(jno, "不使用(跳过卡)")
        elif adr is not None and adc is not None and not closed_ad:
            sc.click(adc, "广告关闭")
            closed_ad = True
        kit.nap(1.5)

    log(f"第{idx}轮 等待奖励超时")
    sc.shot(f"explore_fail_reward{idx}")
    return False


def one_round(sc: kit.Screen, idx: int) -> str:
    """一轮。返回 \"done\" / \"exhausted\" / \"fail\"。"""
    name, hit = claim_button(sc)
    if hit is None:
        q = sc.find("exp_quick")
        if q is None:
            log(f"第{idx}轮: 领取按钮与快速探索均不存在 → 今日次数已耗尽")
            return "exhausted"
        if sc.dry:
            log(f"[dry] 第{idx}轮: 计划点快速探索 {q} → 等弹窗领取按钮 → 领取")
            return "done"
        sc.click(q, "快速探索")
        if not sc.wait("exp_free", 12) and not sc.wait("exp_video", 1):
            if sc.find("exp_popup_close") is not None:
                log(f"第{idx}轮: 弹窗已开但无领取按钮 → 今日次数已耗尽")
                return "exhausted"
            log(f"第{idx}轮: 快速探索未弹出弹窗")
            sc.shot(f"explore_fail_popup{idx}")
            return "fail"
        name, hit = claim_button(sc)

    what = "免费领取(绿)" if name == "exp_free" else "看广告领取(蓝)"
    log(f"第{idx}轮 领取按钮: {name} {hit}")
    if sc.dry:
        log(f"[dry] 第{idx}轮: 计划点 {what} → 等广告/恭喜弹窗 → 领取")
        return "done"

    sc.click(hit, what)
    return "done" if handle_reward(sc, idx) else "fail"


def close_panels(sc: kit.Screen) -> bool:
    """关弹窗 → 关面板 → 确认回首页。"""
    h = sc.find("exp_popup_close")
    if h is not None:
        sc.click(h, "快速探索弹窗X")
        kit.nap(1.5)
    h = sc.find("exp_close")
    if h is not None:
        sc.click(h, "星际探索面板X")
        kit.nap(2.0)
    back = sc.find("star_explore") is not None
    log("已回首页" if back else "未确认回到首页")
    return back


def run(sc: kit.Screen, args: kit.Args) -> bool:
    rounds = max(1, args.max)
    log(f"计划 {rounds} 轮")

    if sc.find("star_explore") is None:
        log("当前不在首页，先清理遗留弹窗/面板")
        close_panels(sc)
    if sc.find("star_explore") is None:
        kit.goto_home(sc)
    if sc.find("star_explore") is None:
        log("仍不在首页(找不到星际探索入口)")
        sc.shot("explore_fail_home")
        return False
    if sc.dry:
        log(f"[dry] 计划: 星际探索 → 快速探索 → 免费/看广告领取 → 恭喜领取 × {rounds}")
        return True

    if sc.find("exp_close") is None:
        entry = sc.find("star_explore")
        sc.click(entry, "星际探索")
        if not sc.wait("exp_close", 12):
            log("星际探索面板未打开")
            sc.shot("explore_fail_panel")
            return False

    ready = sc.find("exp_claim", th=CLAIM_TH)       # 已探索满 → 先领掉一桶收益
    if ready is not None:
        log("已探索满，先领取收益")
        sc.click(ready, "领取(已探索收益)")
        c = sc.wait("claim_btn", 12)
        if c is not None:
            sc.click(c, "恭喜弹窗-领取")
            kit.nap(2.5)

    done = 0
    for i in range(1, rounds + 1):
        st = one_round(sc, i)
        if st == "done":
            done += 1
            log(f"第{i}轮 完成 ({done}/{rounds})")
            kit.nap(1.5)
        elif st == "exhausted":
            log(f"停止: 今日快速探索次数已耗尽(共完成 {done} 轮)")
            break
        else:
            log(f"第{i}轮 失败 → 停止")
            break

    back = close_panels(sc)
    log(f"共完成 {done}/{rounds} 轮, {'已回首页' if back else '需人工确认页面'}")
    return done > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_explore", f"星际探索（快速探索，循环到次数耗尽）", run,
        # 上限 6 只是防呆: 「次数耗尽」检测(弹窗无领取键/入口键全无)会提前停 ——
    # 2026-10-10 用户抓到: 默认 3 轮打满就收工, 其实还剩 1 次没领
    plan=PLAN, prefix="explore_", lock_ttl=600, th=TH, default_max=6,
    ))
