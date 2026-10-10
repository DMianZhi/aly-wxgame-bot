# wxgame-bot 双层封装设计：rich TUI + JSON CLI

- 日期：2026-10-10
- 状态：待评审
- 相关：`wb/kit.py`、`wb/registry.py`、`tools/cases/*`、`main.py`

## 1. 背景与目标

现状：22 个每日用例只能逐个手跑（`uv run python tools/cases/xxx.py --flags`），且必须盯着裸日志看。
需要在其上加一层**产品外壳**，同时服务两类受众：

| 受众 | 要什么 |
|---|---|
| 人（操作者本人） | 看今天有哪些用例、各自额度，选一个跑，实时看进度和结果 |
| AI（"aiagain" 等 agent） | 结构化、稳定、可程序化地调用同一批能力，拿到 JSON 结果 |

### 成功标准

- 人：`uv run python -m wbtui` → 表格列出用例 → 菜单选中 → 实时日志 → 结果面板。
- AI：`uv run python tools/cases/void_rift.py --json` → **stdout 恰好一行 JSON**，stderr 是人类日志。
- 二者走**同一条命令、同一份契约**，不存在"界面能跑但 AI 调不通"的漂移。
- 用例的进程隔离、单实例锁、`--dry` 零副作用、看门狗全部原样保留。
- 新增依赖仅 `rich` 一个。

## 2. 非目标（YAGNI）

- ❌ 额度跟踪 / 历史记录（不建 `runlog.json`，不做"今日已跑 n/m"）。
- ❌ MCP server（要的话以后薄包一层 JSON CLI 即可，不预建）。
- ❌ Web UI。
- ❌ TUI 内直接 `import` 用例（会破坏"一个用例一个进程、失败不互相影响"的既有设计）。
- ❌ 自写 ANSI 面板 / 裸键读取（交给 rich，见 §3 决策）。

## 3. 关键决策与取舍

### 3.1 技术选型：为什么是 rich

| 方案 | 结论 |
|---|---|
| 零依赖自写 ANSI 面板 | ❌ 需自己处理 VT 开启（ctypes）、UTF-8、光标、按键（`msvcrt.getch()` 在 Git Bash 的 mintty 下**读不到键**）、双缓冲防闪 —— 代码量与维护面最大，正是"能用就行"要避开的 |
| **rich（采用）** | ✅ 渲染、表格、面板、Live 刷新、`Prompt.ask` 菜单全包；纯 Python 单依赖、成熟；**在所有终端（含 mintty）都能跑**，无需裸键模式 |
| Textual | ❌ 全屏交互 TUI，能力过剩、依赖更重 |

**代价**：rich 的交互是"菜单式"而非"全屏常驻面板"——每次操作后有清晰的表格/提示，不是那种 ↑↓ 光标实时游走的界面。对"选用例 → 跑 → 看日志"的流程完全够用，且**换来了跨终端可用性与可维护性**，符合"性价比优先、好维护优先"。

### 3.2 谁来持有进程：子进程（沿用方案 A）

TUI 通过 `subprocess` 起 `tools/cases/x.py … --json`，**不 import 用例**。理由：项目现有设计的核心卖点就是"一个用例独立进程、失败不互相影响"（见 `registry.py` 开头），且这样 TUI 与 AI 天然同路。

### 3.3 契约：stdout 只留 JSON

`wb/kit.py` 的 `log()` 当前写 stdout（`print(..., flush=True)`）。要让 stdout 只承载 JSON，必须把日志让到 stderr。

## 4. 架构总览

```
        ┌─── 唯一契约 ─────────────────────────────────┐
        │  uv run python tools/cases/x.py … --json      │
        │    stdout = 恰好一行 JSON（结果）              │
        │    stderr = 人类日志（原格式不变）             │
        └───────────────┬──────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
   人 ──┤ wbtui（rich：表格/菜单/Live 日志）│
        └───────────────────────────────┘
   AI ─ run 同一命令 → json.loads(stdout)
```

## 5. 内核改造（只动 `wb/kit.py` + `wb/registry.py`，**不碰 22 个用例**）

| 改动 | 内容 |
|---|---|
| `log()` | 输出改到 `sys.stderr`：`print(..., file=sys.stderr, flush=True)`。全局唯一改道点，终端照常可见；`2>&1` 可重定向。 |
| `--json` | 加入 `CORE_FLAGS`；`parse_args` → `Args.json_out`。 |
| 结果收集器 | 新增轻量 `Result`：`Screen.shot()` 自动登记 `shots`（零改用例）；`steps` 在 **v1 由日志前缀派生**（`⚠` / `✓` / `→` 开头的行）；另提供 `kit.note(msg, ok=True)` 供以后精化。 |
| `run_case` 收尾 | `finally` 之后，若 `json_out` → 向 stdout `print` 一行 `json.dumps({...})`；异常路径也保证有结果（`ok=false`, `code=1`, `error=...`）。 |
| `registry.py` | 新增一组 `ui`，登记 `wbtui`，使 smoke 清单校验与 README 结构块能覆盖到。 |

### 5.1 JSON 契约（v1，字段冻结）

