"""裁剪「超限 125%」模板(hyper_125) —— boss_hyper 的**出击前提**判据。

⚠ 2026-10-15 重裁原因（用户反馈"明明没有超限 125% 为什么出击"→ 实为反例）:
   旧模板在真帧(818x1507)上只有 **0.7044**（裁自旧版/缩放帧）→ **明明显示 125%
   却判否** → "经常判断错误不出击"。重裁后正验 1.000。

判据口径（用户要求，2026-10-15 恢复）: 抗性面板必须显示「超限 125%」才出击。

用法:
    uv run python tools/crop/crop_hyper125.py                # 裁剪 + 双验证
    uv run python tools/crop/crop_hyper125.py --dry          # 只验证不写文件

源帧: shots/probe_hyper_detail.png
    · 「破晓雷神」详情页, 右侧抗性面板 = 普通 125% / **超限 125%**（该出击的样本）
    · 目标行 bbox (629,624,793,654)（老模板命中中心 (710,639) 附近）
⚠ shots/ 不入库: 缺源帧时本工具会提示，模板仍可直接用（已验证过）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from wb import bot  # noqa: E402

SRC = ROOT / "shots" / "probe_hyper_detail.png"
DST = ROOT / "templates" / "hyper_125.png"
# 目标行 bbox（源帧坐标）: 「超限 125%」整行（含"超限"标签，用于与「普通 125%」区分）
BBOX = (629, 624, 793, 654)
TH = 0.93            # 与 boss_hyper.NUKE_125_TH 一致


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只验证，不写模板")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"[skip] 源帧缺失（shots/ 不入库）: {SRC.relative_to(ROOT)}")
        print("       模板已存在则无需重裁；要重裁请先跑 tools/maint/probe_live.py 抓帧。")
        return 0

    img = cv2.imread(str(SRC))
    x0, y0, x1, y1 = BBOX
    tpl = img[y0:y1, x0:x1]
    print(f"裁剪 {tpl.shape[1]}x{tpl.shape[0]}  bbox=({x0},{y0},{x1},{y1})")

    # ---- 正验: 必须在源帧命中（旧模板此处仅 0.7044）----
    hit = bot.match_adaptive(img, tpl, 0.5)
    ok_pos = hit is not None and hit[2] >= TH
    print(f"正验 源帧(超限125%) : {hit}  → {'PASS' if ok_pos else 'FAIL'}")

    # ---- 反验1: 相邻「普通 125%」行不得以 ≥TH 命中 ----
    strip = img[585:622, 620:800]
    r1 = bot.match_adaptive(strip, tpl, 0.3)
    ok1 = r1 is None or r1[2] < TH
    print(f"反验 普通125%行      : {r1}  → {'PASS' if ok1 else 'FAIL'}")

    # ---- 反验2: 无关页面不得命中 ----
    ok2 = True
    for name in ("_dbg_before_home.png",):
        p = ROOT / "shots" / name
        if not p.exists():
            continue
        im2 = cv2.imread(str(p))
        r2 = bot.match_adaptive(im2, tpl, 0.3)
        ok2 = ok2 and (r2 is None or r2[2] < TH)
        print(f"反验 {name:18s}: {r2}  → {'PASS' if ok2 else 'FAIL'}")

    if not (ok_pos and ok1 and ok2):
        print("\n[FAIL] 验证未通过 → 不写模板（阈值/bbox 需调整）")
        return 1
    if args.dry:
        print("\n[dry] 验证通过，未写文件")
        return 0
    cv2.imwrite(str(DST), tpl)
    print(f"\n[ok] 已写 {DST.relative_to(ROOT)}（阈值 TH={TH}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
