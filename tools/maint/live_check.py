"""用例: 模板实时校验 — PrintWindow 抓当前游戏窗口, 全部模板逐个匹配。

用法:
    .venv/Scripts/python.exe tools/maint/live_check.py            # 抓实时画面校验
    .venv/Scripts/python.exe tools/maint/live_check.py --snap     # 同时存 shots/live_check_*.png

游戏窗口不在时自动回退 shots/ 最新截图（打印 [src] 标记提醒这只是离线校验）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb.croplab import TEMPLATES_DIR, _match_one, live_target  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402


def main() -> int:
    tgt, tag = live_target()
    if tgt is None:
        files = sorted(SHOTS_DIR.glob("snap_*.png"), key=lambda p: p.stat().st_mtime)
        if not files:
            print("FAIL: 游戏窗口不在且 shots/ 无截图")
            return 1
        tgt = cv2.imread(str(files[-1]))
        tag = f"src:{files[-1].name}"
    assert tgt is not None
    if "--snap" in sys.argv:
        out = SHOTS_DIR / f"live_check_{time.strftime('%Y%m%d_%H%M%S')}.png"
        cv2.imwrite(str(out), tgt)
        print(f"OUTPUT={out.resolve()}")

    print(f"校验目标: [{tag}] {tgt.shape[1]}x{tgt.shape[0]}")
    weak: list[str] = []
    total = 0
    for p in sorted(TEMPLATES_DIR.glob("*.png")):
        score, cx, cy = _match_one(tgt, p)
        total += 1
        flag = "ok  " if score >= 0.90 else "weak"
        if score < 0.90:
            weak.append(p.stem)
        print(f"[{flag}] {p.stem:18s} score={score:.4f} center=({cx},{cy})")
    print(f"\n共 {total} 张, 薄弱(<0.90) {len(weak)} 张: {weak if weak else '无'}")
    return 0 if not weak else 2


if __name__ == "__main__":
    raise SystemExit(main())
