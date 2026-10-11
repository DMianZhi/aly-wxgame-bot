"""重建扫荡材料计数模板 templates/mdigits/dg0..dg9.png（供 wb/mcount.py 用）。

数据源 = wb/mcount.GOLDEN 里的 5 帧真值条带（参考尺度 814×44）。脚本按
「金色阈值 → 连通域切字形 → 按高度拉伸归一化」，用 4 图标 × 5 帧 = 20 个数
（60 个字形，覆盖 0..9 全部数字）逐个标注，逐数字取**中心字**（medoid，
与同数字其它样本平均相关最高者）作模板，避免取到个别渲染毛刺。

    uv run python tools/maint/build_mcount_digits.py
    uv run python wb/mcount.py --selftest     # 零消耗自证
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from wb.mcount import (GOLDEN, ICON_XS, SHOTS, TPL_DIR,  # noqa: E402
                       _glyph_boxes, _gold_mask, _norm)


def harvest() -> dict[str, list[np.ndarray]]:
    """从真值夹具收割「数字 → 归一化字形列表」。"""
    buckets: dict[str, list[np.ndarray]] = {c: [] for c in "0123456789"}
    for name, truth in GOLDEN:
        p = os.path.join(SHOTS, name)
        band = cv2.imread(p)
        if band is None:
            print(f"  [warn] 缺夹具 {p}，跳过")
            continue
        for xc, num in zip(ICON_XS, truth):
            x0, x1 = max(0, xc - 50), min(band.shape[1], xc + 50)
            mask = _gold_mask(band[:, x0:x1])
            boxes = _glyph_boxes(mask)
            digits = str(num)
            if len(boxes) != len(digits):
                print(f"  [warn] {name} xc={xc} 真值 {num} 切出 {len(boxes)} 个字形，跳过")
                continue
            for (x, y, w, h), ch in zip(boxes, digits):
                buckets[ch].append(_norm(mask[y:y + h, x:x + w]))
    return buckets


def dedupe(items: list[np.ndarray], th: float = 0.98) -> list[np.ndarray]:
    """去掉与已保留样本几乎相同的重复（保留有差异的渲染，压掉冗余）。"""
    kept: list[np.ndarray] = []
    for it in items:
        dup = False
        for k in kept:
            if float(cv2.matchTemplate(it.astype(np.float32), k.astype(np.float32),
                                       cv2.TM_CCOEFF_NORMED).max()) >= th:
                dup = True
                break
        if not dup:
            kept.append(it)
    return kept


def main() -> None:
    import glob
    buckets = harvest()
    os.makedirs(TPL_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(TPL_DIR, "dg*.png")):   # 清掉旧模板（含旧的单模板 dgN.png）
        os.remove(old)
    missing = []
    total = 0
    for ch in "0123456789":
        items = buckets[ch]
        if not items:
            missing.append(ch)
            continue
        kept = dedupe(items)
        for k, tpl in enumerate(kept, 1):
            cv2.imwrite(os.path.join(TPL_DIR, f"dg{ch}_{k}.png"), tpl)
        total += len(kept)
        print(f"  dg{ch}: {len(items):2d} 个样本 → 去重后 {len(kept)} 个模板")
    if missing:
        print(f"[warn] 缺数字模板: {' '.join(missing)}（真值夹具未覆盖）→ 这些数字将读不出")
    print(f"模板写入 {TPL_DIR}（{total} 个，覆盖 {10 - len(missing)}/10 个数字）")


if __name__ == "__main__":
    main()
