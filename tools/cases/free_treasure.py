#!/usr/bin/env python
"""用例: 寻宝（两张宝箱卡的免费广告各领一次）。

链路(2026-10-11 改版):
    首页 → 寻宝(nav_treasure，默认 tab 就是寻宝) → 页面上拖露出完整卡片
    → 两张卡的免费 icon(treasure_free，美术一致 → 多命中检测) → 逐个:
         点免费 icon → 广告(ad_rewarded ≥0.93 才算播完) → 关广告
         → 卡上出现**金色宝箱 → 点宝箱开箱**(用户实测: 改版后要点击宝箱才算领取完毕,
           旧版的开箱动画+中缝推进点已废) → claim_btn 领取
    → 领取成功的判据: 该位置的免费 icon **消失**(次数 -1)

    ⚠ 广告播放期全屏盖住整页，且 ad_close 可能检不到(<0.85) → 页面标志
      treasure_help 不在 ⇒ 广告中，**绝不点屏幕**(否则会点到广告内容)
    ⚠ 两卡 icon 美术一致，单模板多命中 + NMS(涂黑重找)；命中按 x 升序，x<406 为左卡
    ⚠ 金色宝箱用**金色像素 bbox** 定位(实测 818x1507 帧: bbox x306-618 / y1007-1208,
      金色 ~3500px)，不依赖模板; 点击后 ~2s 内弹「恭喜获得」

用法:
    uv run python tools/cases/free_treasure.py [--max=2] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402
import numpy as np  # noqa: E402

TH = 0.85               # 通用阈值
TH_ICON = 0.88          # 免费 icon(多命中): 0.88 时正好 2 个命中、无幻影
TH_REWARDED = 0.93      # 广告「已获得奖励」——低于此是播放中的假命中，不许关广告
FLOW_TIMEOUT = 150      # 单个宝箱(广告+开箱+领取)总超时
# 金色宝箱检测区(2026-10-11 在 818x1507 实帧量得): 宝箱出现在卡带下方 y1007-1208。
# 判据见 find_chest(数量区间 + bbox 宽度双条件, 防正常卡插画/兑换页金色钮误报)。
CHEST_Y0, CHEST_Y1 = 950, 1300

PLAN = """[dry] 计划:
  首页 --(nav_treasure 寻宝)--> 寻宝页 --(上拖)--> 露出两张宝箱卡
  --> 逐个免费 icon(treasure_free，两卡美术一致→多命中检测):
        点免费 → 广告(ad_rewarded≥0.93 才算播完) → 关广告
        → 卡上出现金色宝箱 → 点宝箱开箱 → claim_btn 领取(2026-10-11 改版流程)
  --> 成功判据: 该位置免费 icon 消失(次数 -1)；最多 2 个
  ⚠ 广告播放期全屏遮住页面且 ad_close 可能检不到 → 判页面标志，广告中绝不点屏幕
  ⚠ x<406 为左卡(装备宝箱)，否则右卡(高级装备宝箱)"""


def find_chest(sc: kit.Screen) -> tuple[int, int] | None:
    """金色宝箱(改版流程): 关广告后卡上出现, 点它才开箱发奖。

    金色像素 bbox 定位(不依赖模板), 双条件判「宝箱特写在场」:
      ① 金色(px) ∈ [500, 15000] —— 宝箱 ~7400; 正常寻宝页卡插画 ~33000(超上限拒绝)
      ② bbox 宽 < 450 —— 宝箱特写居中 ~312 宽; 兑换页金色钮 ~7457px 但宽 658(靠此挡住)
    实测(818x1507): 宝箱 bbox x306-618 / y1007-1208。
    """
    img = sc.grab()
    sub = img[CHEST_Y0:CHEST_Y1, :]
    b = sub[..., 0].astype(int)
    g = sub[..., 1].astype(int)
    r = sub[..., 2].astype(int)
    gold = (r > 150) & (g > 110) & (b < 110)
    n = int(gold.sum())
    if not (500 <= n <= 15000):
        return None
    xs = np.where(gold.sum(axis=0) > 2)[0]
    ys = np.where(gold.sum(axis=1) > 2)[0]
    if int(xs.max() - xs.min()) >= 450:
        return None
    cx = int((int(xs.min()) + int(xs.max())) // 2)
    cy = int(ys.min() + ys.max()) // 2 + CHEST_Y0
    return (cx, cy)


def page_ready(sc: kit.Screen) -> bool:
    return sc.find("treasure_help") is not None or sc.find("treasure_tab") is not None


def goto_treasure(sc: kit.Screen) -> bool:
    """从任意状态导航到寻宝页(寻宝为默认 tab)。"""
    if page_ready(sc):
        log("已在寻宝页")
        return True
    entry = sc.find("nav_treasure")
    if entry is None:
        log("找不到寻宝入口(nav_treasure)，可能不在首页")
        return False
    sc.click(entry, "寻宝入口")
    if sc.dry:
        return True
    # ⚠ 点完立即单帧判会撞上页面切换动画(2026-10-11 实测: 留证帧上 treasure_tab
    #   0.996 早已就位, 当时的单帧却报「未就绪」) → 未中再轮询等 6s
    ok = page_ready(sc) or sc.wait("treasure_help", 6) is not None \
        or sc.find("treasure_tab") is not None
    log("寻宝页就绪" if ok else "寻宝页未就绪")
    return ok


def reveal_cards(sc: kit.Screen) -> list[tuple[int, int, float]]:
    """确保两张宝箱卡完整可见(返回可用的免费 icon 列表)。"""
    hits = sc.find_all("treasure_free", th=TH_ICON)
    log(f"检测到免费 icon {len(hits)} 个: {[(h[0], h[1], round(h[2], 3)) for h in hits]}")
    if len(hits) >= 2:
        log("两个宝箱卡已完整可见，无需拖动")
        return hits
    for attempt in (1, 2):
        log(f"卡片不完整，第 {attempt} 次上拖")
        sc.drag_up()          # 起点 x 默认窗口中心，y 走基准换算
        hits = sc.find_all("treasure_free", th=TH_ICON)
        log(f"拖动后免费 icon {len(hits)} 个: {[(h[0], h[1], round(h[2], 3)) for h in hits]}")
        if len(hits) >= 2 or sc.dry:
            break
    return hits


def drain_claim(sc: kit.Screen, x0: int, timeout: float = 14.0) -> bool:
    """点掉所有「恭喜获得」弹窗，直到该位置的免费 icon 消失。

    实测: 点 claim_btn 后直接回寻宝页；但保险起见处理二次弹窗——
    图标还在就继续等/继续点，避免把「弹窗盖住图标」误判成领取成功。
    """
    end = kit.time.time() + timeout
    while kit.time.time() < end:
        st = sc.look("claim_btn", "ad_close")
        if st["claim_btn"] is not None:
            sc.click(st["claim_btn"], "领取(恭喜获得)")
            continue
        if st["ad_close"] is not None:
            kit.nap(1.0)
            continue
        if not [h for h in sc.find_all("treasure_free", th=TH_ICON) if abs(h[0] - x0) < 40]:
            return True
        kit.nap(1.5)
    return False


def one_chest(sc: kit.Screen, hit, label: str) -> bool:
    """点一个宝箱的免费 icon → 广告 → 金色宝箱开箱 → 领取(2026-10-11 改版流程)。"""
    x0 = hit[0]
    log(f"=== {label} 免费寻宝 (icon at {x0},{hit[1]} score={hit[2]:.3f}) ===")
    sc.click(hit, f"{label}·免费广告icon")
    t0 = kit.time.time()
    ad_seen = False
    chest = None
    while kit.time.time() - t0 < FLOW_TIMEOUT:
        st = sc.look("jump_no", "claim_btn", "ad_rewarded", "ad_close", "treasure_help")
        jno, cbtn, adr, adc = st["jump_no"], st["claim_btn"], st["ad_rewarded"], st["ad_close"]
        page = st["treasure_help"] is not None
        adr_s = f"{adr[2]:.3f}" if adr else "——"
        log(f"t={kit.time.time() - t0:5.1f} jump_no={jno is not None} claim={cbtn is not None} "
            f"ad_close={adc is not None} ad_rewarded={adr_s} page={page}")

        if jno is not None:
            sc.click(jno, "不使用(跳过卡)")
            continue
        if cbtn is not None:                        # 恭喜获得 → 领取
            if adc is not None:
                sc.click(adc, "广告关闭")
                kit.nap(1.5)
                continue
            sc.click(cbtn, "领取")
            kit.nap(1.5)
            if drain_claim(sc, x0):
                log(f"{label} 领取完成: 免费icon 已消失(今日剩余次数 -1)")
                return True
            log(f"{label} 已点领取，但该 icon 仍在 → 可能未成功")
            sc.shot(f"afterclaim_{label}")
            return False
        if adr is not None and adc is not None and adr[2] >= TH_REWARDED:    # 广告播完 → 关
            ad_seen = True
            sc.click(adc, "广告关闭")
            kit.nap(2.0)
            continue
        if adc is not None and kit.time.time() - t0 >= kit.AD_FALLBACK_AT:
            # ⭐ 2026-10-15 实测（用户反馈「有卡流程了」）: 「已获得奖励」走**字形路径**时
            #   分数可能落在 0.86~0.93 之间（欧派皮肤实测 0.9159）→ 既进不了上面
            #   ≥TH_REWARDED(0.93) 的分支，又因 adr 非 None 跳过下面「被盖住」兜底
            #   → 干等到 150s 超时（实测 t=103.9→150 一直 True/True/False）。
            #   超过 AD_FALLBACK_AT 秒仍只有「关闭」→ 只凭「关闭」关掉（兑底差允）。
            log(f"  「已获得奖励」分数长期不足(adr={adr_s}) → 仅凭「关闭」关广告")
            ad_seen = True
            sc.click(adc, "广告关闭(兜底)")
            kit.nap(2.0)
            continue
        if not page and adc is None and adr is None:
            # 页面被全屏广告/弹层盖住 —— 千万别在这里点屏幕:
            # 实测广告播放中 ad_close 可能检不到，盲点会点到广告内容。
            if kit.time.time() - t0 > 60 and not ad_seen:
                log("[warn] 广告已 >60s 仍未出现「已获得奖励」，继续等")
            kit.nap(2.0)
            continue
        # 广告已关、寻宝页回来了 → 改版流程: 卡上出现**金色宝箱**, 点它开箱
        if ad_seen and page:
            chest = chest or find_chest(sc)
            if chest is not None:
                log(f"金色宝箱出现 ({chest[0]},{chest[1]}) → 点击开箱")
                sc.click_at(chest[0], chest[1], "宝箱(开箱)")
                kit.nap(2.0)
                continue
        kit.nap(2.0)

    log(f"{label} 流程超时")
    sc.shot(f"fail_{label}")
    return False


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if not goto_treasure(sc):
        log("未就绪到寻宝页")
        sc.shot("fail_nav")
        return False
    if sc.dry:
        log("[dry] 计划: 上拖露卡 → 逐个免费 icon → 广告 → 金色宝箱开箱 → 领取 × 最多 "
            f"{max(1, args.max or 1)} 个")
        return True

    reveal_cards(sc)

    consumed: list[int] = []
    for _ in range(max(1, args.max or 1)):
        hits = [h for h in sc.find_all("treasure_free", th=TH_ICON)
                if all(abs(h[0] - cx) >= 40 for cx in consumed)]
        if not hits:
            log("没有可用的免费 icon(两个宝箱都领完 / 未露出)")
            break
        target = hits[0]
        label = "装备宝箱" if target[0] < sc.w / 2 else "高级装备宝箱"   # 以窗口中线分左右卡
        if one_chest(sc, target, label):
            consumed.append(target[0])
        else:
            log(f"{label} 未完成，停止后续(避免重复消费)")
            break
        kit.nap(1.5)

    left = sc.find_all("treasure_free", th=TH_ICON)
    log(f"收尾: 剩 {len(left)} 个免费 icon {[(h[0], round(h[2], 3)) for h in left]} "
        f"| 已完成 {len(consumed)} 个宝箱")
    return bool(consumed)


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_treasure", "寻宝（两张宝箱卡免费广告）", run,
        plan=PLAN, prefix="treasure_", lock_ttl=600, th=TH, default_max=2,
    ))
