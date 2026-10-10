#!/usr/bin/env python
"""wbtui 入口 —— wxgame-bot 的菜单式 TUI（基于 rich）。

用法:
    uv run python -m wbtui

流程: 列出每日用例 → 选编号 → （默认）dry 演练 / 真跑需二次确认 → 实时日志 → 结果面板。

真跑会**真实操作游戏并消耗每日次数**，所以默认走 dry，真跑必须显式确认；
用例本身另有单实例锁与看门狗兜底（见 wb/kit.py）。
"""
from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from wb import registry
from wb.cfg import SHOTS_DIR
from wbtui import run as runner
from wbtui import view

REPO = Path(__file__).resolve().parents[1]


def _daily():
    return registry.by_group(registry.DAILY)


def _ask_argv(console: Console) -> list[str]:
    """附加开关（可空），如 `--max 2` / `--station 战机,装甲`。"""
    raw = Prompt.ask("附加开关（可空，如 [cyan]--max 2[/]）", default="", console=console)
    raw = raw.strip()
    if not raw:
        return []
    try:
        return shlex.split(raw)
    except ValueError as e:
        console.print(f"[red]开关解析失败（引号不配对？）: {e}[/]")
        return []


def main() -> int:
    console = Console()
    entries = _daily()
    if not entries:
        console.print("[red]注册表里没有每日用例[/]")
        return 1
    last: tuple[str, str, list[str]] | None = None   # (repo, title, argv)

    while True:
        console.clear()
        console.print(view.header_panel(len(entries)))
        console.print(view.cases_table(entries))
        console.print(view.hints())

        ans = Prompt.ask("选择用例编号", default="q", console=console).strip().lower()

        if ans in ("", "q", "quit", "exit"):
            console.print("[dim]再见。[/]")
            return 0

        if ans == "shots":
            try:
                os.startfile(SHOTS_DIR)     # noqa: S606  仅 Windows 本地使用
            except Exception as e:          # noqa: BLE001
                console.print(f"[red]打不开截图目录: {e}[/]")
                Prompt.ask("回车返回", default="", console=console)
            continue

        if ans.startswith("r") and last is not None:      # r 或 r<回车>
            repo, title, argv = last
            console.rule(f"重跑 {title}")
            _run_one(console, repo, title, argv)
            continue

        try:
            idx = int(ans)
            if not 1 <= idx <= len(entries):
                raise ValueError
        except ValueError:
            console.print("[red]无效编号[/]（q 退出 / shots 看截图 / r 重跑）")
            Prompt.ask("回车返回", default="", console=console)
            continue

        e = entries[idx - 1]
        extra = _ask_argv(console)
        dry = Confirm.ask(f"以 [bold]dry 演练[/]（零点击）运行 [cyan]{e.name}[/]？",
                          default=True, console=console)
        if dry:
            argv = ["--dry", *extra]
        else:
            if not Confirm.ask("[red]⚠ 将真实操作游戏（可能消耗每日次数），确认执行？[/]",
                               default=False, console=console):
                console.print("[dim]已取消。[/]")
                continue
            argv = list(extra)

        console.rule(f"运行 {e.title}")
        _run_one(console, e.repo, e.title, argv)
        last = (e.repo, e.title, argv)


def _run_one(console: Console, repo: str, title: str, argv: list[str]) -> None:
    """跑一个用例（始终带 --json），打印结果面板后等一次回车。"""
    console.print(f"[dim]uv run python {repo} {' '.join(argv)} --json[/]")
    res, rc, logs, interrupted = runner.run_console(
        console, repo, [*argv, "--json"], cwd=REPO)
    console.print(view.result_panel(res, rc=rc, stderr_tail=logs))
    if interrupted:
        console.print("[yellow]（本次被手动中断）[/]")
    Prompt.ask("回车返回菜单", default="", console=console)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已退出。", file=sys.stderr)
        raise SystemExit(130)