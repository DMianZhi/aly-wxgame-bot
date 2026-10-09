#!/usr/bin/env python
"""用例: 战队 BOSS 征讨（前提「奖励等级 MAX」，领 50M 档物资，最多 3 次/天）。

    链路:
    首页 --(gd_entry 战队)--> 战队页 --(gb_entry BOSS征讨)--> 征讨页
    -->【前提】gb_max 命中(奖励等级 MAX)；不命中 → 立即停手(非 MAX 的号按约定要手打)
    --> 50M 槽已可领(红点)? → 直接领下(不浪费今天的出击次数)
    --> 出击(gb_go) → 局内(wb.battle.fight) → 结算页「挑战完成」(gb_done) → 确定(gb_ok)
        → 回征讨页
    --> 50M 槽三态: 红点=可领 → 点 20钻石 icon → 恭喜获得 → claim_btn 领取 → 收工
                    绿勾=今日已领 → 收工(不再打)
                    都没有=未达 50M → 继续出击(最多 3 次/天)
    收尾: run_case 统一 goto_home

局内复用 wb.battle.fight: 进局等 0.5s → 每 5.2s 点右下角技能 → 阵亡钻石复活 → 装备UP
→ 结算页。**本模式的技能 icon 换皮(红色旋涡)但位置一致**，所以 battle_skill 模板若不命中
会自动退到兜底坐标(基准 740,1300)，无需另裁技能模板。

⚠ 前提「奖励等级 MAX」是用户硬要求: 等级非 MAX 时该行是数字 → gb_max 天然不命中。
   结算页也有「MAX 100%」进度条(gb_max 在结算页实测 0.79 假命中) → 只在**已确认是征讨页**
   之后才查前提，且阈值抬到 TH_MAX=0.90。
⚠ 50M 槽三态用**颜色像素**判，不用模板: 领完的图标被绿勾盖住，未领态裁的模板必然退化。
   实测 未领取 = 槽右上红点 65 像素; 已领取 = 图标区绿勾 459 像素; 两态互斥(0/459)。
   判据取**通道无关**写法(不依赖帧是 RGB 还是 BGR): 红=最高通道>190 且与次高差>110;
   绿=中间通道比另两个都高 40 以上(蓝进度条/粉底都不会落进这两条)。
⚠ 结算页「确定」必须用本用例自己的 gb_ok: 旧模板 wc_settle_go 会在征讨页「100% 进度条」
   上 0.970 假命中(差点点到进度条上)，gb_ok 同场景只有 0.418。
⚠ 点「出击」后可能**仍停在征讨页**(次数用尽/网络慢) → 必须等「离开征讨页」才算开打，
   不能直接进局内循环(否则会在征讨页上白等一整个 FIGHT_TIMEOUT)。

用法:
    uv run python tools/cases/guild_boss.py [--tries N] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import battle, bot as _bot, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86                # 通用阈值
TH_MAX = 0.90            # 「奖励等级 MAX」: 结算页有 MAX 100% 进度条(0.79) → 抬高
TH_CLAIM = 0.92          # 「领取」键: 多页同款，抬到 0.92 防串台(弹层实测 0.945)
FIGHT_TIMEOUT = 300      # 单次出击局内最长等待(自检会改小)
MAX_TRIES = 3            # 今日挑战次数上限(游戏侧 3 次/天)
DOT_MIN = 20             # 50M 槽红点像素阈值(实测未领 65 / 已领 0)
GREEN_MIN = 50           # 50M 图标绿勾像素阈值(实测已领 459 / 未领 0)
START_WAIT = 20.0        # 点出击后等离开征讨页
BACK_WAIT = 15.0         # 领奖/点确定后等回征讨页
CLAIM_WAIT = 10.0        # 点钻石 icon 后等「恭喜获得」弹层
CLICK_TRIES = 3          # 确定键丢点击重试(重试前先查是否还在结算页)

# 50M 奖励槽的判态区(不是点击区)与点击点。
# 坐标量自 814x1507 实帧 _expl_expl_after_ok.png（未领取）+ _expl_expl_claim2.png（已领取）:
#   三槽红点中心 (401,1169)/(557,1170)/(714,1169) 等距 156px，50M 槽=最右那个；
#   图标盘面 x 639..775 / y 1152..1215，中心 (707,1184)。
RED_DOT = _bot.measured_rect(700, 1155, 32, 32, (814, 1507))     # 红点一般在 714,1169
D50_ICON = _bot.measured_rect(646, 1152, 122, 64, (814, 1507))   # 图标盘面(看绿勾)
D50_XY = _bot.client_to_ref(707, 1184, 814, 1507)                # 点击点(基准口径)

HOME, GUILD, PAGE, DONE, POPUP, UNKNOWN = ("HOME", "GUILD", "PAGE", "DONE", "POPUP", "?")

PLAN = """[dry] 计划:
  首页 --(gd_entry 战队)--> 战队页 --(gb_entry BOSS征讨)--> 征讨页
  -->【前提】gb_max 命中「奖励等级 MAX」(不命中则停手，非 MAX 的号要手打)
  --> 50M 槽已可领(红点) → 直接领；今日已领(绿勾) → 直接收工
  --> 出击(gb_go) → 局内每 5.2s 点右下角技能(换皮但同位置) → 阵亡钻石复活 → 装备UP
      → 结算页「挑战完成」(gb_done) → 确定(gb_ok) → 回征讨页
  --> 50M 槽红点=可领 → 点 20钻石 icon(707,1184) → 恭喜获得 → 领取(claim_btn) → 收工
      绿勾=今日已领 → 收工 / 都没有=未达 50M → 继续出击(最多 3 次)
  收尾: 统一回首页"""


def _find(sc: kit.Screen, name: str, th: float = TH):
    """模板缺失时返回 None(不炸)，便于逐步补模板。"""
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def _hit(st: dict, name: str, th: float = TH) -> bool:
    h = st.get(name)
    return h is not None and h[2] >= th


def page(sc: kit.Screen) -> str:
    """当前页面: popup(恭喜获得) > done(结算页) > page(征讨页) > guild > home > unknown。

    判层顺序要紧: 「恭喜获得」是全屏暗幕, 会把底下的页面标志压掉(gb_go 掉到 0.407、
    gb_max 0.755) —— 用 claim_btn 命中且 gb_go 不命中来认它。
    首页标志只能用 stage_btn(闯关模式)；gd_entry 只当点击目标(首页 1.000)。
    """
    st = sc.look("claim_btn", "gb_done", "gb_go", "gb_entry", "gd_entry", "stage_btn")
    if _hit(st, "claim_btn", TH_CLAIM) and not _hit(st, "gb_go"):
        return POPUP
    if _hit(st, "gb_done"):
        return DONE
    if _hit(st, "gb_go"):
        return PAGE
    if _hit(st, "gb_entry"):
        return GUILD
    if _hit(st, "stage_btn"):
        return HOME
    return UNKNOWN


def _count(roi, kind: str) -> int:
    """ROI 里符合「红」/「绿」的像素数。写法与帧的通道顺序无关。

    红(红点): 最高通道 > 190 且与次高差 > 110 —— 蓝进度条/粉底(次高也亮)都被排除；
    绿(绿勾): 中间通道(绿)比另两个都高 40+ —— 两种通道顺序下都成立。
    """
    if roi is None or roi.size == 0:
        return 0
    a, b, c = (roi[:, :, i].astype(int) for i in range(3))
    if kind == "red":
        hi = np.maximum(np.maximum(a, b), c)
        lo = np.minimum(np.minimum(a, b), c)
        mid = a + b + c - hi - lo
        return int(((hi > 190) & (hi - mid > 110)).sum())
    return int(((b > a + 40) & (b > c + 40)).sum())


def reward_state(sc: kit.Screen) -> str:
    """50M 奖励槽三态: claim(可领) / claimed(今日已领) / pending(未达 50M)。"""
    img = sc.grab()
    if _count(sc.roi(*RED_DOT, img=img), "red") >= DOT_MIN:
        return "claim"
    if _count(sc.roi(*D50_ICON, img=img), "green") >= GREEN_MIN:
        return "claimed"
    return "pending"


def enter_page(sc: kit.Screen) -> bool:
    """从任意页进到征讨页: 首页→战队页→征讨页；残留弹层/结算页顺手收掉。"""
    for _ in range(5):
        p = page(sc)
        log(f"当前页面: {p}")
        if p == PAGE:
            return True
        if p == POPUP:                       # 残留「恭喜获得」: 先领掉
            c = _find(sc, "claim_btn", TH_CLAIM)
            if c is None:
                log("恭喜获得弹层上找不到「领取」键")
                return False
            sc.click(c, "领取(残留弹层)")
            kit.nap(3.0)
            continue
        if p == DONE:                        # 残留结算页: 点确定
            ok = _find(sc, "gb_ok")
            if ok is None:
                log("结算页上找不到「确定」键")
                return False
            sc.click(ok, "确定(残留结算页)")
            kit.nap(3.0)
            continue
        if p == HOME:
            e = _find(sc, "gd_entry")
            if e is None:
                log("首页找不到「战队」入口(gd_entry)")
                sc.shot("fail_entry")
                return False
            sc.click(e, "战队入口(gd_entry)")
            kit.nap(3.0)
            continue
        if p == GUILD:
            b = _find(sc, "gb_entry")
            if b is None:
                log("战队页找不到「BOSS征讨」入口(gb_entry)")
                sc.shot("fail_gb_entry")
                return False
            sc.click(b, "BOSS征讨(gb_entry)")
            kit.nap(3.5)
            continue
        log("未知页面(非首页/战队页/征讨页)，请人工确认")
        sc.shot("unknown_page")
        return False
    return False


def claim(sc: kit.Screen) -> bool:
    """点 20钻石 icon → 等「恭喜获得」→ 点「领取」→ 等回征讨页。"""
    sc.click_base(D50_XY[0], D50_XY[1], "20钻石 icon(50M 档)")
    t0 = kit.time.time()
    got = False
    while kit.time.time() - t0 < CLAIM_WAIT:
        c = _find(sc, "claim_btn", TH_CLAIM)
        if c is not None:
            sc.click(c, "领取(恭喜获得)")
            got = True
            break
        kit.nap(1.0)
    if not got:
        log("点了钻石 icon 但没等到「恭喜获得」弹层 → 断定领取失败(留证)")
        sc.shot("claim_nopopup")
        return False
    kit.nap(3.0)
    t0 = kit.time.time()
    while kit.time.time() - t0 < BACK_WAIT:
        if _find(sc, "gb_go") is not None:
            log("领取完成 → 已回征讨页")
            return True
        kit.nap(1.0)
    log("领取后没回到征讨页(留证)")
    sc.shot("claim_noback")
    return False


def out_of_battle(sc: kit.Screen) -> int:
    """局内退出判据: 结算页「挑战完成」1 次即收工；征讨页需连续 2 次(防点出击后短暂停留)。

    结算页是全屏接管页，不存在「战斗间隙闪过」的问题 → 1 次即可；
    征讨页要走「确定」这一步，正常不会在局内出现，留 2 次防抖。
    """
    if _find(sc, "gb_done") is not None:
        return 1
    if _find(sc, "gb_go") is not None:
        return 2
    return 0


def fight(sc: kit.Screen) -> bool:
    """局内一轮(等价 BOSS 闪击的局内): 技能/复活/装备UP/结算页。"""
    ok, rounds, revives = battle.fight(sc, out_of_battle,
                                       timeout=FIGHT_TIMEOUT, label="本轮征讨")
    log(f"局内结束: {'完成' if ok else '超时'} (结算页 {rounds} 张 / 复活 {revives} 次)")
    return ok


def finish_result(sc: kit.Screen) -> bool:
    """结算页「挑战完成」→ 点确定 → 等回征讨页(丢点击则重试，重试前先查还在不在本页)。"""
    for _ in range(CLICK_TRIES):
        ok = _find(sc, "gb_ok")
        if ok is None:
            break
        sc.click(ok, "确定(挑战完成)")
        kit.nap(3.0)
    t0 = kit.time.time()
    while kit.time.time() - t0 < BACK_WAIT:
        if _find(sc, "gb_go") is not None:
            return True
        kit.nap(1.0)
    log("点确定后没回到征讨页(留证)")
    sc.shot("noback_after_result")
    return False


def sortie(sc: kit.Screen) -> bool:
    """点「出击」→ 等真的离开征讨页(次数用尽/网络慢会停在原页) → 跑完局内。"""
    g = _find(sc, "gb_go")
    if g is None:
        log("征讨页找不到「出击」键(gb_go)")
        return False
    sc.click(g, "出击")
    t0 = kit.time.time()
    while kit.time.time() - t0 < START_WAIT:
        if _find(sc, "gb_go") is None:
            break
        kit.nap(1.5)
    else:
        log("点了出击但仍在征讨页 → 今日挑战次数可能已用尽(留证)")
        sc.shot("sortie_stuck")
        return False
    log("已离开征讨页 → 进局内")
    return fight(sc)


def run(sc: kit.Screen, args: kit.Args) -> bool:
    tries = int(args.extra.get("tries") or MAX_TRIES)
    p = page(sc)
    log(f"起点页面 {p}")

    if sc.dry:
        for n, note in (("gd_entry", "首页「战队」入口"), ("gb_entry", "战队页「BOSS征讨」"),
                        ("gb_max", "前提「奖励等级 MAX」"), ("gb_go", "征讨页「出击」"),
                        ("gb_done", "结算页「挑战完成」"), ("gb_ok", "结算页「确定」"),
                        ("claim_btn", "「恭喜获得」领取键")):
            h = _find(sc, n)
            log(f"[dry] {n:10s} {note:16s} "
                + (f"命中 {h[:2]} score={h[2]:.3f}" if h else "未命中"))
        log(f"[dry] 50M 槽判态区 红点区={RED_DOT} 图标区={D50_ICON} 点击点(基准)={D50_XY}")
        log(f"[dry] 最多出击 {tries} 次; 前提不满足则停手")
        log("[dry] 计划输出完毕(未点击)")
        return True

    if not enter_page(sc):
        return False
    sc.shot("page_state")            # 留证: 今日伤害 / 今日挑战次数剩余

    if _find(sc, "gb_max", TH_MAX) is None:
        log("⚠ 奖励等级不是 MAX → 按约定停手(非 MAX 的号请手打，自动化不适用)")
        sc.shot("not_max")
        return False

    st0 = reward_state(sc)
    log(f"开局 50M 槽三态={st0}")
    if st0 == "claim":
        log("50M 档已可领 → 直接领(不浪费今天的出击次数)")
        return claim(sc)
    if st0 == "claimed":
        log("50M 档今日已领 → 无需出击")
        return True

    for i in range(1, tries + 1):
        log(f"===== 第 {i}/{tries} 次出击 =====")
        if not sortie(sc):
            log(f"第 {i} 次出击未开打 → 停手(次数用尽/超时)")
            return False
        if not finish_result(sc):
            return False
        st = reward_state(sc)
        log(f"第 {i} 次出击后 50M 槽三态={st}")
        if st == "claim":
            return claim(sc)
        if st == "claimed":
            log("50M 档已领(今日) → 收工")
            return True
        if i < tries:
            log("伤害未达 50M → 继续出击")
    log(f"{tries} 次出击后仍未达 50M → 按约定停手(留证)")
    sc.shot("not_reached")
    return False


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "guild_boss", "战队 BOSS 征讨（前提奖励等级 MAX，领 50M 档物资）", run,
        plan=PLAN, prefix="guildboss_", lock_ttl=3600, th=TH,
        need_home=True, extra_kv=("--tries",), default_timeout=1800,
    ))
