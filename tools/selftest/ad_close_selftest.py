#!/usr/bin/env python
"""离线自检: 广告页兜底关闭 + 收尾自愈（2026-10-14 病根回归）。

病根（真跑实测，用户口径 + 留证帧双证）:
    微信广告**每次换背景图**，而「已获得奖励」在**部分皮肤上压根不出现**。
    free_stamina 旧逻辑把它当唯一出口 → 傻等 55s、判定失败、**从不点「关闭」**
    → 卡在广告页（既不是首页、也没有游戏返回键）→ goto_home「找不到返回键，停手」
    → **后面 2~5 号用例全报「找不到商城入口/不在首页」，一个广告连坐一整轮**。

关键事实（真帧实测）:
    * 「关闭」文字**播放中就已经在**（_run/_adstart_10.png: ad_close=0.98），
      变的只是背景图 → 文字层匹配（TEXT_MATCH 0.86）跨皮肤可用 → 应当以它为准。
    * 「已获得奖励」只在播完后出现、且**有的皮肤不显示** → 只能当「提前知道播完」
      的加分项（_adstart_10 播放中 = None / _ad_state 播完 = 0.9137）。

覆盖:
    ① 广告播完页   → close_ad_page 点「关闭」(且点击落在顶部浮层)
    ② 播放中页     → 同样能关（「关闭」一直都在）且**只点浮层**、不碰广告内容
    ③ 首页帧       → **零点击**（安全属性: 不能把首页元素误当广告）
    ④ goto_home 遇广告页 → 先关广告页、再回首页（防「连坐一整轮」的回归）
    ⑤ 纯广告页     → 必须点「关闭」而不是直接「停手」（旧行为就是停手）
    ⑥ 「恭喜获得」结算页 → 点「领取」（漏了这步同样卡死: 该页没返回键）
    ⑦ goto_home 遇结算页 → 先领取、再回首页

夹具（真帧；缺了 → SKIP）:
    _fs_fs_timeout2.png        2026-10-14 真跑留证（广告播完待关闭, 833x1515）
    _run/_adstart_10.png       2026-10-11 实跑广告播放中帧（818x1507）
    _run/_ad_state.png         2026-10-11 实跑广告播完帧（另一皮肤）
    _csstest_pill_ok_home.png  首页真帧（非广告页）
    _adclaim_get.png         「恭喜获得(扫荡卡×3)」结算页（2026-10-14 真帧，
                             关掉广告页后就会出现；点「领取」后 stamina_entry 0.973 回首页）

用法:
    uv run python tools/selftest/ad_close_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st  # noqa: E402

AD_DONE = "_fs_fs_timeout2.png"        # 广告播完待关闭（今日真跑留证）
AD_PLAY = "_run/_adstart_10.png"       # 广告播放中（当日皮肤）
AD_DONE2 = "_run/_ad_state.png"        # 广告播完（旧皮肤）
HOME = "_csstest_pill_ok_home.png"     # 首页（非广告）
AD_CLAIM = "_adclaim_get.png"          # 「恭喜获得」结算页（广告页关掉之后的下一层）
FLOAT_Y = 260                          # 顶部广告浮层下界（真实浮层在基准 y≈100~170）


def _all_in_float(rp) -> tuple[bool, str]:
    """所有点击都落在顶部浮层（y 小）—— 保证不会点到广告正文（「立即体验」）。"""
    bad = [(x, y) for x, y, _ in rp.events if y > FLOAT_Y]
    return (not bad), f"浮层点击={len(rp.events) - len(bad)} 越界={bad[:3]}"


def scene_close_done(rp):
    """① 广告播完页 → 点「关闭」。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    got = kit.close_ad_page(sc, settle=0.0)
    lay, note = _all_in_float(rp)
    ok = got and len(rp.events) == 1 and lay
    return ok, f"close_ad_page={got} 事件={rp.events} {note}"


def scene_close_done2(rp):
    """①b 另一皮肤的播完页 → 也要能关（跨皮肤）。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    got = kit.close_ad_page(sc, settle=0.0)
    lay, note = _all_in_float(rp)
    ok = got and len(rp.events) == 1 and lay
    return ok, f"close_ad_page={got} {note}（另一皮肤）"


def scene_close_playing(rp):
    """② 播放中页 → 也必须能关，且只点浮层（不碰广告内容）。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    got = kit.close_ad_page(sc, settle=0.0)
    lay, note = _all_in_float(rp)
    ok = got and len(rp.events) == 1 and lay
    return ok, f"close_ad_page={got} 事件={rp.events} {note}（「关闭」播放中就在）"


def scene_home_noop(rp):
    """③ 首页帧 → 零点击（不能把首页元素误当广告关）。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    got = kit.close_ad_page(sc, settle=0.0)
    ok = (not got) and len(rp.events) == 0
    return ok, f"close_ad_page={got} 点击={len(rp.events)}（期望 False / 0 次）"


def scene_goto_home_recovers(rp):
    """④ goto_home 遇广告页: 先关广告页、再回首页（不是「停手」）。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    ok = kit.goto_home(sc)
    lay, note = _all_in_float(rp)
    good = ok and len(rp.events) >= 1 and lay
    return good, f"goto_home={ok} 点击={len(rp.events)} {note}（期望 True 且先关广告页）"


def scene_goto_home_not_stuck(rp):
    """⑤ 一直停在广告页 → 必须点「关闭」，而不是直接「找不到返回键，停手」。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    ok = kit.goto_home(sc)
    lay, note = _all_in_float(rp)
    good = (not ok) and len(rp.events) >= 1 and lay
    return good, f"goto_home={ok}(期望 False: 广告页永远回不去) 点击={len(rp.events)} {note}"


def scene_claim_settle(rp):
    """⑥「恭喜获得」结算页 → 点「领取」（不领也是死路: 该页无返回键）。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    got = kit.claim_if_present(sc)
    ok = got and len(rp.events) == 1
    return ok, f"claim_if_present={got} 事件={rp.events}"


def scene_goto_home_claim(rp):
    """⑦ goto_home 遇结算页 → 先领取、再回首页（旧行为: 直接停手）。"""
    sc = kit.open_screen(th=0.86, prefix="_adc_self")
    ok = kit.goto_home(sc)
    good = ok and len(rp.events) >= 1
    return good, f"goto_home={ok} 点击={len(rp.events)}（期望 True 且先点领取）"


if __name__ == "__main__":
    st.run_one("广告页兜底关闭 + 收尾自愈自检", [
        ("① 播完页 → 点「关闭」(今日皮肤)", [AD_DONE], scene_close_done),
        ("①b 播完页 → 点「关闭」(旧皮肤)", [AD_DONE2], scene_close_done2),
        ("② 播放中页 → 也能关且只点浮层", [AD_PLAY], scene_close_playing),
        ("③ 首页帧 → 零点击", [HOME], scene_home_noop),
        ("④ goto_home 遇广告页 → 自愈回首页", [AD_DONE, HOME], scene_goto_home_recovers),
        ("⑤ 纯广告页 → 点关闭, 不「停手」", [AD_DONE], scene_goto_home_not_stuck),
        ("⑥「恭喜获得」页 → 点「领取」", [AD_CLAIM], scene_claim_settle),
        ("⑦ goto_home 遇结算页 → 自愈回首页", [AD_CLAIM, HOME], scene_goto_home_claim),
    ])
