#!/usr/bin/env python
"""离线自检: --json 契约（TUI/AI 双层封装的唯一接口）—— 零消耗，不碰游戏窗口。

被测的是 kit.run_case 的**子进程行为**（契约的另一半在进程之外）：
    stdout = 恰好一行结构化 JSON；stderr = 人类日志；退出码不变。
所以每个场景都真起一个子进程（探针脚本内 stub 掉窗口/截图/点击），
用「另起进程 + 分离两条管道」的方式验证 —— 这是唯一能测到「stdout 干净」的办法。

覆盖:
    ① 正常: --json 恰好一行、字段齐全、shots 自动登记、steps 前缀派生(⚠→ok=False)
    ② dry : --dry --json 正交可用（shots 为空, code=0）
    ③ 无窗口: 仍出 JSON（code=2, error 非空）—— 契约在失败路径上也要成立
    ④ 锁冲突: 仍出 JSON（code=3）
    ⑤ 人类模式: 不带 --json 时 **stdout 必须为空**（日志已全部让给 stderr）

用法:
    uv run python tools/selftest/json_contract_selftest.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LOCK = SHOTS_DIR / ".ct_probe.lock"          # 与探针里的用例名一致
SHOT = SHOTS_DIR / "_ct_boom.png"            # 探针留证截图（用完即删）
TS_RE = re.compile(r"\[\d\d:\d\d:\d\d\]")   # 人类日志行的时间戳前缀

PROBE_SRC = '''\
"""--json 契约探针：进程内 stub 掉窗口/截图/点击，只跑 run_case 的收尾路径。"""
import os
import sys

import numpy as np

sys.path.insert(0, {repo!r})
from wb import bot, kit


class _R:
    x = y = 0
    w, h = 812, 1518


_nogame = os.environ.get("CT_NOGAME") == "1"
_fail = os.environ.get("CT_FAIL") == "1"
bot.find_game_window = (lambda *a, **k: None) if _nogame else (lambda *a, **k: _R())
bot.grab_window = lambda rect: np.zeros((1518, 812, 3), dtype=np.uint8)
bot.click_xy = lambda *a, **k: None          # 双保险：绝不动鼠标
bot.drag_xy = lambda *a, **k: None
bot.configure_mouse = lambda *a, **k: None


def fn(sc, args):
    kit.log("普通日志不该进 steps")
    sc.shot("boom")                          # 应自动进 shots
    kit.log("→ 语义节点 A")
    kit.log("⚠ 不顺利节点 B")
    return not _fail


raise SystemExit(kit.run_case("ct_probe", "契约探针", fn, prefix="ct_", argv=sys.argv[1:]))
'''

FIELDS = {"case", "title", "ok", "code", "dry", "dur", "shots", "steps", "error"}


def _probe(argv: list[str], *, env: dict | None = None) -> subprocess.CompletedProcess:
    """起探针子进程；stdout/stderr 分离捕获（契约的关键就是这两条管道各司其职）。"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(PROBE_SRC.format(repo=str(REPO)))
        path = f.name
    try:
        full = dict(os.environ, PYTHONUTF8="1")   # 儿童进程也必须 UTF-8，否则中文 JSON 编码崩
        if env:
            full.update(env)
        return subprocess.run([sys.executable, path, *argv], cwd=str(REPO),
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=120, env=full)
    finally:
        Path(path).unlink(missing_ok=True)


def _one_json(p: subprocess.CompletedProcess) -> dict | None:
    """stdout 必须**恰好一行**可解析 JSON（多一行都算契约破裂）。"""
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    if len(lines) != 1:
        print(f"[!!] stdout 期望恰好 1 行, 实得 {len(lines)} 行: {lines[:3]}")
        return None
    try:
        return json.loads(lines[0])
    except json.JSONDecodeError as e:
        print(f"[!!] stdout 不是 JSON: {e} :: {lines[0][:200]}")
        return None


