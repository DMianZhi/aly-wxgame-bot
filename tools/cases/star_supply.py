#!/usr/bin/env python
"""用例: 逐星补给（逐星长阶 → 补给领5次 → ×5 逐星信标）。

链路:
    首页 --(stage_btn 闯关模式)--> 闯关页
    --(stage_stair 逐星长阶横幅)--> 逐星长阶页
    --(ss_entry 左下「逐星补给」)--> 逐星补给面板
         --(ss_claim5 领5次)--> 恭喜获得(黑匣密钥+金币) --(claim_btn 领取)--> 回面板
         --(ss_close 右上 X)--> 逐星长阶页
    --(ss_beacon 开始挑战上方的 ×5 装置，仅「可领」时存在)--> 恭喜获得(逐星信标×5)
         --(claim_btn 领取)--> 逐星长阶页
    --(wc_res_back 返回)--> 闯关页 --(返回)--> 首页

2026-10-08 实探事实（别再踩）:
    * 面板上的 `×1`/`×5` 是「领几次」**不是价格**: 每次 10 个逐星信标
      （实测 1021 → 971 = 领5次花 50，得 5×(黑匣密钥30 + 金币3000) = 密钥150 + 金币15000 ✓）
      → 领5次是**消耗**动作: 默认只做 1 次；**点后无覆盖层不重试**（防重复消耗）
    * ×5 装置 = 「逐星信标×5」领取点（右上计数器的图标就是逐星信标）:
      可领 = 装置带**红点**且在；已领 = **装置整个消失**（不是变灰，是没了）
      → 装置本身即「今日可领」判据（ss_beacon 命中 = 可领），领完再点**完全无反应**
    * 逐星补给面板是**半透明压暗**：底下的 ss_entry 在面板帧上仍 0.97 命中
      → 判层必须 **PANEL 先于 STAIR**
    * 目测按钮坐标会差 8px 点空（首点 (551,957) 落在按钮上方空白，毫无反应）
      → 一律用**颜色测真实 bbox** 再取中心（面板按钮基准 bbox: 橙 x487-735 / 蓝 x138-386, y969-1039）
    * `stage_stair` 横幅**美术会轮换**（旧「整横幅」模板只 0.589 命中）→ 已改成只裁
      「逐星长阶」文字（162x72）并同步 tools/crop/crop_stage.py

用法:
    uv run python tools/cases/star_supply.py [--dry] [--times N] [--no-back]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86             # 通用阈值（ss_entry 次高 0.58 / ss_claim5 次高 0.53）
TH_BEACON = 0.88      # ×5 装置（可领 1.00 / 已领 0.59 / 其它帧 ≤0.53）
TH_BTN = 0.90         # 「领5次」橙键（面板 1.00 / 其它帧 ≤0.53）
TH_CLOSE = 0.90       # 面板右上 X（面板 1.00 / 其它帧 ≤0.76）
TH_GIFT = 0.90        # 恭喜获得里的「领取」（复用 claim_btn，面板 0.41）
TH_STAIR = 0.86       # 逐星长阶横幅（新裁文字版：旧美术 0.89 / 当前 0.96~1.00）
TH_HOME = 0.90        # 首页「闯关模式」（stage_btn）
TH_BACK = 0.85        # 「返回」键（wc_res_back 在逐星长阶 0.976 / 闯关页 0.99，复用）
COUNTER = _bot.measured_rect(700, 203, 112, 67, (812, 1518))
# ↑ ×5 装置计数区 (x,y,w,h)。当年在 812x1518 实帧上量: 右边界正好贴窗口右沿(x=812) ——
#   归一后换算回去，任何尺寸下它依然贴右沿(@601 → 右边界=601)，这正是「右上计数区」该有的行为。
COUNTER_DIFF = 3.0    # 该区平均差 > 3 判「计数变了」（实测: 未变 0.0 / 变 10.2）
GIFT_WAIT = 8.0       # 点完等「恭喜获得」覆盖层的最长秒数（实测 1~2s）
BACK_WAIT = 8.0       # 覆盖层收掉后等页面稳定的最长秒数
CLICK_TRIES = 3       # ×5 装置丢点击重试上限（免费领取，重试安全）

HOME, STAGE, STAIR, PANEL, GIFT, UNKNOWN = "HOME", "STAGE", "STAIR", "PANEL", "GIFT", "?"

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 闯关页
  --(stage_stair 逐星长阶)--> 逐星长阶页
  --(ss_entry 左下逐星补给)--> 补给面板
  --(ss_claim5 领5次)--> 恭喜获得(黑匣密钥+金币) --(claim_btn 领取)--> 回面板
  --(ss_close X)--> 逐星长阶页
  --(ss_beacon ×5装置)--> 恭喜获得(逐星信标×5) --(claim_btn 领取)--> 逐星长阶页
  --(返回 x2)--> 首页
  消耗: 每次领5次 = 10 个逐星信标 ×5 次 = 50 个（默认只做 1 次）
  降级:
      领5次后无覆盖层  = 信标不足/触顶 或 点击被吞 => 不重试(防重复消耗)，记数停手
      ×5 装置不在      = 今日已领 => 跳过，不算失败
      装置在但点了没反应 = 丢点击 => 重试（免费，重试安全）"""


