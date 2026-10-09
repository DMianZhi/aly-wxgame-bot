#!/usr/bin/env python
"""用例: 扫荡关卡（快速扫荡，普通 5/5 + 英雄 5/5，吃「双倍奖励」广告）。

链路:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_sweep 快速扫荡)--> 扫荡面板
    --> 切模式(普通/英雄) --> 普通模式选「4星材料」页签 --> 选材料类型
    --> 点最上面的可用行「扫荡」(sweep_btn) --> 「双倍奖励」(sweep_double)
    --> 看广告(ad_rewarded 出现才关) --> 关「扫荡完成」弹层(点空白) --> 下一轮

    ⚠ 面板顶部 4 个材料图标**按计数升序**(实测 711<763<810<831) → 默认点第 1 个(材料最少)，
      --material=N 指定，--material=0 保持「全部」
    ⚠ 「双倍奖励」是**每关每日限次** → 某关没翻倍机会时**换下一关继续**，
      连续 3 关都没有才收工（额度耗尽当天验不满是正常的，先看额度再判脚本好坏）
    ⚠ 关结算弹层点空白可能**连带关掉整个面板** → 每轮开跑前 ensure_context 复查并重进
    ⚠ 「背包已满」会盖住面板 → 先 clear_bag 清理再重进面板
    ⚠ 4星材料「已选中」态阈值须 ≥0.95（3星 会误匹配到 0.942）

用法:
    uv run python tools/cases/sweep_stage.py [--max N] [--material N] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402
from tools.maint.clear_bag import clear_if_full  # noqa: E402   # 背包满自动清理

MAT_ICONS = [_bot.client_to_ref(x, 345, 812, 1518) for x in (156, 299, 440, 582)]
# ↑ 当年在 812x1518 实帧上量的坐标, 先归一成基准口径(见 bot.client_to_ref),
#   点击时再由 click_base 换到当时的窗口 —— 812(主流尺寸)往返恒等, 601/845 才算得准。
TH = 0.88            # 通用
SWEEP_TH = 0.93      # 「扫荡」按钮（橙色，只有可用/未耗尽的行才会命中）
TOGGLE_TH = 0.93     # 切换器 label
TAB_TH = 0.96        # 4星材料「已选中」态（未选中时 3星 会误匹配到 0.942，故阈值须 ≥0.95）
TABBAR_TH = 0.90     # 整条页签栏（任意选中态都该命中）
DOUBLE_TH = 0.93     # 「双倍奖励」按钮
DONE_TH = 0.90       # 「扫荡完成」弹层
AD_TH = 0.90         # 广告链路
BLANK = _bot.client_to_ref(420, 620, 812, 1518)   # 「扫荡完成」弹层上的空白点（点它关弹层）
OVERLAY_SIG = "sweep_done"
BLANK_LIMIT = 3      # 连续几关无翻倍机会就收工

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_sweep 快速扫荡)--> 扫荡面板
  --> 切模式: sweep_to_hero(切英雄) / sweep_to_normal(切普通)
  --> 普通模式选「4星材料」页签(sweep_tab4 / 点页签栏中心+20px)
  --> 选材料类型: 面板顶部 4 图标按计数升序 → 默认点第 1 个(材料最少) [--material=N / 0=全部]
  --> 点最上面可用行「扫荡」(sweep_btn, 阈值 0.93)
  --> 「双倍奖励」(sweep_double) → 看广告(jump_no 不使用跳过卡 → ad_rewarded 才关)
  --> 关「扫荡完成」弹层(点空白 420,620)  ← 可能连带关掉面板 → 下轮 ensure_context 复查重进
  无翻倍机会: 换下一关继续；连续 3 关都没有才收工
  背包已满(bag_full 盖住面板): 先清理 → 重新进面板 → 继续
  收尾: normal / hero 两模式各跑 N 轮 → 回首页"""


def detect_mode(sc: kit.Screen):
    """"normal" = 普通模式，"hero" = 英雄模式，None = 不在扫荡面板/识别失败。"""
    if sc.find("sweep_to_hero", TOGGLE_TH) is not None:
        return "normal"
    if sc.find("sweep_to_normal", TOGGLE_TH) is not None:
        return "hero"
    return None


