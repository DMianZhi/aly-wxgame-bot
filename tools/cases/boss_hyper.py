#!/usr/bin/env python
"""用例: BOSS 超限模式（4 站 × 6 boss，每日次数游戏内默认，阵亡钻石复活）。

链路（2026-10-10 实探 + 超限#1 实跑打通）:
    首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_boss)--> BOSS 列表
    --(boss_hyper「超限模式」)--> 超限页(hyper_title, 4 个空间站卡)
    --(hyper_stn_* 铭牌)--> 详情页(刺针·XX, 普通/超限两档)
    --(切换箭头「下一个/上一个」扫掠 6 个 boss)--> 依次「超限挑战」(hyper_chal)
    --> 确认弹窗「是否开始挑战?」(hyper_start 黄键) --> 局内
    --> 每 5.2s 点右下技能 + 每 30s 点左下爆弹(battle_nuke, CD 30s)
        → 阵亡复活(钻石20) → 装备UP(取默认) → 结算继续 → 回详情页

⚠ 每站 6 个 boss(底部 6 个指示点): 详情页顶部名条显示当前 boss 名。切换键是
  左缘「上一个」/右缘「下一个」箭头(非循环, 到头消失; 游戏会记住上次浏览位置,
  重进详情页不一定从 #1 开始) → 策略=双向扫掠: 向右扫到头, 再向左扫回,
  路过已打过的(名条指纹 diff≤阈值)不重复打。箭头有明/暗两种样式(模板分不稳)
  → 坐标盲点点击, 生效与否靠名条 diff 事后验证(防丢点击重复打同一个)。
⚠ 「超限挑战」点击后可能弹「黄金钥匙」物品详情(按钮上方的奖励图标 0.974 高仿)
  → hyper_chal 模板已重裁为真按钮(811 帧实测 (511,1407))；弹了就 popup_blue_x 关掉重试。
⚠ 装备战力 37729 > 上限 8000: 超限模式**削装备战力**，输入再高进场也按 8000 算 ——
  别被「战力虚高」迷惑，该复活复活。
⚠ 局内比闪击难打(复活阈值低) → FIGHT_TIMEOUT 放宽到 600s。

用法:
    uv run python tools/cases/boss_hyper.py [--station 装甲,战机|drago,pegasus|all] [--dry]

    默认 4 站全跑(每站 6 boss = 24 场)；--station 显式指名跑部分站。
    中途每场打完即记数，超时/异常保留进度(下一个 boss 从当前详情页接着切)。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import battle, kit  # noqa: E402
from wb.kit import log, nap  # noqa: E402

TH = 0.85
FIGHT_TIMEOUT = 600         # 单场最长等待(超限难打，比闪击的 480 再宽)
SKILL_FIRST_X = 3.5         # 进局先等 3.5s 再点第一下(比闪击的 0.5s 晚 3s):
                            # 超限局开场前 3~4s 是进场动画+计分板，早点是空点
NUKE_FIRST_X = 6.0          # 第一次爆弹同样延后(等开场动画+技能先手)
                            # 用户反馈(2026-10-11): 爆弹和技能初始点击太早
NAV_WAIT = 2.5              # 导航点击后等画面稳定
SWITCH_WAIT = 2.0           # 点切换键后等名条刷新
BOSS_TOTAL = 6              # 每站 6 个 boss(环状切换, 6 场全覆盖)
ROI_NAME = (90, 317, 300, 53)    # 名条**文字区**(刺针·XX; 不含右侧动态人数条)
ROI_DIFF_TH = 0.030         # 名条 diff 阈值。实测(窄ROI): 同boss跨帧 0.008~0.021,
                            # 换boss 6.6+ / 换站 80+ → 300 倍余量; 旧宽ROI(整条)
                            # 同boss 0.75/换boss 1.7 仅 2 倍余量, 人数变动即可误判换过
ARROW_RIGHT = (826, 702)    # 右缘「下一个」箭头(基准坐标; 811 客户区实测点击中心 793,700)
ARROW_LEFT = (39, 697)      # 左缘「上一个」箭头(暗色样式模板分仅 0.59 → 坐标盲点)
CHAL_BTN = (511, 1407)      # 「超限挑战」按钮(基准坐标; 811 帧实测中心)
DONE_TH = 0.90              # hyper_done(挑战成功绿标)阈值: 已击败 1.000 / 未完成 0.693
                            # (中间带很宽, 0.90 稳) —— 绿标在右卡右上角斜角, 左卡绿勾不串台

STATIONS = {
    "drago":   ("hyper_stn_drago",   "装甲"),
    "cygnus":  ("hyper_stn_cygnus",  "副武器"),
    "pegasus": ("hyper_stn_pegasus", "战机"),
    "andro":   ("hyper_stn_andro",   "僚机"),
}
DEFAULT_STATIONS = ("drago", "cygnus", "pegasus", "andro")   # 默认 4 站全跑
_STATION_ALIAS = {name: key for key, (_, name) in STATIONS.items()}
HYPER_MARKS = ("hyper_title",) + tuple(t for t, _ in STATIONS.values())

PLAN = """[dry] 计划:
  首页 --(stage_btn 闯关模式)--> 关卡页 --(stage_boss)--> BOSS 列表
  --(boss_hyper)--> 超限页 → 空间站(hyper_stn_*) → 详情页
  --(切换箭头扫掠: 右到头换向, 名条指纹跳过已打)--> hyper_chal 超限挑战
  --> 确认弹窗(hyper_start) → 局内: 技能 5.2s + 爆弹 30s → 复活 → 装备UP → 结算
  --> 回详情页 → 下一场；每站 6 场 × 默认 4 站 = 24 场
  降级: 黄金钥匙物品弹窗(popup_blue_x 关掉重试) / 切换无反应(名条 diff=0 → 丢点击重试)
  收尾: 全部完成回首页"""


def _find(sc, name, th=TH):
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def parse_stations(raw: str | None) -> list[str]:
    """解析 --station: key/中文名/all/default，去重保序。默认 4 站全跑。"""
    txt = (raw or "").strip()
    if not txt or txt.lower() in ("default", "默认"):
        return list(DEFAULT_STATIONS)
    if txt.lower() in ("all", "*", "全部"):
        return list(STATIONS)
    keys: list[str] = []
    bad: list[str] = []
    for tok in txt.replace("，", ",").replace("、", ",").replace(" ", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        k = tok if tok in STATIONS else _STATION_ALIAS.get(tok)
        if k is None or k in keys:
            if k is None:
                bad.append(tok)
            continue
        keys.append(k)
    if bad:
        raise SystemExit(f"未知 --station {bad[0]}（可选: {', '.join(STATIONS)} / "
                         f"{'/'.join(_STATION_ALIAS)} / all / default）")
    return keys or list(DEFAULT_STATIONS)


# ---------------------------------------------------------------- 名条 diff

def name_roi(sc: kit.Screen) -> np.ndarray | None:
    """抓详情页顶部 boss 名条(基准 ROI 自动换算)。名条区域全暗返回 None。"""
    roi = sc.roi(*ROI_NAME)
    return roi if roi.size and roi.mean() > 8 else None


def roi_diff(a: np.ndarray, b: np.ndarray) -> float:
    """两张名条图的 mean-abs-diff(/255)。形状不同按最大差异处理。"""
    if a.shape != b.shape:
        return 1.0
    return float(np.abs(a.astype(int) - b.astype(int)).mean()) / 255.0


def name_changed(sc: kit.Screen, before: np.ndarray | None) -> bool:
    """名条与切换前比是否变化(diff > 阈值)。before 为 None 时只要求名条可抓。"""
    after = name_roi(sc)
    if after is None:
        return False
    if before is None:
        return True
    return roi_diff(before, after) > ROI_DIFF_TH


def name_seen(sc: kit.Screen, seen: list[np.ndarray]) -> bool:
    """当前名条是否与已打过的某场相同(环闭合 = 一站已打完一圈)。"""
    cur = name_roi(sc)
    if cur is None:
        return False
    return any(roi_diff(cur, prev) <= ROI_DIFF_TH for prev in seen)


# ---------------------------------------------------------------- 页面流程

def on_hyper(sc: kit.Screen) -> bool:
    """超限页: 标题或任一站铭牌命中。"""
    for t in HYPER_MARKS:
        if _find(sc, t, 0.90) is not None:
            return True
    return False


def goto_hyper(sc: kit.Screen) -> bool:
    """从首页/关卡页/BOSS列表 → 超限页。"""
    if on_hyper(sc):
        return True
    if not kit.is_home(sc) and _find(sc, "stage_btn") is None:
        kit.goto_home(sc)
    btn = _find(sc, "stage_btn")
    if btn is not None:
        sc.click(btn, "闯关模式")
        nap(NAV_WAIT)
    b = _find(sc, "stage_boss")
    if b is None:
        log("关卡页没找到 BOSS 模式入口")
        return False
    sc.click(b, "BOSS 模式")
    nap(NAV_WAIT)
    hp = _find(sc, "boss_hyper")
    if hp is None:
        log("BOSS 列表页没找到「超限模式」入口")
        return False
    sc.click(hp, "超限模式")
    nap(NAV_WAIT)
    if not on_hyper(sc):
        sc.shot("hyper_nav_lost")
        log("点完超限模式仍不在超限页")
        return False
    return True


def already_done(sc: kit.Screen, img=None) -> bool:
    """当前详情页 boss 今天是否已被击败(右卡绿色「挑战成功」斜角标在场)。"""
    return _find(sc, "hyper_done", DONE_TH) is not None


def close_key_popup(sc: kit.Screen) -> bool:
    """关「黄金钥匙」物品详情弹窗(点超限挑战误触奖励图标时弹)。"""
    x = _find(sc, "popup_blue_x", 0.80)
    if x is None:
        return False
    log("出现物品详情弹窗(黄金钥匙等) → 蓝X关闭")
    sc.click(x, "蓝X(关物品详情)")
    nap(1.2)
    return True


def open_detail(sc: kit.Screen, tpl: str, name: str) -> bool:
    """超限页 → 某站详情页(点铭牌)。已在新详情页/已在详情页均可。"""
    if _find(sc, tpl, 0.90) is None:
        if not goto_hyper(sc):
            return False
    st = _find(sc, tpl, 0.90)
    if st is None:
        log(f"超限页没找到{name}铭牌")
        return False
    sc.click(st, f"{name}(进详情)")
    nap(NAV_WAIT)
    chal = _find(sc, "hyper_chal")
    if chal is None:
        close_key_popup(sc)
        chal = _find(sc, "hyper_chal")
    if chal is None:
        sc.shot(f"hyper_nodetail_{tpl.split('_')[-1]}")
        log(f"点铭牌后没进{name}详情页")
        return False
    return True


def fight_one(sc: kit.Screen) -> bool:
    """打一场当前 boss: 超限挑战 → 确认 → 局内全自动 → 回详情页/超限页。

    出击前提(今天未击败)在 one_station 里把关, 这里只负责打。
    节拍: 初始技能 3.5s/爆弹 6s 后再点(进场动画 3~4s), 爆弹 CD 20s。
    """
    chal = _find(sc, "hyper_chal")
    if chal is None:
        log("详情页没找到「超限挑战」按钮")
        return False
    sc.click(chal, "超限挑战")
    # 确认弹窗右上也有同款蓝X(实测同位同分) → 先等确认弹窗, 其在场绝不点X
    go = sc.wait("hyper_start", 4.0, 1.0, th=0.88)
    if go is None and close_key_popup(sc):      # 仅确认弹窗缺席才可能是物品弹窗
        go = sc.wait("hyper_start", 3.0, 1.0, th=0.88)
    if go is None:                      # 弹窗可能弹得慢, 再兜一轮
        go = sc.wait("hyper_start", 4.0, 1.0, th=0.88)
    if go is None:
        sc.shot("hyper_nodialog")
        log("点超限挑战后没出确认弹窗(可能已在战斗或按钮没点到)")
        return False
    sc.click(go, "挑战(确认弹窗)")
    nap(3.0)

    def out_of_battle(s) -> int:
        if _find(s, "hyper_chal", 0.90) is not None:
            return 1                    # 回详情页 = 打完(实跑 70~90s/场)
        if on_hyper(s):
            return 3                    # 回超限页也算打完(结算后可能直接出详情)
        return 0

    ok, rounds, revives = battle.fight(sc, out_of_battle, timeout=FIGHT_TIMEOUT,
                                       skill_first=SKILL_FIRST_X,
                                       nuke_period=20.0, nuke_first=NUKE_FIRST_X,
                                       label="超限本场")
    log(f"超限本场: {'完成' if ok else '超时'} (结算 {rounds} / 复活 {revives})")
    ok = fight_settle(sc) and ok
    return ok


def fight_settle(sc: kit.Screen) -> bool:
    """打完收尾: 从任何残留弹层回到「详情页或超限页」。"""
    for _ in range(6):
        if _find(sc, "hyper_chal", 0.90) is not None or on_hyper(sc):
            return True
        if close_key_popup(sc):
            continue
        nx = _find(sc, "boss_result_next", 0.90)
        if nx is not None:
            sc.click(nx, "继续(残留结算页)")
            nap(2.5)
            continue
        back = _find(sc, kit.BACK_KEY, 0.90)
        if back is not None:
            sc.click(back, "返回(收尾)")
            nap(1.5)
    return False


def one_station(sc: kit.Screen, key: str) -> int:
    """一站打完 6 个 boss(双向扫掠)。

    切换键是「上一个/下一个」箭头而非环形循环: 右到头右箭头消失,
    只能反向 → 策略为先向右扫到头, 再向左扫回来。方向翻转后名条会
    指向已打过的 boss, 属于预期, 不能当环闭合误判 → 用 done 计数判停,
    名条指纹只负责「验证切换生效」和「跳过已打的 boss」。
    箭头点击走基准坐标盲点(明暗两种样式模板分不稳, 空白处点击无副作用),
    生效与否由名条 diff 事后验证。
    返回完成场数(如实)。
    """
    tpl, name = STATIONS[key]
    log(f"===== 超限·{name} ({tpl}) =====")
    if not open_detail(sc, tpl, name):
        return 0
    done = 0
    skipped = 0                          # 今日已击败而跳过的场数
    seen: list[np.ndarray] = []          # 已打 boss 的名条指纹
    forward = True                       # True=向右(下一个) / False=向左(上一个)
    flipped = False                      # 已换过方向(防来回抖动)
    while done + skipped < BOSS_TOTAL:
        cur = name_roi(sc)
        if cur is not None:
            seen.append(cur)
        bn = "未见" if cur is None else "可见"
        # ---- 出击前提(2026-10-11 二次反馈): 只要今天未击败就打 ----
        # (早先「非 125% 跳过」的门槛已删: 不同 boss 抗性数值不同, 那条规则把
        #  未击败的 boss 全跳过 → 列表页 8/12、6/12 打不满, 活动最后一天漏打)
        if already_done(sc):
            log(f"--- {name} 第 {done + skipped + 1}/{BOSS_TOTAL} 场 (名条{bn}): "
                f"今日已击败(挑战成功绿标) → 跳过")
            skipped += 1
        else:
            log(f"--- {name} 第 {done + skipped + 1}/{BOSS_TOTAL} 场 (名条{bn}) ---")
            won = False
            for attempt in (1, 2):      # 失败不计完成, 原地重试一次
                if fight_one(sc):
                    won = True
                    break
                fight_settle(sc)
                if _find(sc, "hyper_chal", 0.90) is None and not on_hyper(sc):
                    break               # 回不到详情页/超限页, 无法原地重试
                if attempt == 1:
                    log(f"第 {done + 1} 场未完成 → 原地重试")
            if not won:
                log(f"{name}: 第 {done + 1} 场未完成 → 停在本站(如实已完成 {done})")
                return done
            done += 1
        if done + skipped >= BOSS_TOTAL:
            break
        # ---- 切到下一个(按当前方向): 名条必须变化, 否则当丢点击重试 ----
        def _arrow_xy() -> tuple[int, int]:
            x, y = ARROW_RIGHT if forward else ARROW_LEFT
            return x, y

        def _switch_step(tag: str) -> bool:
            """点一次方向箭头(基准坐标), 名条变了才算切成功。"""
            ax, ay = _arrow_xy()
            before2 = name_roi(sc)
            sc.click_base(ax, ay, f"切换→{'下一' if forward else '上一'}boss({tag})")
            nap(SWITCH_WAIT)
            if name_changed(sc, before2):
                return True
            for tries in range(2):      # 丢点击很常见: 最多补 2 次
                log(f"切换后名条未变(第 {tries + 1} 次重试)")
                sc.click_base(ax, ay, f"切换重试({tag})")
                nap(SWITCH_WAIT)
                if name_changed(sc, before2):
                    return True
            return False

        if not _switch_step("正手"):
            if flipped:
                log(f"{name}: 两个方向都切不动 → 停在本站(已完成 {done} 场)")
                return done
            forward = not forward       # 到头了: 换方向继续扫
            flipped = True
            log(f"{name}: {'右' if not forward else '左'}箭头到头 → 反向扫掠")
            if not _switch_step("反手"):
                log(f"{name}: 反向也切不动 → 停在本站(已完成 {done} 场)")
                return done
        # 反向回程一串都是本场次已打过的属正常, 用绿标判断决定去留 ——
        # 已击败会走上面 skipped++, 无需 name_seen 跳过。
    log(f"{name}: 本站收工 → 完成 {done} / 跳过 {skipped} (挑战成功)")
    # 收尾回「详情页或超限页」(下一站自己导航)
    if not fight_settle(sc):
        log(f"{name}: 打完但收尾停不回详情页(下一站会自己导航)")
    return done


def run(sc: kit.Screen, args: kit.Args) -> bool:
    keys = parse_stations(args.extra.get("station"))
    log(f"本次站点({len(keys)}): " + "、".join(STATIONS[k][1] for k in keys)
        + f" → 最多 {len(keys) * BOSS_TOTAL} 场")

    if sc.dry:
        p = "hyper" if on_hyper(sc) else "elsewhere"
        log(f"当前页面 {p}")
        for k in keys:
            tpl, name = STATIONS[k]
            hit = _find(sc, tpl) if on_hyper(sc) else None
            log(f"[dry] {name}({tpl}): "
                + (f"命中 {hit[:2]} score={hit[2]:.3f} → 会点它" if hit
                   else "需先导航到超限页"))
        log("[dry] 计划输出完毕(未点击)")
        return True

    total = 0
    for k in keys:
        got = one_station(sc, k)
        total += got
        log(f"站点 {STATIONS[k][1]} 完成 {got}/{BOSS_TOTAL} 场")
    log(f"超限模式总计: 完成 {total} 场(跳过的=今日已击败)")
    return True   # 跳过不是失败: 出击前提是动态的, 完成多少算多少


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "boss_hyper", "BOSS 超限模式(4站×6boss，技能+爆弹+复活)",
        run, plan=PLAN, prefix="hyper_", lock_ttl=7200, th=TH,
        extra_kv=("--station",), default_timeout=7200.0,
    ))
