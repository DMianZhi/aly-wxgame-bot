#!/usr/bin/env python
"""用例: 兑换码（工具箱小程序批量复制今日失效码 → 游戏内「设置/兑换」逐个兑换）。

链路（用户口径 2026-10-13）
    ① 工具箱小程序「Yang昜工具箱」→ 确保停在「兑换码」列表页
    ② 底部「批量复制」→ 弹窗里「今日失效」**默认已勾选** → 点「复制所选内容」
    ③ 读剪贴板（形如 `今日失效兑换码： A, B, C, D`）→ 解析出码列表
    ④ 回游戏：首页 → 齿轮(设置) → 兑换 → 【逐码】输入框输入 → 点「兑换」→ 关结果弹层
    ⑤ 关设置面板 → 回首页

⚠ 硬约束 / 踩过的坑（都实测过）
  - 小程序窗口**加载期宽度不稳**（实测 728 → 稳定后 1455）：必须等尺寸连续两次一致
    再动手，否则点击全落在错位画布上（第一次点「雷霆兑换码」没反应就是这个原因）。
  - 小程序是**页面栈**：当前页渲染在客户区**右半**（内容 728 宽，落在 x≈728..1455），
    左半是上一个页面的残留帧。所以「兑换码页」上的按钮坐标带 +728 的偏移。
  - 小程序与游戏**同一进程**（pid 相同，两个 HWND）→ 每次点击前必须切前台，
    wb.bot._guard_click 已内建（SetWindowPos 提 z 序 + 重试 SetForegroundWindow）。
  - 剪贴板是唯一数据通道：点「复制所选内容」后**轮询**剪贴板变化，不能写死 sleep。
  - 窗口尺寸与实测不一致时按比例换算（本机实测：游戏 826x1503 / 小程序 1455x1369）。
  - 兑换结果弹层未知：成功/失败/重复都要兜住并关掉，不因单个码失败中断整轮。

坐标来源: 本机实测客户区坐标（2026-10-13），随窗口尺寸按比例换算。
    NOTE 游戏侧坐标为「比例换算」口径（x·w/826, y·h/1503），已与 wb.bot.ref_to_client 一致。
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

# ⚠ 必须插在 import wb 之前: 批量跑器用「脚本路径」方式启动(python tools/cases/x.py)，
#   此时 sys.path[0]=tools/cases → 不加这行会 ModuleNotFoundError: No module named 'wb'
#   (2026-10-14 批量跑 [10/10] 实测炸在这里；用 -m 方式跑不会暴露)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot, kit  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from wb.kit import log, nap  # noqa: E402

# ---- 实测基准尺寸 ------------------------------------------------
GAME_W, GAME_H = 826, 1503          # 游戏客户区（实测）
# ⚠ 2026-10-14 复测更正: 小程序**真实窗口宽 731**（≈ TOOL_PANE 728）。旧值 1455 把
#   「小程序窗口 + 右侧游戏区」一起抓进来了（grab_window 拓超）→ 按 1455 换算时 x 被
#   缩掉一半（365 → 183），点入口打在空白上、永远进不了兑换码页（用户实跑多次失败的真因）。
#   实测：窗口稳定在 (731, 1369) at (917, 70)，且 100s 内不再变化。
TOOL_W, TOOL_H = 731, 1369          # 小程序客户区（实测，稳定态）
TOOL_PANE = 728                     # 小程序内容画布宽

TOOL_TITLE = "Yang昜工具箱"
TOOL_LNK = Path(r"C:\Users\21908\Desktop\Yang昜工具箱.lnk")   # 小程序桌面快捷方式
TOOL_WAIT = 75.0                    # 冷启动等待上限(微信拉起小程序 10~40s, 留足余量)

# ---- 小程序坐标（客户区实测，已含右半偏移）------------------------
# ⚠ 2026-10-14 全部重标（小程序真实窗口 731×1369）：旧值按误测的 1455 基准标注，
#   除 XY_HOME_CODE_ENTRY 恰好落在窗口内，其余 x 均 >731 → 永远点不到。
XY_HOME_CODE_ENTRY = (365, 700)     # 首页「雷霆兑换码」入口（实测有效）
XY_BATCH_COPY = (268, 1330)         # 底部工具栏「批量复制」（实测）
XY_COPY_SELECTED = (378, 768)       # 弹窗「复制所选内容」（实测；「今日失效」默认已勾选）
XY_BATCH_CLOSE = (378, 857)         # 弹窗「关闭」（实测）

# ---- 游戏坐标（客户区实测 @826x1503）------------------------------
XY_SETTING = (745, 1226)            # 首页右下角齿轮(设置)
XY_EXCHANGE = (553, 908)            # 设置面板「兑换」
XY_INPUT = (422, 766)               # 兑换码输入框
XY_INPUT_DONE = (316, 864)          # 「输入文字」弹窗的「完成」（确认文字，弹窗关闭）
XY_CONFIRM = (424, 895)             # 绿色「兑换」键（弹窗关闭后原位）
XY_DLG_X = (724, 665)               # 兑换码弹窗右上 X（**模态**：必须先关，否则遮罩吃掉面板 X）
XY_PANEL_X = (750, 347)             # 设置面板右上 X

CODE_RE = re.compile(r"[0-9A-Za-z]{6,12}")
CLIP_MARK = "兑换码"
SENTINEL = "__rd_sentinel__"       # 复制前写入剪贴板的哨兵（见 batch_copy 注释）


# ---------------------------------------------------------------- 工具
def _px(xy: tuple[int, int], w: int, h: int, bw: int, bh: int) -> tuple[int, int]:
    """实测客户区坐标 → 当前客户区坐标（按比例换算）。"""
    return round(xy[0] * w / bw), round(xy[1] * h / bh)


def tool_screen(dry: bool = False, wait: float = 20.0):
    """找小程序窗口；等它**稳定在就绪尺寸**（加载期会从窄变宽：728 → 1455）。

    wait: 最多等多少秒 —— 冷启动（刚拉起微信小程序）比就绪态久得多，故可调大。

    ⚠ 2026-10-14 踩坑（自动启动小程序后**必失败**的真因）：旧逻辑「尺寸连续两次一致就
      返回」会在**加载中间态 728 宽**上提前返回（728 能稳定好几秒且尺寸前后一致），
      于是坐标按 728 换算 → 点 (183,699) 打到空白（正确应 365）→ 永远进不了兑换码页。
      → 改为**必须达到就绪宽度**（TOOL_W 的 95%）才认，且仍需连续两次一致。
    """
    rect = None
    deadline = time.monotonic() + max(wait, 2.0)
    while time.monotonic() < deadline:
        cur = bot.find_game_window(TOOL_TITLE)
        if cur is None:
            if dry:
                break
            nap(1.0)
            continue
        ready = cur.w >= TOOL_W * 0.95        # 必须是就绪宽度, 不是加载中间态(728)
        if ready and rect is not None and (cur.w, cur.h) == (rect.w, rect.h):
            return kit.Screen(cur, dry=dry, prefix="rd_")
        rect = cur
        nap(1.0)
    return kit.Screen(rect, dry=dry, prefix="rd_") if rect else None


def launch_tool(dry: bool = False) -> bool:
    """自动拉起工具箱小程序（双击桌面快捷方式）—— 用例应自己启动，别让人先手动开。

    ⚠ 2026-10-14 用户要求：批量跑时小程序没开就 code=1 失败，应自己启动。
    dry 模式只打印计划不真启动；快捷方式不存在则提示手动打开。
    """
    if not TOOL_LNK.exists():
        log(f"⚠ 桌面快捷方式不存在: {TOOL_LNK} → 请手动打开小程序")
        return False
    log(f"小程序未开 → 自动启动: {TOOL_LNK.name}")
    if dry:
        log("[dry] 跳过实际启动")
        return True
    try:
        os.startfile(str(TOOL_LNK))          # Windows: 交 shell 关联打开 .lnk
    except Exception as e:                   # noqa: BLE001
        log(f"⚠ 启动失败: {e}")
        return False
    return True


def parse_codes(text: str) -> list[str]:
    """从剪贴板文本解析兑换码（去重、保序）。需要含「兑换码」标记。"""
    if CLIP_MARK not in text:
        return []
    head = text.split(CLIP_MARK, 1)[1]
    out: list[str] = []
    for m in CODE_RE.findall(head):
        if m not in out:
            out.append(m)
    return out


def codes_from_text(text: str) -> list[str]:
    """从任意文本取兑换码：优先按「兑换码」标记解析；否则按分隔符切分整段。

    两种写法都支持：
      - `今日失效兑换码： A, B, C`（小程序剪贴板原文）
      - `A, B, C`（--codes 直传的纯列表）
    """
    codes = parse_codes(text)
    if codes:
        return codes
    out: list[str] = []
    for tok in re.split(r"[,\s，、;；|]+", text):
        tok = tok.strip()
        if CODE_RE.fullmatch(tok) and tok not in out:
            out.append(tok)
    return out


def batch_copy(sc, wait: float = 8.0) -> list[str]:
    """批量复制「今日失效」码：点按钮 → 轮询剪贴板 → 解析。

    ⚠ 判据**不能**用「内容 != 上一次」：同一天重跑时上轮已把同一批码写进剪贴板，
    内容相同 → 会被误判成「复制失败」直接退出（2026-10-13 实测踩到）。
    改法：先把剪贴板写成**哨兵值**，只要之后出现「含『兑换码』标记且能解析出码」
    的内容就认成功 —— 无论它是否与历史内容相同。
    """
    try:
        import pyperclip
    except Exception:                                   # pragma: no cover
        log("✗ 缺 pyperclip，无法读剪贴板")
        return []
    try:
        pyperclip.copy(SENTINEL)                        # 清场：屏蔽旧内容干扰
    except Exception:
        pass
    sc.click_at(*_px(XY_BATCH_COPY, sc.w, sc.h, TOOL_W, TOOL_H), "批量复制")
    nap(1.5)
    sc.click_at(*_px(XY_COPY_SELECTED, sc.w, sc.h, TOOL_W, TOOL_H), "复制所选内容(今日失效)")
    end = time.time() + wait
    while time.time() < end:
        nap(0.5)
        now = pyperclip.paste()
        if now and now != SENTINEL:
            codes = parse_codes(now)
            if codes:
                log(f"剪贴板拿到 {len(codes)} 个今日失效码: {', '.join(codes)}")
                sc.click_at(*_px(XY_BATCH_CLOSE, sc.w, sc.h, TOOL_W, TOOL_H), "关闭批量复制弹窗")
                nap(0.8)
                return codes
    log("✗ 剪贴板未拿到兑换码（批量复制失败/今日无失效码）")
    return []


def ensure_code_page(sc) -> bool:
    """确保小程序停在「兑换码」列表页：用「今晚失效」标签模板判页。

    ⚠ 2026-10-14 用户要求「用例自己启动小程序」后跏到的坑：自动启动后窗口很快出现，
      但**内容还在加载** —— 旧代码只点一次、只等 3s 就判失败（实跑点完只隔 2s 就报
      「看不到今晚失效标签」）。改为「点入口 → 轮询等标签就绪 → 没出来就再点」。
    """
    if sc.find("rj_expire_tag") is not None:
        log("小程序已在兑换码页")
        return True
    for attempt in range(3):
        sc.click_at(*_px(XY_HOME_CODE_ENTRY, sc.w, sc.h, TOOL_W, TOOL_H),
                    "雷霆兑换码" + ("" if attempt == 0 else f"·重试{attempt + 1}"))
        for _ in range(12):                  # 最多等 ~24s（冷启动后小程序还在渲染）
            nap(2.0)
            if sc.find("rj_expire_tag") is not None:
                return True
        log("⚠ 已点入口但 24s 内没看到「今晚失效」标签 → 再试一次")
    return False


# ---------------------------------------------------------------- 游戏
def _g(xy: tuple[int, int], sc) -> tuple[int, int]:
    return _px(xy, sc.w, sc.h, GAME_W, GAME_H)


def open_redeem(sc) -> bool:
    """首页 → 齿轮(设置) → 兑换。返回是否打开兑换码弹窗。"""
    sc.click_at(*_g(XY_SETTING, sc), "设置(齿轮)")
    nap(2.5)
    sc.click_at(*_g(XY_EXCHANGE, sc), "兑换")
    nap(2.5)
    return True


def close_popups(sc) -> None:
    """处理兑换结果弹层。

    - 成功 → 全屏「恭喜获得」页，底部「领取」(claim_btn) → 点它收奖励；
    - 失败 → 提示弹层，绿「确认」与「兑换」同槽位 (424,895) → 点它关掉；
      ⚠ 失败文案**不止一种**（实测：「无效兑换码」/「无法重复使用同一个兑换码」）→ 两个模板都判；
    - 其他（稀有提示）→ popup_blue_x 兜底。

    ⚠ 漏判的后果是**连环失效**（2026-10-13 实测踩到）：弹层没被关掉，模态遮罩会把
      后续**每一轮**的点击全部吃掉 —— 表现为第 4~5 个码集体哑火、收尾回不了首页。
    本函数在无弹层时**幂等**（什么都不点），所以 redeem_one 开头也调一次清残层。
    """
    hit = sc.find("claim_btn", 0.90)
    if hit:
        sc.click(hit, "结果：领取(恭喜获得)")
        nap(1.5)
        return
    if sc.find_any(("rd_invalid_tag", "rd_repeat_tag"), 0.85)[0]:
        sc.click_at(*_g(XY_CONFIRM, sc), "结果：确认(兑换失败提示层)")
        nap(1.2)
        return
    hit = sc.find("popup_blue_x", 0.90)
    if hit:
        sc.click(hit, "结果：popup_blue_x")
        nap(1.2)


def redeem_one(sc, code: str, idx: int) -> bool:
    """输入一个码并点兑换；返回是否兑换成功（有「恭喜获得」页）。

    ⚠ 开头先 close_popups 清残层：上轮万一漏关（新文案/丢点击），模态遮罩会让本轮
      所有点击失效；无弹层时该函数幂等 → 安全。
    """
    close_popups(sc)                                # 清上一轮残留弹层（幂等）
    sc.click_at(*_g(XY_INPUT, sc), "兑换码输入框")
    nap(0.8)
    if not sc.dry and not bot.ime_english(sc.rect, sc.dry):
        log("⚠ 未能切换英文输入法（若输入冒出汉字，先手动切英文再跑）")
    bot.clear_text(sc.rect, sc.dry)                 # 弹窗会保留上一轮文字 → 必须先清
    bot.type_text(code, sc.rect, sc.dry, interval=0.08)
    nap(0.5)
    sc.click_at(*_g(XY_INPUT_DONE, sc), "输入弹窗「完成」")
    nap(1.0)
    sc.click_at(*_g(XY_CONFIRM, sc), f"兑换「{code}」")
    nap(2.5)
    ok = sc.dry or sc.find("claim_btn", 0.90) is not None
    sc.shot(f"redeem_{idx}_{code}_result")          # 留证结果弹层（成功/无效）
    close_popups(sc)
    sc.shot(f"redeem_{idx}_{code}_after")            # 关完成后补一张：可见输入框内容
    log(f"{'✓' if ok else '✗'} {code} → {'已兑换' if ok else '无效/重复'}")
    return ok


def close_panel(sc) -> None:
    """收尾：清结果弹层 → 关兑换码弹窗（模态）→ 关设置面板 → 复查弹层。

    ⚠ 两条实测教训（2026-10-13）:
      ① **顺序**：兑换码弹窗是模态，遮罩会把「设置面板 X」的点击吃掉 → 必须先关弹窗；
      ② 「无法重复」弹层漏判会连锁失效 → 收尾前先 close_popups 兜底清一次。
    ⚠ 不能拿 stage_btn 判「已回首页」：弹层是半透明遮罩，底下的「闯关模式」照样
      命中（实测 0.971 vs 正常 0.996）→ 会把残留弹层误判成已收尾。
    """
    close_popups(sc)                                # 兜底：清掉可能残留的结果弹层
    sc.click_at(*_g(XY_DLG_X, sc), "关兑换码弹窗")
    nap(1.0)
    sc.click_at(*_g(XY_PANEL_X, sc), "关设置面板")
    nap(1.2)
    still = (sc.find_any(("claim_btn", "rd_invalid_tag", "rd_repeat_tag"), 0.85)[0]
             or sc.find("popup_blue_x", 0.90) is not None)
    if still:
        log("⚠ 收尾仍见弹层 → 再关一轮")
        close_popups(sc)
        sc.click_at(*_g(XY_PANEL_X, sc), "关设置面板(补)")
        nap(1.2)


# ---------------------------------------------------------------- 主流程
def run(sc, args) -> bool:                              # noqa: C901
    # ① 取码：--codes 直传 优先；否则走小程序批量复制
    given = str(args.extra.get("codes") or "").strip()
    if given:
        codes = codes_from_text(given)
        log(f"--codes 直传 → {len(codes)} 个码: {', '.join(codes)}")
        if not codes:
            log("✗ --codes 里没解析出有效兑换码")
            return False
    else:
        tsc = tool_screen(args.dry)
        if tsc is None and not args.dry:
            # ⭐ 用户要求(2026-10-14): 小程序没开就**自己拉起**（桌面快捷方式），
            #   别让人先手动开——之前没开就 code=1 失败。
            if launch_tool(dry=False):
                tsc = tool_screen(dry=False, wait=TOOL_WAIT)
        if tsc is None:
            if args.dry:
                log("[dry] 小程序未开（实跑时会自动启动）→ 计划模式直接结束")
                return True
            log("✗ 找不到工具箱小程序窗口（Yang昜工具箱）→ 请确认微信已登录")
            return False
        if not ensure_code_page(tsc):
            log("✗ 未能进入小程序兑换码页（看不到「今晚失效」标签）")
            return False
        codes = batch_copy(tsc)
        if not codes:
            return False
    if not args.all and len(codes) > args.max:
        log(f"仅处理前 {args.max} 个（共 {len(codes)} 个，--max/--all 可调）")
        codes = codes[:args.max]

    # ② 回游戏：设置 → 兑换 → 逐码
    if sc.find("stage_btn") is None and not getattr(args, "no_home", False):
        kit.goto_home(sc)
    open_redeem(sc)
    codes = codes[:args.max] if not args.all else codes
    ok = 0
    for i, code in enumerate(codes, 1):
        log(f"[{i}/{len(codes)}] 兑换 {code}")
        if redeem_one(sc, code, i):
            ok += 1
    close_panel(sc)
    if not args.no_back:
        kit.goto_home(sc)
    log(f"兑换流程完成：{ok}/{len(codes)} 个码兑换成功")
    return ok > 0


PLAN = """
取码: --codes 直传直接用；否则小程序「Yang昜工具箱」: 确保在兑换码页
底部「批量复制」→「复制所选内容」(今日失效默认勾选) → 读剪贴板解析码
回游戏: 首页 → 齿轮(设置) → 兑换
逐个码: 点输入框 → 输入 → 点「兑换」→ 关结果弹层
关设置面板 → 回首页
"""


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "redeem_code", "兑换码（小程序批量复制今日失效码 → 游戏内兑换）", run,
        plan=PLAN, prefix="rd_", lock_ttl=1800, default_max=20,
        extra_kv=("--codes",),
    ))