def counter_region(sc: kit.Screen):
    return sc.roi(*COUNTER).astype("int16")


def state(sc: kit.Screen) -> str:
    """按页面标志判层: 覆盖层 > 面板 > 逐星长阶 > 闯关页 > 首页 > 未知。

    顺序要紧: 补给面板是半透明压暗，底下的 ss_entry 在面板帧上依然 0.97 命中
    → 必须先把面板挑出来，否则会在面板上按「进面板」的逻辑瞎点。
    首页标志只能用 stage_btn（nav_home 在子页也命中）。
    """
    st = sc.look("claim_btn", "ss_claim5", "ss_entry", "stage_stair", "stage_btn",
                 "stage_event_lv")
    if st["claim_btn"] is not None:
        return GIFT
    if st["ss_claim5"] is not None:
        return PANEL
    if st["ss_entry"] is not None:
        return STAIR
    # 关卡页判层用**稳定标记** stage_event_lv(活动关卡按钮)：横幅美术 stage_stair 是
    # 最后才渲染的，关卡页刚切过去时只有按钮在(实测横幅 0.490 / 本标记 0.994)
    # → 只认横幅会把「渲染中」误判成未知页而中止。
    if st["stage_stair"] is not None or st["stage_event_lv"] is not None:
        return STAGE
    if st["stage_btn"] is not None:
        return HOME
    return UNKNOWN


def wait_state(sc: kit.Screen, want, timeout: float = BACK_WAIT,
               interval: float = 0.6) -> str:
    """等进入 want（可以是集合）里的某个状态；超时返回当前状态。"""
    want = {want} if isinstance(want, str) else set(want)
    end = kit.time.time() + timeout
    while True:
        st = state(sc)
        if st in want:
            return st
        if kit.time.time() >= end:
            return st
        kit.nap(interval)


def claim_gift(sc: kit.Screen) -> bool:
    """收掉「恭喜获得」覆盖层（点「领取」）。"""
    b = sc.find("claim_btn", TH_GIFT)
    if b is None:
        log("  覆盖层里找不到「领取」(claim_btn)")
        sc.shot("fail_gift_btn")
        return False
    sc.click(b, "领取(恭喜获得)")
    return True


def close_panel(sc: kit.Screen) -> bool:
    """关掉逐星补给面板（右上 X）→ 回逐星长阶页。"""
    x = sc.find("ss_close", TH_CLOSE)
    if x is None:
        log("面板上找不到右上 X(ss_close)")
        sc.shot("fail_close")
        return False
    sc.click(x, "关闭补给面板")
    return wait_state(sc, STAIR, BACK_WAIT) == STAIR


