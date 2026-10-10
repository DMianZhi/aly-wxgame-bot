#!/usr/bin/env python
"""用例: 陨石陷阱「闪击」（活动关卡页第一张卡 · 极难，每日免费次数，消耗体力）。

链路（与 laser_maze / missile_hunt 完全同款, 共享 wb.actcard）:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
    --(选中该卡「极难」页签 lm_hard，取离本卡标题最近的那个)-->
    --(陨石陷阱卡标题 ys_title 锚点 + 偏移 → 该卡橙「闪击」)-->
      闪击对话框(ys_dlg_title「闪击-陨石陷阱 极难」)
    --(mh_dlg_go「闪击」)--> 局内(同一套 wb.battle.fight:
        每 5.2s 点技能 → 阵亡钻石复活 → 装备UP默认项 → 结算继续)--> 回活动关卡页

    ⚠ 活动关卡页三张卡(陨石陷阱/激光迷宫/导弹猎场)**同款布局、同款闪击键** →
      一律用 ys_title 锚点定位，绝不按绝对坐标硬点(点错卡 = 花错资源的真事故)
    ⚠ 「极难」页签三张卡同款(lm_hard 模板) → 取「离 ys_title 最近」的那个命中
    ⚠ 对话框里「闪击 2 次 / ⚡80」是**游戏默认**，不擅改(改次数=改消耗，交给玩家决定)
    ⚠ 0 次降级: 点闪击 → 弹「今日可攻打次数已耗尽」→ 关掉即算跳过，**不算失败**
    ⚠ 局内结束判据: 回到活动关卡页(ys_title 在) **连续 3 次** —— 战斗间隙会短暂闪过
    ⚠ 点完对话框「闪击」必须等真的进局(actcard 的进局闸门, 2026-10-10 加) ——
      该点击被吞时会在卡页上盲点技能并假完成(导弹猎场踩过)

    模板标定(2026-10-10, 812x1518 实帧 _mt_actpage_full.png / _mt3_mt_dialog.png):
      ys_title   自匹配 1.000 / 次高 0.712 / vs lm_title 0.592 / vs mh_title -0.040
      ys_dlg_title 自匹配 1.000 / 次高 0.413 (lm_dlg_title 在本卡对话框只有 0.576)

用法:
    uv run python tools/cases/meteor_trap.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import actcard, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = actcard.TH
TITLE_TPL = "ys_title"          # 卡标题「陨石陷阱」(定位本卡的闪击/极难)
DLG_TPL = "ys_dlg_title"        # 对话框标题「闪击-陨石陷阱」
HARD_TPL = "lm_hard"            # 「极难」页签(选中态；三张卡同款)
FIGHT_TIMEOUT = 480             # 单轮(对话框默认 2 次闪击)最长等待(自检会改小)

# 量自 812x1518 实帧: 卡标题命中中心(157,323) → 本卡「闪击」(564,588) / 「极难」页签(740,307)
FLASH_OFF = (407, 265)
HARD_OFF = (583, -16)
CALIB = (812, 1518)

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
  --> 陨石陷阱卡: 先点「极难」页签(lm_hard，取离 ys_title 最近的命中)
  --> 该卡橙「闪击」(ys_title 锚点 + 偏移 407,265) → 闪击对话框(ys_dlg_title)
  --> 点「闪击」(mh_dlg_go，次数 2 次/⚡80 = 游戏默认，**不擅改**) → 局内
      → 每 5.2s 点技能 → 阵亡复活 → 装备UP → 结算继续，直到回活动关卡页(连续 3 次)
  次数已耗尽: 弹「今日可攻打次数已耗尽」→ 确认关闭 → 跳过(不算失败)
  收尾: 回首页"""


def page(sc: kit.Screen) -> str:
    """当前页面: prompt / dialog / actpage / stage / home / unknown。"""
    return actcard.page(sc, TITLE_TPL, DLG_TPL)


def goto_actpage(sc: kit.Screen) -> bool:
    """任意页 → 陨石陷阱所在的活动关卡页。"""
    return actcard.goto_card(sc, TITLE_TPL, DLG_TPL)


