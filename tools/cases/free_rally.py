#!/usr/bin/env python
"""用例: 十年集结（召集宝箱 Lv15 + 发弹幕）。

实测链路(2026-10-08):
    首页 → (寻宝正下方) 第一张卡 是视频 banner(整帧都在动/无固定文字) →
           第二张「十年集结」金卡 → 十年集结页
    集结页: 右下带红点宝箱(ral_chest) → 召集宝箱弹窗
    弹窗:  点 Lv15 大宝箱(ral_lv15, 未领态) → 「恭喜获得」(claim_btn) → 领取
           奖励: 强化魔方x3 + 金币5000 + 钻石50; 领完箱盖打开、红点消失、「今日可领取次数 0/1」
    弹窗「返回」(ral_back) → 回集结页
    集结页「发弹幕」(ral_wish) → 弹幕面板(ral_danmu_bar)
    面板第 1 条「发送」(ral_send) → 面板关闭 = 已发出(每日首次 +10 钻石)
    「返回」(ral_back) → 首页

坑 (都实测过):
    * 首页右侧活动卡是**轮播**的: 旧帧同位置是「雷霆集结/游戏圈」，金卡不在固定位置也不总在屏。
      点「寻宝下方第一张卡」(动态视频 banner，无固定字体) = **翻到下一组活动卡** → 金卡才出现。
      (曾经误判为「无反应」: 它不跳页，只是把右边那列活动卡翻页 → 所以不能靠"页面变了"判定。)
      → 金卡已在屏就直接点；否则点第一张卡翻页 + 轮询金卡，最多 3 次；翻页后若已离开首页则中止。
    * 入口模板 ral_card 取**整张金卡**(正例 1.000 / 负例 ≤0.384)；几何偏移仅用于定位第一张卡。
    * 「返回」按钮在集结页与召集宝箱弹窗里**同款同位置**，只看模板分不出层级 →
      必须用页面标志判层；弹窗里分数略降(0.894 vs 1.000)，故阈值 0.85。
    * Lv15 宝箱模板用**未领态**裁: 领取后箱盖打开，分数掉到 0.34 → 「不命中」正好当「今日已领」判据。
    * 宝箱红点领完消失 → 宝箱模板只裁白盒本体(红点掉了也认)。
    * 「发弹幕」按钮右上角红点会随已发消失 → 模板只裁 y>=1072 的文字带(天然避开红点)。
    * 弹幕是动态的，会飞过标题 → 集结页标志 ral_title 是静态文字部分，且与 ral_wish 互为备份。
    * 首页**不能**用 nav_home / nav_treasure 判: 实测 nav_home 在寻宝/兑换/转盘三个子页都是
      0.978(子页顶部也有同款返回首页键)，nav_treasure 在子页 0.987。
      首页专属标志只有 stage_btn(闯关模式): 首页 0.992 / 其余页 ≤ 0.516。

用法:
    uv run python tools/cases/free_rally.py [--dry] [--no-wish]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.85          # 通用阈值
TH_WISH = 0.88     # 「发弹幕」: 非本页最高 0.735，抬到 0.88 更稳
TH_BACK = 0.85     # 「返回」: 弹窗层 0.894，低于通用 0.86 会漏

REF_H = 1518               # 入口偏移量基于 812x1518 实测
CARD1_DY = 122             # 「寻宝下方第一张卡」(活动卡轮播翻页区) 相对寻宝入口的 y 偏移
CARD_TAPS = 3              # 最多翻几次活动卡轮播
CARD_POLL = 10.0           # 每次翻页后轮询金卡的最长秒数

HOME, RALLY, CHEST, DANMU, UNKNOWN = "HOME", "RALLY", "CHEST", "DANMU", "?"

PLAN = """[dry] 计划(全链路):
  首页 → 第一张卡(动态视频banner, 寻宝入口正下方) → 验证未进页 → 「十年集结」金卡 → 集结页
  → 右下宝箱(ral_chest) → 召集宝箱弹窗 → Lv15 宝箱(ral_lv15) → claim_btn 领取
  → 返回(ral_back) → 集结页 → 发弹幕(ral_wish) → 弹幕面板 → 第 1 条发送(ral_send)
  → 返回(ral_back) → 首页
  (已领态: ral_lv15 不命中 → 自动跳过开箱；弹幕面板已开 → 直接发送)
  ⚠ 金卡不在固定位置且不总在屏 —— 靠翻「寻宝下方第一张卡」轮播 + 轮询
  ⚠ 「返回」在集结页与弹窗同款同位置 → 必须判层，否则会在弹窗里误点"""


def state(sc: kit.Screen) -> str:
    """按页面标志判层: 弹幕面板 > 召集宝箱弹窗 > 集结页 > 首页 > 未知。

    层级顺序不能反: 弹幕面板压在集结页上(标题仍可见)，宝箱弹窗把标题替掉。
    """
    st = sc.look("ral_danmu_bar", "ral_chest_title", "ral_title", "ral_wish", "stage_btn")
    if st["ral_danmu_bar"] is not None:
        return DANMU
    if st["ral_chest_title"] is not None:
        return CHEST
    if st["ral_title"] is not None:
        return RALLY
    w = st["ral_wish"]
    if w is not None and w[2] >= TH_WISH:
        return RALLY
    if st["stage_btn"] is not None:
        return HOME
    return UNKNOWN


def poll(sc: kit.Screen, name: str, min_score: float = TH, timeout: float = CARD_POLL,
         interval: float = 0.8):
    """轮询等模板出现(用于活动卡轮播后等金卡翻上来)。"""
    end = kit.time.time() + timeout
    while True:
        hit = sc.find(name, th=min_score)
        if hit is not None:
            return hit
        if kit.time.time() >= end:
            return None
        kit.nap(interval)


def enter_rally(sc: kit.Screen) -> bool:
    """首页 → 十年集结页（含活动卡轮播翻页）。"""
    if state(sc) == RALLY:
        log("已在十年集结页")
        return True

    card = sc.find("ral_card", th=TH)
    nav = sc.find("nav_treasure", th=TH)
    k = sc.h / REF_H
    p1 = (nav[0], nav[1] + round(CARD1_DY * k)) if nav else None

    if card is None:
        if p1 is None:
            log("既找不到寻宝入口也找不到金卡(不在首页?)")
            return False
        for attempt in range(1, CARD_TAPS + 1):
            if state(sc) != HOME:
                log("翻页前已不在首页 → 中止，不盲点")
                sc.shot("fail_card1")
                return False
            sc.click_at(p1[0], p1[1], f"寻宝下方第一张卡(翻活动卡轮播 {attempt}/{CARD_TAPS})")
            card = poll(sc, "ral_card", TH)
            if card is not None:
                log(f"轮播已翻到「十年集结」金卡 {card[:2]} score={card[2]:.3f}")
                break
        if card is None:
            log(f"翻了 {CARD_TAPS} 次仍未出现「十年集结」金卡 → 中止")
            sc.shot("fail_card2")
            return False
    else:
        log(f"「十年集结」金卡已在屏 {card[:2]} score={card[2]:.3f}")

    sc.click(card, "「十年集结」金卡")
    kit.nap(4.0)
    st = state(sc)
    log(f"点金卡后 → {st}")
    if st == RALLY:
        return True
    sc.shot("fail_card2")
    return False


def do_chest(sc: kit.Screen) -> bool:
    """集结页 → 右下宝箱 → 召集宝箱弹窗 → Lv15 开箱领取 → 返回集结页。"""
    if state(sc) != CHEST:
        ch = sc.find("ral_chest", th=TH)
        if ch is None:
            log("找不到右下宝箱(ral_chest)")
            return False
        sc.click(ch, "右下宝箱(带红点)")
        kit.nap(3.0)
        st = state(sc)
        log(f"点宝箱后 → {st}")
        if st != CHEST:
            log(f"未进入召集宝箱弹窗({st}) → 中止")
            sc.shot("fail_chest")
            return False

    lv = sc.find("ral_lv15", th=TH)
    if lv is None:
        log("Lv15 宝箱未命中(箱盖已打开 = 今日已领) → 跳过开箱")
    else:
        sc.click(lv, "Lv15 大宝箱")
        kit.nap(2.5)
        c = sc.wait("claim_btn", 6)
        if c is None:
            log("点了 Lv15 但未出现「恭喜获得」→ 可能今日已领，继续后续步骤")
            sc.shot("lv15_noresult")
        else:
            sc.click(c, "领取(恭喜获得)")
            kit.nap(2.5)
            again = sc.find("ral_lv15", th=TH)
            if again is None:
                log("Lv15 领取完成 ✓ (校验: 箱盖已开，ral_lv15 不再命中)")
            else:
                log(f"[warn] 点过领取，但宝箱仍命中 {again[2]:.3f} → 可能未真正领到")
            sc.shot("claimed")

    bk = sc.find("ral_back", th=TH_BACK)
    if bk is None:
        log("弹窗里找不到「返回」→ 中止")
        sc.shot("fail_back")
        return False
    sc.click(bk, "返回(弹窗 → 集结页)")
    kit.nap(2.5)
    st = state(sc)
    log(f"返回后 → {st}")
    if st != RALLY:
        log(f"没回到集结页({st}) → 中止后续")
        sc.shot("fail_backto_rally")
        return False
    return True


def do_danmu(sc: kit.Screen) -> bool:
    """集结页 → 发弹幕 → 发送(每日首次 +10 钻石) → 回集结页。"""
    if state(sc) != DANMU:
        ws = sc.find("ral_wish", th=TH_WISH)
        if ws is None:
            log("找不到「发弹幕」(ral_wish)")
            return False
        sc.click(ws, "发弹幕")
        kit.nap(2.5)
        st = state(sc)
        log(f"点发弹幕 → {st}")
        if st != DANMU:
            log(f"弹幕面板未出现({st}) → 中止")
            sc.shot("fail_danmu")
            return False

    sd = sc.find("ral_send", th=TH)
    if sd is None:
        log("弹幕面板里找不到「发送」(ral_send)")
        sc.shot("fail_send")
        return False
    sc.click(sd, "发送(第 1 条)")
    kit.nap(3.0)
    st = state(sc)
    log(f"发送后 → {st}")
    if st == RALLY:
        log("弹幕已发出 ✓ (面板已关闭)")
        sc.shot("sent")
        return True
    log(f"[warn] 发送后面板未关闭({st})")
    sc.shot("sent_odd")
    return False


def back_home(sc: kit.Screen) -> bool:
    if state(sc) != RALLY:
        log("当前不在集结页，不自动返回")
        return False
    bk = sc.find("ral_back", th=TH_BACK)
    if bk is None:
        log("找不到「返回」")
        return False
    sc.click(bk, "返回(集结页 → 首页)")
    kit.nap(3.0)
    st = state(sc)
    log(f"返回后 → {st}")
    return st == HOME


def run(sc: kit.Screen, args: kit.Args) -> bool:
    no_wish = bool(args.extra.get("no_wish"))
    st = state(sc)
    log(f"当前状态 {st}")
    if sc.dry:
        log(f"[dry] 活动卡轮播: ral_card "
            f"{'已在屏' if sc.find('ral_card', th=TH) else '不在屏(会点第一张卡翻页，最多 %d 次)' % CARD_TAPS}"
            f" → 金卡 → 宝箱 → Lv15 → 领取 → 返回 → 发弹幕 → 发送 → 返回首页"
            + ("（--no-wish: 跳过发弹幕）" if no_wish else ""))
        return True

    if st == HOME and not enter_rally(sc):
        log("未能进入十年集结页")
        return False
    if state(sc) == UNKNOWN:
        log("当前是未知页面 → 中止")
        sc.shot("unknown")
        return False

    chest_ok = do_chest(sc)
    if chest_ok and not no_wish:
        do_danmu(sc)
    elif not chest_ok:
        log("召集宝箱流程未完成，跳过发弹幕(避免在错误层级盲点)")
    back_home(sc)
    log("收尾完成")
    return chest_ok


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_rally", "十年集结（召集宝箱 Lv15 + 发弹幕）", run,
        plan=PLAN, prefix="rally_", lock_ttl=300, th=TH, extra=("--no-wish",),
    ))
