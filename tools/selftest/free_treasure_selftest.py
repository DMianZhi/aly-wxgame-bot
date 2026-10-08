#!/usr/bin/env python
"""离线自检: free_treasure（寻宝双宝箱）—— 零消耗，不碰游戏窗口。

夹具来源（重要，别当成全真实帧）:
    * 底帧 `_rec_treasure_page.png` 是**当天实测帧**（含 treasure_help + 两个免费 icon）。
    * 广告/恭喜获得那几帧是**合成的**: 底帧涂黑 = 广告全屏盖住；把 templates/ 里的
      ad_close / ad_rewarded / claim_btn **贴到实测帧上**得到对应状态。
      为什么合成: 广告播放期我们从没抓过图（那正是最危险、绝不乱点的时刻），
      而本自检要验的恰是**分支与护栏**（广告中不点、领取后判 icon 消失），不是模板质量。

本自检覆盖:
    ① 广告播放期**零点击**（关键安全属性）
    ② 广告播完(≥0.93)才关广告 → 领取 → 以「免费 icon 消失」为成功判据
    ③ 两宝箱按 x 升序逐个消费，已消费的不重复点
    ④ dry 零点击零写盘；⑤ 并发锁互斥

时间驱动: 广告「播完」不靠点击推进 → 用 holds={1: 12.0} 让该帧停 12 虚拟秒后自动切下一帧。

用法:
    uv run python tools/selftest/free_treasure_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.bot import _template_variants, match_adaptive  # noqa: E402
from wb.cfg import SHOTS_DIR, TEMPLATE_PATH  # noqa: E402
from tools.cases import free_treasure as ft  # noqa: E402

BASE = "_rec_treasure_page.png"
PAGE2 = BASE                       # 两个免费 icon 都在（实测帧直接用）
LEFT_DONE = "_ts_treasure_left_done.png"     # 左卡已领（合成: 涂掉左 icon）
BOTH_DONE = "_ts_treasure_both_done.png"     # 两卡都领完（合成）
AD_PLAY = "_ts_ad_playing.png"               # 广告播放中（合成: 全屏盖住，无按钮）
AD_DONE = "_ts_ad_done.png"                  # 广告播完（合成: 盖住 + 已获得奖励 + 关闭）
CLAIM_L = "_ts_claim_left.png"               # 恭喜获得（合成: 左 icon 已消 + 领取键）
CLAIM_R = "_ts_claim_right.png"              # 恭喜获得（合成: 两 icon 全消 + 领取键）

CLAIM_XY = (416, 1288)      # claim_btn 在实测帧里的位置（同 rally/turn/guild 各页）
ICON_HALF = 62              # 免费 icon 的抹除半径


def _multihit(img, name: str, th: float, max_hits: int = 4):
    """在一张数组上做多命中匹配（与 kit.Screen.find_all 同算法）。"""
    tpl = _template_variants(name)[0]
    r = int(max(tpl.shape[:2]) * 0.8)
    canvas = img.copy()
    out = []
    for _ in range(max_hits):
        h = match_adaptive(canvas, tpl, th)
        if h is None:
            break
        out.append(h)
        cv2.rectangle(canvas, (h[0] - r, h[1] - r), (h[0] + r, h[1] + r), (0, 0, 0), -1)
    return sorted(out, key=lambda x: x[0])


def _erase(img, cx: int, cy: int, half: int = ICON_HALF) -> None:
    """用四周中位色盖掉一块（模拟「icon 因已领取而消失」）。"""
    x0, x1 = max(0, cx - half), min(img.shape[1], cx + half)
    y0, y1 = max(0, cy - half), min(img.shape[0], cy + half)
    ring = np.concatenate([img[max(0, y0 - 24):y0, x0:x1].reshape(-1, 3),
                           img[y1:y1 + 24, x0:x1].reshape(-1, 3)])
    img[y0:y1, x0:x1] = np.median(ring, axis=0).astype(np.uint8)


FIX: dict = {}  # 合成夹具的实际元素位置（安装时填入）


def _paste(img, tpl_name: str, *, left: int = 30, top: int = 210,
           right: int | None = None) -> tuple[int, int]:
    """把 templates/<tpl_name>.png 贴到图上（自动夹紧到画面内），返回实际中心。"""
    t = cv2.imread(str(TEMPLATE_PATH(tpl_name)))
    h, w = t.shape[:2]
    x0 = (img.shape[1] - w - left) if right is not None else left
    x0 = max(0, min(x0, img.shape[1] - w))
    y0 = max(0, min(top, img.shape[0] - h))
    img[y0:y0 + h, x0:x0 + w] = t
    return x0 + w // 2, y0 + h // 2


def ensure_fixtures() -> bool:
    """按需生成合成夹具，并自检生成结果（生成不对就直接暴露）。"""
    if not (SHOTS_DIR / BASE).is_file():
        return False
    base = cv2.imread(str(SHOTS_DIR / BASE))
    icons = _multihit(base, "treasure_free", ft.TH_ICON)
    if len(icons) != 2:
        print(f"[!!] 底帧 {BASE} 上应有两个免费 icon，实测 {len(icons)} 个")
        return False
    (lx, ly), (rx, ry) = icons[0][:2], icons[1][:2]

    left_done = base.copy()
    _erase(left_done, lx, ly)
    both_done = left_done.copy()
    _erase(both_done, rx, ry)
    claim_l = left_done.copy()
    FIX["claim"] = _paste(claim_l, "claim_btn", left=CLAIM_XY[0] - 60,
                          top=CLAIM_XY[1] - 30)
    claim_r = both_done.copy()
    _paste(claim_r, "claim_btn", left=CLAIM_XY[0] - 60, top=CLAIM_XY[1] - 30)
    ad_play = np.full_like(base, 16)                       # 广告全屏盖住，且没有关闭键
    ad_done = ad_play.copy()
    _paste(ad_done, "ad_rewarded", left=30, top=210)        # 左上「已获得奖励」
    FIX["ad_close"] = _paste(ad_done, "ad_close", left=40, top=210, right=40)

    for name, img in [(LEFT_DONE, left_done), (BOTH_DONE, both_done),
                      (AD_PLAY, ad_play), (AD_DONE, ad_done),
                      (CLAIM_L, claim_l), (CLAIM_R, claim_r)]:
        cv2.imwrite(str(SHOTS_DIR / name), img)

    # 生成结果自检（夹具不对 → 后面用例会误判）
    checks = [
        ("左已领帧剩 1 个 icon", len(_multihit(left_done, "treasure_free", ft.TH_ICON)) == 1),
        ("全领完帧剩 0 个 icon", len(_multihit(both_done, "treasure_free", ft.TH_ICON)) == 0),
        ("广告中帧无页面标志", _multihit(ad_play, "treasure_help", ft.TH)[:1] == []),
        ("广告中帧检不到关闭键", _multihit(ad_play, "ad_close", 0.85)[:1] == []),
        ("广告完帧有已获得奖励", bool(_multihit(ad_done, "ad_rewarded", ft.TH_REWARDED))),
        ("广告完帧有关闭键", bool(_multihit(ad_done, "ad_close", 0.85))),
        ("恭喜帧有领取键", bool(_multihit(claim_l, "claim_btn", 0.92))),
        ("恭喜帧左 icon 已消", not [h for h in _multihit(claim_l, "treasure_free", ft.TH_ICON)
                                 if abs(h[0] - lx) < 40]),
    ]
    bad = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  [{'ok  ' if ok else '!!  '}] 夹具 {n}")
    return not bad


ARGS1 = kit.Args(max=1)
ARGS2 = kit.Args(max=2)


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=ft.TH, dry=dry, prefix="treasure_")


def case_one_chest(rp):
    """一个宝箱: 广告中零点击 → 播完才关 → 领取 → icon 消失判据。"""
    ok = ft.run(_sc(), ARGS1)
    clicks_ok = st.check_clicks("单宝箱", rp.real_clicks,
                               [(93, 1247), FIX["ad_close"], FIX["claim"]], tol=8)
    safe = st.no_click_on("广告播放期", rp, AD_PLAY)
    return ok and clicks_ok and safe, f"run={ok} 点击={rp.real_clicks}"


def case_two_chests(rp):
    """两个宝箱: 按 x 升序逐个消费，已消费的不重复点。"""
    ok = ft.run(_sc(), ARGS2)
    clicks_ok = st.check_clicks(
        "双宝箱", rp.real_clicks,
        [(93, 1247), FIX["ad_close"], FIX["claim"],
         (484, 1246), FIX["ad_close"], FIX["claim"]], tol=8)
    return ok and clicks_ok, f"run={ok} 点击={rp.real_clicks}"


def case_dry(rp):
    """dry: 零点击零写盘。"""
    ok = ft.run(_sc(dry=True), ARGS2)
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(rp):
    name = "free_treasure_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


SCENES = [
    ("单宝箱(广告中零点击 → 播完关 → 领取)", [PAGE2, AD_PLAY, AD_DONE, CLAIM_L, LEFT_DONE], case_one_chest),
    ("双宝箱(按 x 升序消费)", [PAGE2, AD_PLAY, AD_DONE, CLAIM_L, LEFT_DONE,
                          AD_PLAY, AD_DONE, CLAIM_R, BOTH_DONE], case_two_chests),
    ("dry 零点击零写盘", [PAGE2], case_dry),
    ("并发锁互斥", [PAGE2], case_lock),
]

HOLDS = {1: 12.0, 5: 12.0}      # 广告帧 1 / 5 各停 12 虚拟秒 = 「广告播完」

if __name__ == "__main__":
    print("=== 夹具准备 ===")
    if not ensure_fixtures():
        print("[SKIP] 缺底帧或合成失败 —— 请确认 shots/_rec_treasure_page.png 存在")
        raise SystemExit(0)
    st.run_one("free_treasure 离线自检（点击+时间双驱动回放）", SCENES, holds=HOLDS)
