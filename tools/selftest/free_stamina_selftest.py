#!/usr/bin/env python
"""离线自检: free_stamina（免费体力）—— 零消耗，不碰游戏窗口。

为什么补这个自检（2026-10-09 实跑暴露）:
    该用例原先用**默认阈值 0.86** 判「体力弹窗在场」。首页右侧轮播区偶尔能让
    `stamina_close` 配到 **0.904**（实测点：12:30:05 收尾点击落在首页 (715,417)）——
    后果有两个：① goto_popup 误判「弹窗已开」而跳过点体力入口；
    ② 收尾 close_popup 在首页盲点一下（可能点到别的入口）。
    修复: 判「弹窗在场」统一走 POPUP_TH=0.95（真弹窗实测 0.998，两档分得开）。

夹具来源:
    * `_fs_home_after_ad.png`    真帧：首页（广告结束后）；2026-10-14 原帧丢失，用
      `_cg_home.png` 复原 → 入口命中点随之从 (32,135) 变为 (44,135)，场景③期望已同步
    * `_fs_popup_exhausted.png` 真帧：体力购买弹窗「免费」额度=0（灰键只匹配 0.73）⚠ 待补
    * `_ts_fs_close_fp.png`     **合成**：上面首页帧 + `stamina_close` 以 alpha0.70
      混入 (715,417)，得到 score≈0.918（≈实测 0.904）→ 复现假阳性，且可复现。
    * `_fs_ad_stuck.png`        真帧：**广告页卡住**（左上「已获得奖励」、无识别得到的关闭键，
      4 个广告标志最高只有 0.41）—— 2026-10-14 用户反馈「没广告了还在等」的现场
    * `_ts_fs_ad_close.png`     **合成**：广告页 + `ad_close`/`ad_rewarded` 混入(alpha 0.92)
      → 先「有广告层」、点一下就变 `_fs_ad_stuck`(关闭键消失) → 用来测早退

本自检覆盖:
    ① 假阳性帧：旧阈值判「在场」/新 popup_open 判「不在场」
    ② 假阳性帧收尾：**零点击**（不再盲点首页）
    ③ 首页正常态：仍会去点体力入口（一次）
    ④ 真弹窗：仍判「在场」（没把阈值抬坏）＋灰键不算「免费」
    ⑤ 次数耗尽全链路：真弹窗 → 「没有免费按钮」→ 点真 X 收尾（恰好 1 次）
    ⑥ 广告层消失即早退：不再空等到 timeout（曾经白等 ~67s，用户反馈）

用法:
    uv run python tools/selftest/free_stamina_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st  # noqa: E402
from tools.cases import free_stamina as fs  # noqa: E402

HOME = "_fs_home_after_ad.png"           # 真帧：首页（广告后）
FP = "_ts_fs_close_fp.png"               # 合成：首页假阳性帧 score≈0.897
POPUP = "_fs_popup_exhausted.png"        # 真帧：弹窗 + 免费额度 0（灰键）
POPUP_CLOSE_XY = (716, 416)              # 真弹窗里 stamina_close 的位置（实测 0.998）
AD_STUCK = "_fs_ad_stuck.png"            # 真帧：广告页卡住（无识别得到的关闭键）
AD_CLOSE_TS = "_ts_fs_ad_close.png"      # 合成：广告页 + ad_close/ad_rewarded（先有层→点掉→无层）


def scene_fp(rp):
    """① 假阳性帧：旧写法(默认 0.86)判在场，新 popup_open 判不在场。"""
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    old = sc.find("stamina_close")                    # 旧写法
    raw = sc.find("stamina_close", th=0.0)
    new = fs.popup_open(sc)
    ok = (old is not None) and (new is False)
    return ok, (f"旧阈值判在场={old is not None}（原始分 {raw[2]:.3f} ≥0.86 = 假阳性）"
                f"→ 新 popup_open={new}（期望 False）")


def scene_fp_noclick(rp):
    """② 假阳性帧收尾：一次都不许点（旧代码会盲点 (715,417)）。"""
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    fs.close_popup(sc)
    clicks = list(rp.real_clicks)
    return not clicks, f"收尾点击={clicks}（期望空）"


def scene_entry(rp):
    """③ 首页正常态：goto_popup 仍会去点体力入口，且只点一次。"""
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    got = fs.goto_popup(sc, 1)
    clicks = list(rp.real_clicks)
    # ⚠ 夹具换成 _cg_home.png 后入口命中点 = (44,135)（旧夹具是 (32,135)，帧已丢）
    ok = (got is False) and clicks == [(44, 135)]     # 夹具里入口点不亮 → 等不到弹窗 → False
    return ok, f"goto_popup={got}（期望 False）点击={clicks}（期望点入口一次）"


def scene_popup(rp):
    """④ 真弹窗：仍判在场；灰色「免费」不算有免费键。"""
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    opened = fs.popup_open(sc)
    free = sc.find("stamina_free")
    return (opened and free is None), (
        f"popup_open={opened}（期望 True）免费键={free}（期望 None，灰键仅 0.73）")


def scene_exhausted_round(rp):
    """⑤ 次数耗尽全链路：真弹窗 → 没有免费按钮 → 点真 X 收尾（恰好 1 次）。

    帧表带一帧 HOME：close_popup 现在带「点了复查, 还开着才补点备用 X」的
    丢点击重试 —— 回放里点 X 翻到 HOME(弹窗已关) → 不得补点。
    """
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    got = fs.one_round(sc, 1)
    clicks = list(rp.real_clicks)
    near = [(x, y) for x, y in clicks
            if abs(x - POPUP_CLOSE_XY[0]) <= 8 and abs(y - POPUP_CLOSE_XY[1]) <= 8]
    # ⚠ 2026-10-14: one_round 返回值由 bool 改成 str('ok'|'exhausted'|'fail')，期望同步
    ok = (got == "exhausted") and len(clicks) == 1 and len(near) == 1
    return ok, f"one_round={got}（期望 exhausted）点击={clicks}（期望仅关闭键 {POPUP_CLOSE_XY}）"


def scene_ad_gone(rp):
    """⑥ 广告层消失后提前收手：不得再空等到 timeout。

    帧表： [合成「有广告层」帧 → 点一下推进 → 真「广告页卡住」帧]
    ⚠ gone_grace 传 0.3（默认 8s）：自检里 now() 走真实时间、sleep 走虚拟，
      用默认值会真等 8 秒；逻辑是同一条分支，只把阈值调小。
    """
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    res = kit.ad_flow(sc, page="stamina_free", timeout=30.0, gone_grace=0.3)
    return res == "gone", f"ad_flow={res}（期望 gone；若 timeout 说明又空等了）"


def _ensure_synth() -> None:
    """合成夹具缺失时自动重建（真帧丢了没救，但**合成**帧不该因丢文件而 SKIP）。

    ⚠ 必须在 st.run() 之前调用（scene 会先查夹具存在性）。
    """
    import cv2
    import numpy as np

    from wb.croplab import SHOTS_DIR, TEMPLATES_DIR

    def blend(base_name: str, out_name: str,
              items: list[tuple[str, int, int, float]]) -> None:
        base = cv2.imread(str(SHOTS_DIR / base_name))
        if base is None:
            return
        out = base.copy()
        for tname, cx, cy, alpha in items:
            tpl = cv2.imread(str(TEMPLATES_DIR / f"{tname}.png"))
            if tpl is None:
                return
            th, tw = tpl.shape[:2]
            x = max(0, min(cx - tw // 2, out.shape[1] - tw))
            y = max(0, min(cy - th // 2, out.shape[0] - th))
            roi = out[y:y + th, x:x + tw].astype(np.float32)
            out[y:y + th, x:x + tw] = (roi * (1 - alpha)
                                       + tpl.astype(np.float32) * alpha).astype(np.uint8)
        cv2.imwrite(str(SHOTS_DIR / out_name), out)
        print(f"[夹具] 已合成 {out_name}（源 {base_name}）")

    if (SHOTS_DIR / HOME).exists() and not (SHOTS_DIR / FP).exists():
        blend(HOME, FP, [("stamina_close", 715, 417, 0.70)])
    if (SHOTS_DIR / AD_STUCK).exists() and not (SHOTS_DIR / AD_CLOSE_TS).exists():
        blend(AD_STUCK, AD_CLOSE_TS, [("ad_close", 700, 129, 0.92),
                                      ("ad_rewarded", 300, 120, 0.92)])


if __name__ == "__main__":
    _ensure_synth()
    raise SystemExit(st.run("free_stamina 离线自检", [
        ("① 首页假阳性帧: 旧判在场/新判不在场", [FP], scene_fp),
        ("② 假阳性帧收尾零点击", [FP], scene_fp_noclick),
        ("③ 首页仍会去点体力入口", [HOME], scene_entry),
        ("④ 真弹窗仍判在场 + 灰键非免费", [POPUP], scene_popup),
        ("⑤ 次数耗尽链路: 点真 X 收尾一次", [POPUP, HOME], scene_exhausted_round),
        ("⑥ 广告层消失即早退(不再空等到超时)", [AD_CLOSE_TS, AD_STUCK], scene_ad_gone),
    ]))
