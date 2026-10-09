#!/usr/bin/env python
"""用例: 导弹猎场「闪击」（活动关卡页，每日免费次数，消耗体力）。

链路:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(act_entry 活动关卡)--> 活动关卡页
    --(导弹猎场卡片右下「闪击」mh_flash)--> 闪击对话框(mh_dlg_title)
    --(mh_dlg_go「闪击」)--> 局内 --(每 5.2s 点技能 → 阵亡复活 → 装备UP → 结算继续)-->
    回到活动关卡页

    ⚠ 「当前关卡今日可攻打次数已耗尽 明日再来吧」弹窗会叠在活动关卡页上 → 判层 prompt 最优先
    ⚠ 活动关卡页有两张卡(陨石陷阱/导弹猎场)，「闪击」键**同款**(命中 0.998 / 0.978) →
      用导弹猎场卡标题 mh_title 做锚点 + 偏移(在 601 实帧上量得 301,176)，取最近的那个；
      另一张卡在 (421,455)，离锚点预测 ~550px，必被排除
    ⚠ 对话框打开时背后那张卡的 mh_flash 仍能命中(0.997) → 判层必须 dialog 先于 actpage
    ⚠ 对话框里「闪击 N 次」的次数**不动**(游戏默认 2 次/⚡80)：改次数=改消耗，交给玩家决定
    ⚠ 0 次降级: 点闪击 → 弹「次数已耗尽」→ 关掉即算跳过，**不算失败**
      关弹窗只在「看到次数已耗尽文案」时才点绿确认，避免把付费确认当成它点掉
    ⚠ 局内结束判据: 回到活动关卡页(mh_title) 连续 3 次 —— 战斗间隙会短暂闪过

用法:
    uv run python tools/cases/missile_hunt.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import battle, bot, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.85
FIGHT_TIMEOUT = 480         # 单轮(对话框里默认 2 次闪击)最长等待(自检会改小)
NAV_WAIT = 2.5              # 点完导航键等页面切换
FLASH_OFF = (301, 176)      # 导弹猎场卡标题 → 该卡「闪击」键的偏移(量自 601x1143 实帧)
FLASH_CALIB = (601, 1143)   # 上面那个偏移的标定帧尺寸
FLASH_TOL = 60              # 模板命中与锚点预测的最大距离(超过就认为命中的是另一张卡)

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(act_entry 活动关卡)--> 活动关卡页
  --> 导弹猎场卡片(标题 mh_title 锚定 + 偏移 301,176)「闪击」(mh_flash)
  --> 闪击对话框(mh_dlg_title): 次数=游戏默认(2 次/⚡80，**不擅改**)
  --> 点「闪击」(mh_dlg_go) → 局内: 每 5.2s 点一次技能(battle_skill / 坐标兜底)
      → 阵亡复活 → 装备UP选择 → 结算页继续，直到回到活动关卡页(连续 3 次)
  次数已耗尽: 弹「当前关卡今日可攻打次数已耗尽」(叠在活动关卡页) → 确认关闭 → 跳过(不算失败)
  收尾: 回首页"""


def _find(sc: kit.Screen, name: str, th: float = TH):
    """模板缺失时返回 None(不炸)，便于逐步补模板。"""
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def on_actpage(sc: kit.Screen) -> bool:
    """活动关卡页: 导弹猎场卡标题在(闪击键/对话框都不足以单独判层)。"""
    return _find(sc, "mh_title") is not None


def page(sc: kit.Screen) -> str:
    """当前页面: prompt(模态提示) / dialog / actpage / stage / home / unknown。

    顺序即优先级，两条都是踩过的坑:
      * prompt 最优先 —— 次数已耗尽弹窗会叠在活动关卡页上，不先认它就会误判成 actpage
      * dialog 先于 actpage —— 对话框背后那张卡的 mh_flash 仍能命中(0.997)
    """
    if _find(sc, "boss_noattempts") is not None:
        return "prompt"
    if _find(sc, "mh_dlg_title") is not None:
        return "dialog"
    if on_actpage(sc):
        return "actpage"
    if _find(sc, "act_entry") is not None:
        return "stage"
    if _find(sc, "stage_btn") is not None:
        return "home"
    return "unknown"


def close_prompt(sc: kit.Screen) -> bool:
    """关掉「次数已耗尽」提示。

    ⚠ 只在确认看到该文案后才调用 —— 绿确认键与付费确认长得像(0.898)，
      盲点有把付费框点掉的风险。
    """
    ok = _find(sc, "boss_confirm_ok")       # 提示层上它是唯一的绿键(实测 0.96)
    if ok is None:
        log("提示层上没看到确认键(可能在淡入/淡出)，稍后再看")
        kit.nap(1.5)
        ok = _find(sc, "boss_confirm_ok")
    if ok is None:
        log("提示层上始终没有确认键 → 放弃关闭")
        sc.shot("prompt_noclose")
        return False
    sc.click(ok, "确认(关掉次数已耗尽提示)")
    if sc.dry:
        return True
    kit.nap(2.0)
    return True


