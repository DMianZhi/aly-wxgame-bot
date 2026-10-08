#!/usr/bin/env python
"""文档生成: 把 wb/registry.py 的清单写进 README.md 的标记区。

动机: 用例清单以前是手抄的 —— 新增一个用例要同时改脚本、smoke 的 CASES、README 表格，三处漏一处就漂移。
现在清单只在 wb/registry.py 定义一次，README 里由本脚本从标记区生成：

    <!-- BEGIN:CASES -->     ...由 docs.py 重写...
    <!-- END:CASES -->
    <!-- BEGIN:STRUCTURE --> ...由 docs.py 重写...
    <!-- END:STRUCTURE -->

用法:
    uv run python tools/maint/docs.py           # 生成/更新 README 清单区
    uv run python tools/maint/docs.py --check   # 只校验是否已同步（不同步 exit 1，CI/收尾自检用）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from wb import registry as R  # noqa: E402

README = ROOT / "README.md"
BANNER = f"<!-- 以下清单由 tools/maint/docs.py 自动生成，请勿手改；改清单请改 wb/registry.py -->"


def _block(body: str, note: str = BANNER) -> str:
    return f"{note}\n\n{body}"


def render_cases() -> str:
    parts = [
        "## 用例清单",
        "",
        "全部脚本在 `tools/` 下按角色分四组；**一个用例一个文件**，互不影响。",
        "新增用例：① 在对应目录丢一个 `.py`（建议直接抄同组最像的那个当模板）"
        "② 在 `wb/registry.py` 登记一行 —— smoke 与本文档会自动跟上。",
        "",
    ]
    for g in (R.DAILY, R.CROP, R.SELFTEST, R.MAINT):
        parts += [R.render_table(g), ""]
    return "\n".join(parts).rstrip()


def render_structure() -> str:
    return _block(R.render_structure(), note="<!-- 目录结构由 tools/maint/docs.py 生成 -->")


def apply_section(text: str, tag: str, body: str) -> tuple[str, bool]:
    begin, end = f"<!-- BEGIN:{tag} -->", f"<!-- END:{tag} -->"
    if begin not in text or end not in text:
        raise SystemExit(f"README 里找不到标记 {begin} / {end}，请先补上")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    new = f"{head}{begin}\n{body}\n{end}{tail}"
    return new, new != text


def main() -> int:
    check = "--check" in sys.argv[1:]
    text = README.read_text(encoding="utf-8")
    text, c1 = apply_section(text, "CASES", render_cases())
    text, c2 = apply_section(text, "STRUCTURE", render_structure())
    if check:
        if c1 or c2:
            print("README 清单与注册表不同步 → 跑一次: uv run python tools/maint/docs.py")
            return 1
        print("[ok] README 清单与 wb/registry.py 一致")
        return 0
    README.write_text(text, encoding="utf-8")
    print(f"[ok] README 已更新（用例 {len(R.CASES)} / 裁剪 {len(R.CROPS)} / 测试 "
          f"{len(R.SELFTESTS)} / 维护 {len(R.MAINT_TOOLS)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
