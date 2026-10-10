"""wbtui 的渲染层 —— 纯函数：state → rich 可渲染对象。

刻意零 I/O：因此可以用 `Console(record=True)` 离线快照断言（不依赖 TTY，见 selftest）。
"""
from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# 退出码语义（与 kit.run_case 的约定一致）
CODE_MEAN = {0: "成功", 1: "未达成", 2: "环境问题(没窗口等)", 3: "已有实例在跑", 4: "超时"}


def header_panel(n_cases: int, *, version: str = "") -> Panel:
    t = Text()
    t.append("wxgame-bot", style="bold cyan")
    t.append(f"   每日用例 {n_cases} 个", style="dim")
    if version:
        t.append(f"   {version}", style="dim")
    t.append("\n选编号运行 · dry 演练零副作用 · 日志实时滚动", style="dim")
    return Panel(t, border_style="cyan")


def cases_table(entries, *, title: str = "每日用例") -> Table:
    """用例清单（直接吃 wb.registry 的 Entry，单一事实源）。"""
    t = Table(title=title, title_justify="left", expand=True,
              header_style="bold", border_style="dim", pad_edge=False)
    t.add_column("#", justify="right", style="bold", no_wrap=True)
    t.add_column("用途", overflow="fold")
    t.add_column("每日额度", no_wrap=True, style="cyan")
    t.add_column("开关", style="dim", overflow="fold")
    for i, e in enumerate(entries, 1):
        t.add_row(str(i), e.title, e.quota, e.flags)
    return t


def log_panel(lines: list[str], *, limit: int = 18, title: str = "实时日志") -> Panel:
    """日志尾部 N 行（Panel 固定高度，防止跑长用例时把屏幕撑爆）。"""
    tail = lines[-limit:] if limit > 0 else list(lines)
    body = Text("\n".join(tail) if tail else "（等待输出…）")
    return Panel(body, title=title, border_style="blue", height=limit + 2)


def result_panel(res: dict | None, *, rc: int | None = None,
                 stderr_tail: list[str] | None = None, limit: int = 14) -> Panel:
    """--json 结果面板；拿不到结构化结果时降级为「退出码 + 日志尾巴」。"""
    if res is None:
        okish = rc == 0
        body = Text()
        body.append("✓ 退出码 0" if okish else f"✗ 退出码 {rc}",
                    style="bold green" if okish else "bold red")
        body.append("（没有拿到结构化结果：老脚本 / 未加 --json / 输出被截断）", style="yellow")
        if stderr_tail:
            body.append("\n" + "\n".join(stderr_tail[-limit:]), style="dim")
        return Panel(body, title="结果", border_style="green" if okish else "red")

    ok = bool(res.get("ok"))
    code = res.get("code")
    head = Text()
    head.append("✓ 完成" if ok else "✗ 未达成", style="bold green" if ok else "bold red")
    head.append(f"   code={code}", style="bold")
    mean = CODE_MEAN.get(code)
    if mean:
        head.append(f"（{mean}）", style="dim")
    head.append(f"   耗时 {res.get('dur')}s", style="dim")
    if res.get("dry"):
        head.append("   [dry 演练]", style="yellow")
    if res.get("error"):
        head.append(f"\n错误: {res['error']}", style="red")

    parts: list = [head]
    steps = res.get("steps") or []
    if steps:
        st = Table(box=None, show_header=True, header_style="dim", pad_edge=False)
        st.add_column("", no_wrap=True, width=2)
        st.add_column("节点", overflow="fold")
        for s in steps[-limit:]:
            st.add_row("⚠" if not s.get("ok") else "✓",
                       Text(str(s.get("t", "")), style="" if s.get("ok") else "yellow"))
        parts.append(st)
    shots = res.get("shots") or []
    if shots:
        parts.append(Text("留证: " + "  ".join(shots), style="dim"))
    if res.get("case"):
        parts.append(Text(f"用例: {res['case']}", style="dim"))
    return Panel(Group(*parts), title="结果", border_style="green" if ok else "red")


def hints() -> Text:
    t = Text()
    t.append("q", style="bold")
    t.append(" 退出   ", style="dim")
    t.append("r", style="bold")
    t.append(" 重跑上一个   ", style="dim")
    t.append("shots", style="bold")
    t.append(" 打开截图目录", style="dim")
    return t