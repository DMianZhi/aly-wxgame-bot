#!/usr/bin/env python
"""用例: BOSS 闪击（四站轮转，每站 3 次/轮，阵亡钻石复活）。

链路:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_boss)--> BOSS 列表
    --> 选空间站(boss_stn_*) --> 站内点「闪击」(boss_flash) → 对话框(boss_flash_go)
    --> 钻石确认(boss_confirm_ok) --> 局内: 每 5.2s 点一次右下角技能 → 阵亡复活(钻石20)
        → 装备UP选择(取默认) → 结算页继续，直到回到站内页/列表页

    ⚠ 「今日可攻打次数已耗尽」提示弹窗可叠在任意页面上 → 判层时 prompt 必须最优先
    ⚠ 「装备UP」键在列表页会误命中仓库键(0.866) → 站内页判定把阈值抬到 0.92
    ⚠ 装备UP弹窗的绿「确认」与钻石确认弹窗的绿「确认」长得很像(0.898) → 用标题
      boss_equipup_title 判层；钻石确认键阈值抬到 0.90
    ⚠ 战斗间隙会短暂回站内页 → 连续 3 次(~6s)仍停留才算闪击真正打完
    ⚠ 技能要每 5.2s 点一次(不是进局点一下): 进局先过「资源加载中」页，那一下是空点
    ⚠ 站内页判定里「闪击键消失」= 次数用尽，用站内独有的「装备UP」键兑现(而非当成失败)

用法:
    uv run python tools/cases/boss_mode.py [--station pegasus|drago|cygnus|andro] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import battle, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.85
FIGHT_TIMEOUT = 480         # 单站(闪击3次)最长等待: 每轮 40~80s + 加载缓冲(自检会改小)
STATION_WAIT = 3.0          # 点空间站后等进站
STATIONS = {
    "pegasus": ("boss_stn_pegasus", "战机"),
    "drago":   ("boss_stn_drago",   "装甲"),
    "cygnus":  ("boss_stn_cygnus",  "副武器"),
    "andro":   ("boss_stn_andro",   "僚机"),
}
BOSS_LIST_MARKS = ("boss_stn_pegasus", "boss_stn_drago", "boss_hyper")

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_boss)--> BOSS 列表
  --> 选空间站(boss_stn_pegasus/drago/cygnus/andro，四站轮转)
  --> 站内「闪击」(boss_flash) --> 对话框(boss_flash_go，次数=游戏默认 3)
  --> 钻石确认(boss_confirm_ok) --> 局内
  --> 每 5.2s 点一次右下角技能(battle_skill / 坐标兜底 740,1300) → 阵亡复活(钻石20)
      → 装备UP选择(boss_equipup_title → 默认项确认) → 结算页继续(boss_result_next)
  --> 回到站内页(连续 3 次停留才算打完) / 列表页
  次数用尽: 「今日可攻打次数已耗尽」提示(叠在任意页) → 确认关闭 → 跳过本站
  收尾: 本站完成即下一站，全部完成回首页"""


def _find(sc: kit.Screen, name: str, th: float = TH):
    """模板缺失时返回 None(不炸)，便于逐步补模板。"""
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def on_boss_list(sc: kit.Screen) -> bool:
    return any(_find(sc, m) is not None for m in BOSS_LIST_MARKS)


def on_station(sc: kit.Screen) -> bool:
    """站内挑战页: 有「闪击」键；或次数用尽时闪击键消失，用站内独有的「装备UP」键兑现。

    「装备UP」键在列表页会误命中仓库键(0.866)，所以阈值抬到 0.92。
    """
    if _find(sc, "boss_flash") is not None:
        return True
    return _find(sc, "boss_equipup_btn", 0.92) is not None