```json
{
  "case": "void_rift",
  "title": "虚空裂隙-秘钥工坊（免费领取）",
  "ok": true,
  "code": 0,
  "dry": false,
  "dur": 41.2,
  "shots": ["vk_nothing.png"],
  "steps": [
    {"t": "免费不在槽位(已领/冷却/只有付费钮) → 留证收工", "ok": true}
  ],
  "error": null
}
```

- `code` 语义沿用 `run_case` 既有约定：`0 成功 / 1 未达成 / 2 环境问题 / 3 已有实例 / 4 超时`。
- `--json` 与 `--dry` 正交，`--dry --json` 合法（零副作用演练 + 结构化结果）。
- 字段一旦发布不删不改名，只增。

## 6. TUI：`wbtui/`（新增依赖 `rich`）

```
wbtui/
  __init__.py
  __main__.py   入口：菜单循环（表格 → Prompt.ask 选号 → 跑 → 回菜单）
  run.py        子进程运行器：起进程、流式读 stderr 喂 Live、解析 stdout JSON
  view.py       纯渲染函数：用例表 / 实时日志面板 / 结果面板 / 帮助
```

- **入口**：`uv run python -m wbtui`。
- **流程**：rich `Table` 列出 `registry.by_group("daily")`（序号 / 用途 / 额度 / 开关）→ `Prompt.ask` 选号 → 可选 `Confirm.ask` 问是否 dry（默认 dry，防误触真实消耗）→ `Live` 面板流式显示 stderr 日志 → 结束打印结果面板（✓/✗ + code + 耗时 + 留证截图名）→ 回菜单。
- **键位不再是键位**：一切通过 rich 的 prompt 实现（输入编号、`y/N`），因此无需裸模式，跨终端一致。
- **停止**：菜单里提供"停止当前任务"（在 `Live` 期间 `Ctrl+C` 捕获 → `terminate()` 子进程并显示已取消）。子进程在 Windows 下用 `taskkill /T /F` 确保孙进程一并回收。
- **看截图**：结果面板列出本次 `shots`，另给菜单项"打开最近截图"（`os.startfile`）。

## 7. 数据流

```
选号 r
  → run.py: subprocess.Popen([sys.executable, repo, *flags, "--json"], stderr=PIPE, stdout=PIPE, text=True)
  → 后台线程逐行读 stderr → queue
  → 主线程 Live 每 ~0.1s 刷新日志面板（新增行追加，尾部保留 N 行）
  → 进程退出：读 stdout → json.loads → 结果面板；异常/空 → 降级为"仅有退出码"
```

## 8. 错误处理

| 情况 | 表现 |
|---|---|
| 游戏窗口未开 | 内核返回 `code=2`，结果面板红字提示 |
| 已有实例在跑（锁） | `code=3`，提示"另一次任务正在运行"，非报错 |
| 用例未预期异常 | 内核已留证 `*_crash`，JSON 里带 `error`，面板展开显示 |
| stdout 非 JSON（老用例未迁移） | runner 捕获 `JSONDecodeError` → 降级显示退出码 + 日志尾部，不崩 |
| 终端过窄 | rich 自动截断；表格退化但可用 |
| Ctrl+C | 取消当前任务并回菜单；在菜单里再按一次则退出并恢复终端 |

## 9. 测试

1. **回归门槛**：`log` 改道后，**全部 20 个 selftest 必须全绿**（这是改道唯一的风险面）。
2. **契约测试**（新 selftest）：用假用例（`python -c 'print(json)'` 或桩）断言 stdout **恰好一行**可解析 JSON、字段齐全、stderr 承载日志。
3. **渲染测试**：`view.py` 的渲染写成纯函数 → 用 `rich.Console(record=True)` 导出文本做快照断言，不需要 TTY。
4. **runner 测试**：假命令验证 stderr 流式入队、退出码 → 状态映射、非 JSON 降级。

## 10. 实施顺序（小步，每步可回滚，每步一提交）

1. **kit**：`log`→stderr + `Result` + `--json` → 全 selftest 绿 + 手工验 1 个用例的 JSON。
2. **示范**：只给 `void_rift` 加一个 `note()`，评估派生 steps 的质量是否够用。
3. **TUI 骨架**：`view.py` 渲染 + `__main__.py` 菜单（先只列用例，不跑）。
4. **接 runner**：真跑 + Live 日志流 + 结果面板。
5. **收尾**：截图查看、Ctrl+C 停止、降级路径；更新 `registry.py`（ui 组）、README、`pyproject.toml`（加 `rich`）。

## 11. 验收

- [ ] `uv run python tools/cases/void_rift.py --json` → stdout 一行合法 JSON，字段符合 §5.1
- [ ] `uv run python tools/cases/void_rift.py --json 2>/dev/null` → 只有 JSON，无杂音
- [ ] `uv run python -m wbtui` → 列出 22 个用例；选号能真跑并实时看日志
- [ ] dry 默认开启，真跑需显式确认（防真实资源消耗）
- [ ] 原有 20 个 selftest 全绿 + 新增契约测试通过（合计 21）
- [ ] 没有引入 `rich` 之外的任何新依赖