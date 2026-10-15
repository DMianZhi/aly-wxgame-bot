"""裁「雷霆兑换码」入口模板 templates/rd_home_entry.png（小程序**单屏首页**）。

    uv run python tools/crop/crop_rdhome.py

源帧: shots/_rd_home_732.png（用户 2026-10-15 提供的单屏首页截图, 732x1370）

⚠ 事故背景（用户「点击错了，点到了活动时间线」）: 旧模板是分屏时代留的，且入口坐标
   硬编码 (365,700)；单屏就绪态下首页 4 个图标是**均分**的（118 / 283 / 449 / 617），
   于是 (365,700) 恰好压在「活动时间线」上 → 点进去 24s 找不到「今晚失效」→ 反复重试。
   本次重裁图标 + **反验证**（不得与相邻图标混淆）+ 用例侧 x 区间校验。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import bot  # noqa: E402

SRC = ROOT / "shots" / "_rd_home_732.png"
DST = ROOT / "templates" / "rd_home_entry.png"
BOX = (219, 658, 347, 756)          # 「雷霆兑换码」图标 bbox（蓝色像素实测）
NEIGHBOR = (400, 651, 500, 754)     # 「活动时间线」区域（反验：不得命中）


def main() -> int:
    if not SRC.exists():
        print(f"[SKIP] 缺源帧 {SRC}")
        return 0
    img = cv2.imdecode(np.fromfile(str(SRC), np.uint8), cv2.IMREAD_COLOR)
    x0, y0, x1, y1 = BOX
    tpl = img[y0:y1, x0:x1]
    cv2.imwrite(str(DST), tpl)
    print(f"[ok  ] 裁剪 {tpl.shape[1]}x{tpl.shape[0]} → {DST.relative_to(ROOT)}")

    h = bot.match_adaptive(img, tpl, 0.5)
    cx = (x0 + x1) // 2
    ok_pos = h is not None and abs(h[0] - cx) <= 4
    print(f"[{'ok  ' if ok_pos else '!!  '}] 正验 命中{h} 期望中心 x≈{cx}")

    nx0, ny0, nx1, ny1 = NEIGHBOR
    h2 = bot.match_adaptive(img[ny0:ny1, nx0:nx1], tpl, 0.5)
    ok_neg = h2 is None or h2[2] < 0.8
    print(f"[{'ok  ' if ok_neg else '!!  '}] 反验 「活动时间线」区域不命中: {h2}")

    ok = ok_pos and ok_neg
    print("结论:", "PASS" if ok else "FAIL")
    print("OUTPUT=" + str(DST.resolve()))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
