#!/usr/bin/env python
"""用例: 导弹猎场「闪击」（活动关卡页，每日免费次数，消耗体力）。

链路:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
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

from wb import actcard, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.85
FIGHT_TIMEOUT = 480         # 单轮(对话框里默认 2 次闪击)最长等待(自检会改小)
NAV_WAIT = 3.0              # 导航点击后等画面稳定
MH_TITLE = "mh_title"        # 卡标题(定位本卡的闪击)
MH_DLG_TPL = "mh_dlg_title"  # 对话框标题(「闪击-导弹猎场」)
UNKNOWN_TOLERATE = 3        # 连续几次 unknown 才认输(关卡页空载帧可达数秒)
NAV_WAIT = 2.5              # 点完导航键等页面切换
FLASH_OFF = (301, 176)      # 导弹猎场卡标题 → 该卡「闪击」键的偏移(量自 601x1143 实帧)
FLASH_CALIB = (601, 1143)   # 上面那个偏移的标定帧尺寸
FLASH_TOL = 60              # 模板命中与锚点预测的最大距离(超过就认为命中的是另一张卡)

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_event_lv 活动关卡)--> 活动关卡页
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
    return actcard.on_card(sc, MH_TITLE)


def page(sc: kit.Screen) -> str:
    """当前页面: prompt / dialog / actpage / stage / home / unknown(顺序即优先级)。"""
    return actcard.page(sc, MH_TITLE, MH_DLG_TPL)


def close_prompt(sc: kit.Screen) -> bool:
    """关掉「次数已耗尽」提示(只在确认看到该文案后才调用)。"""
    return actcard.close_prompt(sc)


def pick_flash(sc: kit.Screen):
    """导弹猎场那张卡的「闪击」键: 卡标题锚定 + 缩放偏移 → 最近命中。"""
    return actcard.pick_flash(sc, MH_TITLE, FLASH_OFF, FLASH_CALIB)


def goto_actpage(sc: kit.Screen) -> bool:
    """从首页/关卡页/已在活动关卡页都能到活动关卡页。"""
    return actcard.goto_card(sc, MH_TITLE, MH_DLG_TPL)


def fight(sc: kit.Screen):
    """局内(循环见 wb.battle.fight): 点技能 → 复活 → 装备UP → 结算继续。

    退出条件 = 回到活动关卡页，连续 3 次(~6s)仍停留才算真打完。
    """
    return actcard.fight(sc, MH_TITLE, FIGHT_TIMEOUT, label="本轮闪击")


def one_round(sc: kit.Screen) -> bool:
    """一轮闪击: 到活动关卡页 → 点闪击 → 对话框 → 点闪击 → 局内。"""
    return actcard.one_round(sc, title_tpl=MH_TITLE, dlg_tpl=MH_DLG_TPL,
                             flash_off=FLASH_OFF, flash_calib=FLASH_CALIB,
                             timeout=FIGHT_TIMEOUT)


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
