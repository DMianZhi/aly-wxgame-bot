#!/usr/bin/env python
"""用例: 好友体力（每天一次「一键收赠」）。

链路:
    首页 --(friend_btn 小人 icon, 在「无尽模式」正上方一排的最左)--> 好友页
    --(fr_onekey 一键收赠)--> 回礼弹窗「成功向好友送出了体力 并收到以下回礼 ⚡+N」
        (fr_gift_title) --> 绿「确认」(gd_no_cnt_ok) / 右上 X(boss_flash_close)
    --> 回好友页 --(wc_res_back 返回)--> 首页

2026-10-08 实探事实（别再踩）:
    * 一次 一键收赠 = +150 体力（66/120 → **216/120**，可以超上限）
    * 底部「今日获赠体力次数: 0/30 → 30/30」；到 30/30 后再点**没有任何弹层**（静默无效，
      不是「次数不足」提示层）→ 所以判据只能是「点后有没有回礼弹窗」
    * 收赠后键上**红角标消失**（该区红像素 917 → 0）→ 用来区分「点击被吞」与「今日没得收」；
      同时好友列表的「互赠」黄键会变灰（页面状态，仅供人眼看）
    * 收赠前后 一键收赠键外观**逐像素完全相同**（平均差 0.0）→ 别想靠外观判「今日已领」
    * 「好友」标题牌是**通用页面标题牌**（其它页 0.883 误命中，踩过）→ 页面标志改用
      fr_counter（「今日获赠体力次数：」文字，刻意避开会变的数字）
    * 回礼弹窗**不遮**页面底部与标题（fr_onekey / fr_counter 在弹窗帧上仍 1.000 命中）
      → 判层必须**先弹窗后页面**

用法:
    uv run python tools/cases/friend_stamina.py [--dry] [--no-back] [--times N]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86            # 通用阈值（friend_btn / fr_counter）
TH_BTN = 0.90        # 一键收赠键（fr_onekey 判别力极强: 86 帧仅本页命中，可放心抬）
TH_POP = 0.90        # 回礼弹窗标志（fr_gift_title 次高才 0.362）
TH_OK = 0.88         # 弹窗里的绿「确认」/ X
TH_BACK = 0.85       # 「返回」键（wc_res_back 在好友页 1.000，复用现成模板）
BADGE = (_bot.client_to_ref(590, 1358, 812, 1518)
         + _bot.client_to_ref(652, 1414, 812, 1518))
# ↑ 一键收赠键右上红角标区。**(x0,y0,x1,y1) 四角点、基准口径** —— 与下面 has_badge 的
#   `sc.roi(x0,y0,x1-x0,y1-y0)` 配套；量自 812x1518 实帧(见 bot.client_to_ref)。
BADGE_MIN = 200      # 红像素 > 200 判定「有角标」（实测有=917 / 无=0）
POP_WAIT = 6.0       # 点完等回礼弹窗的最长秒数（实测 1.2s 内出现）
BACK_WAIT = 8.0      # 点确认/返回后等页面稳定的最长秒数
CLICK_TRIES = 3      # 丢点击重试上限（重试前必查角标，不会重复白点）

HOME, FRIEND, GIFT, UNKNOWN = "HOME", "FRIEND", "GIFT", "?"

PLAN = """[dry] 计划:
  首页 --(friend_btn 小人 icon)--> 好友页
  --(fr_onekey 一键收赠)--> 回礼弹窗「成功向好友送出了体力 并收到以下回礼 ⚡+N」
  --> 绿「确认」(gd_no_cnt_ok) 或右上 X(boss_flash_close) --> 回好友页
  --> 返回(wc_res_back) --> 首页
  点后无弹窗:
      键上红角标还在 = 点击被吞 => 重试(最多 3 次)
      红角标已消失   = 今日已满/无可收(静默无效) => 立刻停手，视为已完成
  收尾: 好友页 返回 --> 首页"""


def has_badge(sc: kit.Screen) -> bool:
    """一键收赠键右上是否还有红角标（颜色判态，比模板稳）。

    实测: 有角标 = 该区红像素 917; 收赠后 = 0; 弹窗压暗时 = 0。
    纯色小方块模板在这里会误命中，故走像素计数。
    """
    x0, y0, x1, y1 = BADGE
    roi = sc.roi(x0, y0, x1 - x0, y1 - y0).astype(int)
    if roi.size == 0:
        return False
    b, g, r = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    return int(((r > 150) & (g < 115) & (b < 115)).sum()) > BADGE_MIN


def state(sc: kit.Screen) -> str:
    """按页面标志判层: 回礼弹窗 > 好友页 > 首页 > 未知。

    顺序要紧: 回礼弹窗只压中屏，好友页的 fr_counter / fr_onekey 在弹窗下依然满血命中
    → 必须先把弹窗挑出来。首页标志只能用 stage_btn（nav_home 在子页也命中）。
    """
    st = sc.look("fr_gift_title", "fr_counter", "stage_btn")
    g = st["fr_gift_title"]
    if g is not None and g[2] >= TH_POP:
        return GIFT
    if st["fr_counter"] is not None:
        return FRIEND
    if st["stage_btn"] is not None:
        return HOME
    return UNKNOWN


def wait_state(sc: kit.Screen, want: str, timeout: float = BACK_WAIT,
               interval: float = 0.6) -> str:
    end = kit.time.time() + timeout
    while True:
        st = state(sc)
        if st == want:
            return st
        if kit.time.time() >= end:
            return st
        kit.nap(interval)


def dismiss_gift(sc: kit.Screen) -> bool:
    """收掉回礼弹窗（确认优先，退而求其次点右上 X）。"""
    ok = sc.find("gd_no_cnt_ok", TH_OK)
    if ok is None:
        ok = sc.find("boss_flash_close", TH_OK)
    if ok is None:
        log("  弹窗里找不到「确认」/X")
        sc.shot("fail_gift_btn")
        return False
    sc.click(ok, "确认(回礼弹窗)")
    return True


def enter_friend(sc: kit.Screen) -> bool:
    """首页 → 好友页（残留弹窗先收掉；未知页**零点击**中止）。"""
    for i in range(4):
        st = state(sc)
        if st == FRIEND:
            return True
        if st == GIFT:            # 残留回礼弹窗: 先收掉再看
            log("发现残留回礼弹窗 → 先收掉")
            if not dismiss_gift(sc):
                return False
            kit.nap(1.5)
            continue
        if st == UNKNOWN:
            # 未知页零点击（项目铁律: 页面认不出来就不许瞎点，免得误买）
            log("当前是认不出的页面 → 不瞎点，中止（请手动回首页后重跑）")
            sc.shot("fail_unknown_page")
            return False
        e = sc.find("friend_btn", TH)      # 走到这里只能是首页
        if e is None:
            log("首页找不到小人 icon(friend_btn)")
            sc.shot("fail_friend_entry")
            return False
        sc.click(e, f"小人 icon(好友入口){'' if i == 0 else f'(第{i + 1}次)'}")
        kit.nap(2.0)          # 让页面切过去，下一圈再判层（丢点击也能自愈重试）
    log(f"进好友页失败(停在 {state(sc)})")
    sc.shot("fail_enter_friend")
    return False


def onekey(sc: kit.Screen) -> tuple[bool, str]:
    """点一次「一键收赠」→ 回礼弹窗 → 确认 → 回好友页。

    返回 (是否达成, 原因):
      ok      = 收到回礼并确认
      nocontent = 点后无弹窗且角标已消失 = 今日已满/无可收（静默无效，正常收尾）
      noluck  = 连点 CLICK_TRIES 次都没弹窗且角标一直在（异常，非次数问题）
    """
    for attempt in range(1, CLICK_TRIES + 1):
        b = sc.find("fr_onekey", TH_BTN)
        if b is None:
            return False, "找不到一键收赠键(fr_onekey)"
        where = "" if attempt == 1 else f"(第 {attempt} 次)"
        sc.click(b, f"一键收赠{where}")
        if wait_state(sc, GIFT, POP_WAIT) == GIFT:
            if not dismiss_gift(sc):
                return False, "gift_btn"
            if wait_state(sc, FRIEND, BACK_WAIT) != FRIEND:
                return False, "stuck_after_gift"
            return True, "ok"
        if not has_badge(sc):
            log(f"  点后无弹窗且红角标已消失{where} → 今日已满/无可收（静默无效）")
            return False, "nocontent"
        log(f"  点后无弹窗但红角标仍在{where} → 判定丢点击")
        kit.nap(1.0)
    return False, "noluck"


def back_home(sc: kit.Screen) -> bool:
    """好友页 → 首页。"""
    for _ in range(4):
        st = state(sc)
        if st == HOME:
            return True
        if st == GIFT:
            if not dismiss_gift(sc):
                return False
        elif st == FRIEND:
            b = sc.find("wc_res_back", TH_BACK)
            if b is None:
                log("好友页找不到「返回」键")
                sc.shot("fail_back")
                return False
            sc.click(b, "返回")
        else:
            if not kit.goto_home(sc):
                return False
            continue
        kit.nap(2.0)
    st = state(sc)
    log(f"收尾结束状态 {st}")
    return st == HOME


def run(sc: kit.Screen, args: kit.Args) -> bool:
    st = state(sc)
    log(f"当前状态 {st}")

    if sc.dry:
        st = FRIEND if sc.find("fr_counter") else st
        e = sc.find("friend_btn", TH)
        log("[dry] 小人入口 friend_btn: " + (f"命中 {e[:2]} score={e[2]:.3f}" if e
                                            else "未命中（不在首页或入口变了）"))
        if st == FRIEND:
            b = sc.find("fr_onekey", TH_BTN)
            log("[dry] 一键收赠键: " + (f"命中 {b[:2]} score={b[2]:.3f}" if b
                                       else "未命中"))
            log(f"[dry] 键上红角标: {'有(有得收)' if has_badge(sc) else '无(今日已满/无可收)'}")
        else:
            log("[dry] 不在好友页：需先首页→小人 icon→好友页")
        log("[dry] 计划输出完毕(未点击)")
        return True

    goal = max(1, args.n_times(1))
    if not enter_friend(sc):
        log("未能进入好友页")
        return False

    log(f"好友页就绪，红角标: {'有' if has_badge(sc) else '无'}")
    done = 0
    hard_fail = False
    for i in range(1, goal + 1):
        if state(sc) != FRIEND:
            log(f"[warn] 第 {i} 次前状态 {state(sc)} ≠ 好友页 → 停手")
            break
        log(f"一键收赠 第 {i}/{goal} 次")
        ok, why = onekey(sc)
        if ok:
            done += 1
            log(f"  ✓ 已送出并收到回礼（累计 {done}）")
            continue
        if why == "nocontent":
            log("  今日已无待收（静默无效）→ 视为已完成")
            break
        log(f"  异常停止: {why}")
        sc.shot(f"fail_{why}")
        if why in ("stuck_after_gift", "gift_btn"):
            back_home(sc)
            return False
        hard_fail = True
        break
    log(f"本次收到回礼 {done} 次")
    ok = back_home(sc)
    log("收尾" + ("完成(已回首页)" if ok else "未确认回到首页，见日志"))
    # 没收到回礼不算失败（今日已满/无可收本来就是「点一下没反应」的静默态），
    # 但连点被吞 / 找不到键 = 真异常，必须报失败
    return ok and not hard_fail


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "friend_stamina", "好友体力（每日一键收赠）", run,
        plan=PLAN, prefix="friend_", lock_ttl=300, th=TH,
    ))
