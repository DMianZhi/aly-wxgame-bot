"""重建战内得分数字模板 templates/bdigits/dg0..dg9.png（供 wb.bscore 读数用）。

源: 战内真帧（顶部中央「得分 NNNNNNN」）+ 已知真值。按定间距切格取字形，
归一化后按数字平均（多个样本取均值降噪）。

默认用仓库里两帧已知真值的战内帧:
    uv run python tools/maint/build_bscore_digits.py
换新帧重建:
    uv run python tools/maint/build_bscore_digits.py --add shots/xxx.png=5012345

⚠ 目前源数据只覆盖 {0,1,2,3,4,6,9}, 缺 {5,7,8}（见 wb/bscore 模块 docstring）。
  补齐要再截一帧「得分里含 5/7/8」的战内帧；**不要**拿别的场景的字形凑数。

跑完零消耗自证: uv run python wb/bscore.py --selftest
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from wb.bscore import REF_H, TPL_DIR, _band, _glyphs, _norm

SRC = [("shots/bscore_4092602.png", 4092602),
       ("shots/bscore_3263612.png", 3263612)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", action="append", default=[],
                    help="追加源帧, 形如 shots/xxx.png=5012345（可多次）")
    ap.add_argument("--dry", action="store_true", help="只看切分结果, 不写模板")
    a = ap.parse_args()

    srcs = list(SRC)
    for spec in a.add:
        fp, _, tv = spec.partition("=")
        srcs.append((fp, int(tv)))

    acc: dict[str, list[np.ndarray]] = {}
    for rel, truth in srcs:
        fp = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        f = cv2.imread(fp)
        if f is None:
            print(f"  [!] 读不到 {rel} → 跳过")
            continue
        k = f.shape[0] / REF_H
        gs = [g for g in _glyphs(_band(f, k), k) if g is not None]
        tstr = str(truth)
        if len(gs) != len(tstr):
            print(f"  [!] {rel} 切出 {len(gs)} 格 ≠ 真值 {len(tstr)} 位 → 跳过")
            continue
        got = []
        for g, ch in zip(gs, tstr):
            acc.setdefault(ch, []).append(_norm(g))
            got.append(ch)
        print(f"  {rel} 真值{truth} 切{len(gs)}格 → {''.join(got)}")

    print(f"共 {len(acc)} 个数字 ({''.join(sorted(acc))}), "
          f"缺: {''.join(c for c in '0123456789' if c not in acc) or '无'}")
    if a.dry:
        return
    os.makedirs(TPL_DIR, exist_ok=True)
    for ch, lst in sorted(acc.items()):
        t = np.mean(np.stack(lst), axis=0)          # 同样本取均值降噪
        cv2.imwrite(os.path.join(TPL_DIR, f"dg{ch}.png"), t.astype("uint8"))
        print(f"  dg{ch}: {len(lst)} 个样本 → 已写入")
    print(f"已写入 {TPL_DIR}")


if __name__ == "__main__":
    main()