def enter_stair(sc: kit.Screen) -> bool:
    """任意页 → 逐星长阶页（残留覆盖层/面板先收掉；未知页**零点击**中止）。"""
    for i in range(6):
        st = state(sc)
        if st == STAIR:
            return True
        if st == GIFT:              # 残留覆盖层: 先领掉再看
            log("发现残留「恭喜获得」覆盖层 → 先收掉")
            if not claim_gift(sc):
                return False
            wait_state(sc, (PANEL, STAIR), BACK_WAIT)
            continue
        if st == PANEL:             # 残留面板: 先关掉
            log("发现残留补给面板 → 先关掉")
            if not close_panel(sc):
                return False
            continue
        if st == UNKNOWN:
            log("当前是认不出的页面 → 不瞎点，中止（请手动回首页后重跑）")
            sc.shot("fail_unknown_page")
            return False
        if st == STAGE:
            e = sc.find("stage_stair", TH_STAIR)     # 逐星长阶横幅
            what = "逐星长阶横幅"
        else:                                        # 走到这里只能是首页
            e = sc.find("stage_btn", TH_HOME)        # 闯关模式
            what = "闯关模式"
        if e is None:
            if st == STAGE:          # 关卡页横幅美术还没渲染出来 → 等下一圈再判
                log("关卡页横幅未就绪(美术加载中) → 等待重判")
                kit.nap(2.0)
                continue
            log(f"找不到入口({what})")
            sc.shot("fail_stair_entry")
            return False
        sc.click(e, f"{what}{'' if i == 0 else f'(第{i + 1}次)'}")
        kit.nap(2.2)      # 让页面切过去，下一圈再判层（丢点击也能自愈重试）
    log(f"进逐星长阶页失败(停在 {state(sc)})")
    sc.shot("fail_enter_stair")
    return False


def open_supply(sc: kit.Screen) -> bool:
    """逐星长阶页 → 补给面板（点左下的「逐星补给」）。"""
    st = state(sc)
    if st == PANEL:
        return True
    if st != STAIR:
        log(f"当前状态 {st} ≠ 逐星长阶页，开不了补给面板")
        sc.shot("fail_not_stair")
        return False
    e = sc.find("ss_entry", TH)
    if e is None:
        log("逐星长阶页找不到「逐星补给」入口(ss_entry)")
        sc.shot("fail_supply_entry")
        return False
    sc.click(e, "逐星补给")
    if wait_state(sc, PANEL, BACK_WAIT) != PANEL:
        log("点「逐星补给」后没看到面板")
        sc.shot("fail_supply_panel")
        return False
    return True


def one_supply(sc: kit.Screen) -> tuple[str, bool]:
    """点一次「领5次」。返回 (原因, 是否已领取)。

    ok        = 出覆盖层并领掉
    nocontent = 点后无覆盖层且计数没变（信标不足/触顶，或点击被吞）
                → **不重试**（领5次是消耗动作，宁可少领也不重复花钱）
    nocounter = 无覆盖层但计数变了（覆盖层被跳过/太快）→ 视为已领取
    """
    b = sc.find("ss_claim5", TH_BTN)
    if b is None:
        return "no_btn", False
    before = counter_region(sc)
    sc.click(b, "领5次")
    if wait_state(sc, GIFT, GIFT_WAIT) == GIFT:
        if not claim_gift(sc):
            return "gift_btn", False
        if wait_state(sc, (PANEL, STAIR), BACK_WAIT) not in (PANEL, STAIR):
            return "stuck", False
        return "ok", True
    diff = float(abs(counter_region(sc) - before).mean())
    if diff > COUNTER_DIFF:
        log(f"  无覆盖层但逐星信标计数变了(该区平均差 {diff:.1f}) → 视为已领取")
        return "nocounter", True
    log(f"  点后无覆盖层且计数没变(平均差 {diff:.1f}) → 信标不足/触顶？不重试(防重复消耗)")
    return "nocontent", False


def claim_beacon(sc: kit.Screen) -> tuple[str, bool]:
    """领「×5 逐星信标」。返回 (原因, 是否已领取)。

    absent = 装置不在（今日已领）→ 跳过，不算失败
    ok     = 领到并收掉覆盖层（含「覆盖层被跳过但装置已消失」）
    """
    if state(sc) != STAIR:
        log("不在逐星长阶页，先回去")
        if not enter_stair(sc):
            return "not_stair", False
    for attempt in range(1, CLICK_TRIES + 1):
        b = sc.find("ss_beacon", TH_BEACON)
        if b is None:
            return ("absent", False) if attempt == 1 else ("gone_no_gift", False)
        where = "" if attempt == 1 else f"(第 {attempt} 次)"
        sc.click(b, f"×5装置(逐星信标){where}")
        if wait_state(sc, GIFT, GIFT_WAIT) == GIFT:
            if not claim_gift(sc):
                return "gift_btn", False
            wait_state(sc, (STAIR, PANEL), BACK_WAIT)
            return "ok", True
        if sc.find("ss_beacon", TH_BEACON) is None:
            log("  装置已消失 → 视为已领取（覆盖层可能被跳过）")
            return "ok", True
        log(f"  装置仍在且无覆盖层{where} → 判定丢点击，重试")
        kit.nap(1.0)
    return "noluck", False


