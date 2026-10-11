#!/usr/bin/env python
"""维护工具: 零消耗实况探针 —— 导航到目标面板, 只读判据 + 取样, **绝不点消耗性按钮**。

为什么要有它:
    每日次数/体力一次实跑就消耗掉, 当天想再核对「脚本此刻到底看到了什么画面 / 判据
    命中没」只能零消耗地去现场看一眼。以前的做法是临时写脚本(shots 里就躺过 4 个
    草稿: _probe_status / _crop_flags / _verify_flags / _zoom_flags), 用完就删、经验
    也带不走。这里收敛成一个: 复用各用例**已经实跑验证过**的导航与只读判据函数。

硬约束(代码级):
    只调用白名单里的「导航 / 只读」函数 —— sweep_stage.open_panel/close_panel、
    boss_hyper.goto_hyper/open_detail/name_roi/already_done/nuke_125_ok 与方向箭头
    盲点坐标。**绝不**调用 one_round / run_phase / fight_one / one_station / 任何
    「扫荡」「超限挑战」按钮 —— 探针全程零消耗, 不点材料、不点挑战。

用法:
    uv run python tools/maint/probe_live.py                       # 默认扫荡面板材料计数
    uv run python tools/maint/probe_live.py --case sweep_stage
    uv run python tools/maint/probe_live.py --case boss_hyper --station 装甲 --switch 5

产出: 实况帧存 shots/probe_<case>*.png, 并在 stdout 打印 OUTPUT=<绝对路径>。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from wb import kit, mcount  # noqa: E402
from wb.bot import find_game_window  # noqa: E402
from wb.cfg import CONF, SHOTS_DIR  # noqa: E402
from wb.kit import nap  # noqa: E402


def _screen() -> kit.Screen | None:
    rect = find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        print("[fail] 未找到游戏窗口（先打开游戏）")
        return None
    print(f"[ok] 游戏窗口 ({rect.x},{rect.y}) {rect.w}x{rect.h}")
    return kit.Screen(rect, th=0.86, prefix="probe_")


def _save(img, name: str) -> Path:
    p = SHOTS_DIR / name
    cv2.imwrite(str(p), img)
    print(f"[留证] {p}")
    print(f"OUTPUT={p.resolve()}")
    return p


# ------------------------------------------------------------------ 扫荡面板

def probe_sweep(sc: kit.Screen) -> int:
    """扫荡面板顶部 4 个材料计数: 只读 → 报「最少的是第几个」。

    ⚠ 只开面板、只读计数, **不点材料图标、不点扫荡** —— 零体力消耗。
    这就是 --material=auto 的判据现场: 计数不按升序, 「第 1 个最少」是错的。
    """
    from tools.cases import sweep_stage as sw

    if not sw.open_panel(sc):
        print("[FAIL] 进不了扫荡面板")
        return 1

    img = sc.grab()
    counts = mcount.read_row(img)
    idx = mcount.argmin_material(img)
    _save(img, "probe_sweep_mcount.png")

    pretty = ["?" if c is None else str(c) for c in counts]
    print(f"[读数] 材料计数 = {pretty}")
    if idx is None:
        print("[警告] 读数不可用 → 正式跑会退化为「全部」(零点击, 安全方向)")
    else:
        print(f"[读数] 真正最少 = 第 {idx} 个（{counts[idx - 1]}）")
        if idx == 1:
            print(f"[对比] 旧假设(第 1 个 = {counts[0]}) 恰好一致")
        else:
            print(f"[对比] ❌ 旧假设点第 1 个 = {counts[0]}，真最少是第 {idx} 个 = {counts[idx - 1]}")
    sw.close_panel(sc)                      # 收尾回首页（导航, 非消耗）
    return 0


# ------------------------------------------------------------------ 超限详情页

def probe_hyper(sc: kit.Screen, station: str | None, switch: int) -> int:
    """某站详情页: 沿右箭头扫掠, 逐个报「已击败 / 超限125%」两个出击前提。

    ⚠ 只点铭牌 + 方向箭头（导航）, **绝不点「超限挑战」** —— 零次数消耗。
    名条指纹用于确认切换真的生效（丢点击会重试, 和正式跑同一判据）。
    """
    from tools.cases import boss_hyper as bh

    key = None
    if station:
        alias = {nm: k for k, (_, nm) in bh.STATIONS.items()}   # 中文别名 → key
        key = station if station in bh.STATIONS else alias.get(station)
        if key is None:
            print(f"[FAIL] 未知站点 {station!r}，可选: " + "、".join(alias))
            return 1
    key = key or bh.DEFAULT_STATIONS[0]
    tpl, name = bh.STATIONS[key]

    if not bh.goto_hyper(sc):
        print("[FAIL] 进不了超限页")
        return 1
    if not bh.open_detail(sc, tpl, name):
        print(f"[FAIL] 进不了「{name}」详情页")
        return 1

    print(f"[采样] 站点「{name}」详情页，双向扫掠 {switch + 1} 个 boss（零消耗）")

    def _switch(forward: bool) -> bool:
        """点一次方向箭头（盲点）, 名条变了才算切成功（与正式跑同一判据）。"""
        x, y = bh.ARROW_RIGHT if forward else bh.ARROW_LEFT
        before = bh.name_roi(sc)
        sc.click_base(x, y, f"切换→{'下一' if forward else '上一'}boss(探针)")
        nap(bh.SWITCH_WAIT)
        if bh.name_changed(sc, before):
            return True
        for _ in range(2):                     # 丢点击很常见, 最多补 2 次
            sc.click_base(x, y, "切换重试(探针)")
            nap(bh.SWITCH_WAIT)
            if bh.name_changed(sc, before):
                return True
        return False

    forward, flipped = True, False
    n = 0
    for i in range(switch + 1):
        cur = bh.name_roi(sc)
        done = bh.already_done(sc)
        ok125 = bh.nuke_125_ok(sc)
        if done:
            verdict = "跳过（今日已击败）"
        elif not ok125:
            verdict = "跳过（抗性非 125%）"
        else:
            verdict = "可出击（正式跑会打）"
        print(f"  #{i + 1} 名条={'可见' if cur is not None else '未见'}"
              f"  已击败={'是' if done else '否'}  超限125%={'是' if ok125 else '否'}"
              f"  → {verdict}")
        n += 1
        if i >= switch:
            break
        if not _switch(forward):
            if flipped:
                print("  [警告] 两个方向都切不动 → 停止采样")
                break
            forward, flipped = not forward, True     # 到头了: 反向扫掠（同正式跑）
            print(f"  [切换] {'右' if not forward else '左'}箭头到头 → 反向扫掠")
            if not _switch(forward):
                print("  [警告] 反向也切不动 → 停止采样")
                break

    _save(sc.grab(), "probe_hyper_detail.png")
    kit.goto_home(sc)                          # 收尾回首页
    print(f"[完成] 采样 {n} 个 boss（零消耗, 未点挑战）")
    return 0


# ------------------------------------------------------------------ CLI

def _arg(flag: str) -> str | None:
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def main() -> int:
    case = _arg("--case") or "sweep_stage"
    sc = _screen()
    if sc is None:
        return 2
    if case == "sweep_stage":
        return probe_sweep(sc)
    if case == "boss_hyper":
        switch = int(_arg("--switch") or 0)
        return probe_hyper(sc, _arg("--station"), max(0, min(switch, 5)))
    print(f"[FAIL] 未知 --case {case!r}（可选 sweep_stage / boss_hyper）")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
