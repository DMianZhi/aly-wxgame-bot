#!/usr/bin/env python
"""离线自检: free_stamina（免费体力）—— 零消耗，不碰游戏窗口。

为什么补这个自检（2026-10-09 实跑暴露）:
    该用例原先用**默认阈值 0.86** 判「体力弹窗在场」。首页右侧轮播区偶尔能让
    `stamina_close` 配到 **0.904**（实测点：12:30:05 收尾点击落在首页 (715,417)）——
    后果有两个：① goto_popup 误判「弹窗已开」而跳过点体力入口；
    ② 收尾 close_popup 在首页盲点一下（可能点到别的入口）。
    修复: 判「弹窗在场」统一走 POPUP_TH=0.95（真弹窗实测 0.998，两档分得开）。

夹具来源:
    * `_fs_home_after_ad.png`   真帧：广告结束后回到首页（当天实跑留证帧）
    * `_fs_popup_exhausted.png` 真帧：体质购买弹窗「免费」额度=0（灰键只匹配 0.73）
    * `_ts_fs_close_fp.png`     **合成**：上面首页帧 + `stamina_close` 以 alpha0.70
      混入 (715,417)，得到 score≈0.897（≈实测 0.904）→ 复现假阳性，且可复现。

本自检覆盖:
    ① 假阳性帧：旧阈值判「在场」/新 popup_open 判「不在场」
    ② 假阳性帧收尾：**零点击**（不再盲点首页）
    ③ 首页正常态：仍会去点体力入口（一次）
    ④ 真弹窗：仍判「在场」（没把阈值抬坏）＋灰键不算「免费」
    ⑤ 次数耗尽全链路：真弹窗 → 「没有免费按钮」→ 点真 X 收尾（恰好 1 次）

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
    ok = (got is False) and clicks == [(32, 135)]     # 夹具里入口点不亮 → 等不到弹窗 → False
    return ok, f"goto_popup={got}（期望 False）点击={clicks}（期望点入口一次）"


def scene_popup(rp):
    """④ 真弹窗：仍判在场；灰色「免费」不算有免费键。"""
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    opened = fs.popup_open(sc)
    free = sc.find("stamina_free")
    return (opened and free is None), (
        f"popup_open={opened}（期望 True）免费键={free}（期望 None，灰键仅 0.73）")


def scene_exhausted_round(rp):
    """⑤ 次数耗尽全链路：真弹窗 → 没有免费按钮 → 点真 X 收尾（恰好 1 次）。"""
    sc = kit.open_screen(th=0.86, prefix="_fs_self")
    got = fs.one_round(sc, 1)
    clicks = list(rp.real_clicks)
    near = [(x, y) for x, y in clicks
            if abs(x - POPUP_CLOSE_XY[0]) <= 8 and abs(y - POPUP_CLOSE_XY[1]) <= 8]
    ok = (got is False) and len(clicks) == 1 and len(near) == 1
    return ok, f"one_round={got}（期望 False）点击={clicks}（期望仅关闭键 {POPUP_CLOSE_XY}）"


if __name__ == "__main__":
    raise SystemExit(st.run("free_stamina 离线自检", [
        ("① 首页假阳性帧: 旧判在场/新判不在场", [FP], scene_fp),
        ("② 假阳性帧收尾零点击", [FP], scene_fp_noclick),
        ("③ 首页仍会去点体力入口", [HOME], scene_entry),
        ("④ 真弹窗仍判在场 + 灰键非免费", [POPUP], scene_popup),
        ("⑤ 次数耗尽链路: 点真 X 收尾一次", [POPUP], scene_exhausted_round),
    ]))