def run(sc: kit.Screen, args: kit.Args) -> bool:
    st = state(sc)
    log(f"当前状态 {st}")

    if sc.dry:
        e = sc.find("ss_entry", TH)
        log("[dry] 逐星长阶入口 ss_entry: " + (f"命中 {e[:2]} score={e[2]:.3f}" if e
                                            else "未命中（需先首页→闯关模式→逐星长阶）"))
        b = sc.find("ss_beacon", TH_BEACON)
        log("[dry] ×5 装置 ss_beacon: " + (f"命中 {b[:2]} score={b[2]:.3f} → 可领"
                                        if b else "未命中 → 今日已领/不在本页"))
        p = sc.find("ss_claim5", TH_BTN)
        log("[dry] 补给面板「领5次」: " + (f"命中 {p[:2]} score={p[2]:.3f}" if p
                                       else "未命中（面板未开）"))
        rounds = max(1, args.n_times(1))
        log(f"[dry] 计划领5次 {rounds} 次 = 消耗 {rounds * 50} 个逐星信标（每次 50）")
        log("[dry] 计划输出完毕(未点击)")
        return True

    if not enter_stair(sc):
        log("未能进入逐星长阶页")
        return False

    log("逐星长阶页就绪 | ×5装置: "
        + ("可领" if sc.find("ss_beacon", TH_BEACON) else "不在(今日已领)"))

    # ---- 第一段: 逐星补给 领5次（消耗动作，默认 1 次，失败不重试）----
    rounds = max(1, args.n_times(1))
    log(f"逐星补给 领5次 × {rounds}（每次 50 逐星信标，共 {rounds * 50}）")
    if not open_supply(sc):
        return False
    done = 0
    for i in range(1, rounds + 1):
        if state(sc) != PANEL:
            log(f"[warn] 第 {i} 次前状态 {state(sc)} ≠ 补给面板 → 停手")
            break
        log(f"领5次 第 {i}/{rounds} 次")
        why, got = one_supply(sc)
        if got:
            done += 1
            log(f"  ✓ 已领取（累计 {done}）")
            continue
        if why in ("no_btn", "gift_btn", "stuck"):
            log(f"  异常停止: {why}")
            sc.shot(f"fail_{why}")
            kit.goto_home(sc)
            return False
        log("  未领取 → 停手（不重试，防重复消耗）")
        break
    log(f"领5次完成 {done}/{rounds} 次")

    # ---- 第二段: ×5 逐星信标（免费，可重试）----
    if state(sc) == PANEL:
        if not close_panel(sc):
            log("关面板失败")
            sc.shot("fail_close_panel")
            kit.goto_home(sc)
            return False
    log("×5 装置 领逐星信标")
    why, got_beacon = claim_beacon(sc)
    if why == "absent":
        log("  ×5 装置不在 → 今日已领，跳过")
    elif got_beacon:
        log("  ✓ 已领取逐星信标×5")
    else:
        log(f"  异常停止: {why}")
        sc.shot(f"fail_beacon_{why}")
        kit.goto_home(sc)
        return False

    # ---- 收尾 ----
    ok = kit.goto_home(sc)
    log("收尾" + ("完成(已回首页)" if ok else "未确认回到首页，见日志"))
    # 领5次一次都没成 = 目标没达成（真异常已提前返回）
    return ok and done >= 1


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "star_supply", "逐星补给（领5次 + 领逐星信标×5）", run,
        plan=PLAN, prefix="star_", lock_ttl=420, th=TH, default_max=1,
    ))