def pick_flash(sc: kit.Screen):
    """陨石陷阱那张卡的「闪击」键(卡标题锚定 + 缩放偏移，取最近的命中)。"""
    return actcard.pick_flash(sc, TITLE_TPL, FLASH_OFF, CALIB)


def pick_hard(sc: kit.Screen):
    """陨石陷阱那张卡的「极难」页签: 同款页签取离本卡标题最近的那个。"""
    t = actcard.find(sc, TITLE_TPL)
    if t is None:
        return None
    pred = actcard.predict(sc, t, HARD_OFF, CALIB)
    return actcard.pick_near(sc, HARD_TPL, pred, "极难页签")


def click_hard(sc: kit.Screen) -> bool:
    """点「极难」页签。

    ⚠ 卡1的极难页签**默认不一定是选中态**(实测: 选中态模板在它身上只有 0.867,
      卡2/卡3 的选中态是 0.99) → 共享模板经常不命中。页签点击无消耗且幂等
      (已选中再点=无操作), 所以模板不中就**按标题锚定预测点直接点**，点完复查。
    """
    h = pick_hard(sc)
    if h is not None and h[2] > 0:
        sc.click(h, "陨石陷阱·极难页签")
        if not sc.dry:
            kit.nap(2.0)
        return True
    # 模板不中 → 标题锚定 + 偏移的预测点(页签无消耗, 点错也只是点在卡1标题附近空白)
    t = actcard.find(sc, TITLE_TPL)
    if t is None:
        log("[warn] 连卡标题都找不到 → 沿用当前难度(留证)")
        sc.shot("hard_tab_missing")
        return True
    pred = actcard.predict(sc, t, HARD_OFF, CALIB)
    log(f"极难页签模板不命中 → 按预测点直接点 {pred[:2]} (锚定自标题 {t[:2]})")
    if sc.dry:
        return True
    sc.click_at(pred[0], pred[1], "陨石陷阱·极难页签(预测点)")
    kit.nap(2.0)
    h2 = pick_hard(sc)
    if h2 is not None and h2[2] > 0:
        log("点完复查: 极难页签已选中 ✓")
    else:
        log("[warn] 点完仍验不到极难页签选中 → 留证(对话框层还有难度闸门兜底)")
        sc.shot("hard_tab_unverified")
    return True


def fight(sc: kit.Screen):
    """局内(见 wb.battle.fight)。退出条件 = 回活动关卡页连续 3 次。"""
    return actcard.fight(sc, TITLE_TPL, FIGHT_TIMEOUT, label="陨石陷阱闪击")


def one_round(sc: kit.Screen) -> bool:
    """一轮: 到卡页 → 点极难 → 点闪击 → 对话框 → 局内。"""
    return actcard.one_round(
        sc, title_tpl=TITLE_TPL, dlg_tpl=DLG_TPL,
        flash_off=FLASH_OFF, flash_calib=CALIB,
        timeout=FIGHT_TIMEOUT, before_flash=click_hard,
    )


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if sc.dry:
        p = page(sc)
        log(f"当前页面 {p}")
        if p in ("actpage", "dialog"):
            h = pick_hard(sc)
            fl = pick_flash(sc)
            log(f"[dry] 极难页签: " + (f"会点 {h[:2]} (score={h[2]:.3f})" if h
                                    else "未命中(沿用当前难度)"))
            log(f"[dry] 闪击键: " + (f"会点 {fl[:2]} (score={fl[2]:.3f})" if fl
                                   else "未命中(需先导航到活动关卡页)"))
        else:
            log("[dry] 需先导航到活动关卡页(首页→闯关模式→活动关卡)")
        log("[dry] 计划输出完毕(未点击)")
        return True
    return one_round(sc)


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "meteor_trap", "陨石陷阱闪击（活动关卡页·极难）", run,
        plan=PLAN, prefix="mtrap_", lock_ttl=3600, th=TH,
    ))
