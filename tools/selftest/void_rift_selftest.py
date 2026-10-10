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
    ⑤ dry 零点击零写盘; ⑥ 并发锁互斥

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
SHEET = "_vkB2_now_state.png"    # 事故帧: 误点 18元付费钮后弹出的充值订单页(2026-10-10)

C_ENTRY = (710, 745)        # 虚空裂隙卡中心
C_WORKSHOP = (99, 1450)     # 秘钥工坊钮中心
C_FREE = (225, 811)         # 免费钮中心
C_STAIR = (701, 613)        # 逐星长阶卡(对照: 别点错)


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
        a) 订单弹窗检测: 事故帧 True / 正常工坊页 False
        b) 槽位锚定: 桩 find 返回**事故中真实发生**的非槽位命中 (613,1219, 0.934=18元钮)
           → find_free 必须拒绝(None), 绝不点它
    """
    import wb.bot as _bot
    # a) 订单弹窗检测
    old_f = _bot.grab_window
    try:
        sheet = cv2.imread(str(SHOTS_DIR / SHEET))
        _bot.grab_window = lambda r, _i=sheet: _i
        h1, w1 = sheet.shape[:2]
        sc1 = kit.Screen(FakeRect(0, 0, w1, h1), th=vr.TH, dry=True)
        a1 = vr._order_sheet_open(sc1)
        ws = cv2.imread(str(SHOTS_DIR / SHOP))
        _bot.grab_window = lambda r, _i=ws: _i
        h2, w2 = ws.shape[:2]
        sc2 = kit.Screen(FakeRect(0, 0, w2, h2), th=vr.TH, dry=True)
        a2 = vr._order_sheet_open(sc2)
        # b) 槽位锚定拒付
        real_find = sc2.find
        sc2.find = lambda n, th=None: (613, 1219, 0.934) if n == vr.FREE_TPL else real_find(n, th)
        rej = vr.find_free(sc2)
        # c) 正例: 真槽位命中照常放行
        sc2.find = real_find
        hit = vr.find_free(sc2)
    finally:
        _bot.grab_window = old_f
    good = (a1 is True) and (a2 is False) and (rej is None) and (hit is not None)
    return good, (f"订单页检测={a1}(期望 True) 工坊页={a2}(期望 False) "
                  f"非槽位命中被拒={rej is None} 真槽位放行={hit and (hit[0], hit[1])}")


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
    ("⑤误点付费两道防线(订单页检测+槽位锚定)", [SHEET, SHOP], case_order_guard),
    ("⑥dry 零点击零写盘", [SHOP], case_dry),
    ("⑦并发锁互斥", [SHOP], case_lock),
]


def ensure_fixtures() -> bool:
    need = [STAGE, RIFT, SHOP, SHEET]
    missing = [f for f in need if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具: {missing}")
        return False
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("void_rift 离线自检（三级导航定位/免费钮区分度）", SCENES)