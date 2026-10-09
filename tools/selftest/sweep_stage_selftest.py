#!/usr/bin/env python
"""离线自检: sweep_stage（扫荡关卡）—— 零消耗，不碰游戏窗口。

夹具:
    真帧 —— 首页(`_guildtest_home.png`) / 关卡页(`snap_20261008_091133.png`，只有 stage_sweep)
            / 扫荡面板+背包已满(`_diag_now.png`)
    合成 —— 面板各状态 = 深底 + `templates/` 里的**真模板**（面板帧历史上没留过图）。
            注意 `sweep_tabbar` 模板本身就是在「4星已选中」时截的（`sweep_tab4` 在它内部命中 1.000），
            所以贴了 tabbar 的帧 = tab4 已选中态。
            合成帧一律用 `_ts_sweep_` 前缀 —— 各自检共用 shots/，重名会被别的自检覆盖（踩过）。

覆盖:
    ① 模式识别/切换（normal ↔ hero 的 label 互斥，已实测无交叉误命中）
    ② 导航: 首页→关卡页→扫荡面板
    ③ 4星页签: 已选中=零点击 / 未选中=点「页签栏中心+20px」后再确认
    ④ 材料最少优先: 默认 idx=1 → 点第 1 个图标(812 下(156,345))；--material=0 → 零点击
    ⑤ 单轮成功: 扫荡 → 双倍奖励 → 跳过卡弹窗选「不使用」→ 广告看完关掉 → 关结算弹层
    ⑥ 无翻倍机会 → 换下一关（no_double，不误判成完成）
    ⑦ 连续 3 关无翻倍 → 收工（不空转到 N 轮）
    ⑧ 背包已满 → 清理后重进面板 → 本轮照常完成
    ⑨ 面板被误关 → ensure_context 复查并重进
    ⑩ dry 零点击零写盘；⑪ 并发锁互斥；⑫ 小窗口(601x1143)下基准坐标必须换算

已知缺口（诚实标注）:
    「4星页签未选中」没有真帧（tabbar 模板只截过选中态），场景 ③b 用桩让 tab4 首次检查落空，
    验的是**点击坐标与二次确认逻辑**，未验未选中态的像素差异。

用法:
    uv run python tools/selftest/sweep_stage_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR, TEMPLATE_PATH  # noqa: E402
from tools.cases import sweep_stage as sw  # noqa: E402

HOME = "_guildtest_home.png"                     # 真帧: 首页
STAGE_PAGE = "snap_20261008_091133.png"          # 真帧: 关卡页(只有 stage_sweep)
BAGFULL = "_diag_now.png"                        # 真帧: 扫荡面板 + 背包已满弹窗

# 合成面板帧（深底 + 真模板）
BR, BH = 400, 140          # 页签栏中心
P_NORMAL = "_ts_sweep_normal.png"       # 普通模式 + 页签栏(4星已选中) + 关闭键
P_HERO = "_ts_sweep_hero.png"           # 英雄模式 + 同上
P_BTN = "_ts_sweep_btn.png"             # P_NORMAL + 「扫荡」可用行
P_DOUBLE = "_ts_sweep_double.png"       # P_BTN + 「双倍奖励」
P_DONE = "_ts_sweep_done.png"           # P_NORMAL + 「扫荡完成」弹层
AD_JUMPNO = "_ts_sweep_ad_jumpno.png"         # 跳过卡弹窗
AD_DONE = "_ts_sweep_ad_done.png"             # 广告看完(已获得奖励) + 关闭键
BTN_XY = (400, 500)                     # 合成帧里 sweep_btn 的位置
DBL_XY = (400, 900)
CLOSE_XY = (752, 60)
TOGGLE_XY = (700, 1400)
JUMP_XY = (400, 620)
ADCLOSE_XY = (700, 300)

# 金标准坐标（真帧上实测）
C_STAGE_BTN = (620, 1383)               # stage_btn@首页
C_STAGE_SWEEP = (93, 1334)              # stage_sweep@关卡页
MAT1 = (156, 345)                       # MAT_ICONS[0] 在 RECT=812x1518 下的实际落点(= 实帧量得的原值)


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=sw.TH, dry=dry, prefix="sweep_")


def _blank() -> np.ndarray:
    """深底 + 轻微噪声。

    纯平底色会让归一化相关变得病态(TM_CCOEFF_NORMED 在平坦区域可任意位置命中 1.0)，
    真截图从不会完全平坦 —— 加可复现的噪声，让峰值唯一落在贴图位置。
    """
    rng = np.random.default_rng(20261008)
    return (16 + rng.integers(0, 7, (1518, 812, 3))).astype(np.uint8)


def _paste(img, tpl: str, cx: int, cy: int):
    t = cv2.imread(str(TEMPLATE_PATH(tpl)))
    h, w = t.shape[:2]
    x0, y0 = max(0, cx - w // 2), max(0, cy - h // 2)
    img[y0:y0 + h, x0:x0 + w] = t
    return img


def _panel(name: str, toggle: str, extra: tuple[tuple[str, int, int], ...] = ()) -> None:
    img = _blank()
    _paste(img, "sweep_close", *CLOSE_XY)
    _paste(img, toggle, *TOGGLE_XY)
    _paste(img, "sweep_tabbar", BR, BH)          # tabbar 自带「4星已选中」态
    for tpl, cx, cy in extra:
        _paste(img, tpl, cx, cy)
    cv2.imwrite(str(SHOTS_DIR / name), img)


def ensure_fixtures() -> bool:
    for f in (HOME, STAGE_PAGE, BAGFULL):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}")
            return False
    made = []

    def need(name: str) -> bool:
        return not (SHOTS_DIR / name).is_file()

    if need(P_NORMAL):                           # to_hero 在场 = 当前 normal
        _panel(P_NORMAL, "sweep_to_hero")
        made.append(P_NORMAL)
    if need(P_HERO):                             # to_normal 在场 = 当前 hero
        _panel(P_HERO, "sweep_to_normal")
        made.append(P_HERO)
    if need(P_BTN):
        _panel(P_BTN, "sweep_to_hero", (("sweep_btn", *BTN_XY),))
        made.append(P_BTN)
    if need(P_DOUBLE):
        _panel(P_DOUBLE, "sweep_to_hero", (("sweep_btn", *BTN_XY), ("sweep_double", *DBL_XY)))
        made.append(P_DOUBLE)
    if need(P_DONE):
        _panel(P_DONE, "sweep_to_hero", (("sweep_done", 400, 700),))
        made.append(P_DONE)
    if need(AD_JUMPNO):
        cv2.imwrite(str(SHOTS_DIR / AD_JUMPNO), _paste(_blank(), "jump_no", *JUMP_XY))
        made.append(AD_JUMPNO)
    if need(AD_DONE):
        cv2.imwrite(str(SHOTS_DIR / AD_DONE),
                    _paste(_paste(_blank(), "ad_rewarded", 400, 200), "ad_close", *ADCLOSE_XY))
        made.append(AD_DONE)
    if made:
        print(f"[生成] 合成面板夹具 {', '.join(made)}（深底 + 真模板）")
    return True


# ------------------------------------------------------------------ 场景

def case_mode(rp):
    """① 模式识别 + 切换（hero → normal）。"""
    sc = _sc()
    rp.idx = 0                                # P_HERO 帧
    hero = sw.detect_mode(sc)
    rp.idx = 1                                # P_NORMAL 帧
    normal = sw.detect_mode(sc)
    print(f"  [{'ok  ' if hero == 'hero' else '!!  '}] 英雄帧识别={hero} (期望 hero)")
    print(f"  [{'ok  ' if normal == 'normal' else '!!  '}] 普通帧识别={normal} (期望 normal)")
    rp.idx = 0
    ok = sw.ensure_mode(sc, "normal")         # hero 帧上点 to_normal → 切到 normal(P_NORMAL)
    clicks_ok = st.check_clicks("切换器", rp.real_clicks, [(TOGGLE_XY[0], TOGGLE_XY[1])])
    return hero == "hero" and normal == "normal" and ok and clicks_ok, \
        f"识别 {hero}/{normal} 切换={ok} 点击={rp.real_clicks}"


def case_nav(rp):
    """② 导航: 首页→关卡页→扫荡面板。"""
    ok = sw.open_panel(_sc())
    clicks_ok = st.check_clicks("导航", rp.real_clicks, [C_STAGE_BTN, C_STAGE_SWEEP])
    return ok and clicks_ok, f"到达面板={ok} 点击={rp.real_clicks}"


def case_tab4_selected(rp):
    """③a 4星页签已选中 → 零点击直接通过。"""
    ok = sw.select_tab4(_sc())
    return ok and not rp.real_clicks, f"通过={ok} 点击={rp.real_clicks}(期望空)"


def case_tab4_unselected(rp):
    """③b 4星页签未选中 → 点「页签栏中心+20px」后再确认（未选中态无真帧，见文件头缺口说明）。"""
    sc = _sc()
    real_find, first = sc.find, {"done": False}

    def fake_find(name, th=None):
        if name == "sweep_tab4" and th == sw.TAB_TH and not first["done"]:
            first["done"] = True              # 桩: 首次检查「未选中」
            return None
        return real_find(name, th)

    sc.find = fake_find
    ok = sw.select_tab4(sc)
    clicks_ok = st.check_clicks("页签", rp.real_clicks, [(BR + 20, BH)])
    return ok and clicks_ok, f"通过={ok} 点击={rp.real_clicks}(期望 页签栏中心+20)"


def case_material_least(rp):
    """④ 材料最少优先: 默认 idx=1 → 点第 1 个图标。"""
    sw.select_material(_sc(), 1)
    clicks_ok = st.check_clicks("材料#1", rp.real_clicks, [MAT1])
    return clicks_ok, f"点击={rp.real_clicks}(期望 {MAT1} = 面板顶部计数最少的那个)"


# 同一基准点(172,346 = 812 实帧 (156,345) 归一来的) 在 601x1143 窗口下的落点。
# 手算: s=(1143-77)/1444=0.738227; x=(172-422.5)*s+300.5=115.6→116; y=77+(346-77)*s=275.6→276
# 不换算就是 (156,345) —— 偏 40px，tol=6 必抓。
C_MAT1_601 = (116, 276)


def case_small_window(rp):
    """⑫ 小窗口下基准坐标**必须**换算（否则 601 宽时 x=740 会点到窗口外）。

    这个尺寸不是编的：shots 里就存在 601x1143 的真帧（标题栏同样是 77px → 原生截图），
    说明游戏窗口会被改小。这里把 RECT 临时改成它，验的是「用例的基准常量确实过了换算」。
    """
    old = st.RECT
    st.RECT = (0, 0, 601, 1143)
    try:
        sw.select_material(_sc(), 1)
    finally:
        st.RECT = old
    ok = st.check_clicks("小窗口换算", rp.real_clicks, [C_MAT1_601])
    return ok, f"点击={rp.real_clicks}(期望 {C_MAT1_601} = 基准(156,345) 换算到 601x1143)"


def case_material_all(rp):
    """④b --material=0 → 保持「全部」，零点击。"""
    sw.select_material(_sc(), 0)
    return not rp.real_clicks, f"点击={rp.real_clicks}(期望空)"


def case_round_ok(rp):
    """⑤ 单轮成功: 扫荡 → 双倍 → 跳过卡「不使用」→ 关广告 → 关弹层。"""
    r = sw.one_round(_sc(), 1, "normal")
    clicks_ok = st.check_clicks("单轮", rp.real_clicks,
                                [BTN_XY, DBL_XY, JUMP_XY, ADCLOSE_XY])
    return r == "ok" and clicks_ok, f"结果={r}(期望 ok) 点击={rp.real_clicks}"


def case_round_no_double(rp):
    """⑥ 无翻倍机会 → 换下一关（不误判成完成）。"""
    r = sw.one_round(_sc(), 1, "normal")
    clicks_ok = st.check_clicks("无翻倍", rp.real_clicks, [BTN_XY])
    return r == "no_double" and clicks_ok, f"结果={r}(期望 no_double) 点击={rp.real_clicks}"


def case_phase_stop(rp):
    """⑦ 连续 3 关无翻倍 → 收工（不空转到 N 轮）。"""
    stat = sw.run_phase(_sc(), "normal", 5, 1)
    ok = stat.get("no_double") == 3 and len(stat) == 1
    n_btn = sum(1 for c in rp.real_clicks if abs(c[0] - BTN_XY[0]) <= 6
                and abs(c[1] - BTN_XY[1]) <= 6)
    print(f"  [{'ok  ' if ok else '!!  '}] stat={stat} (期望 {{'no_double': 3}})")
    print(f"  [{'ok  ' if n_btn == 3 else '!!  '}] 「扫荡」只点了 {n_btn} 次 (期望 3，第 4 轮不再点)")
    return ok and n_btn == 3, f"stat={stat} 扫荡键点击={n_btn} 全部点击={rp.real_clicks}"


def case_bagfull(rp):
    """⑧ 背包已满 → 清理后重进面板 → 本轮照常完成。"""
    sc = _sc()
    called = {"n": 0}
    real = sw.clear_if_full

    def stub(rect, log=print, dry=False):
        called["n"] += 1
        rp.idx += 1                  # 桩: 清理会换页（真逻辑会把游戏带回首页再导航）
        return True

    sw.clear_if_full = stub
    try:
        r = sw.one_round(sc, 1, "normal")
    finally:
        sw.clear_if_full = real
    ok = called["n"] == 1 and r == "ok"
    print(f"  [{'ok  ' if called['n'] == 1 else '!!  '}] 清理被调用 {called['n']} 次 (期望 1)")
    return ok, f"清理={called['n']} 结果={r}(期望 ok) 点击={rp.real_clicks}"


def case_panel_lost(rp):
    """⑨ 面板被误关 → ensure_context 复查并重进。"""
    ok = sw.ensure_context(_sc(), "normal", 1)     # 起始帧是首页 → 应先重进面板
    clicks_ok = st.check_clicks("重进", rp.real_clicks, [C_STAGE_BTN, MAT1])
    return ok and clicks_ok, f"就位={ok} 点击={rp.real_clicks}"


def case_dry(rp):
    """⑩ dry: 零点击零写盘。"""
    ok = sw.run(_sc(dry=True), kit.Args(dry=True, max=5))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    name = "sweep_stage_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("模式识别/切换", [P_HERO, P_NORMAL], case_mode),
    ("导航: 首页→关卡页→扫荡面板", [HOME, STAGE_PAGE, P_NORMAL], case_nav),
    ("4星页签已选中(零点击)", [P_NORMAL], case_tab4_selected),
    ("4星页签未选中(点中心+20，桩)", [P_NORMAL], case_tab4_unselected),
    ("材料最少优先(默认 #1)", [P_NORMAL], case_material_least),
    ("材料全部(--material=0 零点击)", [P_NORMAL], case_material_all),
    ("小窗口(601x1143)基准坐标换算", [P_NORMAL], case_small_window),
    ("单轮成功(双倍+跳过卡不使用+关弹层)", [P_BTN, P_DOUBLE, AD_JUMPNO, AD_DONE, P_NORMAL],
     case_round_ok),
    ("无翻倍机会 → 换关", [P_BTN, P_NORMAL], case_round_no_double),
    ("连续 3 关无翻倍 → 收工", [P_BTN] * 6 + [P_NORMAL] * 2, case_phase_stop),
    ("背包已满 → 清理后重进(桩)", [BAGFULL, P_BTN, P_DOUBLE, AD_DONE, P_NORMAL], case_bagfull),
    ("面板被误关 → 复查重进", [HOME, P_NORMAL], case_panel_lost),
    ("dry 零点击零写盘", [P_NORMAL], case_dry),
    ("并发锁互斥", [P_NORMAL], case_lock),
]

if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("sweep_stage 离线自检（真帧+合成面板：材料优先/双倍/背包满/重进）", SCENES)
