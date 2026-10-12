#!/usr/bin/env python
"""夹具重采 —— 把 shots/ 下被误删的真帧夹具按**原始像素尺寸**重新采回来。

背景（2026-10-12）：一次清理把 shots/ 下所有 `_*.png`(597 张) 当成临时留证删了，
其中约 146 张是离线自检依赖的**真帧夹具**。shots/ 在 .gitignore 第 12 行、从未入库，
不可回滚 → 只能重采。

⚠⚠ 重采前**必须**把游戏客户区改成夹具的原始尺寸：
    自检里的期望坐标（如 void_rift 的 C_ENTRY=(710,745)±8）是按夹具原始像素记录的，
    而模板匹配会按 (845,1521) 归一后反映射 → 尺寸不一致会让落点整体偏移
    （814x1507 vs 812x1518 在 y≈1300 处差 ~9px，已经吃掉整个 ±8 容差）。

零消耗原则：本工具只做**纯导航**（进页面/切页签），绝不点任何会消耗额度或
产生公开动作的按钮（扫荡/挑战/领取/发送）。

用法：
    uv run python tools/maint/capture_fixtures.py --list          # 看有哪些配方
    uv run python tools/maint/capture_fixtures.py --case=void_rift
    uv run python tools/maint/capture_fixtures.py --case=void_rift --keep-size   # 不改窗口尺寸
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

import wb.bot as bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402

GAME_TITLE = "雷霆战机"


def log(msg: str) -> None:
    print(f"[重采] {msg}", flush=True)


# --------------------------------------------------------------- 窗口尺寸
def _client(hwnd: int) -> tuple[int, int]:
    r = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right, r.bottom


def resize_client(rect: bot.WinRect, w: int, h: int, tries: int = 5) -> bot.WinRect:
    """把游戏窗口的**客户区**调成 w×h（自检夹具的原始尺寸）。"""
    user32 = ctypes.windll.user32
    HWND_TOP, SWP_NOSIZE, SWP_NOMOVE = 0, 1, 2
    for _ in range(tries):
        cur = bot.find_game_window(GAME_TITLE, "")
        if cur is None:
            return rect
        cw, ch = _client(cur.hwnd)
        if (cw, ch) == (w, h):
            log(f"客户区已是 {w}x{h}")
            return cur
        wr = ctypes.wintypes.RECT()
        user32.GetWindowRect(cur.hwnd, ctypes.byref(wr))
        ow, oh = wr.right - wr.left, wr.bottom - wr.top
        user32.SetWindowPos(cur.hwnd, HWND_TOP, wr.left, wr.top,
                            ow + (w - cw), oh + (h - ch), 0)
        time.sleep(0.7)
    cur = bot.find_game_window(GAME_TITLE, "")
    log(f"调整后客户区 = {_client(cur.hwnd) if cur else None} (目标 {w}x{h})")
    return cur or rect


def _save(name: str, img) -> str:
    """按**夹具原始文件名**落盘（不套 Screen 的 prefix 前缀）。"""
    path = SHOTS_DIR / name
    cv2.imwrite(str(path), img)
    log(f"  ✓ 落盘 {name}  {img.shape[1]}x{img.shape[0]}")
    return name


# --------------------------------------------------------------- 配方
# 每个配方返回「已落盘的文件名」。
# ⚠ 不少夹具是**每日状态帧**（必须在当日未领/满额度时采）：
#    void_rift 工坊页的免费钮、claim_reward 的「6 行全橙」…
#    今日额度已耗尽时采到的会是「已领/绿勾」态 → 与自检的期望坐标不符 → 必须**跳过**
#    并报「需等次日刷新」，绝不能落盘（否则把 SKIP 变成 FAIL，反而掩盖真状态）。
def cap_void_rift(sc: kit.Screen) -> list[str]:
    """void_rift 的 3 帧：关卡页 / 虚空裂隙页 / 密钥工坊页。纯导航，零消耗。"""
    import tools.cases.void_rift as vr

    out: list[str] = []
    # ① 先到关卡页（climb: 首页 → 闯关模式）
    for _ in range(6):
        if sc.find(vr.ENTRY_TPL) is not None:
            break
        if kit.is_home(sc):
            sc.tap("stage_btn", th=0.90, wait=2.5, label="闯关模式(重采)")
        elif not kit.goto_home(sc):
            break
    if sc.find(vr.ENTRY_TPL) is None:
        log("  ✗ 没到关卡页, 放弃")
        return out
    out.append(_save("_vk7_vk7_stagepage.png", sc.grab()))

    # ② 点「虚空裂隙」卡 → 裂隙页
    sc.click(sc.find(vr.ENTRY_TPL), "虚空裂隙卡(重采)")
    kit.nap(4.0)
    if sc.find(vr.SHOP_TPL) is None:
        log("  ✗ 没到虚空裂隙页, 放弃")
        return out
    out.append(_save("_vk8_vk8_rift.png", sc.grab()))

    # ③ 点「秘钥工坊」→ 工坊页（只进页, 绝不点免费钮）
    sc.click(sc.find(vr.SHOP_TPL), "秘钥工坊(重采)")
    kit.nap(3.0)
    # —— 状态守卫：免费钮必须在固定槽位 (225,811)±25，否则今日已领 → 不落盘
    f = sc.find(vr.FREE_TPL, vr.TH_FREE)
    if f is None or abs(f[0] - vr.FREE_XY[0]) > vr.FREE_TOL or abs(f[1] - vr.FREE_XY[1]) > vr.FREE_TOL:
        log(f"  ✗ 工坊页免费钮不在槽位(今日已领) → **不落盘** {f}")
        log("    → 这帧是每日状态帧, 请等次日刷新后再采")
        return out
    out.append(_save("_vk9_vk9_workshop.png", sc.grab()))
    return out


RECIPES: dict[str, tuple[tuple[int, int], object]] = {
    #  f"{case}": (夹具原始尺寸, 采集函数)
    "void_rift": ((812, 1518), cap_void_rift),
}


# --------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="夹具重采（零消耗纯导航）")
    ap.add_argument("--case", default="", help="配方名, 见 --list")
    ap.add_argument("--list", action="store_true", help="列出配方")
    ap.add_argument("--keep-size", action="store_true", help="不改窗口客户区尺寸")
    args = ap.parse_args()

    if args.list or not args.case:
        print("可用配方（case → 夹具原始尺寸）:")
        for k, (sz, _) in RECIPES.items():
            print(f"  {k:16s} {sz[0]}x{sz[1]}")
        return 0

    if args.case not in RECIPES:
        log(f"未知配方 {args.case}")
        return 1
    size, fn = RECIPES[args.case]

    r0 = bot.find_game_window(GAME_TITLE, "")
    if r0 is None:
        log("找不到游戏窗口（exit=2 约定码）")
        return 2
    orig = (r0.w, r0.h)
    bot._ensure_foreground(r0)

    if not args.keep_size:
        r0 = resize_client(r0, *size)
    log(f"窗口客户区 {r0.w}x{r0.h}（起始 {orig[0]}x{orig[1]}）")

    sc = kit.Screen(r0, th=0.86, dry=False, prefix="cap_")
    got = fn(sc)

    # 收尾：回首页 + 还原窗口尺寸
    kit.goto_home(sc)
    if not args.keep_size and (orig != (r0.w, r0.h)):
        resize_client(r0, *orig)
    log(f"完成: {len(got)} 帧 {got}")
    return 0 if got else 1


if __name__ == "__main__":
    raise SystemExit(main())
