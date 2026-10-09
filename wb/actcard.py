#!/usr/bin/env python
"""活动关卡页公共流程 —— 陨石陷阱 / 激光迷宫 / 导弹猎场 三张卡共用一套。

链路:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
    --> 选卡(卡标题锚点) ± 选难度(简单/普通/困难/极难 页签)
    --> 卡上橙色「闪击」--> 闪击对话框(底部橙键 mh_dlg_go；次数/⚡ = 游戏默认)
    --> 局内(与 BOSS 闪击同一套 wb.battle.fight: 每 5.2s 点技能 → 阵亡复活
        → 装备UP默认项 → 结算继续) --> 回到活动关卡页(卡标题在，连续 3 次算打完)

三张卡美术同款，只有两处模板不同 → 所以整条流程写成一份，用例只传三个参数:
    title_tpl  卡标题(用它定位该卡的「闪击」/「极难」)
    dlg_tpl    对话框标题(「闪击-<关卡名>」)
    tag        日志与证据前缀

⚠ 三张卡的「闪击」键**同款**(命中 0.998/0.978) → 必须用卡标题锚点 + 偏移取
  **最近的**那个命中，否则会点到别的卡(点错卡 = 花错资源的真事故)。
⚠ 难度页签(简单..极难)三张卡也同款 → 同样靠「离本卡标题最近」来归属。
⚠ 对话框打开时背后那张卡的「闪击」仍能命中(0.997) → 判层里 dialog 必须先于 actpage。
⚠ 「今日可攻打次数已耗尽」提示会叠在活动关卡页上 → prompt 优先级最高。
⚠ 关卡页判定用 stage_event_lv(只框按钮本体)；旧的 act_entry 把会变的关卡编号也框了
  进去，换一关就从 0.99 掉到 0.833 → 判层 unknown、导航失败(2026-10-09 实踩)。
"""
from __future__ import annotations

from wb import battle, bot, kit  # noqa: F401  (bot 供 scale_delta)
from wb.kit import log

TH = 0.85
NAV_WAIT = 2.5              # 点完导航键等页面切换
UNKNOWN_TOLERATE = 3        # 连续几次 unknown 才认输(关卡页空载帧可达数秒)
NEAR_TOL = 60               # 命中点与锚点预测的最大距离(超过认为是别的卡)
DIALOG_WAIT = 15.0          # 点闪击后等对话框/次数提示


def find(sc: kit.Screen, name: str, th: float = TH):
    """模板缺失时返回 None(不炸)，便于逐步补模板。"""
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def on_card(sc: kit.Screen, title_tpl: str) -> bool:
    """该卡所在的活动关卡页(用卡标题判定；闪击键/对话框都不足以单独判层)。"""
    return find(sc, title_tpl) is not None


def page(sc: kit.Screen, title_tpl: str, dlg_tpl: str | None = None) -> str:
    """当前页面: prompt / dialog / actpage / stage / home / unknown。

    顺序即优先级，两条都是踩过的坑:
      * prompt 最优先 —— 次数已耗尽提示叠在活动关卡页上，不先认它就会误判 actpage
      * dialog 先于 actpage —— 对话框背后那张卡的「闪击」仍能命中
    """
    if find(sc, "boss_noattempts") is not None:
        return "prompt"
    if dlg_tpl and find(sc, dlg_tpl) is not None:
        return "dialog"
    if on_card(sc, title_tpl):
        return "actpage"
    if find(sc, "stage_event_lv") is not None:
        return "stage"
    if find(sc, "stage_btn") is not None:
        return "home"
    return "unknown"


def close_prompt(sc: kit.Screen) -> bool:
    """关掉「次数已耗尽」提示。

    ⚠ 只在确认看到该文案后才调用 —— 绿确认键与付费确认长得像(0.898)，
      盲点有把付费框点掉的风险。
    """
    ok = find(sc, "boss_confirm_ok")        # 提示层上它是唯一的绿键(实测 0.96)
    if ok is None:
        log("提示层上没看到确认键(可能在淡入/淡出)，稍后再看")
        kit.nap(1.5)
        ok = find(sc, "boss_confirm_ok")
    if ok is None:
        log("提示层上始终没有确认键 → 放弃关闭")
        sc.shot("prompt_noclose")
        return False
    sc.click(ok, "确认(关掉次数已耗尽提示)")
    if not sc.dry:
        kit.nap(2.0)
    return True


def predict(sc: kit.Screen, anchor, off: tuple[int, int], calib: tuple[int, int]):
    """锚点中心 + 缩放后的偏移 → 目标预测点。"""
    dx, dy = bot.scale_delta(*off, calib, (sc.w, sc.h))
    return anchor[0] + dx, anchor[1] + dy


def pick_near(sc: kit.Screen, tpl: str, pred, what: str, tol: float = NEAR_TOL):
    """取离 pred 最近且在 tol 内的命中；都不够近就返回 None(绝不瞎猜坐标)。"""
    hits = sc.find_all(tpl)
    if not hits:
        log(f"{what}: 模板 {tpl} 未命中")
        return None
    best = min(hits, key=lambda h: (h[0] - pred[0]) ** 2 + (h[1] - pred[1]) ** 2)
    d = ((best[0] - pred[0]) ** 2 + (best[1] - pred[1]) ** 2) ** 0.5
    if d > tol:
        log(f"{what}: 最近命中 {best[:2]} 离预测 {d:.0f}px > {tol} → 放弃"
            f"(很可能命中的是别的卡)")
        return None
    log(f"{what}: 命中 {best[:2]} (s={best[2]:.3f}, 距锚点预测 {d:.0f}px)")
    return best


