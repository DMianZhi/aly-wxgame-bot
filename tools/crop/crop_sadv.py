#!/usr/bin/env python
"""用例: 「经验过多」提示条模板裁剪 + **反验证**(2026-10-14 事故后新增)。

用法:
    uv run python tools/crop/crop_sadv.py
产出:
    templates/exp_over_text.png   「经验过多」提示条**第一行固定文案**
    shots/sadv_expover_crops.csv / sadv_expover_crops_montage.png

背景(为什么单独一个工具、且**必须**反验证):
    旧的 exp_over_text.png 把提示条上的**蓝色「调整材料」按钮**当成了提示条文字裁下来；
    而那颗键与「确认快速进阶所选装备到极限?」确认框里的蓝色「取消」几乎同形 →
    在确认框上 0.9304 ≥ 0.90 命中 → 用例在**第一个确认框就提前结束**(用户反馈的真因)。
    所以本工具除正验证(源帧命中)外，**必须**在确认框帧上反验证(不得命中)。

⚠ 只裁**第一行**「本次进阶经验已超过进阶所需的经验，」——
    第二行含会变的「溢出N」数字, 裁进去会因数字变化而失配。
⚠ 提示条上两颗键: 左=蓝「调整材料」(取消, 安全) / 右=绿「继续进阶」(⛔确认消耗溢出经验)。
    用例 _dismiss_exp_over 只点左键, 落点 = 模板命中中心 + EXP_OVER_ADJ_DXY。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from tools.cases import s_advance as sa  # noqa: E402
from wb.croplab import SHOTS_DIR, TEMPLATES_DIR, _match_one, run_crop  # noqa: E402

BAR = "_sadv_exp_over_bar.png"        # 提示条真身(用户提供, 835x1509)
NEG = ["_sadv_dialog_continue.png",   # 「继续进阶」二次确认框(旧模板误命中处)
       "_diag_now.png"]               # 同款确认框(另一帧)

# (x, y, w, h) —— 835x1509 实测帧坐标
EXP_OVER = (149, 706, 519, 36)        # 提示条第一行固定文案
BTN_ADJ = (147, 873, 234, 67)         # 左: 蓝「调整材料」(仅落点核验, 不裁模板)
NEG_LIMIT = 0.70


def main() -> int:
    weak = run_crop(
        {"exp_over_text": (*EXP_OVER, "「经验过多」提示条第一行固定文案")},
        tag="sadv_expover", shot=BAR,
    )
    print(f"--- 正/反验证 (阈值 {sa.TH_EXPOVER:.2f}) ---")
    bad = 0
    for shot in [BAR] + NEG:
        img = cv2.imread(str(SHOTS_DIR / shot))
        if img is None:
            print(f"[skip] {shot} 不存在")
            continue
        score, cx, cy = _match_one(img, TEMPLATES_DIR / "exp_over_text.png")
        want = shot == BAR
        ok = (score >= sa.TH_EXPOVER) if want else (score <= NEG_LIMIT)
        bad += 0 if ok else 1
        kind = "正验(须命中)" if want else "反验(须不命中)"
        print(f"[{'ok  ' if ok else '!!  '}] {shot:32s} {score:.4f} "
              f"center=({cx},{cy}) {kind}")
        if want and score >= sa.TH_EXPOVER:
            dx, dy = sa.EXP_OVER_ADJ_DXY
            px, py = cx + dx, cy + dy
            x, y, w, h = BTN_ADJ
            inb = x <= px <= x + w and y <= py <= y + h
            bad += 0 if inb else 1
            print(f"      _dismiss 落点=({px},{py}) 蓝键bbox=({x},{y},{w},{h}) "
                  f"→ 命中蓝键? {inb}")
    print(f"=== 薄弱模板 {weak} / 验证失败 {bad} ===")
    print(f"OUTPUT={TEMPLATES_DIR / 'exp_over_text.png'}")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