def case_normal(_rp):
    """① 正常路径：字段齐全 + shots 登记 + steps 前缀派生 + stdout 干净。"""
    p = _probe(["--json", "--no-back"])
    d = _one_json(p)
    if d is None:
        return False, "stdout 不是一行 JSON"
    probs = []
    if not FIELDS <= set(d):
        probs.append(f"缺字段 {FIELDS - set(d)}")
    if d.get("case") != "ct_probe" or d.get("title") != "契约探针":
        probs.append(f"case/title 不符 {d.get('case')}/{d.get('title')}")
    if d.get("ok") is not True or d.get("code") != 0:
        probs.append(f"ok/code 不符 {d.get('ok')}/{d.get('code')}")
    if d.get("dry") is not False:
        probs.append(f"dry 应为 False, 得 {d.get('dry')}")
    if d.get("shots") != [SHOT.name]:
        probs.append(f"shots 应自动登记 [{SHOT.name!r}], 得 {d.get('shots')}")
    if d.get("error") is not None:
        probs.append(f"error 应为 None, 得 {d.get('error')!r}")
    steps = d.get("steps") or []
    if [s.get("t") for s in steps] != ["→ 语义节点 A", "⚠ 不顺利节点 B"]:
        probs.append(f"steps 派生不符: {steps}")
    elif [s.get("ok") for s in steps] != [True, False]:
        probs.append(f"steps ok 判定不符(⚠ 应为 False): {steps}")
    if TS_RE.search(p.stdout):
        probs.append("stdout 混进了日志行（时间戳前缀）")
    if "普通日志不该进 steps" not in p.stderr or not TS_RE.search(p.stderr):
        probs.append("stderr 没承载人类日志")
    if not p.returncode == 0:
        probs.append(f"退出码 {p.returncode} != 0")
    return not probs, ("字段/推导全对, stdout 恰一行" if not probs else "; ".join(probs))


def case_dry(_rp):
    """② --dry 与 --json 正交：dry 时零留证、code 仍 0。"""
    SHOT.unlink(missing_ok=True)     # 清掉场景①留下的证据，否则「dry 没落盘」断言失去意义
    p = _probe(["--json", "--no-back", "--dry"])
    d = _one_json(p)
    if d is None:
        return False, "stdout 不是一行 JSON"
    probs = []
    if d.get("dry") is not True:
        probs.append(f"dry 应为 True, 得 {d.get('dry')}")
    if d.get("shots") != []:
        probs.append(f"dry 不该留证, 得 {d.get('shots')}")
    if d.get("ok") is not True or d.get("code") != 0:
        probs.append(f"ok/code 不符 {d.get('ok')}/{d.get('code')}")
    if SHOT.exists():
        probs.append("dry 却落了盘")
    return not probs, ("dry 正交: 零留证 + JSON 完好" if not probs else "; ".join(probs))


def case_nogame(_rp):
    """③ 失败路径也要出 JSON（AI 不能只对成功路径可解析）。"""
    p = _probe(["--json", "--no-back"], env={"CT_NOGAME": "1"})
    d = _one_json(p)
    if d is None:
        return False, "stdout 不是一行 JSON"
    probs = []
    if p.returncode != 2 or d.get("code") != 2:
        probs.append(f"应 code=2, 得 rc={p.returncode}/json={d.get('code')}")
    if d.get("ok") is not False or not d.get("error"):
        probs.append(f"ok/error 不符 {d.get('ok')}/{d.get('error')!r}")
    return not probs, (f"无窗口 → code=2 且 JSON 完好 (error={d.get('error')!r})"
                       if not probs else "; ".join(probs))


def case_locked(_rp):
    """④ 锁冲突路径也要出 JSON。"""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text("0", encoding="utf-8")     # 造一个「别人正在跑」的锁
    try:
        p = _probe(["--json", "--no-back"])
        d = _one_json(p)
    finally:
        LOCK.unlink(missing_ok=True)
    if d is None:
        return False, "stdout 不是一行 JSON"
    probs = []
    if p.returncode != 3 or d.get("code") != 3:
        probs.append(f"应 code=3, 得 rc={p.returncode}/json={d.get('code')}")
    if not d.get("error"):
        probs.append("error 应非空")
    return not probs, ("锁冲突 → code=3 且 JSON 完好" if not probs else "; ".join(probs))


def case_human_mode(_rp):
    """⑤ 不带 --json：stdout 必须**完全为空**（日志已全部改走 stderr）。"""
    p = _probe(["--no-back"])
    probs = []
    if p.stdout.strip() != "":
        probs.append(f"stdout 应为空, 得 {p.stdout[:200]!r}")
    if "普通日志不该进 steps" not in p.stderr:
        probs.append("stderr 没接到日志")
    if p.returncode != 0:
        probs.append(f"退出码 {p.returncode} != 0")
    return not probs, ("人类模式 stdout 干净、日志全在 stderr" if not probs else "; ".join(probs))


def _cleanup() -> None:
    SHOT.unlink(missing_ok=True)
    LOCK.unlink(missing_ok=True)


SCENES = [
    ("①--json 字段/推导/stdout 干净", [], case_normal),
    ("②--dry 与 --json 正交", [], case_dry),
    ("③无窗口仍出 JSON", [], case_nogame),
    ("④锁冲突仍出 JSON", [], case_locked),
    ("⑤人类模式 stdout 为空", [], case_human_mode),
]

if __name__ == "__main__":
    try:
        st.run_one("--json 契约自检（子进程双管道）", SCENES)
    finally:
        _cleanup()