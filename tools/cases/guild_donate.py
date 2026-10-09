#!/usr/bin/env python
"""用例: 战队捐献（金币 2000 / 钻石 50 各 3 次/天）。

链路:
    首页 --(gd_entry 战队入口)--> 战队页 --(gd_donate_entry 捐献)--> 捐献页
    --> 点**卡片底部的黄色支付键**(gd_gold_btn / gd_diamond_btn)
          金币: 直接「恭喜获得」
          钻石: 弹「确定要进行钻石捐献吗?」--> (勾「今日不再提示」) --> 确定
    -->「恭喜获得」--> claim_btn 领取 --> 回捐献页
    次数用完: 点后弹「XX捐献次数不足」(绿「确认」) --> 收掉 + 立即停手

    ⚠ 入口是卡片**底部黄键**，不是卡片正中（点正中打在插画/EXP 条上，毫无反应）
    ⚠ 确认弹窗与「次数不足」提示层都是**半透明遮罩**: 底下捐献页标志照样满血命中
      (gd_title 1.000 / gd_gold_btn 0.999) → 判层必须先把这两层挑出来，否则在模态上瞎点
    ⚠ 点击会丢（实测约一半首次点击被吞、页面毫无变化）→ 点后先等结果，
      **确认仍停在捐献页且没有任何弹层**才重试，最多 3 次 ⇒ 不会重复花钱
    ⚠ 勾选框用**颜色判态**（纯色小方块模板在捐献页会误命中 0.81+）:
      未勾=靛蓝(B≈219) / 已勾=整块黄(R≈255) / 无弹窗=深底(R≈73)

用法:
    uv run python tools/cases/guild_donate.py [--type gold|diamond|both] [--times N] [--all]
                                              [--no-back] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86            # 通用阈值
TH_CLAIM = 0.92      # 「领取」键: 很多页面都有同款，抬到 0.92 防串台
TH_BACK = 0.85       # 「返回」: 弹层/子页分数略降，用 0.85
TH_DLG = 0.88        # 确认弹窗标志「确定要进行」
TH_NOCNT = 0.88      # 提示层「捐献次数不足」/绿「确认」键
POPUP_WAIT = 10.0    # 点支付键后等「恭喜获得」/确认弹窗的最长秒数
BACK_WAIT = 10.0     # 点领取后等回捐献页的最长秒数
CLICK_TRIES = 3      # 支付键最多点几次(丢点击重试; 重试前必查状态, 不会重复捐)
# 勾选框内框(颜色判态)。坐标是在 812x1518 实帧 _guildtest_dialog{,_chk}.png 上量的:
# 两帧唯一差异连通块 = 53x53 中心(345,809)，框内 34x34 即 (331,791) → 归一到基准(347,792)。
_x, _y = _bot.client_to_ref(331, 791, 812, 1518)
CHK = (_x, _y, 34, 34)
ALL_MAX = 9          # --all 的上限(真上限由「点后没弹层」兜住, 这里只防死循环)

HOME, GUILD, DONATE, POPUP, DIALOG, NOCNT, UNKNOWN = ("HOME", "GUILD", "DONATE", "POPUP",
                                                      "DIALOG", "NOCNT", "?")

BTN = {
    "gold": ("gd_gold_btn", "金币捐献 2000"),
    "diamond": ("gd_diamond_btn", "钻石捐献 50"),
}

PLAN = """[dry] 计划:
  首页 --(gd_entry 战队入口)--> 战队页 --(gd_donate_entry 捐献)--> 捐献页
  --> 点卡片底部黄键(gd_gold_btn 2000 / gd_diamond_btn 50)
          金币: 直接「恭喜获得」
          钻石: 弹「确定要进行钻石捐献吗?」--> (勾「今日不再提示」) --> 确定
  -->「恭喜获得」--> claim_btn 领取 --> 回捐献页
  次数用完: 点后弹「XX捐献次数不足」(绿「确认」) --> 收掉 + 立即停手
  点后无任何弹窗且仍在捐献页 = 丢点击 => 最多重试 3 次(重试前必查状态，不会重复捐)
  重试后仍无弹窗 = 次数用尽/货币不足 => 立即停手
  收尾: 捐献页 X(gd_close) --> 战队页 返回(ral_back) --> 首页"""


def _chk_checked(sc: kit.Screen) -> bool | None:
    """「今日不再提示」是否已勾选(颜色判态，比纯色方块模板稳)。

    实测: 未勾 = 靛蓝空格(B≈219 G≈136 R≈18); 已勾 = 整块黄(R≈255 G≈252 B=0);
    没有弹窗时该处是深底(B≈122 R≈73) -> 返回 None。
    """
    x, y, w, h = CHK
    roi = sc.roi(x + 8, y + 8, w - 16, h - 16)
    if roi.size == 0:
        return None
    b, g, r = (float(roi[:, :, i].mean()) for i in range(3))
    if r > 180 and g > 180:
        return True
    if b > 150 and r < 90:
        return False
    return None


def state(sc: kit.Screen) -> str:
    """按页面标志判层: 确认弹窗/不足提示 > 恭喜获得弹层 > 捐献页 > 战队页 > 首页 > 未知。

    判层顺序要紧: 确认弹窗与「次数不足」提示层都只是**半透明遮罩**，底下捐献页的标志依然
    满血命中(gd_title 1.000 / gd_gold_btn 0.999) -> 必须先把这两层挑出来；
    「恭喜获得」是全屏暗幕(标题被压到 0.446)，用 claim_btn 命中且 gd_title 不命中判定。
    首页专属标志只能用 stage_btn(闯关模式)；nav_home 在子页也有(不可用)。
    """
    st = sc.look("gd_confirm_title", "gd_no_cnt_title", "gd_no_cnt_ok", "claim_btn",
                 "gd_title", "gd_donate_entry", "gd_entry", "stage_btn")
    d = st["gd_confirm_title"]
    if d is not None and d[2] >= TH_DLG:
        return DIALOG
    nt, no = st["gd_no_cnt_title"], st["gd_no_cnt_ok"]
    if (nt is not None and nt[2] >= TH_NOCNT) or (no is not None and no[2] >= TH_NOCNT):
        return NOCNT
    c = st["claim_btn"]
    if c is not None and c[2] >= TH_CLAIM and st["gd_title"] is None:
        return POPUP
    if st["gd_title"] is not None:
        return DONATE
    if st["gd_donate_entry"] is not None:
        return GUILD
    if st["stage_btn"] is not None:
        return HOME
    return UNKNOWN


def wait_state(sc: kit.Screen, want: str, timeout: float = BACK_WAIT,
               interval: float = 0.6, honest: bool = False) -> str:
    """等到达 want。honest=True 表示「真的到了」: 连续两次间隔 1.5s 都命中才算，
    避开弹层淡出动画期(状态已在捐献页、但底下还有隐形遮罩吞点击)。"""
    end = kit.time.time() + timeout
    while True:
        st = state(sc)
        if st == want:
            if not honest:
                return st
            kit.nap(1.5)
            if state(sc) == want:
                return st
        if kit.time.time() >= end:
            return st
        kit.nap(interval)


def _click_wait_result(sc: kit.Screen, hit, label: str) -> str:
    """点一次并等「有新弹层出现」，返回 POPUP/DIALOG/NOCNT/其它状态。

    丢点击对策: 支付键点击可能被吞(实测)，因此只在「点击后彻底没变化、且确认仍在捐献页」
    时才交给上层重试。若已出现任何弹层则立刻返回，绝不重点。
    """
    sc.click(hit, label)
    end = kit.time.time() + POPUP_WAIT
    while kit.time.time() < end:
        st = state(sc)
        if st in (POPUP, DIALOG, NOCNT):
            return st
        if st != DONATE:      # 跑到了别的层 -> 立即上报，不重试
            return st
        kit.nap(0.6)
    return state(sc)


def dismiss_nocnt(sc: kit.Screen) -> bool:
    """收掉「XX捐献次数不足」提示层(绿「确认」)—— 这是个明确的停止信号。"""
    hit = sc.find("gd_no_cnt_ok", TH_NOCNT)
    if hit is None:
        log("[warn] 提示层里找不到绿「确认」")
        sc.shot("fail_nocnt_ok")
        return False
    sc.click(hit, "确认(次数不足提示)")
    st = wait_state(sc, DONATE, timeout=6.0)
    log(f"  → {st}")
    return True


def handle_dialog(sc: kit.Screen, confirm: bool) -> bool:
    """确认弹窗: 把「今日不再提示」勾上(下次跳过)，然后确定/取消。

    没勾上就点一下勾选框 -> 后续轮次不再弹窗；已勾选/识别不到则直接继续。
    """
    st = _chk_checked(sc)
    if st is False:
        sc.click_base(CHK[0] + CHK[2] // 2, CHK[1] + CHK[3] // 2, "勾选「今日不再提示」")
        kit.nap(0.8)
    elif st is True:
        log("「今日不再提示」已勾选")
    else:
        log("[warn] 勾选框颜色判不出态，跳过勾选")
    key = "gd_confirm_ok" if confirm else "gd_cancel"
    hit = sc.find(key, TH)
    if hit is None:
        log(f"确认弹窗里找不到 {key}")
        sc.shot("fail_dialog_key")
        return False
    sc.click(hit, "确定" if confirm else "取消")
    return True


def enter_donate(sc: kit.Screen) -> bool:
    """从任意页进到捐献页: 首页→战队页→捐献页；已在捐献页/弹层则原路收拢。"""
    st = state(sc)
    log(f"当前状态 {st}")
    for _ in range(1, 5):
        if st == DONATE:
            return True
        if st == DIALOG:      # 残留弹窗: 取消掉(不花钱)，免得后面在弹窗上瞎点
            log("发现残留确认弹窗 → 先取消")
            handle_dialog(sc, confirm=False)
            st = wait_state(sc, DONATE, timeout=5.0)
            log(f"  → {st}")
            continue
        if st == NOCNT:       # 残留「次数不足」提示: 收掉
            log("发现残留「次数不足」提示层 → 收掉")
            dismiss_nocnt(sc)
            st = state(sc)
            continue
        if st == HOME:
            e = sc.find("gd_entry")
            if e is None:
                log("首页找不到「战队」入口(gd_entry)")
                sc.shot("fail_entry")
                return False
            sc.click(e, "战队入口")
            st = wait_state(sc, GUILD, timeout=6.0)
            log(f"  → {st}")
            if st == UNKNOWN:
                sc.shot("fail_after_entry")
                return False
            if st == HOME:          # 没点动(红点位置/动画)，再试一次
                continue
        if st == GUILD:
            d = sc.find("gd_donate_entry")
            if d is None:
                log("战队页找不到「捐献」(gd_donate_entry)")
                sc.shot("fail_donate_entry")
                return False
            sc.click(d, "捐献")
            st = wait_state(sc, DONATE, timeout=6.0)
            log(f"  → {st}")
            if st == UNKNOWN:
                sc.shot("fail_after_donate")
                return False
        if st == POPUP:
            c = sc.find("claim_btn", TH_CLAIM)
            if c is None:
                return False
            sc.click(c, "领取(残留弹层)")
            st = wait_state(sc, DONATE, timeout=6.0)
            log(f"  → {st}")
    log(f"进捐献页失败(停在 {st}, 步数用尽)")
    sc.shot("fail_enter")
    return False


def donate_once(sc: kit.Screen, kind: str) -> tuple[bool, str]:
    """点一次黄键 → (钻石:确认弹窗→确定) → 「恭喜获得」→ 领取 → 回捐献页。

    返回 (是否成功, 原因)。丢点击最多重试 CLICK_TRIES 次；
    一旦弹出「次数不足」提示层 → 立即收掉并停手(次数用尽的确切信号)。
    """
    name, label = BTN[kind]
    hit = sc.find(name)
    if hit is None:
        return False, f"找不到支付键({name})"

    st = UNKNOWN
    for attempt in range(1, CLICK_TRIES + 1):
        where = "" if attempt == 1 else f"(第 {attempt} 次)"
        st = _click_wait_result(sc, hit, f"{label} 支付键{where}")
        if st == DIALOG:
            log(f"  → 确认弹窗(第 {attempt} 次点击生效)")
            if not handle_dialog(sc, confirm=True):
                return False, "dialog"
            st = wait_state(sc, POPUP, POPUP_WAIT)
            break
        if st == NOCNT:
            log(f"  → 「捐献次数不足」提示层(第 {attempt} 次点击生效) = 今日次数已用完")
            dismiss_nocnt(sc)
            sc.shot(f"nocnt_{kind}")
            return False, "nocnt"
        if st == POPUP:
            break
        log(f"  点后无任何弹层且仍在捐献页 → 判定丢点击{where}")
        kit.nap(1.2)
    if st != POPUP:
        if st == NOCNT:
            dismiss_nocnt(sc)
            return False, "nocnt"
        log(f"点后未出现「恭喜获得」(现在 {st}) → 判定次数用尽/货币不足，停手")
        sc.shot(f"nopopup_{kind}")
        return False, "nopopup"

    pop = sc.find("claim_btn", TH_CLAIM) or sc.wait("claim_btn", 6.0, th=TH_CLAIM)
    if pop is None:
        log("弹层里找不到「领取」(claim_btn)")
        sc.shot(f"fail_claim_{kind}")
        return False, "claim"
    sc.click(pop, "领取(恭喜获得)")
    st = wait_state(sc, DONATE, BACK_WAIT, honest=True)
    if st != DONATE:
        log(f"[warn] 领取后没回到捐献页({st})")
        sc.shot(f"stuck_{kind}")
        return False, "stuck"
    return True, "ok"


def back_home(sc: kit.Screen) -> bool:
    """捐献页 → 战队页 → 首页。"""
    for _ in range(4):
        st = state(sc)
        if st == HOME:
            return True
        if st == DIALOG:
            handle_dialog(sc, confirm=False)
            kit.nap(1.5)
            continue
        if st == NOCNT:
            dismiss_nocnt(sc)
            kit.nap(1.0)
            continue
        if st == DONATE:
            c = sc.find("gd_close", TH_BACK) or sc.find("ral_back", TH_BACK)
            if c is None:
                log("捐献页找不到关闭/返回键")
                sc.shot("fail_back")
                return False
            sc.click(c, "关闭 X")
        elif st == POPUP:
            c = sc.find("claim_btn", TH_CLAIM)
            if c is None:
                return False
            sc.click(c, "领取(残留弹层)")
        elif st in (GUILD, UNKNOWN):
            b = sc.find("ral_back", TH_BACK)
            if b is None:
                log(f"{st}: 找不到「返回」")
                sc.shot("fail_back")
                return False
            sc.click(b, "返回")
        kit.nap(2.2)
    st = state(sc)
    log(f"收尾结束状态 {st}")
    return st == HOME


def parse_kinds(arg: str) -> list[str]:
    if arg == "both":
        return ["gold", "diamond"]
    if arg in BTN:
        return [arg]
    raise SystemExit(f"未知 --type {arg} (gold/diamond/both)")


def run(sc: kit.Screen, args: kit.Args) -> bool:
    kinds = parse_kinds(args.type or "gold")
    times = ALL_MAX if args.all else args.n_times(1)
    log(f"计划: {args.type or 'gold'} x{times} 次")

    st = state(sc)
    log(f"当前状态 {st}")
    if sc.dry:
        for k in kinds:
            n, label = BTN[k]
            if st == DONATE:
                hit = sc.find(n)
                log(f"[dry] {label}: " + (f"命中 {hit[:2]} score={hit[2]:.3f} → 会点它"
                                         if hit else "未命中"))
            else:
                log(f"[dry] {label}: 不在捐献页，需先进入(首页→战队→捐献)")
        log("[dry] 计划输出完毕(未点击)")
        return True

    if not enter_donate(sc):
        log("未能进入捐献页")
        return False

    done = 0
    for k in kinds:
        for i in range(1, times + 1):
            if state(sc) != DONATE:
                log(f"[warn] 第 {i} 次前状态 {state(sc)} ≠ 捐献页 → 停手")
                break
            _n, label = BTN[k]
            log(f"{label} 第 {i}/{times} 次")
            ok, why = donate_once(sc, k)
            if ok:
                done += 1
                log(f"  ✓ 捐献成功(累计 {done})")
            else:
                log(f"  停止: {why}")
                if why == "stuck":
                    back_home(sc)
                    log("异常中止(状态错位)，已尝试收尾")
                    return False
                break
        # 金币次数用尽不该拦着钻石 → 继续下一种
    log(f"本次成功捐献 {done} 次")
    ok = back_home(sc)
    log("收尾" + ("完成(已回首页)" if ok else "未确认回到首页，见日志"))
    return done > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "guild_donate", "战队捐献（金币 2000 / 钻石 50，各 3 次/日）", run,
        plan=PLAN, prefix="guild_", lock_ttl=300, th=TH,
    ))