def ensure_mode(sc: kit.Screen, mode: str) -> bool:
    for i in range(3):
        cur = detect_mode(sc)
        if cur == mode:
            log(f"模式已是 {mode}（第 {i} 次确认）")
            return True
        # 目标模式的 label 只会以「未激活」态存在，所以点它必然是切换
        tgt = "sweep_to_normal" if mode == "normal" else "sweep_to_hero"
        hit = sc.find(tgt, TOGGLE_TH)
        if hit is None:
            log(f"未找到切换器目标 {tgt}（当前模式={cur}）")
            return False
        sc.click(hit, f"切换器 → {mode}")
        kit.nap(2.5)
    return detect_mode(sc) == mode


def open_panel(sc: kit.Screen) -> bool:
    """从首页或关卡选择页进入到「快速扫荡」面板。"""
    for _ in range(4):
        if sc.find("sweep_close", 0.93) is not None:
            log("已在快速扫荡面板")
            return True
        hit = sc.find("stage_sweep", 0.90)
        if hit is not None:
            sc.click(hit, "快速扫荡")
            kit.nap(2.5)
            continue
        hit = sc.find("stage_btn", 0.90)
        if hit is not None:
            sc.click(hit, "闯关模式")
            kit.nap(3.0)
            continue
        log("既不在首页也不在关卡页，导航失败")
        return False
    return sc.find("sweep_close", 0.93) is not None


def select_tab4(sc: kit.Screen) -> bool:
    """确保 4星材料 页签处于选中态。"""
    if sc.find("sweep_tab4", TAB_TH) is not None:
        log("4星材料 已是选中态")
        return True
    bar = sc.find("sweep_tabbar", TABBAR_TH)
    if bar is None:
        log("未找到材料页签栏")
        return False
    # 整条页签栏中心 → 4星材料（中间那个）中心 = +20px
    sc.click_at(bar[0] + 20, bar[1], "4星材料")
    kit.nap(2.0)
    ok = sc.find("sweep_tab4", TAB_TH) is not None
    log(f"4星材料 选中 → {ok}")
    return ok


def handle_ad(sc: kit.Screen, timeout: float = 100.0) -> bool:
    """等广告看完（ad_rewarded 出现）再关。遇跳过卡弹窗选「不使用」不消耗道具。"""
    end = kit.time.time() + timeout
    while kit.time.time() < end:
        hit = sc.find("jump_no", AD_TH)
        if hit is not None:
            sc.click(hit, "跳过卡弹窗 → 不使用")
            kit.nap(1.5)
            continue
        if sc.find("ad_rewarded", AD_TH) is not None:
            close = sc.find("ad_close", 0.93)
            if close is not None:
                sc.click(close, "关闭广告")
                return True
        if sc.dry:
            return False
        kit.nap(2.0)
    log("广告等待超时")
    return False


def close_overlay(sc: kit.Screen) -> bool:
    """关掉「扫荡完成」弹层：在弹层空白处点一下。"""
    for _ in range(4):
        if sc.find(OVERLAY_SIG, DONE_TH) is None:
            return True
        sc.click_base(BLANK[0], BLANK[1], "弹层空白处(关弹层)")
        kit.nap(1.5)
    ok = sc.find(OVERLAY_SIG, DONE_TH) is None
    log(f"弹层关闭 → {ok}")
    return ok


def select_material(sc: kit.Screen, idx: int) -> bool:
    """选材料类型(优先扫材料最少的那个)。

    面板顶部 4 个图标按计数升序排列(实测 711<763<810<831)，故默认 idx=1 = 最少。
    若某日不是升序，用 --material=N 指定，或 --material=0 保持「全部」。
    """
    if not idx or idx < 1:
        log("材料筛选: 保持全部")
        return True
    x, y = MAT_ICONS[min(idx, 4) - 1]
    log(f"选材料类型 #{idx} (材料最少的那个) ({x},{y})")
    sc.click_base(x, y, f"材料类型#{idx}")
    kit.nap(2.0)
    return True


def one_round(sc: kit.Screen, idx: int, mode: str) -> str:
    log(f"—— 第 {idx} 轮 ——")
    if clear_if_full(sc.rect, log, dry=sc.dry):    # 「背包已满」会盖住面板 → 先清理再重进
        log("背包已清理，重新进入扫荡面板")
        if open_panel(sc):
            ensure_mode(sc, mode)
            if mode == "normal":
                select_tab4(sc)
        kit.nap(1.0)
    hit = sc.find("sweep_btn", SWEEP_TH)
    if hit is None:
        log("没有可用的「扫荡」按钮（次数耗尽/体力不足）")
        return "no_sweep"
    sc.click(hit, "扫荡（最上面的可用行）")

    dbl = sc.wait("sweep_double", 14.0, th=DOUBLE_TH)
    if dbl is None:
        log("未出现「双倍奖励」（可能本轮无翻倍机会）")
        close_overlay(sc)
        return "no_double"
    sc.click(dbl, "双倍奖励")

    ok_ad = handle_ad(sc)
    close_overlay(sc)
    if not ok_ad:
        sc.shot(f"sweep_stage_ad_fail{idx}")
        return "ad_timeout"
    log(f"第 {idx} 轮完成（奖励已翻倍）")
    return "ok"


