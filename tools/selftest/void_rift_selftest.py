#!/usr/bin/env python
"""离线自检: void_rift（虚空裂隙-秘钥工坊）—— 零消耗，不碰游戏窗口。

夹具(2026-10-10 实探真帧, 812x1518, 每一步各一张):
    STAGE   = "_vk7_vk7_stagepage.png"   关卡页(右列: 深空巡航/逐星长阶/虚空裂隙)
    RIFT    = "_vk8_vk8_rift.png"        虚空裂隙页(底部: 秘钥工坊/异度集市/幸运星期六/返回)
    SHOP    = "_vk9_vk9_workshop.png"    密钥工坊页(6 张兑换卡, 左上=免费)

覆盖:
    ① 虚空裂隙卡定位: vk_entry 在关卡页命中 (710,745)±8 —— 且**不是**逐星长阶卡
       (stage_stair 在 (701,613), 两卡距离 >100px, 锁「点错卡」)
    ② 秘钥工坊定位: vk_workshop 在裂隙页命中 (99,1450)±8
    ③ 免费钮定位: vk_free 在工坊页命中 (225,811)±8
    ④ 免费钮区分度: vk_free 在**同页**次高 <0.90(500💎 同款黄底 0.842) —— 阈值防线
    ⑤ 误点付费两道防线: 真订单页 True / 工坊页 False / **奖励弹窗 False**(回归); 槽位锚定拒付
    ⑥ dry 零点击零写盘; ⑦ 并发锁互斥
    ⑧ 恭喜弹窗必领取: 回放「点免费→弹窗→点领取」, 断言两次点击 = [免费槽位, 领取钮]
       (回归 2026-10-11: 旧订单页判据是「暗像素>150」, 对暗底的奖励弹窗必误报,
        close 后直接 return → 领取被跳过 → 弹窗滞留 → 返回全失败 code=1)

用法:
    uv run python tools/selftest/void_rift_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from wb.selftest_kit import FakeRect  # noqa: E402
from tools.cases import void_rift as vr  # noqa: E402

STAGE = "_vk7_vk7_stagepage.png"
RIFT = "_vk8_vk8_rift.png"
SHOP = "_vk9_vk9_workshop.png"
SHEET = "_vkB2_now_state.png"    # 事故帧: 误点 18元付费钮后弹出的充值订单页(白底, 2026-10-10)
POPUP = "_vkA_after_free.png"    # 「恭喜获得」奖励弹窗(暗底, 2026-10-10) —— 旧暗像素判据曾把它当订单页

C_ENTRY = (710, 745)        # 虚空裂隙卡中心
C_WORKSHOP = (99, 1450)     # 秘钥工坊钮中心
C_FREE = (225, 811)         # 免费钮中心
C_STAIR = (701, 613)        # 逐星长阶卡(对照: 别点错)
C_CLAIM = (416, 1288)       # 「恭喜获得」弹窗的领取钮中心(claim_btn 在奖励弹窗真帧 0.994)


def _frame(name: str) -> kit.Screen:
    img = cv2.imread(str(SHOTS_DIR / name))
    assert img is not None, f"缺夹具 {name}"
    h, w = img.shape[:2]
    sc = kit.Screen(FakeRect(0, 0, w, h), th=vr.TH, dry=True, prefix="vk_")
    import wb.bot as _bot
    _bot.grab_window = lambda rect, _i=img: _i
    return sc


def case_entry(rp):
    """① 虚空裂隙卡定位 + 不与逐星长阶卡混淆。"""
    sc = _frame(STAGE)
    e = sc.find(vr.ENTRY_TPL)
    stair = sc.find("stage_stair", 0.0)
    ok_e = e is not None and abs(e[0] - C_ENTRY[0]) <= 8 and abs(e[1] - C_ENTRY[1]) <= 8
    # 高阈值下 vk_entry 不得命中逐星长阶卡(距离 >100px)
    near_stair = (e is not None and abs(e[1] - C_STAIR[1]) < 60)
    return ok_e and not near_stair, (
        f"虚空裂隙卡={e and (e[0], e[1])} (期望 {C_ENTRY}±8) "
        f"逐星长阶锚={stair and (stair[0], stair[1])} 误命中间距={e and abs(e[1]-C_STAIR[1])}")


def case_workshop(rp):
    """② 秘钥工坊定位。"""
    sc = _frame(RIFT)
    w2 = sc.find(vr.SHOP_TPL)
    good = w2 is not None and abs(w2[0] - C_WORKSHOP[0]) <= 8 and abs(w2[1] - C_WORKSHOP[1]) <= 8
    return good, f"秘钥工坊={w2 and (w2[0], w2[1])} (期望 {C_WORKSHOP}±8)"


def case_free(rp):
    """③ 免费钮定位 + ④ 同页次高 <0.90(防误点 500💎)。"""
    sc = _frame(SHOP)
    f = sc.find(vr.FREE_TPL, 0.0)
    ok_pos = f is not None and abs(f[0] - C_FREE[0]) <= 8 and abs(f[1] - C_FREE[1]) <= 8
    # 次高(抹掉最佳后)
    img = cv2.imread(str(SHOTS_DIR / SHOP))
    tpl = cv2.imread(str(SHOTS_DIR.parent / "templates" / "vk_free.png"))
    res = cv2.matchTemplate(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                            cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY), cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    r2 = res.copy()
    r2[max(0, loc[1] - 12):loc[1] + 12, max(0, loc[0] - 12):loc[0] + 12] = -1
    _, m2, _, _ = cv2.minMaxLoc(r2)
    ok_margin = m2 < vr.TH_FREE
    return ok_pos and ok_margin, (
        f"免费钮={f and (f[0], f[1])} (期望 {C_FREE}±8) 同页次高={m2:.3f} (需 <{vr.TH_FREE})")


def case_order_guard(rp):
    """⑤ 误点付费事故(2026-10-10)的两道防线:
        a) 订单弹窗检测: 真订单页 True / 正常工坊页 False / **奖励弹窗 False**
           (末项是 2026-10-11 bug 的回归: 旧暗像素判据在奖励弹窗上必误报)
        b) 槽位锚定: 桩 find 返回**事故中真实发生**的非槽位命中 (613,1219, 0.934=18元钮)
           → find_free 必须拒绝(None), 绝不点它
    """
    import wb.bot as _bot
    old_f = _bot.grab_window

    def _sheet_feat(name):
        img = cv2.imread(str(SHOTS_DIR / name))
        _bot.grab_window = lambda r, _i=img: _i
        h, w = img.shape[:2]
        sc = kit.Screen(FakeRect(0, 0, w, h), th=vr.TH, dry=True)
        return vr._order_sheet_open(sc)

    try:
        a1 = _sheet_feat(SHEET)     # 真订单页(白底) → True
        a2 = _sheet_feat(SHOP)      # 正常工坊页(暗底) → False
        a3 = _sheet_feat(POPUP)     # 奖励弹窗(暗底) → False  ← 回归点
        ws = cv2.imread(str(SHOTS_DIR / SHOP))
        _bot.grab_window = lambda r, _i=ws: _i
        h2, w2 = ws.shape[:2]
        sc2 = kit.Screen(FakeRect(0, 0, w2, h2), th=vr.TH, dry=True)
        # b) 槽位锚定拒付
        real_find = sc2.find
        sc2.find = lambda n, th=None: (613, 1219, 0.934) if n == vr.FREE_TPL else real_find(n, th)
        rej = vr.find_free(sc2)
        # c) 正例: 真槽位命中照常放行
        sc2.find = real_find
        hit = vr.find_free(sc2)
    finally:
        _bot.grab_window = old_f
    good = (a1 is True) and (a2 is False) and (a3 is False) and (rej is None) and (hit is not None)
    return good, (f"订单页检测={a1}(期望 True) 工坊页={a2}(期望 False) "
                  f"奖励弹窗={a3}(期望 False, 回归) "
                  f"非槽位命中被拒={rej is None} 真槽位放行={hit and (hit[0], hit[1])}")


def case_claim_popup(rp):
    """⑧ 「恭喜获得」弹窗**必须领取**(2026-10-11 bug 回归)。

    回放: 工坊页(免费钮) → 点免费 → 奖励弹窗(claim_btn) → 点领取 → 回工坊页。
    断言: 恰好 2 次点击 = [免费槽位, 领取钮], 且 claim_free 返回 True。
    旧版会在护栏误报后直接 return, 领取被跳过(只有 1 次点击) → 本场景必 FAIL。
    """
    sc = kit.Screen(FakeRect(0, 0, 812, 1518), th=vr.TH, dry=False, prefix="vk_")
    ok = vr.claim_free(sc)
    clicks = rp.real_clicks
    good = (ok is True and len(clicks) == 2
            and abs(clicks[0][0] - C_FREE[0]) <= 6 and abs(clicks[0][1] - C_FREE[1]) <= 6
            and abs(clicks[1][0] - C_CLAIM[0]) <= 8 and abs(clicks[1][1] - C_CLAIM[1]) <= 8)
    return good, (f"claim_free={ok} 点击={clicks} "
                  f"(期望 [免费{C_FREE}, 领取{C_CLAIM}])")


def case_orphan_popup(rp):
    """⑨ 残留「恭喜获得」弹窗自愈: 上一次中断留下的孤岛弹窗会盖住一切按钮,
    to_workshop 必须先领掉它再导航(否则下次运行必卡死)。

    回放: 奖励弹窗(孤岛) → 点领取 → 回到工坊页。断言 1 次点击 + 返回 True。
    """
    sc = kit.Screen(FakeRect(0, 0, 812, 1518), th=vr.TH, dry=False, prefix="vk_")
    ok = vr.to_workshop(sc)
    clicks = rp.real_clicks
    good = (ok is True and len(clicks) == 1
            and abs(clicks[0][0] - C_CLAIM[0]) <= 8 and abs(clicks[0][1] - C_CLAIM[1]) <= 8)
    return good, f"to_workshop={ok} 点击={clicks} (期望 [领取{C_CLAIM}])"


def case_dry(rp):
    """⑤ dry: 零点击零写盘。"""
    sc = _frame(SHOP)
    sc2 = kit.Screen(sc.rect, th=vr.TH, dry=True, prefix="vk_")
    import wb.bot as _bot
    img = cv2.imread(str(SHOTS_DIR / SHOP))
    _bot.grab_window = lambda rect, _i=img: _i
    ok = vr.run(sc2, kit.Args(dry=True))
    return ok and not rp.real_clicks and not rp.shots, \
        f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(_rp):
    """⑥ 并发锁互斥。"""
    name = "void_rift_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("①虚空裂隙卡定位(不混逐星长阶)", [STAGE], case_entry),
    ("②秘钥工坊定位", [RIFT], case_workshop),
    ("③免费钮定位 + ④同页次高<0.90", [SHOP], case_free),
    ("⑤误点付费两道防线(订单页检测+奖励弹窗不误判+槽位锚定)", [SHEET, SHOP, POPUP], case_order_guard),
    ("⑥dry 零点击零写盘", [SHOP], case_dry),
    ("⑦并发锁互斥", [SHOP], case_lock),
    ("⑧恭喜弹窗必领取(回归: 护栏误报曾跳过领取)", [SHOP, POPUP, SHOP], case_claim_popup),
    ("⑨残留恭喜弹窗自愈(to_workshop 先领掉)", [POPUP, SHOP], case_orphan_popup),
]


def ensure_fixtures() -> bool:
    need = [STAGE, RIFT, SHOP, SHEET, POPUP]
    missing = [f for f in need if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具: {missing}")
        return False
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("void_rift 离线自检（三级导航定位/免费钮区分度）", SCENES)