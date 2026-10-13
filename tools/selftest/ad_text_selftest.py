#!/usr/bin/env python
"""离线自检: 广告「关闭/已获得奖励」的白色文字识别 —— 换肤免疫。

背景（2026-10-13 病根）: 微信广告浮层每换一个广告皮肤，药丸底色/透出的
背景就变，颜色模板得分跟着漂移 —— 当日皮肤上 ad_rewarded_v3 只剩 0.91~0.92，
低于 TEMPLATE_MIN=0.93 的闸门 → ad_flow 的「两者同时命中才点关闭」永不成立，
广告关不掉（当天十几张 *_unknown 留证帧全是这一种病根）。

修复思路: 识别对象从「按钮」换成「白色字形」。浮层的「关闭」「已获得奖励」
白色文字跨皮肤不变（变的只是药丸底色和背景），二值化后匹配天然免疫换肤。
安全属性在文字层依然成立: 播放中「关闭」二字已经在了（左侧带倒计时数字），
但左药丸没有「已获得奖励」→ 文字闸门照样拦住，不会提前点关闭。

夹具（真帧，缺了 → SKIP，与其他自检同策略）:
    * _rec_ad_endcard.png   —— 2026-10-13 实测到账帧（当日失效皮肤，835x1516）
    * _run/_ad_state.png 等 —— 2026-10-11 实跑到账/播放帧（818x1507）

覆盖:
    ① 到账帧: ad_flow 走文字路径点掉关闭（回归 0.91~0.92 被 0.93 闸死的确切病根）
    ② 播放帧: 零点击（安全属性: 文字闸门拦住播放中的「关闭」）
    ③ 阈值余量审计: TEXT_MATCH 闸门必须落在正/负样本分数之间，两侧余量 ≥0.02

用法:
    uv run python tools/selftest/ad_text_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import kit, selftest_kit as st  # noqa: E402
from wb.bot import TEXT_MATCH, _bin_glyph, match_adaptive  # noqa: E402
from wb.cfg import SHOTS_DIR, TEMPLATE_PATH  # noqa: E402

ENDCARD = "_rec_ad_endcard.png"          # 实测到账帧（2026-10-13 失效皮肤）
GONE = "_run/_ad_gone.png"               # 广告已关（负样本）
STATE = "_run/_ad_state.png"             # 到账帧（旧皮肤）
S11 = "_run/_adstart_11.png"             # 到账帧（旧皮肤）
PLAY0 = "_run/_adstart_0.png"            # 播放中（关闭带倒计时 → 不可点）
PLAY5 = "_run/_adstart_5.png"            # 播放中
PLAY10 = "_run/_adstart_10.png"          # 播放中（白屏闪帧）

ENDCARDS = [ENDCARD, STATE, S11]
PLAYS = [PLAY0, PLAY5, PLAY10]


def _text_score(frame: str, name: str) -> float:
    """文字路径打分（不管闸门，取原始最高分，供余量审计）。"""
    img = cv2.imread(str(SHOTS_DIR / frame))
    tpl = cv2.imread(str(TEMPLATE_PATH(f"{name}_txt")))
    hit = match_adaptive(img, tpl, 0.0, pre=_bin_glyph)
    return 0.0 if hit is None else hit[2]


def case_endcard(rp):
    """① 到账帧: 广告被文字路径点掉（恰好 1 次，位置在右上药丸内）。"""
    ok = kit.ad_flow(kit.Screen(st.RECT, dry=False), page="ad_rewarded",
                     timeout=6.0, interval=2.0)
    clicks = rp.real_clicks
    good = (len(clicks) == 1 and 730 <= clicks[0][0] <= 820
            and 100 <= clicks[0][1] <= 160)
    if not good:
        print(f"[!!] 到账帧点击异常: {clicks} (期望恰好 1 次且落在右上药丸)")
    return good, f"ad_flow={ok} 点击={clicks}"


def case_playing(rp):
    """② 播放帧: 全程零点击（「已获得奖励」文字闸门拦住）。"""
    kit.ad_flow(kit.Screen(st.RECT, dry=False), page="ad_rewarded",
                timeout=3.0, interval=2.0)
    return st.no_click_on("广告播放期", rp, PLAY0), f"点击={rp.real_clicks}"


def case_margin(rp):
    """③ 阈值余量审计: 闸门两侧余量 ≥0.02，防止后人随手调参调穿。"""
    bad = []
    for name, gate in TEXT_MATCH.items():
        pos = [_text_score(f, name) for f in ENDCARDS]
        neg = [_text_score(f, name) for f in PLAYS]
        lo, hi = min(pos), max(neg)
        line = f"{name}: 闸门={gate} 到账最低={lo:.3f} 播放最高={hi:.3f}"
        print(f"  [{ 'ok  ' if lo - gate >= 0.02 and gate - hi >= 0.02 else '!!  ' }] {line}")
        if lo - gate < 0.02 or gate - hi < 0.02:
            bad.append(name)
    return not bad, f"异常闸门: {bad or '无'}"


SCENES = [
    ("到账帧走文字路径点掉广告", [ENDCARD, GONE], case_endcard),
    ("播放帧零点击(文字闸门)", [PLAY0], case_playing),
    ("TEXT_MATCH 闸门余量审计", ENDCARDS + PLAYS, case_margin),
]

if __name__ == "__main__":
    st.run_one("广告文字识别（换肤免疫）离线自检", SCENES)