def page(sc: kit.Screen) -> str:
    """当前页面: prompt(模态提示) / bosslist / station / stage / home / unknown。

    prompt 优先: 提示弹窗可叠在任何页面上(列表页/站内页都见过)，模态优先处理。
    先判列表页再判站内页: 列表页有空间站铭牌(boss_stn_*)，站内页没有，两者互斥。
    """
    if _find(sc, "boss_noattempts", 0.92) is not None:
        return "prompt"
    if on_boss_list(sc):
        return "bosslist"
    if on_station(sc):
        return "station"
    if _find(sc, "stage_boss") is not None:
        return "stage"
    if _find(sc, "stage_btn") is not None:
        return "home"
    return "unknown"


def goto_station(sc: kit.Screen, key: str) -> bool:
    """从任意状态导航到目标空间站页(首页/关卡页/列表页/已在别站都能兜回来)。"""
    tpl, name = STATIONS[key]
    for _ in range(5):
        p = page(sc)
        log(f"当前页面: {p}")
        if p == "prompt":                        # 次数耗尽提示(含上次残留) → 关掉
            ok = _find(sc, "boss_confirm_ok", 0.80)   # 弹窗已在=确认键必是它，阈值可放宽
            if ok is None:                             # 弹窗淡入淡出中，再观察一轮
                log("提示弹窗上没看到确认键(可能在淡出)，继续观察")
                kit.nap(1.5)
                continue
            sc.click(ok, "确认(关掉提示弹窗)")
            if sc.dry:
                break
            kit.nap(2.0)
        elif p == "station":                       # 已在某站内 → 先返回列表再选目标站
            back = _find(sc, "boss_back")
            if back is None or back[0] < 0.6 * sc.w:
                log("站内找不到「返回」键")
                return False
            sc.click(back, "返回(BOSS列表)")
            if sc.dry:
                break
            kit.nap(2.5)
        elif p == "bosslist":
            st = _find(sc, tpl)
            if st is None:
                log(f"列表页找不到「{name}」空间站")
                sc.shot(f"nostation_{key}")
                return False
            sc.click(st, f"{name}空间站")
            if sc.dry:
                break
            kit.nap(STATION_WAIT)
            if on_station(sc):
                return True
            log("点了空间站但未进入站内页")
        elif p == "stage":
            sb = _find(sc, "stage_boss")
            if sb is None:
                log("关卡页找不到 BOSS 模式入口")
                return False
            sc.click(sb, "BOSS模式(stage_boss)")
            kit.nap(3.0)
        elif p == "home":
            btn = _find(sc, "stage_btn")
            if btn is None:
                log("首页找不到「闯关模式」入口")
                return False
            sc.click(btn, "闯关模式(stage_btn)")
            kit.nap(2.5)
        else:
            log("未知页面(非首页/关卡页/BOSS列表/站内)，请人工确认")
            sc.shot(f"unknown_{key}")
            return False
        if sc.dry:                 # dry 不真点击，页面不会变，看一步就够
            log("[dry] 计划: 闯关模式 → BOSS模式 → 空间站 → 闪击 → 对话框确认 → 钻石确认"
                " → 局内每 5.2s 点技能 → 阵亡复活 → 装备UP → 结算继续")
            break
    return False


def fight(sc: kit.Screen) -> tuple[bool, int, int]:
    """局内(逻辑见 wb.battle.fight): 点技能 → 阵亡复活 → 装备UP → 结算继续。

    退出条件 —— BOSS 列表页=确认无疑(1 次即收工)；站内页要连续 3 次(~6s)仍停留
    才算打完(战斗间隙会短暂回站内页)。
    """
    def out_of_battle(s: kit.Screen) -> int:
        if on_boss_list(s):
            return 1                            # 列表页 = 真的收工了
        if on_station(s):
            return 3                            # 站内页可能是战斗间隙，需连续 3 次
        return 0

    return battle.fight(sc, out_of_battle, timeout=FIGHT_TIMEOUT, label="本轮闪击")


