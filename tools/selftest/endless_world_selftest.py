#!/usr/bin/env python
"""离线自检: endless_world（无尽模式·世界竞赛）局内判据与收尾 —— 零消耗，不碰游戏窗口。

为什么这个用例特别需要离线自检:
  「无尽模式」一轮要花 💎20 + 9 件道具，且今天挑战币已达上限（基本无收益），
  实跑一次就是在烧钱。而最容易翻车的恰恰是**局内判据**这些纯逻辑分支：
  得分未达不拖、闪效假阳性不许拖、真达标要复核两次才拖 —— 这些能用真帧穷举。

核心场景（回归护栏，对应 2026-10-08 实跑踩过的假阳性）:
  ① 一瞬判到 ≥400万（闪效）→ **一次都不许拖**，要等超时兜底才收尾；
  ② 真连续两次 ≥400万 → 才拖（且拖拽起点必须是 (406,1180)）。

做法: 实测帧当「每步画面」，点击/拖拽驱动状态机；holds 让某帧在虚拟秒数后自动翻页
      （用来模拟「得分随时间增长」）。wb.bot 的取帧/点击/拖拽、time.sleep、cv2 落盘
      全部换成替身 → 不消耗任何游戏次数，也不真动鼠标。

用法:
    uv run python tools/selftest/endless_world_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import selftest_kit as st  # noqa: E402
from tools.cases import endless_world as ew  # noqa: E402

# 夹具（实测真帧）—— 缺哪个该场景就 SKIP，不计入分母
#   得分帧用 bscore_*（真值写在文件名里，且是 wb/bscore.py 自检的同一批）
#   结算帧用 _ew_*（endless_settle/result 每轮实跑都会被覆盖，故固化副本）
F = {
    "lo": "bscore_3263612.png",       # 局内 得分 3263612（< 400万）
    "hi": "bscore_4092602.png",       # 局内 得分 4092602（≥ 400万）
    "settle": "_ew_settle.png",       # 本次得分页（按钮「继续」）
    "win": "_ew_result_win.png",      # 战绩页 挑战胜利（按钮「返回」）
    "arena": "exp_world.png",         # 世界竞赛页（wc_title 0.981）
}

DRAG = (406, 1180, 406, 225)          # 拖战机到顶部（游戏内坐标）
BM = 45.0                             # 自检把局内上限从 210s 压到 45s：逻辑一致但跑得快

# 局内上限是模块级常量（battle_watch 里当全局读），直接改它就能压缩虚拟时间
# ── 但这会让「超时兜底」与「复核后拖顶」的界限变近，所以断言阈值同步取 BM。
ew.BATTLE_MAX = BM


def case(rp, **kw):
    """绕过真实窗口查找造用例实例（自检不碰窗口）。"""
    return st.bare_case(ew.Case, dry=False, allow_capped=True, **kw)


def case_confirm(rp):
    """① 未达不拖 → 真达标后**复核第二次**才拖。"""
    c = case(rp)
    c.battle_watch()
    n = len(rp.drags)
    t0 = rp.drag_times[0] if rp.drag_times else -1
    good = n == 2 and all(d == DRAG for d in rp.drags) and 20 <= t0 <= BM - 1
    return good, (f"局内先 326万 后 409万: 拖拽 {n} 次(期望2) 首拖 t={t0:.0f}s"
                  f"(期望 20~{BM - 1:.0f}, 即第二次读数复核后才拖) "
                  f"坐标={'一致' if all(d == DRAG for d in rp.drags) else rp.drags}")


def case_transient(rp):
    """② 闪效假阳性回归：只有一瞬 ≥400万 → 绝不许提前拖（必须等到超时兜底）。"""
    c = case(rp)
    c.battle_watch()
    n = len(rp.drags)
    t0 = rp.drag_times[0] if rp.drag_times else -1
    good = n == 2 and t0 >= BM - 5
    return good, (f"一瞬 409万 后回落 326万: 拖拽 {n} 次(期望2) 首拖 t={t0:.0f}s "
                  f"(期望 ≥{BM - 5:.0f} = 只在超时兜底, 不在闪效时拖)")


def case_no_hi(rp):
    """③ 全程未达标 → 只能由超时兜底收尾（拖顶是兜底动作，不是提前送死）。"""
    c = case(rp)
    c.battle_watch()
    n = len(rp.drags)
    t0 = rp.drag_times[0] if rp.drag_times else -1
    good = n == 2 and t0 >= BM - 5
    return good, f"全程 326万: 拖拽 {n} 次 首拖 t={t0:.0f}s(期望超时兜底)"


def case_settle(rp):
    """④ 结算页「继续」→ 战绩页「返回」：坐标与胜负判定。"""
    c = case(rp)
    ok = c.settle(timeout=90.0)
    got = rp.real_clicks
    exp = [(410, 1323), (731, 1475)]           # 实跑实测坐标
    near = len(got) == len(exp) and all(abs(g[0] - e[0]) <= 8 and abs(g[1] - e[1]) <= 8
                                        for g, e in zip(got, exp))
    good = ok and near and c.last_win is True
    return good, (f"结算→战绩: ok={ok} 点击={got} 期望≈{exp} last_win={c.last_win}(期望 True)")


def case_settle_already(rp):
    """⑤ 已回到世界竞赛页 → settle 直接返回，一次都不点。"""
    c = case(rp)
    ok = c.settle(timeout=5.0)
    good = ok and not rp.real_clicks
    return good, f"已在世界竞赛页: ok={ok} 点击={rp.real_clicks}(期望空)"


def case_dry(rp):
    """⑥ dry：只出计划、零点击零拖拽零写盘。"""
    c = st.bare_case(ew.Case, dry=True, allow_capped=True)
    c.battle_watch()
    c.drag_to_top()
    good = not rp.real_clicks and not rp.drags and not rp.shots
    return good, (f"dry: 点击={rp.real_clicks} 拖拽={rp.drags} 写盘={rp.shots} (三者都要空)")


if __name__ == "__main__":
    st.run_one("endless_world 离线自检（局内判据/收尾，不消耗次数）", [
        # 第 4 项 = 本场景专用 holds：{帧号: 停多少虚拟秒后自动翻页}
        # ① 326万 停 11s 后翻到 409万 → 首个真读数不做数，第二次才拖
        ("局内: 未达不拖 → 达标复核两次才拖", [F["lo"], F["hi"], F["hi"], F["hi"], F["hi"]],
         case_confirm, {0: 11.0}),
        # ② 409万 只停 10.5s（够第一次读数）就回落 → 这就是当时的假阳性场景
        ("局内: 闪效假阳性不许拖（超时才拖）", [F["hi"], F["lo"], F["lo"]], case_transient, {0: 10.5}),
        ("局内: 全程未达标 → 超时兜底", [F["lo"]], case_no_hi),
        ("结算页继续 → 战绩页返回", [F["settle"], F["win"]], case_settle),
        ("已回世界竞赛页不重复点", [F["arena"]], case_settle_already),
        ("dry 零副作用", [F["hi"]], case_dry),
    ])
