#!/usr/bin/env python
"""离线自检: wbtui（交互外壳）—— 零消耗，不碰游戏窗口，也不开真终端。

两层分别验证:
    渲染层 view.* 是纯函数 → 用 Console(record=True) 导出文本做快照断言，**不需要 TTY**；
    运行层 run.run_console 起一个**假用例子进程**（打印 stderr 日志 + stdout JSON），
    验证「实时收日志 + 解析结果 + 拿退出码」这条真实链路。

覆盖:
    ① 用例表列出注册表全部每日用例（数目 = registry.CASES，标题逐条在场）
    ② 结果面板：成功态(✓/code/留证/节点) 与 失败态(✗/error)，无结果时降级为退出码
    ③ 日志面板只保留尾部 N 行（长用例不会把屏幕撑爆）
    ④ stdout 解析容错：有噪声也取到那行 JSON；纯噪声 → None
    ⑤ 端到端：run_console 跑假用例 → 实时日志非空、结果 dict 完整、退出码 0

用法:
    uv run python tools/selftest/wbtui_selftest.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rich.console import Console  # noqa: E402

from wb import registry, selftest_kit as st  # noqa: E402
from wbtui import run as wrun  # noqa: E402
from wbtui import view  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# 假用例：往 stderr 喷日志、往 stdout 喷一行 JSON —— 模拟 kit.run_case 的管道行为
FAKE_CASE = '''\
import sys
import time
for i in range(1, 4):
    print(f"[00:00:0{i}] 步骤 {i}", file=sys.stderr, flush=True)
    time.sleep(0.02)
print("完全不成 JSON 的噪声行", file=sys.stderr, flush=True)
print('{"case":"fake","title":"假用例","ok":true,"code":0,"dry":false,'
      '"dur":0.1,"shots":["x.png"],"steps":[{"t":"a","ok":true}],"error":null}')
'''


def _render(renderable, *, width: int = 120) -> str:
    """把 rich 可渲染对象导出成纯文本（无 TTY、无颜色码），供断言用。"""
    c = Console(record=True, width=width, force_terminal=False, no_color=True)
    c.print(renderable)
    return c.export_text()


def case_cases_table(_rp):
    """① 用例表覆盖注册表全部每日用例。"""
    entries = registry.by_group(registry.DAILY)
    txt = _render(view.cases_table(entries))
    missing = [e.title for e in entries if e.title not in txt]
    n_rows = sum(1 for e in entries if str(e.quota) in txt or e.quota == "-")
    ok = not missing and len(entries) == len(registry.CASES)
    return ok, (f"条目 {len(entries)}/{len(registry.CASES)} 全渲染, 缺标题 {missing or '无'} "
                f"(额度可见 {n_rows})")


def case_result_panel(_rp):
    """② 结果面板成/败两态 + 降级态。"""
    good = {"case": "void_rift", "title": "虚空裂隙", "ok": True, "code": 0, "dry": False,
            "dur": 41.2, "shots": ["vk_nothing.png"],
            "steps": [{"t": "免费不在槽位", "ok": True}], "error": None}
    bad = dict(good, ok=False, code=1, error="未预期异常 Boom", shots=[])
    t_ok, t_bad = _render(view.result_panel(good)), _render(view.result_panel(bad))
    t_deg = _render(view.result_panel(None, rc=2, stderr_tail=["[00:00:01] 找不到窗口"]))
    probs = []
    for want in ("✓ 完成", "code=0", "成功", "留证", "vk_nothing.png", "免费不在槽位"):
        if want not in t_ok:
            probs.append(f"成功态缺 {want!r}")
    for want in ("✗ 未达成", "code=1", "未达成", "Boom"):
        if want not in t_bad:
            probs.append(f"失败态缺 {want!r}")
    for want in ("退出码 2", "结构化结果", "找不到窗口"):
        if want not in t_deg:
            probs.append(f"降级态缺 {want!r}")
    for txt in (t_ok, t_bad, t_deg):
        if "Traceback" in txt:
            probs.append("渲染炸了")
    return not probs, ("成功/失败/降级三态齐全" if not probs else "; ".join(probs))


def case_log_panel(_rp):
    """③ 日志面板只留尾部 N 行。"""
    lines = [f"[00:00:{i:02d}] 第 {i} 行" for i in range(30)]
    txt = _render(view.log_panel(lines, limit=5))
    probs = []
    if "第 29 行" not in txt or "第 25 行" not in txt:
        probs.append("尾部没保留")
    if "第 10 行" in txt:
        probs.append("没截断（超限行还在）")
    empty = _render(view.log_panel([]))
    if "等待输出" not in empty:
        probs.append("空日志提示缺失")
    return not probs, ("只留尾部 5 行 + 空态提示" if not probs else "; ".join(probs))


def case_parse_json(_rp):
    """④ stdout 解析容错。"""
    good = ['警告行', json.dumps({"ok": True}, ensure_ascii=False), '']
    noise = ["hello", "not json {", "{ 半截"]
    g = wrun._parse_json(good)
    n = wrun._parse_json(noise)
    ok = g == {"ok": True} and n is None
    return ok, f"有噪声取到 {g} / 纯噪声 → {n}"


def case_end_to_end(_rp):
    """⑤ 端到端：run_console 跑假用例。"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(FAKE_CASE)
        path = f.name
    try:
        console = Console(record=True, width=120, force_terminal=False, no_color=True)
        env = dict(os.environ, PYTHONUTF8="1")
        old = os.environ.copy()
        os.environ.update(env)
        try:
            res, rc, logs, interrupted = wrun.run_console(
                console, path, [], cwd=REPO, log_limit=10)
        finally:
            os.environ.clear()
            os.environ.update(old)
    finally:
        Path(path).unlink(missing_ok=True)
    probs = []
    if res is None or res.get("case") != "fake" or res.get("ok") is not True:
        probs.append(f"结果解析失败: {res}")
    if rc != 0:
        probs.append(f"退出码 {rc} != 0")
    if len(logs) < 4 or "步骤 1" not in " ".join(logs):
        probs.append(f"stderr 日志没收全: {logs}")
    if interrupted:
        probs.append("不该被判为中断")
    return not probs, (f"结果={res and res.get('case')} rc={rc} 日志 {len(logs)} 行"
                       if not probs else "; ".join(probs))


