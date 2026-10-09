#!/usr/bin/env python
"""用例: 冒烟测试 —— 配置 / 合成模板匹配 / 窗口枚举 / 拟人点击 dry-run / 注册表一致性 / 全脚本可导入。

不真实点击屏幕，不需要游戏在运行。任一项失败即 exit 1。
用法: uv run python tools/selftest/smoke.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def check_config(errors: list[str]) -> None:
    try:
        from wb.cfg import CONF

        assert 0 < CONF.threshold < 1
        assert CONF.jitter_px >= 0
        assert CONF.delay_min <= CONF.delay_max
        print(f"[ok] 配置: threshold={CONF.threshold} jitter={CONF.jitter_px}px "
              f"delay=({CONF.delay_min}~{CONF.delay_max}s)")
    except Exception as e:  # noqa: BLE001
        errors.append(f"config: {e}")


def check_match(errors: list[str]) -> None:
    """合成模板匹配: 大图里截一块，应精确命中。"""
    try:
        import numpy as np

        from wb.bot import match_template

        rng = np.random.default_rng(7)
        screen = rng.integers(0, 255, (900, 1600, 3), dtype=np.uint8)
        tpl = screen[300:360, 700:790].copy()
        hit = match_template(screen, tpl, 0.86)
        assert hit is not None, "合成模板应命中"
        cx, cy, score = hit
        assert abs(cx - 745) <= 1 and abs(cy - 330) <= 1, f"中心偏差: ({cx},{cy})"
        assert score > 0.99
        print(f"[ok] 模板匹配: 中心=({cx},{cy}) score={score:.4f}")
    except Exception as e:  # noqa: BLE001
        errors.append(f"match: {e}")


def check_window(errors: list[str]) -> None:
    """窗口枚举: 不存在的进程必须返回 None。"""
    try:
        from wb.bot import find_game_window

        assert find_game_window("不存在的窗口标题XYZ", "NoSuchProc.exe") is None
        print("[ok] 窗口枚举: 无命中时正确返回 None")
    except Exception as e:  # noqa: BLE001
        errors.append(f"window: {e}")


def check_click(errors: list[str]) -> None:
    try:
        from wb.bot import WinRect, click_xy

        click_xy(400, 300, 6, (0.0, 0.0), WinRect(x=0, y=0, w=800, h=600), dry_run=True)
        print("[ok] dry-run 点击路径无异常")
    except Exception as e:  # noqa: BLE001
        errors.append(f"act: {e}")


def check_registry(errors: list[str]) -> None:
    """注册表 ↔ 文件系统 双向一致（新增用例忘登记会被这里抓住）。"""
    try:
        from wb import kit, registry as R

        assert not R.missing_files(), f"注册了但文件不在: {R.missing_files()}"
        assert not R.unregistered(), f"有脚本但没登记(去 wb/registry.py 补一行): {R.unregistered()}"
        assert callable(kit.run_case) and R.render_table(R.DAILY) and R.render_structure()
        print(f"[ok] 注册表一致 {len(R.ALL)} 个脚本（用例 {len(R.CASES)} / 裁剪 "
              f"{len(R.CROPS)} / 测试 {len(R.SELFTESTS)} / 维护 {len(R.MAINT_TOOLS)}）")
    except Exception as e:  # noqa: BLE001
        errors.append(f"registry: {e}")


def check_import_all(errors: list[str]) -> None:
    """每个登记脚本都能被导入 —— 挪目录/改引导/漏依赖会被这里一次性抓住。"""
    try:
        from wb import registry as R

        bad = []
        for e in R.ALL:
            if e.name == "smoke":        # 别递归自己
                continue
            try:
                importlib.import_module(e.repo[:-3].replace("/", "."))
            except Exception as ex:  # noqa: BLE001
                bad.append(f"{e.repo}: {type(ex).__name__}: {ex}")
        assert not bad, f"导入失败: {bad}"
        print(f"[ok] 全部 {len(R.ALL) - 1} 个脚本可导入（跳过正在运行的 smoke 自身）")
    except Exception as e:  # noqa: BLE001
        errors.append(f"import: {e}")


def check_doc_counts(errors: list[str]) -> None:
    """注册表 docstring 里的手写计数必须与实际条目数一致。

    这类漂移真发生过(一次写 10、实际 12)，而且不报错 —— 只有人对一眼才发现。
    真值一律来自 registry.counts()，手写的那行只当「人话」。
    """
    try:
        import re

        from wb import registry as R

        got = R.counts()
        text = R.__doc__ or ""
        wrote = {m.group(1): int(m.group(2))
                 for m in re.finditer(r"^\s+(daily|crop|selftest|maint)\s+(\d+)\s+个",
                                      text, re.M)}
        assert wrote, "docstring 里没找到分组计数行（格式改了？）"
        bad = [f"{g}: docstring 写 {wrote.get(g)} / 实际 {n}" for g, n in got.items()
               if wrote.get(g) != n]
        assert not bad, f"docstring 计数漂移 → {bad}"
        print("[ok] docstring 计数与注册表一致（" +
              " / ".join(f"{g} {n}" for g, n in got.items()) + "）")
    except Exception as e:  # noqa: BLE001
        errors.append(f"doc-count: {e}")


def main() -> int:
    errors: list[str] = []
    for fn in (check_config, check_match, check_window, check_click, check_registry,
               check_doc_counts, check_import_all):
        fn(errors)
    if errors:
        print("FAIL:", *errors, sep="\n  - ")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
