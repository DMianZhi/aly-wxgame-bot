"""重建小字数字模板 templates/digits/dg0..dg9.png(供 wb/digits.py 读数用)。

需要一帧「选择机友」页 + 那 5 行「战力」的真值(比如 75690/74188/74066/53806/40125),
脚本按「连通域切字形 → 居中底对齐归一化」逐个存模板。

注意: 被选中的那一行是高亮(青色)配色, 字形风格与未选中行不同, **必须跳过**,
否则会污染模板(实测不跳过的模板只能读对 3/5 行, 跳过 5/5)。

默认参数针对仓库里的黄金夹具 shots/b_selrow4_0.png(第 4 行当时是选中态):
    uv run python tools/maint/build_digits.py
换新画面重建时:
    uv run python tools/maint/build_digits.py --shot shots/xxx.png \
        --truth 75690,74188,74066,53806,40125 --skip 930

跑完可零消耗自证: uv run python wb/digits.py --selftest
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import cv2

from wb.digits import CH, CW, _glyphs, _norm

SHOT = os.path.join(ROOT, "shots", "b_selrow4_0.png")
TRUTH = "75690,74188,74066,53806,40125"
YC0, PITCH = 432, 166          # 帧坐标: 首行「战力」小字 y 中心 + 行距
OUT = os.path.join(ROOT, "templates", "digits")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", default=SHOT)
    ap.add_argument("--truth", default=TRUTH, help="各行的战力真值, 逗号分隔")
    ap.add_argument("--skip", default="", help="要跳过的行的 y 中心, 逗号分隔")
    ap.add_argument("--dry", action="store_true", help="只检查切分, 不写模板")
    a = ap.parse_args()

    frame = cv2.imread(a.shot)
    if frame is None:
        print(f"[fail] 读不到 {a.shot}")
        raise SystemExit(1)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    truth = a.truth.split(",")
    skip = {int(v) for v in a.skip.split(",") if v.strip()}

    got: dict[str, any] = {}
    for i, tv in enumerate(truth):
        yc = YC0 + PITCH * i
        if yc in skip:
            print(f"  行{i+1} y={yc} 跳过(高亮行, 配色不同)")
            continue
        gs = _glyphs(gray, yc)
        if len(gs) != len(tv):
            print(f"  行{i+1} y={yc} 切出 {len(gs)} 个字(真值 {len(tv)} 位) → 跳过")
            continue
        for (x, y, w, h), ch in zip(gs, tv):
            if ch not in got:
                got[ch] = _norm(gray[y:y + h, x:x + w])
                print(f"  行{i+1} y={yc} 取到数字 {ch} 于 ({x},{y}) {w}×{h}")

    print(f"共 {len(got)} 个模板 ({''.join(sorted(got))}), 缺: "
          f"{''.join(c for c in '0123456789' if c not in got) or '无'}")
    if a.dry:
        return
    os.makedirs(OUT, exist_ok=True)
    for ch, t in sorted(got.items()):
        cv2.imwrite(os.path.join(OUT, f"dg{ch}.png"), t.astype("uint8"))
    print(f"已写入 {OUT} (画布 {CW}×{CH})")


if __name__ == "__main__":
    main()