def one_station(sc: kit.Screen, key: str) -> bool:
    tpl, name = STATIONS[key]
    log(f"===== {name}空间站 ({tpl}) =====")
    if not goto_station(sc, key):
        return False

    fl = _find(sc, "boss_flash")
    if fl is None:
        log(f"站内找不到「闪击」按钮 → {name} 今日次数可能已用尽，跳过")
        sc.shot(f"noflash_{key}")
        return False
    sc.click(fl, "闪击(打开对话框)")
    if sc.dry:
        return False

    # 点闪击后有两条路: 正常出「闪击对话框」；或次数用尽弹「今日可攻打次数已耗尽」提示
    go = na = None
    deadline = kit.time.time() + 15
    while kit.time.time() < deadline:
        go = _find(sc, "boss_flash_go")
        na = _find(sc, "boss_noattempts")
        if go is not None or na is not None:
            break
        kit.nap(1.0)
    if na is not None:
        ok = _find(sc, "boss_confirm_ok", 0.90)
        log(f"{name}: 「今日可攻打次数已耗尽」→ 关掉提示，跳过本站")
        if ok is not None:
            sc.click(ok, "确认(次数耗尽提示)")
            kit.nap(2.0)
        return False
    if go is None:
        log("未出现闪击对话框，放弃本站")
        sc.shot(f"nodialog_{key}")
        return False
    # 留证: 闪击对话框里选了几次(游戏默认 3 次不动) —— 事后可回看截图核对场次
    sc.shot(f"flash_dialog_{key}")
    sc.click(go, "闪击(确认，次数=游戏默认)")
    kit.nap(2.5)

    ok = _find(sc, "boss_confirm_ok", 0.90)     # 0.90 排除装备UP弹窗那个绿键(0.898)
    if ok is not None:
        sc.shot(f"diamond_confirm_{key}")           # 留证: 钻石确认弹窗上的单价/数量
        log(f"钻石确认弹窗「是否使用钻石进入战斗?」→ 确认 {ok}")
        sc.click(ok, "确认(使用钻石)")
        kit.nap(3.0)
    else:
        log("未出现钻石确认弹窗(可能免费/次数已含)")

    # 保险: 确认后应离开站内页进入战斗，否则多半是次数已用尽
    t0 = kit.time.time()
    started = False
    while kit.time.time() - t0 < 20:
        if _find(sc, "boss_flash") is None:
            started = True
            break
        kit.nap(1.5)
    if not started:
        log(f"{name}: 确认后仍在站内页 → 判定未进入战斗(次数已用尽?)，跳过")
        sc.shot(f"nostart_{key}")
        return False

    ok2, rounds, revives = fight(sc)
    log(f"{name}: {'完成' if ok2 else '未完成'} (结算页 {rounds} 张 / 复活 {revives} 次)")
    return ok2


def run(sc: kit.Screen, args: kit.Args) -> bool:
    keys = [args.extra["station"]] if "station" in args.extra else list(STATIONS)
    bad = [k for k in keys if k not in STATIONS]
    if bad:
        raise SystemExit(f"未知 --station {bad[0]} (可选: {', '.join(STATIONS)})")

    if sc.dry:
        p = page(sc)
        log(f"当前页面 {p}")
        for k in keys:
            tpl, name = STATIONS[k]
            hit = _find(sc, tpl)
            log(f"[dry] {name}空间站({tpl}): "
                + (f"命中 {hit[:2]} score={hit[2]:.3f} → 会点它" if hit
                   else "未命中(需先导航到 BOSS 列表)"))
        log("[dry] 计划输出完毕(未点击)")
        return True

    ok: dict[str, bool] = {}
    for k in keys:
        ok[k] = one_station(sc, k)
        kit.nap(2.0)
    log("汇总: " + ", ".join(f"{STATIONS[k][1]}={'完成' if v else '未完成'}" for k, v in ok.items()))
    return all(ok.values())


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "boss_mode", "BOSS 闪击（四站轮转，每站 3 次/轮）", run,
        plan=PLAN, prefix="bossmode_", lock_ttl=3600, th=TH,
        extra_kv=("--station",),
    ))
