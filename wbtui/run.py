"""wbtui 的运行层 —— 起子进程跑用例：stderr 实时喂 Live，stdout 收一行 JSON。

为什么是子进程而不是 import 用例:
    ① 项目核心设计是「一个用例一个进程，失败不互相影响」——import 会把 22 个用例
       塞进 TUI 进程，一崩全崩，还得重构 run_case 的 SystemExit/单实例锁语义；
    ② 这样 TUI 与 AI 走的是**同一条命令、同一份 --json 契约**，不会出现
       「界面能跑但 AI 调不通」的漂移。

两条管道各司其职（正是 kit 改造的目的）:
    stderr = 人类日志 → 实时滚动进日志面板
    stdout = 恰好一行结果 JSON → 跑完解析成结果面板
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from rich.live import Live

from . import view


def _popen(repo: str, argv: list[str], cwd: Path) -> subprocess.Popen:
    env = dict(os.environ, PYTHONUTF8="1")   # 子进程也必须 UTF-8，否则中文日志/JSON 编码崩
    return subprocess.Popen(
        [sys.executable, repo, *argv],
        cwd=str(cwd), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )


def _pump(pipe, kind: str, sink: queue.Queue, store: list[str]) -> None:
    """把一条管道逐行读干（后台线程）；日志行顺带推进度队列。"""
    try:
        for ln in pipe:
            ln = ln.rstrip("\n")
            store.append(ln)
            if kind == "log":
                sink.put(ln)
    except Exception:  # noqa: BLE001  管道被终止时静默收尾，别把 TUI 带崩
        pass
    finally:
        try:
            pipe.close()
        except Exception:  # noqa: BLE001
            pass


def kill_tree(p: subprocess.Popen) -> None:
    """停掉用例进程**及其子进程**（Windows 用 taskkill /T）。

    ⚠ 只杀我们自己起的那棵进程树；游戏在微信进程里，不是它的子进程，不会受影响。
    """
    if p.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                       capture_output=True, check=False)
    except Exception:  # noqa: BLE001
        p.kill()


def run_console(console, repo: str, argv: list[str], *, cwd: Path,
                log_limit: int = 18, log_title: str | None = None
                ) -> tuple[dict | None, int | None, list[str], bool]:
    """跑一个用例并把 stderr 实时滚进 Live 面板。

    log_title: 日志面板标题(批量模式用来显示「第 n/N · 用例名」)。
    返回 (结果 dict | None, 退出码, 日志行, 是否被用户中断)。
    """
    p = _popen(repo, argv, cwd)
    q: queue.Queue = queue.Queue()
    logs: list[str] = []
    outs: list[str] = []
    threads = [
        threading.Thread(target=_pump, args=(p.stderr, "log", q, logs), daemon=True),
        threading.Thread(target=_pump, args=(p.stdout, "out", q, outs), daemon=True),
    ]
    for t in threads:
        t.start()

    interrupted = False
    with Live(view.log_panel(logs, limit=log_limit, title=log_title or "实时日志"),
              console=console,
              refresh_per_second=10, transient=False) as live:
        try:
            while True:
                try:
                    q.get(timeout=0.1)
                    live.update(view.log_panel(logs, limit=log_limit))
                except queue.Empty:
                    if p.poll() is not None:
                        break
        except KeyboardInterrupt:
            interrupted = True
            console.print("\n[yellow]收到中断 → 正在停止用例…[/]")
            kill_tree(p)
        finally:
            for t in threads:
                t.join(timeout=3.0)
            live.update(view.log_panel(logs, limit=log_limit))

    return _parse_json(outs), p.returncode, logs, interrupted


def _parse_json(lines: list[str]) -> dict | None:
    """从 stdout 里取那**一行** JSON（容忍噪声：只认最后一个能解析的对象）。"""
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None