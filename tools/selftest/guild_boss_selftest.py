#!/usr/bin/env python
"""离线自检: guild_boss（战队 BOSS 征讨）—— 零消耗，不碰游戏窗口。

夹具: 真帧全部来自今天实跑(814x1507 客户区，与自检 RECT 同尺寸 → 黄金坐标=帧坐标)。
    首页 `_home_now.png` / 战队页 `_expl_expl_guildpage.png`
    / 征讨页·未达 `_expl_expl_bossguild.png`(开战前今日伤害 0) / 征讨页·可领 `_expl_expl_after_ok.png`
    / 征讨页·已领 `_expl_expl_claim2.png` / 恭喜获得弹层 `_expl_expl_claim1.png`
    / 结算页 `_expl_expl_w6.png` / 局内 `_expl_expl_inbattle.png`
    —— 三态都是**真帧**(不必合成): 实测 未达 红点0/绿勾0、可领 红点65、已领 绿勾486。
  唯一合成: `_ts_gbb_unknown.png`(纯深色 = 未知页)。

覆盖:
    ① 判层专场: 8 张逐帧判对 —— 含**局内帧必须判 UNKNOWN**(不然 enter_page 会在局内瞎点)、
       弹层不冒充征讨页(全屏暗幕把 gb_go 压到 0.407)
    ② 50M 槽三态: 未达=红点0/绿勾0=pending / 可领(红点)=claim / 已领(绿勾)=claimed
    ③ 前提闸门: 「奖励等级 MAX」在征讨页命中；**结算页必须被 0.90 阈值挡住**
       (结算页有「MAX 100%」进度条，gb_max 实测 0.79 假命中 —— 本用例最容易翻的车)
    ④ 开局已可领 → 直接领(0 次出击，不浪费今天的次数) + 全链路点击比对
    ⑤ 今日已领(绿勾) → 0 次出击直接收工
    ⑥ 未达 → 出击 → 达标就领(2 次就收，不打第 3 次) / 未达 ×3 → 停手 + 留证
    ⑦ 真 sortie: 点出击 → 「离开征讨页」闸门 → 局内跑到超时；卡在征讨页 → 停手留证
    ⑧ 结算页点「确定」→ 回征讨页
    ⑨ 未知页零点击 / dry 零点击零写盘 / 并发锁

用法:
    uv run python tools/selftest/guild_boss_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from tools.cases import guild_boss as gb  # noqa: E402

HM = "_home_now.png"                    # 真帧: 首页(814x1507, 与自检 RECT 同尺寸)
GD = "_expl_expl_guildpage.png"         # 真帧: 战队页
P1 = "_expl_expl_after_ok.png"          # 真帧: 征讨页(50M 可领)
P2 = "_expl_expl_claim2.png"            # 真帧: 征讨页(50M 已领)
POP = "_expl_expl_claim1.png"           # 真帧: 恭喜获得弹层
DN = "_expl_expl_w6.png"                # 真帧: 结算页「挑战完成」
BAT = "_expl_expl_inbattle.png"         # 真帧: 局内
PEND = "_expl_expl_bossguild.png"       # 真帧: 征讨页·开战前(今日伤害 0)= 未达 50M
UNK = "_ts_gbb_unknown.png"             # 合成: 纯深色未知页
LAYERS = [HM, GD, P1, P2, POP, DN, BAT, UNK]

# 黄金点击坐标（帧坐标 = 客户区坐标，容差 ±6）:
#   C_ENTRY 实测 _home_now.png 上 gd_entry 命中中心；C_GB_ENTRY/C_GO/C_OK 是模板裁框中心；
#   C_D50  = 基准(725,1195) 经 ref_to_client(814,1507) → (707,1184)，即实帧上量的钻石 icon 中心；
#   C_CLAIM = claim_btn 在真弹层帧上的命中中心。
C_ENTRY = (699, 1051)
C_GB_ENTRY = (509, 601)
C_GO = (420, 1379)
C_D50 = (707, 1184)
C_OK = (422, 1397)
C_CLAIM = (417, 1280)
C_SKILL = (721, 1288)   # wb.battle 的技能**兜底坐标**(本模式技能键换皮 → 模板不中即走兜底)


def _sc(dry: bool = False) -> kit.Screen:
    # RECT 用夹具帧的真实客户区尺寸 → 帧坐标==客户区坐标，黄金坐标可直接比对
    return kit.Screen((0, 0, 814, 1507), th=gb.TH, dry=dry, prefix="gbb_")


def _stub_sortie(calls: list, rp):
    """出击桩: 每次调用推进一格画面(模拟「打完一次回征讨页，伤害变了」)。

    只测 run() 的循环决策(3 次上限/未达继续/达标就领)，真局内由 boss_mode 自检覆盖。
    返回真身，用例 finally 里恢复。
    """
    real = gb.sortie

    def fake(sc):
        calls.append(rp.idx)
        rp.idx += 1
        return True

    gb.sortie = fake
    return real


def case_layers(rp):
    """① 判层专场: 8 张真帧/合成帧逐帧判对。"""
    sc = _sc()
    want = [gb.HOME, gb.GUILD, gb.PAGE, gb.PAGE, gb.POPUP, gb.DONE, gb.UNKNOWN, gb.UNKNOWN]
    bad = []
    for i, (f, exp) in enumerate(zip(LAYERS, want)):
        rp.idx = i
        got = gb.page(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] {f:26s} -> {got:8s} (期望 {exp})")
        if got != exp:
            bad.append(f"{f}:{got}!={exp}")
    return not bad, f"判层失败项={bad or '无'}"


def case_states(rp):
    """② 50M 槽三态: 红点=可领 / 绿勾=已领 / 都没有=未达。"""
    sc = _sc()
    bad = []
    for i, (f, exp) in enumerate(((P1, "claim"), (P2, "claimed"), (PEND, "pending"))):
        rp.idx = i
        got = gb.reward_state(sc)
        print(f"  [{'ok  ' if got == exp else '!!  '}] {f:26s} -> {got:8s} (期望 {exp})")
        if got != exp:
            bad.append(f"{f}:{got}")
    return not bad, f"三态失败项={bad or '无'}"


def case_gate(rp):
    """③ 前提闸门: 征讨页命中「奖励等级 MAX」；结算页必须被 0.90 挡住。"""
    sc = _sc()
    rp.idx = 0
    on_page = gb._find(sc, "gb_max", gb.TH_MAX)
    rp.idx = 1
    on_done = gb._find(sc, "gb_max", gb.TH_MAX)
    print(f"  [{'ok  ' if on_page else '!!  '}] 征讨页 gb_max@{gb.TH_MAX} = {on_page}")
    print(f"  [{'ok  ' if on_done is None else '!!  '}] 结算页 gb_max@{gb.TH_MAX} = {on_done}"
          f" (该页有 MAX 100% 进度条，必须挡住)")
    return bool(on_page) and on_done is None, f"征讨页={on_page} 结算页={on_done}"


def case_claim_now(rp):
    """④ 开局 50M 已可领 → 直接领，一次出击都不打。"""
    ok = gb.run(_sc(), kit.Args())
    expect = [C_ENTRY, C_GB_ENTRY, C_D50, C_CLAIM]
    clicks_ok = st.check_clicks("开局已可领→直接领", rp.real_clicks, expect)
    n = len(rp.real_clicks)
    print(f"[{'ok  ' if n == 4 else '!!  '}] 点击 {n} 次 (期望 4 = 进场 2 + 领奖 2，**没有出击**)")
    return ok and clicks_ok and n == 4, f"run={ok} 点击={rp.real_clicks}"


def case_already(rp):
    """⑤ 今日已领(绿勾) → 进场即收工，0 次出击。"""
    ok = gb.run(_sc(), kit.Args())
    clicks_ok = st.check_clicks("今日已领→收工", rp.real_clicks, [C_ENTRY, C_GB_ENTRY])
    return ok and clicks_ok, f"run={ok} 点击={rp.real_clicks}"


def case_tries_claim(rp):
    """⑥ 未达 → 继续出击 → 第 2 次达标就领 → 不打第 3 次。"""
    calls: list = []
    real = _stub_sortie(calls, rp)
    try:
        ok = gb.run(_sc(), kit.Args())
    finally:
        gb.sortie = real
    expect = [C_ENTRY, C_GB_ENTRY, C_D50, C_CLAIM]
    clicks_ok = st.check_clicks("未达→出击→达标就领", rp.real_clicks, expect)
    n = len(calls)
    print(f"[{'ok  ' if n == 2 else '!!  '}] 出击 {n} 次 (期望 2: 首次未达继续，第 2 次达标就收)")
    return ok and clicks_ok and n == 2, f"run={ok} 出击={n} 点击={rp.real_clicks}"


def case_tries_stop(rp):
    """⑥b 3 次都未达 50M → 按约定停手(False) + 留证。"""
    calls: list = []
    real = _stub_sortie(calls, rp)
    try:
        ok = gb.run(_sc(), kit.Args())
    finally:
        gb.sortie = real
    n = len(calls)
    shot = st.expect_shot("未达 3 次留证", rp, True)
    print(f"[{'ok  ' if n == gb.MAX_TRIES else '!!  '}] 出击 {n} 次 (期望 {gb.MAX_TRIES})")
    print(f"[{'ok  ' if not ok else '!!  '}] run={ok} (期望 False: 3 次都没到 50M)")
    return (n == gb.MAX_TRIES) and (not ok) and shot, f"出击={n} run={ok} 留证={rp.shots}"


def case_sortie_real(rp):
    """⑦ 真 sortie: 点出击 → 离开征讨页闸门 → 局内跑到超时(FIGHT_TIMEOUT 改小控预算)。

    局内会按节拍点技能 —— 本模式技能键换皮，battle_skill 模板不命中 → 走兜底坐标，
    所以「第一次点击=出击，其余全是技能兜底点」就是正确形状(技能次数随超时长短而变，
    故只校验形状不校验个数)。
    """
    old = gb.FIGHT_TIMEOUT
    gb.FIGHT_TIMEOUT = 6
    try:
        ok = gb.sortie(_sc())
    finally:
        gb.FIGHT_TIMEOUT = old
    got = rp.real_clicks
    first_ok = bool(got) and abs(got[0][0] - C_GO[0]) <= 6 and abs(got[0][1] - C_GO[1]) <= 6
    rest_ok = all(abs(x - C_SKILL[0]) <= 6 and abs(y - C_SKILL[1]) <= 6 for x, y in got[1:])
    print(f"[{'ok  ' if first_ok else '!!  '}] 首次点击=出击 {got[:1]}")
    print(f"[{'ok  ' if rest_ok else '!!  '}] 其余 {len(got) - 1} 次都是局内技能点(兜底 {C_SKILL})")
    print(f"[{'ok  ' if not ok else '!!  '}] 局内不回征讨页 → 超时 sortie={ok} (期望 False)")
    return first_ok and rest_ok and (not ok), f"sortie={ok} 点击={got} 留证={rp.shots}"


def case_sortie_stuck(rp):
    """⑦b 点出击后仍停在征讨页(次数用尽/网络慢) → 停手 + 留证，不进局内白等。"""
    ok = gb.sortie(_sc())
    clicks_ok = st.check_clicks("出击卡页", rp.real_clicks, [C_GO])
    shot = st.expect_shot("出击未开打留证", rp, True)
    return clicks_ok and (not ok) and shot, f"sortie={ok} 点击={rp.real_clicks} 留证={rp.shots}"


def case_finish(rp):
    """⑧ 结算页「确定」→ 回征讨页。"""
    ok = gb.finish_result(_sc())
    clicks_ok = st.check_clicks("结算页确定", rp.real_clicks, [C_OK])
    return ok and clicks_ok, f"finish={ok} 点击={rp.real_clicks}"


def case_unknown(rp):
    """⑨ 未知页中止: 零点击。"""
    ok = gb.run(_sc(), kit.Args())
    safe = not rp.real_clicks
    print(f"[{'ok  ' if safe else '!!  '}] 未知页点击 {len(rp.real_clicks)} 次 (期望 0)")
    return (not ok) and safe, f"run={ok}(期望 False) 点击={rp.real_clicks}"


def case_dry(rp):
    """⑨b dry: 零点击零写盘。"""
    ok = gb.run(_sc(dry=True), kit.Args(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    """⑨c 并发锁互斥。"""
    name = "guild_boss_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("①判层专场(局内必须 UNKNOWN)", LAYERS, case_layers),
    ("②50M 槽三态", [P1, P2, PEND], case_states),
    ("③前提闸门(结算页必须挡住)", [P1, DN], case_gate),
    ("④开局已可领→直接领(0 次出击)", [HM, GD, P1, POP, P2], case_claim_now),
    ("⑤今日已领→0 次出击收工", [HM, GD, P2], case_already),
    ("⑥未达→出击→达标就领", [HM, GD, PEND, PEND, P1, POP, P2], case_tries_claim),
    ("⑥b 未达×3→停手+留证", [HM, GD, PEND, PEND, PEND, PEND], case_tries_stop),
    ("⑦真 sortie: 出击→局内超时", [P1] + [BAT] * 40, case_sortie_real),
    ("⑦b 出击后卡在征讨页→停手留证", [P1, P1, P1], case_sortie_stuck),
    ("⑧结算页点确定→回征讨页", [DN, P1], case_finish),
    ("⑨未知页零点击", [UNK], case_unknown),
    ("⑨b dry 零点击零写盘", [P1], case_dry),
    ("⑨c 并发锁互斥", [P1], case_lock),
]


def ensure_fixtures() -> bool:
    """合成夹具按需生成（缺真帧则整份自检失去意义 → 直接跳过）。"""
    for f in (HM, GD, PEND, P1, P2, POP, DN, BAT):
        if not (SHOTS_DIR / f).is_file():
            print(f"[SKIP] 缺真帧夹具 {f}")
            return False
    if not (SHOTS_DIR / UNK).is_file():
        cv2.imwrite(str(SHOTS_DIR / UNK), np.full((1507, 814, 3), 16, np.uint8))
        print(f"[生成] {UNK}（合成: 纯深色，不含任何页面标志）")
    return True


if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("guild_boss 离线自检（真帧回放: 三态/闸门/循环/出击闸门）", SCENES)