def pick_flash(sc: kit.Screen):
    """导弹猎场那张卡的「闪击」键: 卡标题锚定 + 缩放后的偏移，取最近的模板命中。

    三张活动卡同款按键，靠「离锚点最近」来归属；模板全空则退回预测点(因此必须
    先有标题命中，否则不给预测点 —— 乱猜一个坐标比不点更糟)。
    """
    t = _find(sc, "mh_title")
    if t is None:
        return None
    dx, dy = bot.scale_delta(*FLASH_OFF, FLASH_CALIB, (sc.w, sc.h))
    px, py = t[0] + dx, t[1] + dy
    hits = sc.find_all("mh_flash")
    if hits:
        best = min(hits, key=lambda h: (h[0] - px) ** 2 + (h[1] - py) ** 2)
        d = ((best[0] - px) ** 2 + (best[1] - py) ** 2) ** 0.5
        if d <= FLASH_TOL:
            log(f"闪击键: 模板命中 {best[:2]} (s={best[2]:.3f}, 距锚点预测 {d:.0f}px)")
            return best
        log(f"闪击键: 最近的命中 {best[:2]} 离预测 {d:.0f}px > {FLASH_TOL} → 改用预测点")
    else:
        log("闪击键: 模板未命中 → 用锚点+偏移的预测点")
    log(f"闪击键: 预测点 ({px},{py}) = 标题{t[:2]} + 偏移({dx},{dy})")
    return (px, py, 0.0)


def goto_actpage(sc: kit.Screen) -> bool:
    """从首页/关卡页/已在活动关卡页都能到活动关卡页。"""
    for _ in range(5):
        p = page(sc)
        log(f"当前页面: {p}")
        if p == "prompt":
            close_prompt(sc)
        elif p in ("actpage", "dialog"):    # 对话框=已经过了活动关卡页那一步
            return True
        elif p == "stage":
            e = _find(sc, "act_entry")
            if e is None:
                log("关卡页找不到「活动关卡」入口(act_entry)")
                sc.shot("no_entry")
                return False
            sc.click(e, "活动关卡(act_entry)")
            kit.nap(NAV_WAIT)
        elif p == "home":
            b = _find(sc, "stage_btn")
            if b is None:
                log("首页找不到「闯关模式」入口(stage_btn)")
                return False
            sc.click(b, "闯关模式(stage_btn)")
            kit.nap(NAV_WAIT)
        else:
            log("未知页面(非首页/关卡页/活动关卡页) → 请人工确认")
            sc.shot("unknown")
            return False
        if sc.dry:
            log("[dry] 计划: 闯关模式 → 活动关卡 → 导弹猎场闪击 → 对话框 → 局内")
            break
    return False


def fight(sc: kit.Screen) -> tuple[bool, int, int]:
    """局内(循环见 wb.battle.fight): 点技能 → 复活 → 装备UP → 结算继续。

    退出条件 = 回到活动关卡页，连续 3 次(~6s)仍停留才算真打完 ——
    战斗间隙会短暂闪过活动关卡页。
    """
    def out_of_battle(s: kit.Screen) -> int:
        return 3 if on_actpage(s) else 0

    return battle.fight(sc, out_of_battle, timeout=FIGHT_TIMEOUT, label="本轮闪击")


def one_round(sc: kit.Screen) -> bool:
    p = page(sc)
    if p == "prompt":
        log("开局就见「次数已耗尽」→ 关掉，跳过(不算失败)")
        close_prompt(sc)
        return True
    if p != "dialog":                       # 残留对话框: 那一步已经过了，直接进局
        if not goto_actpage(sc):
            return False
        fl = pick_flash(sc)
        if fl is None:
            log("活动关卡页找不到导弹猎场卡片标题(mh_title) → 跳过")
            sc.shot("no_card")
            return False
        sc.click(fl, "导弹猎场-闪击(打开对话框)")
        if sc.dry:
            return False

        # 点闪击后有两条路: 正常出闪击对话框；或次数用尽弹「今日可攻打次数已耗尽」
        go = na = None
        deadline = kit.time.time() + 15
        while kit.time.time() < deadline:
            na = _find(sc, "boss_noattempts")
            go = _find(sc, "mh_dlg_go")
            if na is not None or go is not None:
                break
            kit.nap(1.0)
        if na is not None:
            log("「当前关卡今日可攻打次数已耗尽」→ 关掉提示，跳过(不算失败)")
            close_prompt(sc)
            return True
        if go is None:
            log("未出现闪击对话框，放弃本轮")
            sc.shot("nodialog")
            return False
    else:
        log("已是闪击对话框(上次留下/刚打开的) → 直接闪击")

    # 留证: 对话框里选了几次闪击/花多少体力 —— 事后可回看截图核对消耗
    sc.shot("flash_dialog")
    go = _find(sc, "mh_dlg_go")
    if go is None:
        log("闪击对话框上找不到「闪击」键(mh_dlg_go)")
        return False
    sc.click(go, "闪击(确认，次数/体力=游戏默认)")
    kit.nap(3.0)

    ok, rounds, revives = fight(sc)
    log(f"本轮闪击{'完成' if ok else '未完成'} (结算页 {rounds} 张 / 复活 {revives} 次)")
    return ok


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if sc.dry:
        p = page(sc)
        log(f"当前页面 {p}")
        fl = pick_flash(sc) if p in ("actpage", "dialog") else None
        log(f"[dry] 导弹猎场闪击键: "
            + (f"会点 {fl[:2]} (score={fl[2]:.3f})" if fl else "需先导航到活动关卡页"))
        log("[dry] 计划输出完毕(未点击)")
        return True
    return one_round(sc)


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "missile_hunt", "导弹猎场闪击（活动关卡页，每日免费次数）", run,
        plan=PLAN, prefix="missile_", lock_ttl=3600, th=TH,
    ))
