"""wbtui —— wxgame-bot 的交互外壳（基于 rich 的菜单式 TUI）。

设计要点（见 docs/superpowers/specs/2026-10-10-tui-cli-layer-design.md）:
    * 只做「选用例 → 跑 → 看日志/结果」，**不做额度跟踪**、不做全屏常驻面板。
    * 用例一律以**子进程**跑 `tools/cases/xxx.py … --json` —— 与 AI 走同一条命令，
      既保住「一个用例一个进程、失败不互相影响」的既有设计，也避免人机两套路径漂移。
    * 渲染层（view）是纯函数，可离线快照断言；运行层（run）负责子进程与实时日志。
"""