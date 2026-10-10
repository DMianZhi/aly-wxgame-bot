#!/usr/bin/env python
"""用例: 商城「免费资源」第 4 个免费 = 扫荡卡 x3（广告 → 领取，最多 5 轮）。

    ⚠ 免费按钮没有模板: 位置由卡 4 图标中心下移 FREE_BTN_DY 推导
      (图标中心 y≈1092 → 按钮中心 y≈1220)，所以是算坐标点，不是模板匹配。
    ⚠ 商城四个免费位只裁了第 4 个(mall_card4)，本用例只吃这一个位。
    链路: 首页 → 商城 → 卡4 → 点免费 → 广告(ad_close) → 等 ad_rewarded →
          关广告 → 「恭喜获得」领取(claim_btn) → 回商城(card4 重现) = 成功
    次数耗尽时 card4 不再出现 → 自动停（不误点别的卡）。

用法:
    uv run python tools/cases/free_sweep.py [--max=5] [--dry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit  # noqa: E402
from wb.kit import log  # noqa: E402

FREE_BTN_DY = 128          # 免费按钮相对卡图标中心的纵向偏移
ROUND_TIMEOUT = 150        # 单轮总超时(广告最长 30s + 缓冲)
REWARDED_TIMEOUT = 45      # 等『已获得奖励』出现的上限

PLAN = """[dry] 计划:
  首页 --(shop 商城)--> 商城页 --(mall_card4 第4个免费位)--> 点免费按钮(卡4中心下移128px)
  --> 广告页(ad_close) --> 等 ad_rewarded(已获得奖励) --> 点关闭 --> 「恭喜获得」→ 领取
  --> 校验: mall_card4 重现(回商城页) = 本轮成功；最多 5 轮
  ⚠ 免费按钮是「卡4中心 + 128px」算出来的，没有独立模板
  ⚠ 广告播放中 ad_rewarded 可能是假命中，等它真出现(>=0.93)再关"""


def goto_mall(sc: kit.Screen) -> bool:
    """确保在商城页(判据: card4 在场)；不在就从首页点商城进去。"""
    if sc.wait("mall_card4", 1.0):
        return True
    # 等 5s 而不是一枪定成败: 上一个用例可能刚收尾(弹窗淡出/动画未完), 首页要缓一拍
    shop = sc.wait("shop", 5)
    if shop is None:
        log("找不到商城入口，可能不在首页")
        return False
    sc.click(shop, "商城入口(shop)")
    if not sc.wait("mall_card4", 12):
        log("进不去商城页")
        return False
    return True


def one_round(sc: kit.Screen, idx: int) -> bool:
    """一轮领取。True=继续下一轮，False=停(次数耗尽/异常)。"""
    card = sc.wait("mall_card4", 15)
    if card is None:
        log("card4 不在场: 不在商城页或次数已耗尽")
        sc.shot(f"sweep_fail_card{idx}")
        return False

    fx, fy = card[0], card[1] + FREE_BTN_DY
    log(f"card4=({card[0]},{card[1]}) → 免费按钮=({fx},{fy})")
    if sc.dry:
        log(f"[dry] 轮{idx}: 计划点免费按钮 ({fx},{fy}) → 广告 → 关闭 → 领取 → 校验 card4 重现")
        return True

    sc.click_at(fx, fy, "免费按钮(卡4下方)")

    ad = sc.wait("ad_close", 30)
    if ad is None:                      # 偶发跳过卡弹窗 → 点「不使用」再等
        jno = sc.wait("jump_no", 10)
        if jno is not None:
            sc.click(jno, "不使用(跳过卡)")
            ad = sc.wait("ad_close", 30)
    if ad is None:
        log("广告未出现，放弃本轮")
        sc.shot(f"sweep_fail_ad{idx}")
        return False
    log("广告播放中")

    rewarded = sc.wait("ad_rewarded", REWARDED_TIMEOUT)
    if rewarded is not None:
        log("奖励已到账(ad_rewarded)")

    ac = sc.wait("ad_close", 10)
    if ac is None and rewarded is None:
        log("未见『已获得奖励』且无关闭钮 → 超时")
        sc.shot(f"sweep_fail_reward{idx}")
        return False
    if ac is not None:
        sc.click(ac, "广告关闭")
    if not sc.wait_gone("ad_close", 15):
        log("广告关闭失败")
        sc.shot(f"sweep_fail_close{idx}")
        return False

    claim = sc.wait("claim_btn", 20)
    if claim is None:
        log("未见领取按钮")
        sc.shot(f"sweep_fail_claim{idx}")
        return False
    sc.click(claim, "领取(恭喜获得)")

    if sc.wait("mall_card4", 20) is None:
        log("未回到商城页")
        sc.shot(f"sweep_fail_back{idx}")
        return False
    log("回商城页，本轮完成 ✓")
    return True


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if not goto_mall(sc):
        return False
    rounds = max(1, args.max) if args.max else 5
    done = 0
    for i in range(1, rounds + 1):
        log(f"--- 轮 {i}/{rounds} ---")
        if not one_round(sc, i):
            break
        done += 1
        if not sc.dry:
            kit.nap(2)
    log(f"完成 {done}/{rounds} 轮")
    return done > 0


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "free_sweep", "商城免费扫荡卡（卡4，最多 5 轮）", run,
        plan=PLAN, prefix="sweep_", lock_ttl=600, default_max=5,
    ))
