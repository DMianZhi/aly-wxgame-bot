#!/usr/bin/env python
"""用例: 免费体力（体力入口 → 弹窗 → 免费 → 广告 → 循环到次数耗尽）。

实测链路（2026-10-07）:
    - 跳过卡弹窗「是否使用PC端广告跳过卡」: 偶现，点「不使用」走真实广告
    - 广告在游戏窗口内全屏播放；**右上角「关闭」文字在播放中就已经在了**
      （2026-10-14 实测 _run/_adstart_*.png 文字层 0.86~0.98），点了即回体力弹窗
    - 「免费」按钮消失 = 点击被游戏接受(进入广告流程)；按钮重现 = 本轮完成

    ⚠ **广告全流程有两步旧代码都没有**（2026-10-14 真帧实测定的病根）:
      ① 广告页要**点「关闭」** —— 有的皮肤压根不显示「已获得奖励」(ad_rewarded)，
         而「关闭」**播放中就已经在**（_run/_adstart_10.png 文字层 0.98）→ 旧代码
         把 ad_rewarded 当唯一出口，傻等 55s 后判定失败、**从不点关闭**；
      ② 关掉广告页后还有一张「**恭喜获得**(扫荡卡×3)」结算页，必须**点「领取」**
         （_claimprobe_t0→t1 真帧验证: 点领取后 stamina_entry 0.973 回首页）。
      两步漏掉 → 收尾时既不是首页、也没有游戏返回键 → goto_home「找不到返回键，
      停手」→ **后面 2~5 号用例全报「找不到商城入口/不在首页」，一个广告连坐一整轮**。
      现在整段交给 kit.ad_flow（跳卡/关广告/领取三态；它另有「仅凭关闭」的 40s 兜底）。
    ⚠ 点「免费」后先等按钮消失(12s)确认点击生效
    ⚠ 弹窗已在场时不重复点入口(避免把弹窗点掉)；判「弹窗在场」必须用 POPUP_TH=0.95
      —— 默认 0.86 时首页右侧轮播区偶尔能让 stamina_close 配到 0.904（真弹窗 0.998）
    ⚠ 次数用尽特征: 弹窗开着但没有「免费」按钮 → 收尾关弹窗；或广告后弹窗直接被游戏收掉
      （免费额度 0 时实测如此）→ 立即收尾，不去点首页
    ⚠ 灰色「免费」按钮只匹配 0.73（<0.86）→ 天然满足「没有免费按钮」判据

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
AD_TIMEOUT = 90.0         # 广告全链路超时（点「免费」→ 关闭 → 领取；广告 ≤35s）
# 弹窗在场判据阈值：真弹窗里 stamina_close=0.998（实测 2026-10-09），
# 但首页右侧轮播区偶尔能让它配到 0.904（≥默认 0.86）→ 会用默认阈值会误判
# 「弹窗已开」而跳过点入口、并在收尾时盲点首页。两边分得开，取 0.95。
POPUP_TH = 0.95
# 2026-10-10 美术轮换: 真弹窗上 stamina_close 实测掉到 0.905(位置不变) ——
# 与首页轮播假阳性 0.904 完全重叠, X 单模板再也分不开。
# 辅助判据 sweep_close(弹窗右上角同款 X, (750,415)): 弹窗两版实测 0.970/0.994, 首页 <0.90。
POPUP_TH_LOOSE = 0.88
POPUP_AUX_TH = 0.90

PLAN = """[dry] 计划:
  首页 --(stamina_entry 体力入口)--> 体力购买弹窗(stamina_close)
  --> 点「免费」(stamina_free) --> [偶现跳卡弹窗 → 不使用(jump_no)]
  --> [kit.play_ad: 广告 → 点「关闭」→ 「恭喜获得」领取]
  --> 等「免费」重现 = 本轮完成；最多 4 轮
  ⚠ 「关闭」播放中就已经在（文字层 0.86~0.98）；「已获得奖励」部分皮肤不显示
     → 不能当唯一出口；关掉广告页后还有「恭喜获得」要**点领取**（2026-10-14 病根）
  ⚠ 次数用尽特征: 弹窗开着但没有「免费」按钮 → 关弹窗收尾
  ⚠ 弹窗已在场则不重复点入口(否则会把弹窗点掉)"""


def popup_open(sc: kit.Screen) -> bool:
    """弹窗是否真在场：X 主判据(0.95) + 美术轮换辅助判据(sweep_close ≥0.90)。"""
    if sc.find("stamina_close", th=POPUP_TH) is not None:
        return True
    return sc.find("sweep_close", th=POPUP_AUX_TH) is not None


def _popup_x(sc: kit.Screen):
    """弹窗的关闭 X: 主模板(≥0.88, 美术轮换后真弹窗 0.905) → 通用 X(sweep_close)。"""
    x = sc.find("stamina_close", th=POPUP_TH_LOOSE)
    if x is not None:
        return x
    return sc.find("sweep_close", th=POPUP_AUX_TH)


def goto_popup(sc: kit.Screen, idx: int) -> bool:
    """确保体力弹窗开着；已在场则不再点入口。"""
    if popup_open(sc):
        return True
    entry = sc.find("stamina_entry")
    if entry is None:
        log(f"第{idx}轮: 找不到体力入口，放弃")
        return False
    sc.click(entry, "体力入口(stamina_entry)")
    deadline = kit.now() + 6.0
    while kit.now() < deadline:
        if popup_open(sc):
            return True
        kit.nap(0.5)
    log(f"第{idx}轮: 弹窗没开出来")
    sc.shot(f"fs_fail_entry{idx}")
    return False


def close_popup(sc: kit.Screen) -> None:
    """收尾关弹窗(别把弹窗留给下一个用例)。

    ⚠ 必须先过 popup_open 这道门(强判据)再点 X: _popup_x 的松阈值 0.88 在首页
    轮播假阳性帧上也会命中(0.897) —— 直接点就复发了「盲点首页」老 bug(自检②锁的)。
    点了之后复查, 还开着就换另一个 X 再点(丢点击重试)。
    """
    if not popup_open(sc):
        return
    first = _popup_x(sc)
    if first is None:
        return
    sc.click(first, "关闭弹窗(收尾)")
    kit.nap(1.5)
    if not popup_open(sc):
        return
    second = sc.find("sweep_close", th=POPUP_AUX_TH) if first[0] < 730 \
        else sc.find("stamina_close", th=POPUP_TH_LOOSE)
    if second is not None:
        sc.click(second, "关闭弹窗(收尾·备用X)")


def one_round(sc: kit.Screen, idx: int) -> str:
    """跑一轮。返回 'ok' | 'exhausted'(次数已用完) | 'fail'(异常)。

    ⭐ 区分 exhausted 与 fail: 批量跑时「今天次数已用完」是**正常结束**，
      不该报成未达成（2026-10-14: 次数用尽被算成 code=1，看上去像用例坏了）。
    """
    log(f"== 第 {idx} 轮 ==")
    if not goto_popup(sc, idx):
        return "fail"
    log("弹窗已开")

    free = sc.find("stamina_free")
    if free is None:
        log("没有「免费」按钮(次数用尽?) → 收尾")
        close_popup(sc)
        return "exhausted"

    if sc.dry:
        log(f"[dry] 轮{idx}: 会点「免费」→ 广告 → 关闭/领取 → 等「免费」重现")
        return "ok"

    # 广告全链路（点「免费」→ 跳卡弹窗 → 关广告页 → 「恭喜获得」领取 → 回体力弹窗）
    #   2026-10-14 抽成公共封装 kit.play_ad：free_stamina / free_sweep 原先各写一套，
    #   都漏了「关闭」和「领取」两步（病根: 只等 ad_rewarded，部分广告皮肤压根不显示它）。
    res = kit.play_ad(sc, entry="stamina_free", page="stamina_free",
                      label="免费体力", timeout=AD_TIMEOUT)
    log(f"广告流程: {res}")
    if res == "ok":
        log("「免费」按钮重现，本轮完成 ✓")
        return "ok"
    # 次数用尽: 入口已不存在 或 弹窗被游戏自己收掉
    if res == "no_entry" or (not popup_open(sc) and kit.is_home(sc)):
        log("没有「免费」入口 / 弹窗已被游戏收掉（次数用尽）→ 收尾")
        close_popup(sc)
        return "exhausted"
    log(f"广告流程异常({res}) → 收尾")
    kit.close_ad_page(sc)                    # 兜底: 广告页/结算页先清掉, 否则 goto_home 会停手
    close_popup(sc)
    sc.shot(f"fs_timeout{idx}")
    return "fail"


def run(sc: kit.Screen, args: kit.Args) -> bool:
    rounds = min(max(1, args.max or 1), MAX_ROUNDS)
    if sc.dry:
        entry = sc.find("stamina_entry")
        log(f"[dry] 计划: 体力入口({'已找到' if entry else '当前页未找到'}) → 免费 → "
            f"[跳卡弹窗/广告] → 等「免费」重现 × 最多 {rounds} 轮（上限 {MAX_ROUNDS}）")
        return True

    ok = 0
    exhausted = False
    for i in range(1, rounds + 1):
        r = one_round(sc, i)
        if r == "ok":
            ok += 1
            kit.nap(1.2)                          # 领取动画缓冲
        elif r == "exhausted":
            log("今日免费次数已用完 → 正常结束")
            exhausted = True
            break
        else:
            break                                 # 异常 → 停
    kit.close_ad_page(sc)   # ⚠ 广告页必须先关: 否则 goto_home 找不到返回键、直接停手
                            #   （2026-10-14 实测: 一个广告连坐后面 4 个用例）
    close_popup(sc)     # ⚠ 没打满额度就退出时弹窗还开着(2026-10-10: 不压暗、stage_btn 满血,
                        #   is_home 照样判 True → 后续用例的商城入口全被盖住)
    log(f"完成: 成功 {ok} 轮" + ("（次数已用尽）" if exhausted else ""))
    return ok > 0 or exhausted      # 次数已用尽 = 正常结束, 不算未达成


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_stamina", "免费体力（最多 4 轮）", run,
        plan=PLAN, prefix="fs_", lock_ttl=600,
        default_max=4,     # 4 次/日全领(2026-10-11 批量实测: 旧默认 1 只领 1 次剩 3 次)
    ))
