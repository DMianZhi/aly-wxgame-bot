#!/usr/bin/env python
"""用例: 「暂未获得奖励」确认框的「放弃」键模板裁剪 + **反验证**（2026-10-15 卡死事故后新增）。

用法:
    uv run python tools/crop/crop_adgiveup.py
产出:
    templates/ad_giveup.png       「暂未获得奖励 / 是否继续观看视频」确认框左格「放弃」
    shots/ad_giveup_crops.csv / ad_giveup_crops_montage.png

背景(事故):
    广告没满 20s 就点右上「关闭」→ 微信弹**模态**确认框「暂未获得奖励 / 是否继续观看视频」
    盖住广告页；此时再点「关闭」永远无效 —— free_explore 实测 goto_home 连点 13 次、
    卡死 83.8s（用户截图: 「案例卡死了」）。必须点左格「放弃」才能退出。

⚠ 弹窗底部两格: 左=「放弃」(安全, 退出广告) / 右=「继续」(⛔ 接着看视频, 绝不点)。
    本工具除正验证(源帧命中)外，**必须**在无弹窗帧上反验证(不得命中)；
    并要求命中中心落在弹窗**左格**(x < 431)，防止以后重裁时错裁到「继续」。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import kit  # noqa: E402
from wb.croplab import SHOTS_DIR, TEMPLATES_DIR, _match_one, run_crop  # noqa: E402

SRC = "_diag_explore_stuck.png"       # 真帧(834x1507): 广告页 + 该确认框
NEG = ["_fs_ad_stuck.png",            # 广告页(关闭键识别不到), 无确认框
       "_fs_home_after_ad.png"]       # 首页

# (x, y, w, h) —— 834x1507 实测帧坐标（紧裁「放弃」两字 + 6px 白边）
GIVEUP = (264, 851, 70, 40)
DIALOG_MID_X = 431                    # 弹窗竖直中线: 「放弃」必须在它左边
NEG_LIMIT = 0.70


def main() -> int:
    weak = run_crop(
        {"ad_giveup": (*GIVEUP, "「暂未获得奖励/是否继续观看视频」确认框左格「放弃」")},
        tag="ad_giveup", shot=SRC,
    )
    print(f"--- 正/反验证 (阈值 {kit.TH:.2f}) ---")
    bad = 0
    for shot in [SRC] + NEG:
        img = cv2.imread(str(SHOTS_DIR / shot))
        if img is None:
            print(f"[skip] {shot} 不存在")
            continue
        score, cx, cy = _match_one(img, TEMPLATES_DIR / "ad_giveup.png")
        want = shot == SRC
        ok = (score >= kit.TH) if want else (score <= NEG_LIMIT)
        bad += 0 if ok else 1
        kind = "正验(须命中)" if want else "反验(须不命中)"
        print(f"[{'ok  ' if ok else '!!  '}] {shot:26s} {score:.4f} "
              f"center=({cx},{cy}) {kind}")
        if want and score >= kit.TH:
            inleft = cx < DIALOG_MID_X
            bad += 0 if inleft else 1
            print(f"      命中在弹窗左格? {inleft}（x={cx} < 中线 {DIALOG_MID_X}；"
                  f"右格是「继续」，点了=接着看视频）")
    print(f"=== 薄弱模板 {weak} / 验证失败 {bad} ===")
    print(f"OUTPUT={TEMPLATES_DIR / 'ad_giveup.png'}")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
