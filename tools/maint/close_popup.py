"""用例: 关闭当前游戏内弹窗 (点击右上角 × 区域), 常用于误操作恢复。

用法: .venv/Scripts/python.exe tools/maint/close_popup.py [x y]
    默认点击设置弹窗 × 位置 (768, 325); 传参可指定其他弹窗关闭钮。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb.bot import click_xy, find_game_window, grab_window  # noqa: E402
from wb.cfg import CONF, SHOTS_DIR  # noqa: E402

DEFAULT_XY = (768, 325)  # 设置弹窗 × (845x1521)


def main() -> int:
    x, y = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else DEFAULT_XY
    rect = find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        print("[fail] 未找到游戏窗口")
        return 1
    click_xy(x, y, CONF.jitter_px, (CONF.delay_min, CONF.delay_max), rect,
             dry_run=False)
    time.sleep(0.8)
    live = grab_window(rect)
    out = SHOTS_DIR / "after_close.png"
    cv2.imwrite(str(out), live)
    print(f"[ok] 已点击 ({x},{y}), 结果存 {out.name}")
    print(f"OUTPUT={out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
