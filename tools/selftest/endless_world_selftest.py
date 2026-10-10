#!/usr/bin/env python
"""离线自检: endless_world（无尽模式·世界竞赛）局内判据与收尾 —— 零消耗，不碰游戏窗口。

为什么这个用例特别需要离线自检:
  「无尽模式」一轮要花 💎20 + 9 件道具，且挑战币常已达上限（基本无收益），
  实跑一次就是在烧钱。而最容易翻车的恰恰是**局内判据**这些纯逻辑分支：
  得分未达不拖、闪效假阳性不许拖、真达标要复核两次才拖 —— 这些能用真帧穷举。

**时间是怎么变快的（迁移后）**: 用例里的时间一律走 kit.now() / kit.nap()，而 selftest_kit
  把 wb.kit.time 换成 _ShimTime（sleep 不真睡、只把时长计入虚拟时钟）。
  以前用例自己 import time → 自检拦不住 → 局内上限 45s 就是**真等 45 秒**；
  现在同样的虚拟秒在毫秒级跑完，而判据逻辑一字未改。

**断言为什么是「关系式」而不是绝对秒数**: 虚拟时钟 = 真实时间 + 累计 sleep，而每轮匹配
  本身也要花真实时间（实测每轮约 +0.14s）→ 读分时刻会随机器快慢浮动（本机 el≈12.1 / 23.5）。
  所以这里断言的是「拖拽相对**首次达标读数**又等了一轮」这类**关系**，不写死秒数；
  被压/被放的只是秒数尺度，不是规则（规则：连续两次判真才允许拖）。
  ⚠ 上一版把 holds 设成 11s，结果**首个读数就已落到 hi 帧** → 场景①根本没在测「未达不拖」
  （负向对照恒真都照样 PASS）→ 这正是「假绿断言」。改 holds=18s 后才真正覆盖。

覆盖:
  ① 未达不拖 → 达标后**复核第二次**才拖（首达标读数处绝不拖）
  ② 闪效假阳性：首个读数达标后回落 → 全程不许提前拖，只在超时兜底
  ③ 全程未达标 → 同样只在超时兜底
  ④ 结算页「继续」→ 战绩页「返回」坐标与胜负判定；⑤ 已回世界竞赛页零点击
  ⑥ dry 零副作用（含 run() 顶层入口）; ⑦ 并发锁互斥

负向对照（证明断言不为空，外部脚本跑，不在本文件里）:
  强制「≥400万」恒真 → ① 在首达标读数处就拖 → 必须 FAIL；
  强制恒假 → ① 只能靠超时兜底 → 必须 FAIL。battle() 的 force 参数就是给这个用的。

用法:
    uv run python tools/selftest/endless_world_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bscore, bot  # noqa: E402
from wb import kit, selftest_kit as st  # noqa: E402
from tools.cases import endless_world as ew  # noqa: E402

# 夹具（实测真帧）—— 缺哪个该场景就 SKIP，不计入分母
#   得分帧用 bscore_*（真值写在文件名里，且是 wb/bscore.py 自检的同一批）
#   结算帧用 _ew_*（endless_settle/result 每轮实跑都会被覆盖，故固化副本；
#   注意用例留证前缀是 endless_ → 写 _endless_*.png，不会覆盖这些夹具）
F = {
    "lo": "bscore_3263612.png",       # 局内 得分 3263612（< 400万）
    "hi": "bscore_4092602.png",       # 局内 得分 4092602（≥ 400万）
    "settle": "_ew_settle.png",       # 本次得分页（按钮「继续」）
    "reward": "_ew_reward.png",       # 闪击「恭喜获得」奖励页（按钮「领取」）——2026-10-09 实跑真帧
    "win": "_ew_result_win.png",      # 战绩页 挑战胜利（按钮「返回」）
    "arena": "exp_world.png",         # 世界竞赛页（wc_title 0.981）
}

# 拖拽起止点: 用例给的是**基准(ref)坐标**(ew.PLANE_FROM/PLANE_TO), 期望值必须按 st.RECT
# 现算 —— 硬编码客户区坐标会在夹具窗口尺寸变动后立刻过期(812x1518 → 814x1507 时起点
# y 差 9px, 直接假失败; 换算本身是对的, 只是期望值写死了)。比较用 ±6px 容差。
DRAG = tuple(int(v) for v in (
    *bot.ref_rect_to_client(*ew.PLANE_FROM, 1, 1, st.RECT[2], st.RECT[3])[:2],
    *bot.ref_rect_to_client(*ew.PLANE_TO, 1, 1, st.RECT[2], st.RECT[3])[:2]))
BM = 45.0                             # 自检把局内上限从 210s 压到 45s：逻辑一致但跑得快
HOLD_LO = 18.0                        # 场景①：lo 停这么久 → 首个读数落在 lo、首个达标读数在下一轮
HOLD_HI = 15.0                        # 场景②：hi 停这么久 → **首个读数就是达标**（当年被骗那次）

# 局内上限是模块级常量（battle_watch 里当全局读），直接改它就能压缩虚拟时间
ew.BATTLE_MAX = BM
FORCE: bool | None = None            # 负向对照钩子：非 None 时强制「≥400万」判定值
                                     # （由外部脚本设置 → 复用下面**同一份断言代码**，不复制逻辑）


def _sc(dry: bool = False) -> kit.Screen:
    """自检用的 Screen（st.RECT 是裸 tuple，不碰真实窗口）。"""
    return kit.Screen(st.RECT, th=ew.TH, dry=dry, prefix="endless_")


def battle(sc, *, force: bool | None = None) -> tuple[str, list[tuple[float, bool]], list[float]]:
    """跑一次 battle_watch，顺便记录「每次读分的时刻+判定」与「每次拖拽的时刻」。

    时刻一律换算成**相对本次 battle 起点的秒数**（而不是 kit.now() 的 epoch 原值）：
    局内上限 BATTLE_MAX 就是个相对秒数，两者同尺度才能比 —— 上一版直接拿 epoch 值
    去比 `<= BM`，恒为假/恒为真，等于没断言（又一个假绿）。
    force: None = 用真帧读数；True/False = 强制判定值（负向对照用）。
    """
    reads: list[tuple[float, bool]] = []
    drags: list[float] = []
    orig_ge, orig_drag = bscore.score_ge_4m, bot.drag_xy
    base = kit.now()                                  # battle_watch 内部的 t0 ≈ 此刻
    force = FORCE if force is None else force

    def ge_spy(frame, *a, **k):
        v = bool(force) if force is not None else orig_ge(frame, *a, **k)
        reads.append((kit.now() - base, v))
        return v

    def drag_spy(x1, y1, x2, y2, *a, **k):
        drags.append(kit.now() - base)
        return orig_drag(x1, y1, x2, y2, *a, **k)

    bscore.score_ge_4m, bot.drag_xy = ge_spy, drag_spy
    try:
        why = ew.battle_watch(sc)
    finally:
        bscore.score_ge_4m, bot.drag_xy = orig_ge, orig_drag
    return why, reads, drags


def _first_true(reads) -> float | None:
    return next((t for t, v in reads if v), None)


def case_first_miss(rp):
    """① 未达不拖 → 达标后**复核第二次**才拖。"""
    why, reads, drags = battle(_sc())
    t0 = min(drags) if drags else -1.0
    first = _first_true(reads)
    miss = any(not v for _, v in reads)              # 真的过了「未达」那一段
    waited = first is not None and t0 >= first + 0.6 * ew.SCORE_POLL   # 首达标后又等一轮=复核
    by_score = t0 <= BM - 0.5                        # 不是靠超时兜底拖的（否则判据没起作用）
    coords_ok = all(all(abs(a - b) <= 6 for a, b in zip(d, DRAG)) for d in rp.drags)
    good = (why == "finish" and len(rp.drags) == 2 and coords_ok
            and miss and waited and by_score)
    return good, (f"局内: 结束={why} 拖拽={len(rp.drags)}次(期望2) "
                  f"坐标={'一致' if coords_ok else rp.drags} 读过未达={miss} "
                  f"首达标读数 t≈{first:.0f}s 拖拽 t≈{t0:.0f}s(要求 ≥首达标+"
                  f"{0.6 * ew.SCORE_POLL:.0f}s 且 ≤{BM - 0.5:.0f}s)")


def case_transient(rp):
    """② 闪效假阳性回归：首个读数就达标、之后回落 → 绝不提前拖，只等超时兜底拖。"""
    why, reads, drags = battle(_sc())
    t0 = min(drags) if drags else -1.0
    hit_first = bool(reads) and reads[0][1]
    fell_back = any(not v for _, v in reads)
    good = (why == "finish" and len(rp.drags) == 2 and hit_first and fell_back
            and t0 >= BM - 1)
    return good, (f"一瞬达标后回落: 结束={why} 拖拽={len(rp.drags)}次 首读数达标={hit_first} "
                  f"回落={fell_back} 首拖 t≈{t0:.0f}s(要求 ≥{BM - 1:.0f}s = 只走超时兜底)")


def case_never(rp):
    """③ 全程未达标 → 只能由超时兜底收尾（拖顶是兜底动作，不是提前送死）。"""
    why, reads, drags = battle(_sc())
    t0 = min(drags) if drags else -1.0
    good = (why == "finish" and len(rp.drags) == 2
            and not any(v for _, v in reads) and t0 >= BM - 1)
    return good, f"全程未达: 结束={why} 拖拽={len(rp.drags)}次 首拖 t≈{t0:.0f}s(要求超时兜底)"


def case_settle(rp):
    """④ 结算页「继续」→ 战绩页「返回」：坐标与胜负判定。"""
    ok, win = ew.settle(_sc(), timeout=90.0)
    got = rp.real_clicks
    exp = [(410, 1323), (731, 1475)]           # 实跑实测坐标
    near = len(got) == len(exp) and all(abs(g[0] - e[0]) <= 8 and abs(g[1] - e[1]) <= 8
                                        for g, e in zip(got, exp))
    good = ok and near and win is True
    return good, f"结算→战绩: ok={ok} 点击={got} 期望≈{exp} 胜负={win}(期望 True)"


def case_settle_reward(rp):
    """⑧ 闪击奖励页「领取」→ 战绩页「返回」：奖励页**不许**被当成「本次得分页」。

    2026-10-09 实跑就在这卡住：奖励页上 wc_settle_go(继续) 也会命中 0.951、claim_btn 0.979，
    旧代码先判 wc_settle_go → 走错分支（真实点击坐标也对不上）。本场景锁死修正后的分支与坐标。
    """
    ok, win = ew.settle(_sc(), timeout=90.0)
    got = rp.real_clicks
    exp = [(415, 1286), (731, 1475)]           # 领取键 / 返回键（真帧实测坐标）
    near = len(got) == len(exp) and all(abs(g[0] - e[0]) <= 8 and abs(g[1] - e[1]) <= 8
                                        for g, e in zip(got, exp))
    good = ok and near and win is True
    return good, f"奖励页→战绩: ok={ok} 点击={got} 期望≈{exp} 胜负={win}(期望 True)"


def case_settle_already(rp):
    """⑤ 已回到世界竞赛页 → settle 直接返回，一次都不点。"""
    ok, win = ew.settle(_sc(), timeout=5.0)
    good = ok and win is None and not rp.real_clicks
    return good, f"已在世界竞赛页: ok={ok} 胜负={win}(期望 None) 点击={rp.real_clicks}(期望空)"


def case_dry(rp):
    """⑥ dry：只出计划、零点击零拖拽零写盘（局内轮询也不再空转）。"""
    sc = _sc(dry=True)
    why = ew.battle_watch(sc)
    ew.drag_to_top(sc)
    ok = ew.run(sc, kit.Args(dry=True))          # 顶层 dry 入口也要零副作用
    good = (why == "dry" and ok and not rp.real_clicks and not rp.drags and not rp.shots)
    return good, (f"dry: 局内结束={why} run={ok} 点击={rp.real_clicks} 拖拽={rp.drags} "
                  f"写盘={rp.shots} (后三者都要空)")


def case_lock(rp):
    """⑦ 并发锁互斥（一轮要花 💎20，重复实例必须挡住）。"""
    name = "endless_world_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


# ------------------------------------------------- 买道具：≥3 不买（真帧徽标读数）
class _PrepStub:
    """只实现 buy_items 用到的那几个接口；grab() 回真帧 → 徽标读数走真代码。"""

    def __init__(self, frame, rows):
        self.frame, self.rows = frame, rows
        self.clicks: list[tuple[int, int, str]] = []
        self.drags: list[tuple] = []
        self.h, self.w = frame.shape[:2]
        self.rect = st.RECT

    def find(self, name, th=None):
        return self.rows.get(name)

    def grab(self):
        return self.frame

    def click_at(self, x, y, what):
        self.clicks.append((x, y, what))

    def drag_base(self, *a, **k):
        self.drags.append(a)


# ⚠ 夹具必须放在 `_endlessfx_` 命名空间: 用例的每轮留证就是 `_endless_r<N>_prep.png`
#   (2026-10-10 踩过: 夹具叫 _endless_r1_prep.png, 真跑一轮把它覆盖成新帧 → 徽标读不出 → 假 FAIL)
PREP = "_endlessfx_prep_ok.png"                # 战前准备真帧：炽焰冲击 9 / 烈火 13 / 灰烬 10 (原 _endless_r3_prep)
PREP_ROWS = {"prep_it_flame": (702, 430), "prep_it_fire": (702, 584), "prep_row_ash": (702, 893)}
PREP_UNK = "_endlessfx_prep_unk.png"           # 真帧(2026-10-10 实战)：第1道具徽标读不出 → 保守不买
PREP_UNK_ROWS = {"prep_it_flame": (702, 525), "prep_it_fire": (702, 679), "prep_row_ash": (702, 987)}
_FRAME: dict[str, object] = {}


def _migrate_fixtures() -> None:
    """旧名 → fx 名一次性迁移（fx 已存在则不动；旧名会被真跑覆盖, 不可依赖）。"""
    import shutil
    pairs = [("_endless_r3_prep.png", PREP), ("_endless_r1_prep.png", PREP_UNK)]
    for src, dst in pairs:
        if not (st.SHOTS_DIR / dst).is_file() and (st.SHOTS_DIR / src).is_file():
            shutil.copy(str(st.SHOTS_DIR / src), str(st.SHOTS_DIR / dst))
            print(f"[迁移] {src} → {dst}（夹具入 fx 命名空间, 防真跑覆盖）")


def _prep_frame(name: str = PREP):
    if name not in _FRAME:
        import cv2
        _FRAME[name] = cv2.imread(str(st.SHOTS_DIR / name))
    return _FRAME[name]


def _no_buy_case(frame_name: str, rows: dict[str, tuple[int, int]]):
    """真帧徽标 ≥3 → 一件不买（徽标读数走 wb/icount.py 真代码，不桩）。"""
    f = _prep_frame(frame_name)
    stub = _PrepStub(f, rows)
    ew.buy_items(stub)
    vals = [ew.icount.held(f, y)[0] for _, y in rows.values()]
    good = not stub.clicks and all(v is not None and v >= 3 for v in vals)
    return good, f"{frame_name[8:12]} 持有{vals} → 点击 {stub.clicks}（期望空=不买）"


def case_buy_enough(rp):
    """⑨ 真帧徽标 ≥3 → 三个道具一件都不买（本次需求核心：别白花 💎/💰）。"""
    return _no_buy_case(PREP, PREP_ROWS)


def case_buy_unk(rp):
    """⑪ 真实不可读徽标(第1道具 None) → **保守不买**、另两件 ≥3 也不买 → 零点击。"""
    f = _prep_frame(PREP_UNK)
    stub = _PrepStub(f, PREP_UNK_ROWS)
    ew.buy_items(stub)
    vals = [ew.icount.held(f, y)[0] for _, y in PREP_UNK_ROWS.values()]
    good = not stub.clicks
    return good, f"持有{vals}(第1项读不出) → 点击 {stub.clicks}（期望空: 认不出=保守不买）"


def case_buy_short(rp):
    """⑩ 不足才买：持有 1 → 各补 2 次；徽标认不出 → 保守一次不点；无徽标 → 按 0 件各买 3 次。"""
    orig = ew.icount.held
    lines, bad = [], 0
    plan = [((1, 0.9, True), 2, "持有 1 件"), ((None, 0.5, True), 0, "认不出"), ((None, 0.0, False), 3, "无徽标")]
    try:
        for ret, each, tag in plan:
            ew.icount.held = lambda *a, **k: ret
            stub = _PrepStub(_prep_frame(), PREP_ROWS)
            ew.buy_items(stub)
            want_n = 3 * each
            okk = len(stub.clicks) == want_n
            xs = {c[0] for c in stub.clicks}
            if okk and stub.clicks:
                okk = len(xs) == 1                # 同一价格键 x（只换算 x，y 取帧内检测）
            bad += 0 if okk else 1
            lines.append(f"{tag}→{len(stub.clicks)}次(期望{want_n}){'✓' if okk else '✗'}")
    finally:
        ew.icount.held = orig
    return bad == 0, " ".join(lines)


SCENES = [
    # 第 4 项 = 本场景专用 holds：{帧号: 停多少虚拟秒后自动翻页}
    ("局内: 未达不拖 → 达标复核两次才拖",
     [F["lo"], F["hi"], F["hi"], F["hi"], F["hi"]], case_first_miss, {0: HOLD_LO}),
    ("局内: 闪效假阳性不许拖（只走超时兜底）",
     [F["hi"], F["lo"], F["lo"]], case_transient, {0: HOLD_HI}),
    ("局内: 全程未达标 → 超时兜底拖顶", [F["lo"]], case_never),
    ("结算页继续 → 战绩页返回", [F["settle"], F["win"]], case_settle),
    ("奖励页领取 → 战绩页返回", [F["reward"], F["win"]], case_settle_reward),
    ("已回世界竞赛页不重复点", [F["arena"]], case_settle_already),
    ("dry 零副作用", [F["hi"]], case_dry),
    ("并发锁互斥", [F["arena"]], case_lock),
    ("买道具: 持有≥3 不买（真帧徽标）", [PREP], case_buy_enough),
    ("买道具: 徽标读不出 → 保守不买（2026-10-10 实战帧）", [PREP_UNK], case_buy_unk),
    ("买道具: 不足才买/认不出不买", [PREP], case_buy_short),
]


if __name__ == "__main__":
    _migrate_fixtures()
    st.run_one("endless_world 离线自检（局内判据/收尾，不消耗次数；虚拟时钟驱动）", SCENES)
