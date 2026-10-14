#!/usr/bin/env python
"""wbtui 入口 —— wxgame-bot 的菜单式 TUI（基于 rich + msvcrt 按键循环）。

用法:
    uv run python -m wbtui

流程: 列出每日用例 → ↑↓ 移动 + 空格勾选(支持多选) → Enter 执行勾选 / A 一键全部
      → （默认）dry 演练 / 真跑需二次确认 → 实时日志 → 批量汇总面板。

真跑会**真实操作游戏并消耗每日次数**，所以默认走 dry，真跑必须显式确认；
用例本身另有单实例锁与看门狗兜底（见 wb/kit.py）。

菜单用 msvcrt 按键循环（Windows 标准库，零新依赖；本项目本就 win32 限定）。
为什么不用 rich Prompt 行输入: 「空格勾选」是按键语义，行输入模拟不出来；
执行阶段仍走 run_console 的子进程 + Live，与单跑共用同一条 --json 契约。
"""
from __future__ import annotations

import msvcrt
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm

from wb import registry
from wb.cfg import SHOTS_DIR
from wbtui import run as runner
from wbtui import view

REPO = Path(__file__).resolve().parents[1]

# msvcrt.getch 的扫描码(方向键首字节 b'\x00'/b'\xe0' + 次字节)
KEY_UP, KEY_DOWN = b"\x48", b"\x50"
KEY_ENTER, KEY_ESC, KEY_SPACE, KEY_CTRL_C = b"\r", b"\x1b", b"\x20", b"\x03"


def _daily():
    return registry.by_group(registry.DAILY)


def _open_shots(console: Console) -> None:
    try:
        os.startfile(SHOTS_DIR)     # noqa: S606  仅 Windows 本地使用
    except Exception as e:          # noqa: BLE001
        console.print(f"[red]打不开截图目录: {e}[/]")


def _menu_keyloop(console: Console, entries) -> list | None:
    """按键模式菜单: ↑↓ 移动 / 空格勾选 / a 全选 / Enter 执行勾选 / A 一键全部。

    返回勾选的 Entry 列表(按列表顺序)；q/Esc 返回 None(退出)；Ctrl+C 退出。
    (2026-10-12: 只列每日用例 —— 维护工具是开发者用的, 不进这个列表;
     背包清理已归入每日用例, 自然在此列)

    渲染用 rich Live(auto_refresh=False) 原位重写 —— 2026-10-11 修闪烁:
    旧版每帧 console.clear() 全量重画, 清屏瞬间黑闪一下; Live 用 ANSI 把光标
    移回帧首重写同一块区域, 不清屏, 且只在按键后才 update(refresh), 阻塞等键时零重绘。
    """
    from rich.console import Group

    cursor = 0
    selected: set[int] = set()

    def render():
        return Group(
            view.header_panel(len(entries)),
            view.cases_table(entries, selected=selected, cursor=cursor),
            view.hints(),
        )

    with Live(render(), console=console, auto_refresh=False,
              refresh_per_second=4, transient=False) as live:
        while True:
            ch = msvcrt.getch()
            redraw = True
            if ch in (b"\x00", b"\xe0"):            # 功能键 → 读第二个扫描码
                ch = msvcrt.getch()
                if ch == KEY_UP:
                    cursor = (cursor - 1) % len(entries)
                elif ch == KEY_DOWN:
                    cursor = (cursor + 1) % len(entries)
                else:
                    redraw = False
            elif ch == KEY_CTRL_C:
                return None
            elif ch == KEY_SPACE:
                if cursor in selected:
                    selected.discard(cursor)
                else:
                    selected.add(cursor)
            elif ch in (b"a", b"A"):
                if len(selected) == len(entries):
                    selected.clear()
                else:
                    selected = set(range(len(entries)))
            elif ch == KEY_ENTER:
                if selected:
                    return [entries[i] for i in sorted(selected)]
                redraw = False
            elif ch in (b"q", b"Q", KEY_ESC):
                return None
            elif ch == b"s":
                _open_shots(console)
                redraw = False
            else:
                redraw = False
            if redraw:
                live.update(render(), refresh=True)


def _ask_mode(console: Console, n: int) -> list[str] | None:
    """批量执行前选模式: 默认 dry 演练, 真跑要红色二次确认。返回附加 argv 或 None(取消)。"""
    if Confirm.ask(f"以 [bold]dry 演练[/]（零点击）跑这 {n} 个？"
                   f"（选否 = [red]真跑, 会真实操作游戏并可能消耗每日次数[/]）",
                   default=True, console=console):
        return ["--dry"]
    if not Confirm.ask(f"[red]⚠ 将按顺序真跑 {n} 个用例（可能消耗每日次数），确认执行？[/]",
                       default=False, console=console):
        console.print("[dim]已取消。[/]")
        return None
    return []


def _run_batch(console: Console, entries, *, dry: bool) -> None:
    """按顺序跑一批用例（子进程 + 实时日志），结束后出汇总面板。

    dry 由调用方决定（交互在 _ask_mode）；Ctrl+C 停当前用例后询问是否继续队列。
    """
    argv = ["--dry"] if dry else []
    total = len(entries)
    results: list[dict] = []
    for n, e in enumerate(entries, 1):
        console.rule(f"[{n}/{total}] {e.title}")
        res, rc, logs, interrupted = runner.run_console(
            console, e.repo, [*argv, "--json"], cwd=REPO,
            log_title=f"[{n}/{total}] {e.title}")
        results.append({
            "title": e.title,
            "ok": bool(res and res.get("ok")) and not interrupted,
            "code": res.get("code") if res else rc,
            "dur": res.get("dur") if res else None,
            "dry": dry or bool(res and res.get("dry")),
            "interrupted": interrupted,
        })
        console.print(view.result_panel(res, rc=rc, stderr_tail=logs))
        if results[-1]["code"] == 5:
            # ⭐ 2026-10-14 急停(鼠标甩到屏幕角落): 鼠标停在角落期间**每次点击都立即抛**
            #   → 后面每个用例都会在十几秒内连环崩（实测 活跃度/奖励领取/社区奖励 三连崩）。
            #   直接中止队列，别再白跑（用户甩鼠标本来是「停止」意图）。
            console.print("[bold red]⛔ 检测到急停（鼠标在屏幕角落）→ 中止队列剩余用例[/]")
            break
        if interrupted:
            console.print("[yellow]（本次被手动中断）[/]")
            if not Confirm.ask("继续队列剩下的用例？", default=True, console=console):
                break
    console.print(view.summary_table(results))


def main() -> int:
    console = Console()
    entries = _daily()
    if not entries:
        console.print("[red]注册表里没有每日用例[/]")
        return 1

    while True:
        picked = _menu_keyloop(console, entries)
        if picked is None:
            console.print("[dim]再见。[/]")
            return 0
        console.clear()                      # Live 保留了菜单帧, 执行阶段从干净屏开始
        argv = _ask_mode(console, len(picked))
        if argv is None:
            continue
        dry = "--dry" in argv
        _run_batch(console, picked, dry=dry)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已退出。", file=sys.stderr)
        raise SystemExit(130)