def case_multi_select_render(_rp):
    """⑥ 多选渲染: 勾选行带 ✔、表头多「选」列、未选行没有。"""
    entries = registry.by_group(registry.DAILY)
    txt = _render(view.cases_table(entries, selected={0, 2}, cursor=1))
    n_check = txt.count("✔")
    probs = []
    if n_check != 2:
        probs.append(f"✔ 数 {n_check} != 2")
    if "选" not in txt.splitlines()[2]:
        probs.append("「选」列表头缺失")
    plain = _render(view.cases_table(entries))
    if "✔" in plain:
        probs.append("纯展示模式不该出现 ✔")
    return not probs, ("勾选 2 处 + 选列存在 + 纯展示无 ✔" if not probs else "; ".join(probs))


def case_summary_table(_rp):
    """⑦ 批量汇总面板: 成功/失败/被中断+dry 标记。"""
    rows = [
        {"title": "用例A", "ok": True, "code": 0, "dur": 1.2, "dry": False, "interrupted": False},
        {"title": "用例B", "ok": False, "code": 1, "dur": 3.4, "dry": True, "interrupted": False},
        {"title": "用例C", "ok": False, "code": 0, "dur": 0.5, "dry": True, "interrupted": True},
    ]
    txt = _render(view.summary_table(rows))
    probs = []
    for want in ("完成 1/3", "用例A", "用例B", "用例C", "被中断", "dry", "✗"):
        if want not in txt:
            probs.append(f"缺 {want!r}")
    if "1.2s" not in txt or "3.4s" not in txt:
        probs.append("耗时列缺失")
    return not probs, ("汇总三态齐全" if not probs else "; ".join(probs))


def case_run_batch(_rp):
    """⑧ 批量顺序执行: _run_batch 依序跑 2 个假用例(dry) + 汇总面板。"""
    from types import SimpleNamespace
    paths = []
    for tag in ("A", "B"):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as f:
            f.write(FAKE_CASE)
            paths.append(f.name)
    entries = [SimpleNamespace(repo=p, title=f"假用例{t}") for t, p in zip(("A", "B"), paths)]
    console = Console(record=True, width=120, force_terminal=False, no_color=True)
    try:
        m = __import__("wbtui.__main__", fromlist=["_run_batch"])
        m._run_batch(console, entries, dry=True)
    finally:
        for p in paths:
            Path(p).unlink(missing_ok=True)
    txt = console.export_text()
    probs = []
    for want in ("[1/2]", "[2/2]", "假用例A", "假用例B", "批量执行汇总", "完成 2/2"):
        if want not in txt:
            probs.append(f"缺 {want!r}")
    if txt.index("假用例A") > txt.index("假用例B"):
        probs.append("执行顺序不对(A 应在 B 前)")
    return not probs, ("依序 2/2 + 汇总齐全" if not probs else "; ".join(probs))


SCENES = [
    ("①用例表覆盖注册表", [], case_cases_table),
    ("②结果面板三态", [], case_result_panel),
    ("③日志面板尾部截断", [], case_log_panel),
    ("④stdout 解析容错", [], case_parse_json),
    ("⑤端到端: 假用例实时日志+结果", [], case_end_to_end),
    ("⑥多选勾选渲染", [], case_multi_select_render),
    ("⑦批量汇总面板三态", [], case_summary_table),
    ("⑧批量顺序执行(dry)", [], case_run_batch),
]

if __name__ == "__main__":
    st.run_one("wbtui 离线自检（渲染纯函数 + 子进程运行层）", SCENES)