def pick_flash(sc: kit.Screen, title_tpl: str, off, calib,
               flash_tpl: str = "mh_flash"):
    """该卡的「闪击」键: 卡标题锚点 + 偏移 → 最近命中；无命中才退回预测点。

    ⚠ 三张卡同款按键，靠「离锚点最近」归属；模板全空则退回预测点 ——
      因此**必须先有标题命中**，否则不给预测点(乱猜坐标比不点更糟)。
    """
    t = find(sc, title_tpl)
    if t is None:
        return None
    pred = predict(sc, t, off, calib)
    hit = pick_near(sc, flash_tpl, pred, "闪击键")
    if hit is not None:
        return hit
    log(f"闪击键: 模板未命中 → 用锚点+偏移的预测点 {pred}")
    return (pred[0], pred[1], 0.0)


def goto_card(sc: kit.Screen, title_tpl: str, dlg_tpl: str | None = None) -> bool:
    """从首页/关卡页/已在目标卡页 都能到该卡所在的活动关卡页。"""
    unknown = 0
    for _ in range(8):
        p = page(sc, title_tpl, dlg_tpl)
        log(f"当前页面: {p}")
        if p == "prompt":
            close_prompt(sc)
            unknown = 0
        elif p in ("actpage", "dialog"):        # 对话框=已经过了这一页
            return True
        elif p == "stage":
            e = find(sc, "stage_event_lv")
            if e is None:
                log("关卡页找不到「活动关卡」入口(stage_event_lv)")
                sc.shot("no_entry")
                return False
            sc.click(e, "活动关卡(stage_event_lv)")
            kit.nap(NAV_WAIT)
            unknown = 0
        elif p == "home":
            b = find(sc, "stage_btn")
            if b is None:
                log("首页找不到「闯关模式」入口(stage_btn)")
                return False
            sc.click(b, "闯关模式(stage_btn)")
            kit.nap(NAV_WAIT)
            unknown = 0
        else:
            # ⚠ 关卡页/首页资源未加载完时有数秒「空载帧」: 单帧判层必误判 unknown。
            #   2026-10-09 实测: 点「闯关模式」7s 后仍判 unknown，但同一刻的留证截图
            #   已完整渲染(章节/入口全在)。→ unknown 不当终局，等一轮重判。
            unknown += 1
            if unknown >= UNKNOWN_TOLERATE:
                log("未知页面(非首页/关卡页/活动关卡页) → 请人工确认")
                sc.shot("unknown")
                return False
            log(f"页面未就绪(unknown 第 {unknown} 次) → 等 {NAV_WAIT}s 重判")
            kit.nap(NAV_WAIT)
        if sc.dry:
            log("[dry] 计划: 闯关模式 → 活动关卡 → 选卡选难度 → 闪击 → 对话框 → 局内")
            break
    return False


def fight(sc: kit.Screen, title_tpl: str, timeout: float,
          label: str = "本轮闪击"):
    """局内(循环见 wb.battle.fight): 点技能 → 复活 → 装备UP → 结算继续。

    退出条件 = 回到活动关卡页(卡标题在)，**连续 3 次**(~6s)仍停留才算真打完 ——
    战斗间隙会短暂闪过活动关卡页。
    """
    def out_of_battle(s: kit.Screen) -> int:
        return 3 if on_card(s, title_tpl) else 0

    return battle.fight(sc, out_of_battle, timeout=timeout, label=label)


def one_round(sc: kit.Screen, *, title_tpl: str, dlg_tpl: str,
              flash_off, flash_calib, timeout: float = 480.0,
              before_flash=None) -> bool:
    """一轮闪击: 到卡页(+可选地先选难度) → 点闪击 → 对话框 → 点闪击 → 局内。

    before_flash: 可选回调(sc) -> bool，在点「闪击」前执行(如先点「极难」页签)。
    """
    p = page(sc, title_tpl, dlg_tpl)
    if p == "prompt":
        log("开局就见「次数已耗尽」→ 关掉，跳过(不算失败)")
        close_prompt(sc)
        return True
    if p != "dialog":                           # 残留对话框: 那一步已经过了，直接进局
        if not goto_card(sc, title_tpl, dlg_tpl):
            return False
        if before_flash is not None and not before_flash(sc):
            log("前置步骤(难度页签等)未完成 → 为安全起见不闪击")
            return False
        fl = pick_flash(sc, title_tpl, flash_off, flash_calib)
        if fl is None:
            log(f"活动关卡页找不到该卡标题({title_tpl}) → 跳过")
            sc.shot("no_card")
            return False
        sc.click(fl, "闪击(打开对话框)")
        if sc.dry:
            return False

        # 点闪击后有两条路: 正常出闪击对话框；或次数用尽弹「可攻打次数已耗尽」
        go = na = None
        deadline = kit.time.time() + DIALOG_WAIT
        while kit.time.time() < deadline:
            na = find(sc, "boss_noattempts")
            go = find(sc, "mh_dlg_go")
            if na is not None or go is not None:
                break
            kit.nap(1.0)
        if na is not None:
            log("「今日可攻打次数已耗尽」→ 关掉提示，跳过(不算失败)")
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
    go = find(sc, "mh_dlg_go")
    if go is None:
        log("闪击对话框上找不到「闪击」键(mh_dlg_go)")
        return False
    sc.click(go, "闪击(确认，次数/体力=游戏默认)")
    kit.nap(3.0)

    ok, rounds, revives = fight(sc, title_tpl, timeout)
    log(f"本轮闪击{'完成' if ok else '未完成'} (结算页 {rounds} 张 / 复活 {revives} 次)")
    return ok
