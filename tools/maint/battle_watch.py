"""局内用例: 拖拽挪机 + 血量监控 + 低血自动点技能 (可 --dry 只读不动)。

用法 (项目根目录):
    .venv/Scripts/python.exe tools/maint/battle_watch.py           # 挪机+监控45s
    .venv/Scripts/python.exe tools/maint/battle_watch.py 120       # 监控120s
    .venv/Scripts/python.exe tools/maint/battle_watch.py --dry 10  # 只读血量不点击不拖拽
急停: Ctrl+C 或把鼠标甩到屏幕左上角(0,0) (pyautogui FAILSAFE)。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import pyautogui  # noqa: E402

from wb.bot import find_game_window, grab_window  # noqa: E402
from wb.cfg import CONF, SHOTS_DIR  # noqa: E402

# ---- 局内布局常量 (845x1521 客户区坐标, 印在截图上标定) ----
PLANE = (700, 1150)        # 飞机当前位置(粗估)
SKILL = (740, 1300)        # 右下角技能键
PLANE_TARGET = (745, 1090) # 挪到技能键上方一些
HP_BAND = (165, 690, 162, 182)  # 顶部血条采样区 x1,x2,y1,y2
FULL_RED = 525 * 20 * 0.9  # 满血红色像素估计(标定值)

HP_LOW = 0.50              # 血量低于此比例 -> 点技能
SKILL_COOLDOWN = 1.2       # 技能动画/冷却等待

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


def hp_ratio(live) -> float:
    """顶部血条红色像素占比 = 飞机血量比例(青色BOSS条颜色分离不干扰)。"""
    x1, x2, y1, y2 = HP_BAND
    band = live[y1:y2, x1:x2]
    r = (band[:, :, 2].astype(int) > 150) & (band[:, :, 0].astype(int) < 120) \
        & (band[:, :, 1].astype(int) < 120)
    return float(r.mean())


def drag_plane(rect) -> None:
    """拟人分段拖拽: 飞机 -> 技能键上方。"""
    sx, sy = rect.x + PLANE[0], rect.y + PLANE[1]
    tx, ty = rect.x + PLANE_TARGET[0], rect.y + PLANE_TARGET[1]
    pyautogui.moveTo(sx, sy, duration=0.3)
    time.sleep(0.4)
    pyautogui.mouseDown()
    steps = [(705, 1140), (715, 1130), (725, 1120), (733, 1112), (740, 1100),
             (PLANE_TARGET[0], PLANE_TARGET[1])]
    for px, py in steps:
        pyautogui.moveTo(rect.x + px, rect.y + py, duration=0.12)
        time.sleep(0.05)
    time.sleep(0.2)
    pyautogui.mouseUp()
    print(f"[move] 飞机 {PLANE} -> {PLANE_TARGET} 完成", flush=True)


def watch(rect, seconds: float, dry: bool) -> None:
    print(f"[watch] {seconds:.0f}s 阈值{HP_LOW:.0%} dry={dry}", flush=True)
    t0 = time.time()
    last_cast = 0.0
    n_cast = 0
    while time.time() - t0 < seconds:
        live = grab_window(rect)
        if live is None:
            print("[!] 窗口丢失, 退出", flush=True)
            return
        frac = hp_ratio(live)
        cast = False
        if frac < HP_LOW and not dry and time.time() - last_cast >= SKILL_COOLDOWN:
            from wb.bot import click_xy
            click_xy(SKILL[0], SKILL[1], CONF.jitter_px,
                     (CONF.delay_min, CONF.delay_max), rect, dry_run=False)
            last_cast = time.time()
            n_cast += 1
            cast = True
        print(f"t={time.time()-t0:5.1f} HP={frac:5.1%}"
              + ("  >>> 点技能" if cast else ""), flush=True)
        if dry and frac < HP_LOW:
            print("[dry] 血量已低于阈值 (只读模式不点击), 结束", flush=True)
            cv2.imwrite(str(SHOTS_DIR / "battle_dry_lowhp.png"), live)
            return
        time.sleep(0.5)
    print(f"[done] 监控结束, 放技能 {n_cast} 次", flush=True)


def main() -> int:
    args = [a for a in sys.argv[1:]]
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]
    seconds = float(args[0]) if args else 45.0
    rect = find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        print("[fail] 未找到游戏窗口")
        return 1
    print(f"[win] ({rect.x},{rect.y}) {rect.w}x{rect.h}", flush=True)
    if not dry:
        drag_plane(rect)
        time.sleep(0.8)
    watch(rect, seconds, dry)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except pyautogui.FailSafeException:
        print("[STOP] FAILSAFE 急停")
        raise SystemExit(130)