def ensure_context(sc: kit.Screen, mode: str, mat: int) -> bool:
    """确保身处「快速扫荡」面板，且模式 / 材料筛选都对。

    面板会被误关(点弹层空白可能连带关掉面板)，所以每轮开跑前都要确认一次。
    """
    if sc.find("sweep_close", 0.93) is None:
        log("不在扫荡面板，重新进入")
        if not open_panel(sc):
            return False
    if not ensure_mode(sc, mode):
        log(f"切换到 {mode} 模式失败")
        return False
    if mode == "normal" and not select_tab4(sc):
        sc.shot("sweep_stage_tab4_fail")
    select_material(sc, mat)
    return True


def run_phase(sc: kit.Screen, mode: str, n: int, mat: int) -> dict:
    log(f"===== {mode} 模式 ×{n} =====")
    stat: dict[str, int] = {}
    if not ensure_context(sc, mode, mat):
        return {"mode_fail": 1}
    blank = 0                            # 连续无翻倍关数(翻倍是每关每日限次)
    for i in range(1, n + 1):
        if sc.find("sweep_close", 0.93) is None and not ensure_context(sc, mode, mat):
            stat["ctx_fail"] = stat.get("ctx_fail", 0) + 1
            log("面板重进失败，结束本模式")
            break
        r = one_round(sc, i, mode)
        stat[r] = stat.get(r, 0) + 1
        if r == "no_sweep":
            sc.shot(f"sweep_stage_{mode}_stop{i}")
            log(f"{mode} 模式结束：没有可用关卡(次数/体力耗尽)")
            break
        if r == "no_double":
            blank += 1                   # 该关翻倍已用完 → 换下一关继续，连续 3 关都没有才收工
            if blank >= BLANK_LIMIT:
                sc.shot(f"sweep_stage_{mode}_stop{i}")
                log(f"{mode} 模式结束：连续 {blank} 关无翻倍机会")
                break
            log(f"该关无翻倍机会，换下一关继续 ({blank}/{BLANK_LIMIT})")
        else:
            blank = 0
        kit.nap(1.0)
    return stat


def run(sc: kit.Screen, args: kit.Args) -> bool:
    n = args.n_times(5)
    mat = int(args.extra.get("material", 1))

    if sc.dry:
        log("== 侦查模式 ==")
        log(f"当前模式: {detect_mode(sc)}")
        for name, th in (("sweep_close", 0.93), ("stage_sweep", 0.90), ("stage_btn", 0.90),
                         ("sweep_tabbar", TABBAR_TH), ("sweep_tab4", TAB_TH),
                         ("sweep_to_hero", TOGGLE_TH), ("sweep_to_normal", TOGGLE_TH),
                         ("sweep_btn", SWEEP_TH), ("sweep_done", DONE_TH)):
            log(f"  {name:16s} {sc.find(name, th)}")
        log(f"[dry] 计划: 普通 ×{n} + 英雄 ×{n}，材料筛选 #{mat or '全部'}"
            f"（默认 1 = 面板顶部计数最少的那个）")
        log("[dry] 会留证截图 sweep_stage_dry（dry 不写盘）")
        return True

    if not open_panel(sc):
        log("无法打开快速扫荡面板，退出")
        return False

    total: dict[str, int] = {}
    for mode in ("normal", "hero"):
        stat = run_phase(sc, mode, n, mat)
        for k, v in stat.items():
            total[k] = total.get(k, 0) + v

    log(f"===== 汇总: {total} =====")
    sc.shot("sweep_stage_final")
    ok = total.get("ok", 0)
    log(f"成功翻倍 {ok} 次（目标 {n * 2} 次）")
    return ok > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "sweep_stage", "扫荡关卡（普通 5/5 + 英雄 5/5，吃双倍奖励）", run,
        plan=PLAN, prefix="", lock_ttl=3600, th=TH,
        default_max=5, extra_kv=("--material",),
    ))
