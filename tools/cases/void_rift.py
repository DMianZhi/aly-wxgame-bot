#!/usr/bin/env python
"""用例: 虚空裂隙-秘钥工坊（免费领取，每日一次免费位）。

链路(2026-10-10 实探测图定版):
    首页 --(stage_btn 闯关模式)--> 关卡页
    --(vk_entry 「虚空裂隙」卡, 右列最下一张[逐星长阶之下])--> 虚空裂隙页
    --(vk_workshop 底部功能区最左「秘钥工坊」)--> 密钥工坊页(KEY SHOP, 6 张兑换卡)
    --(vk_free 左上卡「免费」钮 (225,811), 阈值 0.90[次高 0.842=相邻500钻石钮])-->
      恭喜弹窗(claim_btn 领取) → vk_back 逐层返回首页

    ⚠ 页面层级: 关卡页 → 虚空裂隙页 → 密钥工坊页 都是**独立页**(各页自带底部「返回」钮
      vk_back, 不在 kit.goto_home 的模板覆盖内 → 本用例自带返回循环)
    ⚠ 免费钮只在**未领取**时是亮黄可点; 已领/冷却 → vk_free 不命中 → 留证收工(不算失败)
    ⚠ 付费钮(500💎/6元/18元)与免费钮同款黄底 → 阈值必须 ≥0.90, 绝不误点付费
    ⚠ 虚空裂隙卡在右列**最下**(深空巡航/逐星长阶/虚空裂隙), 逐星长阶模板 stage_stair
      实测 (701,613) 可作校准锚

    模板标定(2026-10-10, 812x1518 真帧):
      vk_entry    自匹配 1.000 / 次高 0.734
      vk_workshop 自匹配 1.000 / 次高 0.671
      vk_free     自匹配 1.000 / 次高 0.842(500钻石钮) → 用 0.90
      vk_back     自匹配 1.000 / 次高 0.862 → 用 0.90

用法:
    uv run python tools/cases/void_rift.py [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2  # noqa: F401  (订单弹窗兜底检测的灰度用)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86
TH_FREE = 0.90          # 免费钮: 与相邻 500💎 同款黄底 → 抬高
TH_BACK = 0.90
FREE_XY = (225, 811)    # 免费钮的**固定槽位**(左上卡)—— 位置锚定的最后防线, 见 find_free()
FREE_TOL = 25           # 槽位容差(px)
ENTRY_TPL = "vk_entry"          # 关卡页右列「虚空裂隙」卡
SHOP_TPL = "vk_workshop"        # 虚空裂隙页底部「秘钥工坊」
FREE_TPL = "vk_free"            # 密钥工坊页左上卡「免费」钮
BACK_TPL = "vk_back"            # 本页链自带的底部「返回」钮
# ⚠ 付费误点事故(2026-10-10): 免费已领后 vk_free 掉到**次优 0.934**=相邻 18元钮 →
#   点开充值订单页。从此 find_free() **必须位置锚定**: 分数≥0.90 且落点在 FREE_XY±25px。
ORDER_X = (120, 353)    # 充值订单弹窗的关闭 X(左上角) —— 万一误开, 用它兜底关掉


def _ref(x: int, y: int):
    """实帧(812x1518)量出的客户区坐标 → 基准坐标(常量统一口径)。"""
    from wb import bot as _bot
    return _bot.client_to_ref(x, y, 812, 1518)


BACK_SLOT = _ref(727, 1448)   # 三页「返回」钮的固定槽位(工坊页的略大, vk_back 模板不中时兜底)


def find_free(sc: kit.Screen):
    """找**真正**的免费钮: 分数≥TH_FREE 且位置在固定槽位 FREE_XY±25px。其余一律不算。"""
    h = sc.find(FREE_TPL, TH_FREE)
    if h is None:
        return None
    if abs(h[0] - FREE_XY[0]) > FREE_TOL or abs(h[1] - FREE_XY[1]) > FREE_TOL:
        log(f"⚠ vk_free 命中 {h[:2]} (score={h[2]:.3f}) 但**不在免费槽位** {FREE_XY}±{FREE_TOL} "
            f"→ 判为同名黄底付费钮, 拒绝点击")
        return None
    return h


def _order_sheet_open(sc: kit.Screen) -> bool:
    """有没有误开充值订单弹窗(其左上角有个专属的深色 × 字形)。"""
    import numpy as np
    x, y = ORDER_X
    roi = sc.roi(*_ref_roi(x, y, 29, 29), img=sc.grab())
    if roi is None or getattr(roi, "size", 0) == 0:
        return False
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return int((g < 120).sum()) > 150      # 实测 × 字形暗像素 238


def _ref_roi(x: int, y: int, w: int, h: int):
    """把「某帧量出的矩形」按基准口径交给 sc.roi —— 单张实帧(812x1518)量出。"""
    from wb import bot as _bot
    return _bot.measured_rect(x - w // 2, y - h // 2, w, h, (812, 1518))


def _close_order_sheet(sc: kit.Screen) -> None:
    log("⚠ 检测到充值订单弹窗(误点付费按钮) → 只点其左上角 X 关闭, 绝不碰「确认」")
    sc.shot("wrong_payment_sheet")
    sc.click_base(*ORDER_X, "订单弹窗 X(兜底关闭)")
    kit.nap(2.0)


PLAN = """[dry] 计划:
  首页 --(stage_btn)--> 关卡页 --(vk_entry 虚空裂隙卡, 右列最下)--> 虚空裂隙页
  --(vk_workshop 底部最左「秘钥工坊」)--> 密钥工坊页
  --(vk_free 左上卡「免费」钮, 阈值 0.90 **且必须落在免费槽位 ±25px**)--> 恭喜弹窗领取
  --(vk_back 逐层返回)--> 首页
  无可领: 免费钮不命中/不在槽位 → 留证收工(不算失败)
  护栏: 万一误开充值订单页 → 只点其左上角 X 关闭, 绝不碰「确认」"""


def to_workshop(sc: kit.Screen) -> bool:
    """从任意页到密钥工坊页(残留面板顺手退回)。"""
    for _ in range(8):
        # 到页判定: **任何** vk_free 命中(含被槽位闸门拒绝的付费钮命中)都说明已在工坊页
        # —— 免费已领时槽位闸门会拒付, 不能拿它当「到没到页」的判据(2026-10-10 修)
        if sc.find(FREE_TPL, TH_FREE) is not None:
            return True
        ent = sc.find(ENTRY_TPL)
        ws = sc.find(SHOP_TPL)
        if ws is not None:                    # 已在虚空裂隙页 → 点秘钥工坊
            sc.click(ws, "秘钥工坊")
            kit.nap(3.0)
            continue
        if ent is not None:                   # 在关卡页 → 点虚空裂隙卡
            sc.click(ent, "虚空裂隙卡")
            kit.nap(4.0)
            continue
        if kit.is_home(sc):
            if not sc.tap("stage_btn", th=0.90, wait=2.5, label="闯关模式"):
                return False
            continue
        if sc.find(BACK_TPL, TH_BACK) is not None:
            sc.click(sc.find(BACK_TPL, TH_BACK), "返回(脱离未知页)")
            kit.nap(1.8)
            continue
        if kit.goto_home(sc):
            continue
        log("停在无法识别的页面 → 留证放弃")
        sc.shot("vk_lost")
        return False
    return False


def claim_free(sc: kit.Screen) -> bool:
    """在工坊页点「免费」并领取。

    返回「本次是否**无异常完成**」: 领到了 → True; 无可领(已领/冷却, 槽位闸门拒绝) →
    也 True(今天没得领不是失败, 对齐 guild_boss「已领→收工」的语义); 只有误开付费页
    这种真异常才 False。
    """
    free = find_free(sc)
    if free is None:
        log("「免费」不在槽位(已领/冷却/只有付费钮) → 留证收工(今天没得领, 不算失败)")
        sc.shot("vk_nothing")
        return True
    sc.click(free, "免费(槽位锚定)")
    kit.nap(3.0)
    # ⚠ 护栏: 万一仍误开充值订单页 → 只点其左上角 X 关掉(绝不碰确认)
    if _order_sheet_open(sc):
        _close_order_sheet(sc)
        return False
    claimed = 0
    for _ in range(4):
        c = sc.find("claim_btn")
        if c is None:
            break
        sc.click(c, "恭喜获得-领取")
        claimed += 1
        kit.nap(2.0)
    log(f"免费领取完成 (恭喜弹窗领取 {claimed} 次)")
    return True


def back_home(sc: kit.Screen) -> bool:
    """逐层返回: 本页链(工坊→裂隙→关卡)用自带底部「返回」钮; vk_back 模板不中时
    按**固定槽位** (727,1448) 兜底(三页的返回钮都在这个位置附近, 实测工坊页略大不中模板)。"""
    for _ in range(6):
        if kit.is_home(sc):
            return True
        b = sc.find(BACK_TPL, TH_BACK)
        if b is not None:
            sc.click(b, "返回")
        else:
            log("vk_back 模板不中 → 按固定槽位点「返回」")
            sc.click_base(*BACK_SLOT, "返回(槽位兜底)")
        kit.nap(1.8)
    return kit.goto_home(sc)


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if sc.dry:
        e, w2, f2 = sc.find(ENTRY_TPL), sc.find(SHOP_TPL), sc.find(FREE_TPL, TH_FREE)
        log(f"[dry] 计划: 首页→闯关→虚空裂隙({'已在屏' if e else '需导航'})→秘钥工坊"
            f"({'已在屏' if w2 else '需导航'})→免费({'命中' if f2 else '未命中'})"
            f"→恭喜领取→逐层返回")
        return True
    if not kit.is_home(sc):
        kit.goto_home(sc)
    if not to_workshop(sc):
        log("未能到达密钥工坊页")
        sc.shot("vk_nav_fail")
        return False
    ok = claim_free(sc)
    if not back_home(sc):
        sc.shot("vk_back_fail")
        log("[warn] 未能确认回到首页")
    return ok


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "void_rift", "虚空裂隙-秘钥工坊（免费领取）", run,
        plan=PLAN, prefix="vk_", lock_ttl=600, th=TH,
    ))