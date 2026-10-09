#!/usr/bin/env python
"""用例: 激光迷宫「闪击」（活动关卡页第二张卡 · 极难，每日免费次数，消耗体力）。

链路:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
    --(选中该卡「极难」页签 lm_hard，取离本卡标题最近的那个)-->
    --(激光迷宫卡标题 lm_title 锚点 + 偏移 → 该卡橙「闪击」mh_flash)-->
      闪击对话框(lm_dlg_title「闪击-激光迷宫 极难」)
    --(mh_dlg_go「闪击」)--> 局内(与 BOSS 闪击同一套 wb.battle.fight:
        每 5.2s 点技能 → 阵亡钻石复活 → 装备UP默认项 → 结算继续)--> 回活动关卡页

    ⚠ 活动关卡页三张卡(陨石陷阱/激光迷宫/导弹猎场)**同款布局、同款闪击键** →
      一律用 lm_title 锚点定位，绝不按绝对坐标硬点(点错卡 = 花错资源的真事故)
    ⚠ 「极难」页签三张卡也同款 → 同样取「离 lm_title 最近」的那个命中
    ⚠ 对话框里「闪击 2 次 / ⚡80」是**游戏默认**，不擅改(改次数=改消耗，交给玩家决定)
    ⚠ 0 次降级: 点闪击 → 弹「今日可攻打次数已耗尽」→ 关掉即算跳过，**不算失败**
    ⚠ 局内结束判据: 回到活动关卡页(lm_title 在) **连续 3 次** —— 战斗间隙会短暂闪过

    ⚠ 模板缺失(如尚未截到某状态)时判定函数返回 None 并留证截图，不炸、不瞎点。

用法:
    uv run python tools/cases/laser_maze.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import actcard, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = actcard.TH
TITLE_TPL = "lm_title"          # 卡标题「激光迷宫」(定位本卡的闪击/极难)
DLG_TPL = "lm_dlg_title"        # 对话框标题「闪击-激光迷宫」
HARD_TPL = "lm_hard"            # 「极难」页签(选中态；三张卡同款)
FIGHT_TIMEOUT = 480             # 单轮(对话框默认 2 次闪击)最长等待(自检会改小)

# 量自 814x1507 实帧: 卡标题中心 → 本卡「闪击」中心 / 「极难」页签中心
FLASH_OFF = (400, 255)
HARD_OFF = (576, -18)
CALIB = (814, 1507)

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
  --> 激光迷宫卡: 先点「极难」页签(lm_hard，取离 lm_title 最近的命中)
  --> 该卡橙「闪击」(lm_title 锚点 + 偏移 400,255) → 闪击对话框(lm_dlg_title)
  --> 点「闪击」(mh_dlg_go，次数 2 次/⚡80 = 游戏默认，**不擅改**) → 局内
      → 每 5.2s 点技能 → 阵亡复活 → 装备UP → 结算继续，直到回活动关卡页(连续 3 次)
  次数已耗尽: 弹「今日可攻打次数已耗尽」→ 确认关闭 → 跳过(不算失败)
  收尾: 回首页"""


def page(sc: kit.Screen) -> str:
    """当前页面: prompt / dialog / actpage / stage / home / unknown。"""
    return actcard.page(sc, TITLE_TPL, DLG_TPL)


def goto_actpage(sc: kit.Screen) -> bool:
    """任意页 → 激光迷宫所在的活动关卡页。"""
    return actcard.goto_card(sc, TITLE_TPL, DLG_TPL)


def pick_flash(sc: kit.Screen):
    """激光迷宫那张卡的「闪击」键(卡标题锚定 + 缩放偏移，取最近的命中)。"""
    return actcard.pick_flash(sc, TITLE_TPL, FLASH_OFF, CALIB)


def pick_hard(sc: kit.Screen):
    """激光迷宫那张卡的「极难」页签: 同款页签取离本卡标题最近的那个。"""
    t = actcard.find(sc, TITLE_TPL)
    if t is None:
        return None
    pred = actcard.predict(sc, t, HARD_OFF, CALIB)
    return actcard.pick_near(sc, HARD_TPL, pred, "极难页签")


def click_hard(sc: kit.Screen) -> bool:
    """点「极难」页签。找不到就只告警、**不中止**(极难本就是该卡的默认选中态)。"""
    h = pick_hard(sc)
    if h is None:
        log("[warn] 定位不到「极难」页签 → 沿用当前难度(留证截图，事后可核对)")
        sc.shot("hard_tab_missing")
        return True
    if h[2] > 0:
        sc.click(h, "激光迷宫·极难页签")
        if not sc.dry:
            kit.nap(2.0)
    else:
        sc.click(h, "激光迷宫·极难页签(预测点)")
    return True


def fight(sc: kit.Screen):
    """局内(见 wb.battle.fight)。退出条件 = 回活动关卡页连续 3 次。"""
    return actcard.fight(sc, TITLE_TPL, FIGHT_TIMEOUT, label="激光迷宫闪击")


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
        "laser_maze", "激光迷宫闪击（活动关卡页·极难）", run,
        plan=PLAN, prefix="laser_", lock_ttl=3600, th=TH,
    ))
