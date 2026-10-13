#!/usr/bin/env python
"""用例: 体力清空（体力超上限 → 用「4星材料」扫荡花掉，**不看**双倍广告）。

规则（用户口径，2026-10-13）
    体力 > 120 → 扫荡「4星材料」把超出的部分花掉；回到 120 以内即停。
    ⚠ **绝不点「双倍奖励」** —— 那是「看广告换双倍」，本用例明确不要广告。

链路
    首页 --读药丸底色(亮黄=超上限)--> 超? → 闯关模式 --(stage_sweep 快速扫荡)-->
    扫荡面板 → 普通模式 → 「4星材料」页签 → 选材料(默认 auto=计数最少)   ← **只做一次**
    → 【循环】在面板里挑一行「**掉 2 个材料**」的关卡（每行 3 格: 1 经验 + 2/3 材料）
            → 点它那行的「扫荡」→ 弹层上出现「双倍奖励」**不点**
            → 点空白(420,620)快速关掉「扫荡完成」弹层（拿普通奖励）
            → **面板里就地回读药丸底色** → 仍亮黄 → 再来一轮；暗棕 → 收工
            → 4星材料扫不动了（无可扫行）→ 自动降级到「5星材料」继续
    → 收尾: 关面板 → 回首页

⚠ 「只掉 1 个材料」的行不扫：行内材料槽在第 2/3 格——**两格都有图标才算 2 材料**，
   第 3 格是空的 = 只掉 1 个材料 → 跳过。空槽用纹理σ判：真样本（第94关·贴身侍卫）
   空槽 σ=3/μ=38 vs 有图标 σ=57/μ=91，阈值 σ≥45 & μ≥55 余量极大。

判据: wb/stamina.py（药丸区黄像素占比 ≥0.20 = 超上限；实测 0.49 vs 0.05）
⚠ 恰好在 120 时药丸也黄 → 会多扫一轮（≈10 体力过冲），见 wb/stamina.py 说明。
⭐ **不为了读数而关面板**（2026-10-13 按用户反馈提速）：判据只用色相+饱和度，
   面板压暗（~0.26 倍亮度）读出来一模一样 → 一轮只剩「点扫荡 + 关弹层 + 读底色」。
   摆上下文（模式/页签/选材料）**整轮只做一次**，不进热路径。
⚠ 面板被误关 / 「背包已满」盖住面板 → 兜底重进（只在异常时触发，不拖慢正常轮）。

用法
    uv run python tools/cases/clear_stamina.py [--max N] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb import stamina as stam  # noqa: E402
from wb.kit import log  # noqa: E402
from tools.cases import sweep_stage as sw  # noqa: E402
from tools.cases.sweep_stage import TAB_SLOT_TOL, _selected_tab_center  # noqa: E402
from tools.cases.clear_bag import clear_if_full  # noqa: E402   # 背包满自动清理

MAX_ROUNDS = 30          # 过冲保护：一轮 10~15 体力，30 轮够清 ~450
STAR_FIRST = 4           # 用户口径：先扫 4星材料，没了再降级到 5星
MAT = "auto"             # 材料类型：读 4 个计数取**真正最少**（沿用项目口径）

# 页签槽位中心（基准尺度）：3★=165 / 4★=430 / 5★=660（sweep_stage 实测槽位）
TAB_X = {4: 430, 5: 660}
TAB_Y = 325
# 行内 3 个图标槽：第 1 格=经验，第 2/3 格=材料（用户 2026-10-13 口径）
# 相对「扫荡」按钮中心的 x 偏移（基准尺度，实测 frame 833: 按钮 639 / 槽中心 155·270·380）
MAT_SLOT_DX = (-360, -253)
SLOT_SIGMA = 45.0        # 槽内有图标：纹理标准差（实测有图标 47~73 / 空槽与背景 ≤42）
SLOT_MEAN = 55.0         # 兼顾不能太暗（实测有图标 67~123）

PLAN = """[dry] 计划:
  1) 读顶部体力药丸底色 → 亮黄 = 体力超上限(>120)
  2) 不超 → 直接结束（什么都不点）
  3) 超 → 闯关模式 → 快速扫荡面板 → 普通模式 → 4星材料页签 → 选材料(auto=计数最少)
  4) 【循环】挑一行「掉 2 个材料」的关卡（第 1 格经验 + 第 2/3 格材料，两个格子都要有图标）
     → 点它那行的「扫荡」→ 「双倍奖励」**不点**（不看广告）
     → 点空白(420,620)快速关「扫荡完成」弹层 → 面板内就地回读药丸底色
     → 仍亮黄 → 再来一轮；变暗棕(≤120) → 收工
  5) 4星材料没有可扫的行 → 自动降级到 5星材料继续
  上限 30 轮；无可用「扫荡」按钮(次数耗尽/体力不足) → 收工
  收尾: 关面板 → 回首页"""


def select_tab(sc: kit.Screen, stars: int) -> bool:
    """切到指定星级的材料页签（复用 sweep_stage 的槽位 + 几何判据）。"""
    slot = _bot.client_to_ref(TAB_X[stars], TAB_Y, 812, 1518)
    sx, sy = _bot.ref_to_client(*slot, sc.w, sc.h)
    geo = _selected_tab_center(sc)
    if geo is not None and abs(geo[0] - sx) <= TAB_SLOT_TOL:
        log(f"{stars}星材料 已是选中态(几何)")
        return True
    sc.click_at(sx, sy, f"{stars}星材料")
    kit.nap(1.8)
    geo = _selected_tab_center(sc)
    ok = geo is not None and abs(geo[0] - sx) <= TAB_SLOT_TOL
    log(f"切 {stars}星材料页签 → {'成功' if ok else '未确认(几何)'}")
    return ok


def mats_in_row(img, bx: float, by: float) -> int:
    """这行的 2 个材料槽里几个真摆了图标（空槽 = 不掉这个材料）。

    槽位是**相对扫荡按钮中心**的固定偏移；用纹理标准差(σ)判「有没有图标」——
    图标是彩色贴图(σ 47~73)，空槽/面板底是平的(σ ≤42)。
    """
    H, W = img.shape[:2]
    s = int(84 * W / 812)                 # 取样框尺寸（基准尺度换算）
    n = 0
    for dx in MAT_SLOT_DX:
        x = int(bx + dx * W / 812)
        y = int(by)
        box = img[max(0, y - s // 2):y + s // 2, max(0, x - s // 2):x + s // 2]
        if box.size == 0:
            continue
        g = cv2.cvtColor(box, cv2.COLOR_BGR2GRAY)
        if float(g.std()) >= SLOT_SIGMA and float(g.mean()) >= SLOT_MEAN:
            n += 1
    return n


def pick_row(sc: kit.Screen):
    """挑一行来扫：只要掉 2 个材料的行（返回 (按钮命中, 说明)）。"""
    hits = sc.find_all("sweep_btn", sw.SWEEP_TH, max_hits=6)
    if not hits:
        log("没有可用的「扫荡」按钮（次数耗尽 / 体力不足）")
        return None, "no_sweep"
    img = sc.grab()                       # 一次取帧，逐行切槽位（省截图）
    for h in sorted(hits, key=lambda t: t[1]):
        n = mats_in_row(img, h[0], h[1])
        if n >= 2:
            return h, "ok"
        log(f"跳过一行: 只有 {n} 个材料槽有图标（y={int(h[1])}）")
    return None, "one_material_only"


def over_cap_stable(sc: kit.Screen, tries: int = 3, gap: float = 0.8) -> bool | None:
    """面板里回读体力是否超上限，并要求**连续两次一致**才采信。

    ⚠ 为什么要稳定化（2026-10-13 实跑发现过冲）: 一次实跑从 175 扫到 **70**
      （理论应停在 120 附近），怀疑「关掉扫荡完成弹层”的瞬间顶栏数字还没刷新 →
      读到的是上一轮的旧值(仍超上限) → 多扫了好几轮。
      这里先读一次、隔 gap 再读一次，不一致就继续确认（最多 tries 次）；
      **宁可多等一会儿，也不要因为读旧值而多扫**。
    """
    prev = stam.over_cap(sc)
    if prev is None:
        return None
    for _ in range(max(1, tries) - 1):
        kit.nap(gap)
        cur = stam.over_cap(sc)
        if cur is None:
            return None
        if cur == prev:
            return cur
        log(f"体力读数在跳变（{prev} → {cur}，疑似结算未刷新）→ 再确认")
        prev = cur
    return prev


def setup(sc: kit.Screen, stars: int) -> bool:
    """进面板并把上下文摆好（普通模式 + 指定星级材料页签 + 选材料）——**整轮只做一次**。"""
    if not sw.open_panel(sc):
        return False
    if not sw.ensure_mode(sc, "normal"):
        log("切普通模式失败")
        return False
    if not select_tab(sc, stars):
        sc.shot("clear_stamina_tab_fail")
    sw.select_material(sc, MAT)
    select_tab(sc, stars)       # 选材料可能误碰页签 → 复查一次
    return True


def one_round(sc: kit.Screen, idx: int, stars: int) -> tuple[str, int]:
    """一轮 = 挑「掉 2 个材料」的行 → 点扫荡 → 快速关弹层（**不点双倍**）。

    面板原地不动（读数压暗免疫）。返回 (状态, 星级)：状态 ok / no_sweep /
    one_material_only / no_panel。
    """
    log(f"—— 第 {idx} 轮（{stars}星材料）——")
    if sc.find("sweep_close", 0.93) is None:        # 面板被误关 → 交回 run 重进
        return "no_panel", stars
    if clear_if_full(sc.rect, log, dry=sc.dry):     # 「背包已满」会盖住面板
        log("背包已满 → 已自动清理，重进面板")
        return "no_panel", stars
    row, why = pick_row(sc)
    if row is None and stars < 5:                   # 4星扫不动了 → 降级 5星
        log("4星材料没有可扫的行了 → 换 5星材料")
        if select_tab(sc, 5):
            sw.select_material(sc, MAT)
            select_tab(sc, 5)
            stars = 5
            row, why = pick_row(sc)
    if row is None:
        return why, stars
    sc.click(row, f"扫荡（{stars}星材料·掉 2 材料的行）")

    # 结算弹层:「双倍奖励」可能在场，但**绝不点它**（点了就是看广告）
    done = sc.wait(sw.OVERLAY_SIG, 10.0, th=sw.DONE_TH)
    if done is None:
        log("没等到「扫荡完成」弹层（可能已自动收）")
    elif sc.find("sweep_double", sw.DOUBLE_TH) is not None:
        log("弹层上有「双倍奖励」→ **不点**（本用例不看广告）")
        if idx == 1:
            sc.shot("overlay_double")   # 留证: 弹层上确实有「双倍奖励」而我们没点
    sw.close_overlay(sc)                # 点空白快速关弹层（通常 1 次就收）
    return "ok", stars


def run(sc: kit.Screen, args: kit.Args) -> bool:
    rounds = min(max(1, args.n_times(MAX_ROUNDS)), MAX_ROUNDS)

    if sc.dry:
        st = stam.state(sc)
        log(f"[dry] 当前体力药丸={st}（over=亮黄超上限 / ok=暗棕上限内 / unknown=认不出）")
        if st == "over":
            log(f"[dry] 会进扫荡面板扫 4星材料 ×最多 {rounds} 轮，**不看双倍广告**")
        elif st == "ok":
            log("[dry] 体力在上限内 → 实跑时什么都不点")
        else:
            log("[dry] 认不出药丸（不在首页?）→ 实跑时会先回首页再判")
        return True

    if sc.find("sweep_close", 0.93) is not None:   # 上次没关干净(探针/异常退出) → 先关面板
        log("检测到扫荡面板开着 → 先关掉再回首页")
        sw.close_panel(sc)
        kit.nap(1.2)
    kit.goto_home(sc)
    over = stam.over_cap(sc)
    log(f"起始: 体力超上限 = {over}")
    if over is None:
        log("读不到体力药丸（入口未命中/取帧失败），退出")
        return False
    if not over:
        sc.shot("pill_ok")                  # 夹具: 上限内（暗棕）首页真帧
        log("体力在上限内(≤120)，无需清理 → 什么都不点")
        return True
    sc.shot("pill_over")                    # 夹具: 超上限（亮黄）首页真帧

    stars = STAR_FIRST
    if not setup(sc, stars):
        log("无法进入/摆好快速扫荡面板，退出")
        return False
    sc.shot("panel")                        # 夹具: 面板态（读数须与首页一致 = 压暗免疫）

    ok, reason = 0, "max_rounds"
    for i in range(1, rounds + 1):
        r, stars = one_round(sc, i, stars)
        if r == "no_panel":                 # 面板被误关/背包满 → 重进后重试本轮
            log("面板不在场 → 重进")
            if not setup(sc, stars):
                reason = "no_panel"
                break
            r, stars = one_round(sc, i, stars)
        if r != "ok":
            reason = r
            break
        ok += 1
        over = over_cap_stable(sc)          # ⭐ 面板里就地回读（压暗免疫 + 稳定确认）
        log(f"第 {i} 轮后回读: 超上限={over}")   # 定位过冲用（实跑凭这行看清何时该停）
        if over is None:
            reason = "unreadable"
            break
        if not over:
            reason = "reached_cap"
            break
        kit.nap(0.6)

    log(f"完成: 扫荡 {ok} 轮，停止原因={reason}")
    if reason == "reached_cap":
        sc.shot("pill_ok")                  # 夹具: 清完后回到上限内
    sc.shot("clear_stamina_final")
    sw.close_panel(sc)                      # 面板不关掉，goto_home 够不到返回箭头
    if not args.no_back:
        kit.goto_home(sc)

    if reason in ("reached_cap", "max_rounds") and ok > 0:
        log(f"已把体力清回上限内（共扫 {ok} 轮）")
        return True
    if ok == 0:
        log(f"一轮都没扫成（{reason}）→ 体力仍在超上限")
        return False
    log(f"未清干净就收工（{reason}），还剩超上限体力")
    return False


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "clear_stamina", "体力清空（超上限 → 4星材料扫荡，不看双倍广告）", run,
        plan=PLAN, prefix="cs_", lock_ttl=1800, th=sw.TH,
        default_max=MAX_ROUNDS,
    ))
