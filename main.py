"""wxgame-bot — PC 微信小游戏每日任务自动化（截图找图 + 拟人点击）。

用法:
    uv run python main.py check      # 环境自检（依赖/配置/窗口/截屏）
    uv run python main.py snap       # 截游戏窗口到 shots/ 用于裁剪模板

每日任务用例都在 tools/ 下，各自独立运行（全部支持 --dry：只出计划、零点击）:
    uv run python tools/cases/guild_donate.py --all      # 战队捐献（金币/钻石各 3 次）
    uv run python tools/cases/sweep_stage.py             # 扫荡关卡（--material=N 指定材料）
    uv run python tools/cases/free_rally.py              # 十年集结
    uv run python tools/cases/free_rally.py --dry        # 只出计划不点击
"""
from __future__ import annotations

import sys


def cmd_check() -> int:
    print("== wxgame-bot 环境自检 ==")
    ok = True

    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import pyautogui  # noqa: F401

        print("[ok] 依赖导入")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"[fail] 依赖: {e} （先跑 uv sync）")

    try:
        from wb.cfg import CONF

        print(
            f"[ok] 配置: threshold={CONF.threshold}, dry_run={CONF.dry_run}"
        )
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"[fail] 配置: {e}")

    try:
        from wb.bot import find_game_window
        from wb.cfg import CONF as C2

        rect = find_game_window(C2.title_keyword, C2.process_name)
        if rect is None:
            print("[warn] 未找到游戏窗口（先打开游戏，检查 title_keyword / process_name）")
        else:
            print(f"[ok] 游戏窗口: ({rect.x},{rect.y}) {rect.w}x{rect.h}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"[fail] 窗口检测: {e}")

    return 0 if ok else 1


def cmd_snap() -> int:
    import time
    from pathlib import Path

    import cv2

    from wb.bot import find_game_window, grab_window
    from wb.cfg import CONF

    rect = find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        print("[fail] 未找到游戏窗口，先打开游戏界面再试")
        return 1
    img = grab_window(rect)
    path = Path("shots") / f"snap_{time.strftime('%Y%m%d_%H%M%S')}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    print(f"[ok] 截图: {path.resolve()}")
    print("下一步: 画图裁按钮小图 -> templates/<名字>.png")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        return cmd_check()
    if cmd == "snap":
        return cmd_snap()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
