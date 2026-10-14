"""用例运行时脚手架（kit）—— 所有 tools/cases/*.py 共用的底座。

一个用例只该写「本页怎么认、点哪里、什么算成功」，其余都是样板：本模块把样板收干净。

对外能力
    log / banner      统一日志前缀（[HH:MM:SS]）
    nap / now         统一等待与时钟（离线自检可整体打桩成虚拟时钟，别直接用 time.*）
    Screen            一次截屏批量匹配（含 _v2 变体 + TEMPLATE_MIN）、等页、点击、留证、判层
    single_instance   同名用例互斥（防两个实例各点一次 → 重复花次数）
    ad_flow           广告/免广告两种形态的通用状态机（跳过卡 → 播放 → 到账 → 关闭 → 领取）
    claim_if_present  「恭喜获得」→ claim_btn
    is_home/goto_home 首页判定（只用 stage_btn！nav_home 在子页也命中）+ 收尾回首页
    parse_args/run_case  统一 CLI（--dry/--max/--times/--no-back/--yes/--timeout）+ 用例入口

设计约束（踩过的坑，别改回去）
    * 模板匹配一律经 _bot.find_in_game / 本模块 look()，不要自己抄 match_adaptive，
      否则会漏掉 TEMPLATE_MIN（如 ad_rewarded 必须 ≥0.93，否则广告还在播就点关闭）。
    * 所有 bot 调用都走 `_bot.xxx` 属性访问，便于离线自检整体替换（monkeypatch）。
    * dry 模式零副作用：不点击、不写锁、不落截图（除非 force=True）。
    * --timeout 是**硬**看门狗：Screen 每次取帧前 tick，超时抛 CaseTimeout，
      由 run_case 统一留证 + 收尾回首页，避免用例卡死拖着不退出。
"""
from __future__ import annotations

import contextlib
import ctypes
import json
import os
import sys
import time

try:                                     # 急停异常: 鼠标甩到屏幕角落时 pyautogui 抛出
    from pyautogui import FailSafeException
except Exception:                        # 无 GUI 环境(离线自检/CI) 的占位，永不抛出
    class FailSafeException(Exception):  # type: ignore[no-redef]
        pass
from dataclasses import dataclass, field
from pathlib import Path

from . import bot as _bot
from .cfg import APP_DIR, CONF, SHOTS_DIR

# ---------------------------------------------------------------- 阈值

TH = CONF.threshold      # 通用阈值(0.86)
TH_STRICT = 0.92         # 「领取/确定」这类多页同款键，抬阈值防串台
TH_LOOSE = 0.80          # 半透明弹层里的元素，分数略降

# ---------------------------------------------------------------- 日志


def log(msg: str, *, _step: bool = True) -> None:
    """统一日志 —— **一律写 stderr**，把 stdout 完整让给 --json 结果。

    （2026-10-10 改道：之前写 stdout，导致 --json 模式下 AI 侧无法
     `json.loads(stdout)`。终端里 stderr 照常可见，`2>&1` / `2>/dev/null` 可自由重定向。）

    副作用：_step=True 时，若本行是「语义节点」（以 ⚠/✗/✓/√/→ 开头），自动登记进
    --json 的 steps（v1 的零侵入做法，见 Result）。
    """
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
    if _step and CURRENT is not None and msg.lstrip().startswith(STEP_PREFIX):
        ok = not msg.lstrip().startswith(("⚠", "✗"))
        CURRENT.add_step(msg, ok)


def banner(title: str, *, plan: str = "", dry: bool = False) -> None:
    log(f"=== {title} ===")
    if dry and plan:
        for line in plan.strip().splitlines():
            log(line)


# ---------------------------------------------------------------- 结果收集（--json）

# 「语义节点」前缀：这些开头的日志行自动进 steps（ok 判定：⚠/✗ 视为不顺利）
STEP_PREFIX = ("⚠", "✗", "✓", "√", "→")
STEP_MAX = 100      # steps 上限（防个别用例刷屏把 JSON 撑大）


class Result:
    """一次用例运行的机读结果 = --json 契约的载荷。

    零侵入用例：shots 由 Screen.shot() 自动登记；steps 由 log() 的语义节点行派生。
    用例若想主动补充更精确的节点，调 kit.note()。
    """

    def __init__(self, case: str, title: str, dry: bool, started: float):
        self.case = case
        self.title = title
        self.dry = dry
        self.started = started
        self.shots: list[str] = []
        self.steps: list[dict] = []
        self.error: str | None = None

    def add_shot(self, name: str) -> None:
        if name not in self.shots:
            self.shots.append(name)

    def add_step(self, text: str, ok: bool = True) -> None:
        if len(self.steps) >= STEP_MAX:
            return
        self.steps.append({"t": text.strip(), "ok": bool(ok)})

    def as_dict(self, ok: bool, code: int) -> dict:
        return {
            "case": self.case,
            "title": self.title,
            "ok": bool(ok),
            "code": int(code),
            "dry": self.dry,
            "dur": round(now() - self.started, 1),
            "shots": self.shots,
            "steps": self.steps,
            "error": self.error,
        }


CURRENT: "Result | None" = None     # run_case 运行期间指向本次收集器，其余时刻为 None


def note(text: str, ok: bool = True) -> None:
    """用例主动登记一个语义节点：正常记日志 + 进 --json 的 steps（避免被前缀规则漏掉）。"""
    log(text, _step=False)
    if CURRENT is not None:
        CURRENT.add_step(text, ok)


class CaseTimeout(RuntimeError):
    """用例总时长超限（看门狗）。"""


def nap(seconds: float) -> None:
    """等待（用例统一走这里；离线自检会把 sleep 变空转，避免真等）。"""
    time.sleep(seconds)


def now() -> float:
    """当前时间戳（秒）。用例里的等待/超时**一律走这里**，别直接 time.time()。

    离线自检把 wb.kit.time 换成带虚拟时钟的替身（selftest_kit._ShimTime）：它的
    sleep 不真睡、只把时长计入 vt，now() = 真实时间 + vt。于是「局内等 210 秒」
    这类靠时间推进的分支能在毫秒内跑完，而用例的判据逻辑一字不改。

    取法很讲究：真实 time 模块**没有** now 属性 → 落到 time.time()；替身有 → 走它的
    虚拟时钟。所以同一个 now() 在两种环境下都正确，不需要任何 if。
    """
    return getattr(time, "now", time.time)()


# ---------------------------------------------------------------- 单实例锁

LOCKS_DIR = APP_DIR / "shots"


def _pid_alive(pid: int) -> bool:
    """pid 对应进程是否还活着（Windows: OpenProcess 探测, 零依赖）。"""
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return False
    ctypes.windll.kernel32.CloseHandle(h)
    return True


@contextlib.contextmanager
def single_instance(name: str, ttl: float = 600.0, *, dry: bool = False):
    """同名用例互斥：已有实例在跑就退出（防重复花每日次数/重复领取）。

    锁 = shots/.<name>.lock，内容写 pid；超过 ttl 视为残留锁可接管（进程被 kill 等）。
    dry 模式不落锁（零副作用）。

    2026-10-12 补 pid 存活检测: 强杀(如 TUI Ctrl+C 停子进程)时 finally 不会跑,
    锁会残留 —— 旧逻辑在 ttl 内一律退出, 实测残留锁害得后续 3600s 全部 code=3
    (锁里 pid 24488 早已死亡)。现在 pid 已死 = 残留锁 → 立即接管, 不看年龄。
    """
    lock = LOCKS_DIR / f".{name}.lock"
    if dry:
        yield True
        return
    if lock.exists():
        # 这里比的是**文件 mtime**（真实世界的时间）→ 必须用真实时钟，不能用 now()
        # （离线自检下 now() 含虚拟偏移，会把锁年龄算错）
        age = time.time() - lock.stat().st_mtime
        try:
            old_pid = int(lock.read_text(encoding="utf-8").strip() or 0)
        except ValueError:
            old_pid = 0
        if _pid_alive(old_pid):
            if age < ttl:
                log(f"已有实例在跑(pid {old_pid}, 锁 {lock.name} 年龄 {age:.0f}s < {ttl:.0f}s) "
                    f"→ 退出，避免重复操作")
                yield False
                return
            log(f"锁已过期({age:.0f}s)但 pid {old_pid} 仍在 → 视为卡死, 接管")
        else:
            log(f"残留锁(pid {old_pid} 已退出, 年龄 {age:.0f}s) → 接管")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield True
    finally:
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------- 屏幕


class Screen:
    """游戏窗口的一层薄封装：一次截屏匹配多个模板 + dry 感知的点击。

    用法:
        sc = Screen(rect, dry=dry)
        hit = sc.find("turn_daily")        # 单模板
        st  = sc.look("turn_daily", "turn_paid")   # 一次截屏匹配多个(省截屏)
        sc.click(hit, "中心键")
        sc.wait("turn_claim", 30)
    """

    def __init__(self, rect, *, th: float = TH, dry: bool = False, prefix: str = "",
                 deadline: float | None = None, jitter: int = 2,
                 delay: tuple[float, float] = (0.12, 0.35)):
        self.rect = rect
        self.th = th
        self.dry = dry
        self.prefix = prefix          # 留证截图前缀: shots/_<prefix><tag>.png
        self.deadline = deadline      # 绝对时间戳；None = 不限时
        self.jitter = jitter
        self.delay = delay
        self.planned: list[tuple[str, int, int]] = []   # dry 模式记录的计划点击
        self.clicks: list[tuple[str, int, int]] = []    # 实跑记录

    # ---- 取帧 / 匹配 ------------------------------------------------
    @property
    def w(self) -> int:
        """客户区宽（兼容 WinRect 对象与裸 tuple，离线自检用 tuple）。"""
        v = getattr(self.rect, "w", None)
        return int(v) if v else int(self.rect[2] - self.rect[0])

    @property
    def h(self) -> int:
        """客户区高（同上兼容）。"""
        v = getattr(self.rect, "h", None)
        return int(v) if v else int(self.rect[3] - self.rect[1])

    def _tick(self) -> None:
        if self.deadline is not None and now() > self.deadline:
            raise CaseTimeout("用例总时长超限")

    def grab(self):
        """截取当前窗口画面（离线自检会替换掉 _bot.grab_window）。"""
        self._tick()
        return _bot.grab_window(self.rect)

    def look(self, *names: str, th: float | None = None) -> dict:
        """一次截屏，批量匹配多个模板；返回 {name: (x, y, score) | None}。

        阈值取 max(th 或 self.th, TEMPLATE_MIN[name])，与 find_in_game 语义一致。
        """
        img = self.grab()
        floor = self.th if th is None else th
        out: dict = {}
        for n in names:
            out[n] = _bot.find_on_frame(img, n, floor)
        return out

    def find(self, name: str, th: float | None = None):
        """单模板查找；返回 (x, y, score) 或 None。"""
        return self.look(name, th=th)[name]

    def page(self, *names: str, th: float | None = None):
        """判页/判层：返回第一个命中的模板名（并记分），都没命中返回 None。"""
        st = self.look(*names, th=th)
        for n in names:
            if st[n] is not None:
                log(f"  页面={n} score={st[n][2]:.3f}")
                return n
        return None

    def find_any(self, names: tuple[str, ...] | list[str], th: float | None = None):
        """多模板查找，按给定顺序取第一个命中；返回 (hit, 模板名) 或 (None, None)。

        用于「同一目标有多个变体」的判定，如 free_star 的金币
        (ex_coin 本体 / ex_coin_v2 含红点) —— 本体优先。
        """
        st = self.look(*names, th=th)
        for n in names:
            if st[n] is not None:
                return st[n], n
        return None, None

    def wait(self, name: str, timeout: float, interval: float = 1.0, th: float | None = None):
        """等模板出现；超时返回 None。dry 不点击 → 不会跳页，只查一次。"""
        end = now() + timeout
        while True:
            hit = self.find(name, th=th)
            if hit is not None:
                return hit
            if self.dry:
                return None
            if now() >= end:
                return None
            time.sleep(interval)

    def wait_gone(self, name: str, timeout: float, interval: float = 1.0):
        """等模板消失；返回是否消失。dry 不点击 → 只查一次。"""
        end = now() + timeout
        while True:
            if self.find(name) is None:
                return True
            if self.dry:
                return False
            if now() >= end:
                return False
            time.sleep(interval)

    # ---- 动作 ------------------------------------------------------
    def click(self, hit, what: str, *, note: str = "") -> None:
        """点一个匹配结果。dry 模式只登记计划，不碰鼠标。"""
        x, y, score = hit[0], hit[1], hit[2]
        self.planned.append((what, x, y))
        if self.dry:
            log(f"[dry] 会点 {what} @({x},{y}) score={score:.3f}")
            return
        log(f"点击 {what} @({x},{y}) score={score:.3f}" + (f" · {note}" if note else ""))
        self.clicks.append((what, x, y))
        _bot.click_xy(x, y, self.jitter, self.delay, self.rect, False)

    def click_at(self, x: int, y: int, what: str) -> None:
        """按坐标点（用于颜色判态等非模板定位的场景）。

        ⚠️ 这里吃的是**当前客户区坐标**：模板命中的坐标（match_adaptive 已反映射）
        以及像素检测算出来的坐标都必须走这里。手写的**基准坐标常量**请走 click_base。

        窗口外的坐标直接报错 —— 这正是「基准常量当客户区用」的典型后果
        （601 宽窗口下 x=740 落在窗外），以前会静默点空、只表现为「这个键没反应」。
        """
        if not (0 <= x <= self.w and 0 <= y <= self.h):
            raise ValueError(
                f"{what}: 客户区坐标 ({x},{y}) 落在窗口外 (客户区 {self.w}x{self.h})。"
                f"基准坐标常量请用 click_base / sc.roi")
        self.click((x, y, 1.0), what)

    def click_base(self, x: int, y: int, what: str) -> None:
        """按**基准坐标**点（845x1521 下标出来的常量），自动换算到当前客户区。

        基准坐标直接当客户区坐标用是错的：顶部标题栏 77px 不随窗口缩放，
        窗口越小偏得越离谱（601 宽时 x=740 直接点到窗口外）。详见 bot.ref_to_client。
        """
        self.click_at(*_bot.ref_to_client(x, y, self.w, self.h), what)

    def _by(self, y: int) -> int:
        """基准 y → 当前客户区 y（拖拽用；x 另算）。"""
        return _bot.ref_to_client(0, y, self.w, self.h)[1]

    def roi(self, x: int, y: int, w: int, h: int, img=None):
        """按**基准坐标**取当前帧的一块区域（像素判态/裁剪用），自动换算。

        img 传入可复用同一帧（一帧扫多处）。"""
        bx, by, bw, bh = _bot.ref_rect_to_client(x, y, w, h, self.w, self.h)
        return (self.grab() if img is None else img)[by:by + bh, bx:bx + bw]

    def tap(self, name: str, *, th: float | None = None, wait: float = 1.6,
            tries: int = 3, label: str | None = None) -> bool:
        """找模板 → 点 → 等页面反应；找不到就短暂重试（0.6s 一探）。

        重试是给「点吞」「动画未稳」用的；wait 是点完等下页的时间。
        返回是否点到（用例里的 tap/tap_xy 都收在这里，别再各写一份重试循环）。
        """
        for _ in range(max(1, tries)):
            hit = self.find(name, th)
            if hit:
                self.click(hit, label or name)
                nap(wait)
                return True
            nap(0.6)
        log(f"✗ 未找到 {label or name}")
        return False

    def drag_base(self, x1: int, y1: int, x2: int, y2: int, **kw) -> None:
        """按**基准坐标**拖拽（两个端点都换算，与上方的 _by 同一口径）。

        拖拽是游戏交互（滑列表/拖战机），和点击一样只允许这一处换算。
        """
        _bot.drag_xy(*_bot.ref_to_client(x1, y1, self.w, self.h),
                     *_bot.ref_to_client(x2, y2, self.w, self.h), self.rect, self.dry, **kw)

    def find_all(self, name: str, th: float | None = None, max_hits: int = 4,
                 gap_ratio: float = 0.8) -> list[tuple[int, int, float]]:
        """多命中的同款模板检测（如两卡美术一致），按 x 升序返回。

        NMS: 命中后把该区域涂黑再找，抑制半径 = 模板长边 × gap_ratio。
        用于「同名图标有多份、要逐个消费」的场景（寻宝双宝箱）。
        """
        import cv2

        from .bot import _template_variants, match_adaptive

        floor = self.th if th is None else th
        tpl = _template_variants(name)[0]
        r = int(max(tpl.shape[:2]) * gap_ratio)
        canvas = self.grab().copy()
        hits: list[tuple[int, int, float]] = []
        for _ in range(max_hits):
            h = match_adaptive(canvas, tpl, floor)
            if h is None:
                break
            hits.append(h)
            cv2.rectangle(canvas, (h[0] - r, h[1] - r), (h[0] + r, h[1] + r), (0, 0, 0), -1)
        hits.sort(key=lambda x: x[0])
        return hits

    def drag_up(self, x: int | None = None, y_from: int = 1150, y_to: int = 650,
                steps: int = 15, hold: float = 0.25, settle: float = 1.8) -> None:
        """拟人分段上拖（把被遮挡的内容露出来）。dry 只登记计划。

        x 是客户区坐标(None = 窗口中心)；y_from/y_to 是**基准坐标**(当年在 845x1521 下标定)，
        会按当前窗口换算 —— 否则窗口一改矮(实测见过 1143)起点 y=1150 就落到窗外了。
        实测要点: 拖动前必须把游戏窗口置于前台（后台进程 moveTo 会静默失败）。
        """
        import pyautogui

        x = self.w // 2 if x is None else x
        y_from, y_to = self._by(y_from), self._by(y_to)
        self.planned.append((f"上拖 {y_from}->{y_to}", x, y_from))
        if self.dry:
            log(f"[dry] 会从 ({x},{y_from}) 上拖到 ({x},{y_to})")
            return
        _bot._ensure_foreground(self.rect)
        ax, y0, y1 = self.rect.x + x, self.rect.y + y_from, self.rect.y + y_to
        pyautogui.moveTo(ax, y0, duration=0.3)
        time.sleep(0.4)
        pyautogui.mouseDown()
        for i in range(1, steps + 1):
            pyautogui.moveTo(ax, y0 + (y1 - y0) * i // steps, duration=0.06)
            time.sleep(0.03)
        time.sleep(hold)
        pyautogui.mouseUp()
        time.sleep(settle)
        log(f"上拖 {y_from}->{y_to} 完成")

    def shot(self, tag: str, *, force: bool = False) -> Path | None:
        """留证截图 → shots/_<prefix><tag>.png（dry 默认不落盘）。"""
        if self.dry and not force:
            log(f"[dry] 会留证截图 shots/_{self.prefix}{tag}.png")
            return None
        import cv2  # 仅落盘时需要

        out = SHOTS_DIR / f"_{self.prefix}{tag}.png"
        cv2.imwrite(str(out), self.grab())
        log(f"留证截图 {out.name}")
        if CURRENT is not None:      # --json 契约: 留证截图自动进 shots（零侵入用例）
            CURRENT.add_shot(out.name)
        return out


def open_screen(*, dry: bool = False, th: float = TH, prefix: str = "",
                timeout: float | None = 900.0) -> Screen:
    """定位游戏窗口并返回 Screen；找不到窗口抛 RuntimeError。"""
    rect = _bot.find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        raise RuntimeError("找不到游戏窗口（游戏没开或标题变了）")
    log(f"窗口 {rect}")
    return Screen(rect, th=th, dry=dry, prefix=prefix,
                  deadline=None if timeout is None else now() + timeout)


# ---------------------------------------------------------------- 首页


HOME_MARK = "stage_btn"     # 首页专属标志（nav_home 在寻宝/兑换/转盘子页也命中，不能用）
BACK_KEY = "ral_back"       # 子页通用返回键
HOME_CLOSE = "gd_close"     # 子页面板右上 X（面板类页面）
HOME_NAV = "nav_home"       # 「回首页」直达键（寻宝 hub 等页没有 ral_back, 只有它）
# 子页返回键同款兄弟(2026-10-11 补): 仓库/装备系页面**没有** ral_back/nav_home,
# 只有自己那款返回键 —— quick_advance 收尾因此被留在背包页, 连累下一个用例
# (friend_stamina 起点错乱)。goto_home 的后续候选。
BACK_KEY_MORE = ("eq_back", "wc_res_back")


def is_home(sc: Screen) -> bool:
    return sc.find(HOME_MARK) is not None


GROUP_POPUP_JOIN = "grp_join"   # 首页常显弹窗「无尽限时小组赛」的「立即参加」
GROUP_POPUP_X = "grp_x"         # 其右上角 X（等同「稍后参与」，不花钱、不消耗次数）


def dismiss_group_popup(sc: Screen) -> bool:
    """关掉首页常显的「无尽限时小组赛」自动弹窗。

    ⚠ 这不是可选优化：该弹窗会盖住首页标志(stage_btn)与通用返回键，导致
      is_home() 判否 + goto_home() 找不到返回键直接 "停手" —— 2026-10-09 实测
      boss_mode 收尾与 sweep_stage 收尾都因此卡住（活动开启后会周期性自动弹）。
    只当「立即参加 + X」同时 ≥0.93 命中才点，避免误关其它弹窗。
    """
    if sc.find(GROUP_POPUP_JOIN, 0.93) is None or sc.find(GROUP_POPUP_X, 0.93) is None:
        return False
    sc.click(sc.find(GROUP_POPUP_X, 0.93), "关闭「无尽限时小组赛」弹窗(稍后参与)")
    time.sleep(1.6)
    return True


def goto_home(sc: Screen, *, tries: int = 5, wait: float = 1.2) -> bool:
    """尽力回首页：点通用返回键，直到首页标志出现。dry 模式只记录。

    2026-10-10 补 nav_home 回退: 寻宝 hub 等页**没有** ral_back(只有「回首页」直达键)
    → 旧版回不去、游戏被留在半路，下一个用例起点错乱(free_rally/ free_treasure 全被
    连累)。ral_back 找不到就试 nav_home(子页 0.975+, 首页标志 stage_btn 已先行拦截)。
    2026-10-11: 找不到返回键不再立即放弃 —— 领取/转场动画期间所有键都检不到
    (claim_reward 收尾实测: 2s 后页面自己就回首页了) → 等一拍再找, 连续找不到才停手。
    2026-10-11 再修: BACK_KEY 点击无效就换 nav_home —— 寻宝 hub 的底部页签布局
    没有真返回键, ral_back 在 (728,1439) 假命中 0.967 实际是页签栏(free_treasure
    收尾连点 5 次全在切页签, 死活出不去; nav_home (86,216) 0.980 才是正路)。
    """
    stuck = False     # BACK_KEY 点过但没回首页(命中可能是当前页的假阳性)
    for i in range(tries):
        if is_home(sc):
            if i:
                log("已回首页")
            return True
        if dismiss_group_popup(sc):
            stuck = False
            continue
        if close_ad_page(sc):      # 广告页(看完没关) → 点「关闭」；不处理就找不到返回键、直接停手
            stuck = False
            continue
        if claim_if_present(sc):   # 「恭喜获得」结算页 → 点「领取」(不领也是死路: 没返回键)
            stuck = False
            continue
        if sc.dry:
            log(f"[dry] 会点 返回键({BACK_KEY}) 回首页")
            return True
        back = None if stuck else sc.find(BACK_KEY)
        if back is None:
            back = sc.find(HOME_NAV, 0.90)
        if back is None:
            for alt in BACK_KEY_MORE:       # 仓库/装备系子页只有自己的返回键
                back = sc.find(alt)
                if back is not None:
                    break
        if back is None:
            if i >= tries - 1:
                log("[warn] 找不到返回键，停手（请手动回首页）")
                return False
            time.sleep(wait)
            continue
        sc.click(back, f"返回(第{i + 1}次)")
        stuck = True
        time.sleep(wait)
    return is_home(sc)


# ---------------------------------------------------------------- 通用弹窗流程

AD_SKIP = "jump_no"          # 跳过卡弹窗 → 选「不使用」
AD_REWARDED = "ad_rewarded"  # 奖励到账（≥0.93 才可点关闭）
AD_CLOSE = "ad_close"
# 「暂未获得奖励 / 是否继续观看视频」确认框的「放弃」键（2026-10-15）
#   广告没满就点了「关闭」→ 微信弹这个**模态框**盖住广告页；不点它、只反复点右上「关闭」
#   实测 13 次全无效、卡死 83.8s（星际探索 free_explore 现场）。「继续」= 接着看视频，不点。
AD_GIVEUP = "ad_giveup"
CLAIM = "claim_btn"
# 「已获得奖励」不出现时的兜底时刻：用户口径广告 ≤35s，超过它就说明这皮肤压根
# 不显示该标记（只能靠「关闭」），再等下去只是白等。
AD_FALLBACK_AT = 40.0
# 广告层消失后, 再等这么久都回不来业务页 → 提前收手(见 ad_flow docstring)
GONE_GRACE = 8.0


def on_ad_page(sc: Screen) -> bool:
    """当前是不是「广告页」（含播放中与看完待关闭）。

    ⚠ 判据只能靠「关闭」。2026-10-14 实测（_run/_adstart_*.png）：广告**播放中
      「关闭」就已经在了**（文字层 0.86~0.98），而「已获得奖励」**只有部分皮肤
      会出现**（用户口径: 广告 ≤35s，每次广告换背景图 → 颜色模板跟着漂）。
      所以**不能**拿 ad_rewarded 当唯一出口，否则广告永远关不掉。
    """
    st = sc.look(AD_CLOSE, AD_REWARDED)
    return st[AD_CLOSE] is not None or st[AD_REWARDED] is not None


def close_ad_page(sc: Screen, *, settle: float = 1.8) -> bool:
    """广告页兜底关闭（点右上「关闭」），点过返回 True。

    ⭐ 这是「**一个广告把后面所有用例连坐**」的出口（2026-10-14 实测）:
      free_stamina 第 2 轮广告播完后停在广告页，用例只等 ad_rewarded、没点关闭
      → 75s 超时收尾；而广告页**既不是首页、也没有游戏返回键** → goto_home
      直接「找不到返回键，停手」→ 后面 2~5 号用例全报「找不到商城入口/不在首页」。
    ⭐ 2026-10-15: 先查「暂未获得奖励」确认框 —— 广告没满就点关闭会弹它盖住广告页，
      此时再点右上「关闭」永远无效（实测 goto_home 连点 13 次、卡死 83.8s）→ 必须点「放弃」。
    """
    st = sc.look(AD_GIVEUP, AD_CLOSE, AD_REWARDED)
    if st[AD_GIVEUP] is not None:
        sc.click(st[AD_GIVEUP], "放弃(未获得奖励确认)")
        time.sleep(settle)
        return True
    hit = st[AD_CLOSE] or st[AD_REWARDED]
    if hit is None:
        return False
    sc.click(hit, "关闭广告页(兜底)")
    time.sleep(settle)
    return True


def ad_flow(sc: Screen, *, page: str, timeout: float = 120.0, claim: str = CLAIM,
            interval: float = 2.0, gone_grace: float = GONE_GRACE) -> str:
    """广告/免广告两种形态的通用状态机（8 个用例共用）。

    点完「免费/看广告」后调用。循环处理：
        give up(暂未获得奖励确认框)   → 点「放弃」退出（模态框，优先；不处理会卡死）
        jump_no(跳过卡弹窗)        → 点「不使用」，保住道具
        ad_rewarded + ad_close     → 点关闭（ad_rewarded ≥0.93 才认，防广告还在播就点）
        claim_btn(「恭喜获得」)     → 点领取
        已领取且回业务页            → 结束
    page: 业务页标志模板名（领取后回到它即算成功）。
    返回 'claimed' | 'page'（没领但已回业务页）| 'gone'（广告层已消失、业务页也没回）| 'timeout'。

    ⭐ 2026-10-14 补「仅凭关闭」兜底: 微信广告换个背景图就可能**压根不显示
      「已获得奖励」**（用户口径: 广告 ≤35s 且「关闭」播放中就在）→ 旧逻辑把
      ad_rewarded 当唯一出口 → 永不点关闭 → 卡广告页 → 收尾时连返回键都没有。
      现在: 超过 AD_FALLBACK_AT 秒还没等到「已获得奖励」→ 只凭「关闭」关掉。
    ⭐ 2026-10-14 补「广告层消失即早退」(用户反馈: 免费体力次数用尽后还在傻等):
      次数用尽时「免费」变灰 → 业务页标志 stamina_free 匹配不到(0.73<0.86) →
      旧逻辑永远等不到「回到业务页」, 一路空转到 timeout(实测白等 ~67s)。
      现在: **曾出现过广告层**(4 个标志任一) 且随后连续 gone_grace 秒一个都不在 →
      业务页在 = 'page'; 不在 = 'gone'(交给调用方判「次数用尽/被游戏收掉」)。
      要求"曾出现过"是防误伤「广告播放中压根不显示关闭键」的皮肤。
    """
    t0 = now()
    claimed = False
    seen_ad = False
    last_ad = t0          # ⚠ 初始化为当前时刻: 否则"刚进来还没广告"会被算成已消失
    while now() - t0 < timeout:
        st = sc.look(AD_GIVEUP, AD_SKIP, claim, AD_REWARDED, AD_CLOSE, page)
        log(f"t={now() - t0:5.1f} jump_no={st[AD_SKIP] is not None} "
            f"claim={st[claim] is not None} ad_reward={st[AD_REWARDED] is not None} "
            f"ad_close={st[AD_CLOSE] is not None} giveup={st[AD_GIVEUP] is not None} "
            f"{page}={st[page] is not None}")
        ad_visible = any(st[k] is not None
                         for k in (AD_SKIP, claim, AD_REWARDED, AD_CLOSE, AD_GIVEUP))
        if ad_visible:
            seen_ad = True
            last_ad = now()

        if st[AD_GIVEUP] is not None:
            # 模态确认框优先（它盖住一切）：广告没满就点过关闭才会出现 → 点「放弃」退出。
            #   ⭐ 2026-10-15: 不处理它 → 弹窗盖住广告页、之后所有点击全落空（卡死现场）
            sc.click(st[AD_GIVEUP], "放弃(未获得奖励确认)")
            time.sleep(1.5)
        elif st[AD_SKIP] is not None:
            sc.click(st[AD_SKIP], "不使用(跳过卡)")
        elif st[claim] is not None:
            sc.click(st[claim], "领取")
            claimed = True
            time.sleep(2.5)
            if sc.look(claim, AD_CLOSE)[claim] is None:
                log("领取完成")
                return "claimed"
        elif st[AD_REWARDED] is not None and st[AD_CLOSE] is not None:
            sc.click(st[AD_CLOSE], "广告关闭")
            time.sleep(2.0)
        elif st[AD_CLOSE] is not None and now() - t0 >= AD_FALLBACK_AT:
            log(f"  「已获得奖励」始终未出现(皮肤差异) → 仅凭「关闭」关广告(t={now() - t0:.0f}s)")
            sc.click(st[AD_CLOSE], "广告关闭(兜底)")
            time.sleep(2.0)
        elif claimed and st[AD_CLOSE] is None:
            return "page"

        # 广告层消失后早退（见 docstring）
        if seen_ad and not ad_visible and now() - last_ad >= gone_grace:
            if st[page] is not None:
                log(f"广告层已消失 {gone_grace:.0f}s、业务页({page})已在 → 结束")
                return "page"
            log(f"广告层已消失 {gone_grace:.0f}s 且业务页({page})未回 → 提前收手")
            return "gone"
        time.sleep(interval)
    return "timeout"


def play_ad(sc: Screen, *, page: str, entry: str | None = None,
            pos: tuple[int, int] | None = None, label: str = "广告",
            timeout: float = 90.0, appear: float = 15.0, ready: float = 15.0,
            claim: str = CLAIM) -> str:
    """「免费 X（看广告）」的**公共全链路**：点入口 → 跳卡/广告 → 关广告页 → 领奖 → 回业务页。

    ⭐ 2026-10-14 抽通用（用户口径: 进入广告到关闭的逻辑应该都一样）:
      free_stamina / free_sweep 原先各写一套（都漏了「关闭」/「领取」，见各用例注释），
      free_gift / free_star / free_turn 只用 ad_flow、入口点击各写各的 —— 统一到这里。

    入口二选一:
      * entry=模板名（如 "stamina_free" / "gift_free"）
      * pos=(x, y) 算坐标入口（free_sweep 的免费按钮没有模板，是卡心下移算出来的）
    返回:
      'ok'       业务页已重现（成功）
      'no_entry' 没找到入口（可能次数已耗尽 / 不在业务页）；
                 ⚠ 也包含「广告层已消失但业务页没回来」(ad_flow 的 'gone'，2026-10-14)
      'no_ad'    点了入口但既没出现广告层、业务页也没动静（点击没生效）
      'timeout'  广告流程超时且业务页没回来
    """
    if pos is not None:
        if sc.dry:
            log(f"[dry] 会点 {label}入口坐标 {pos} → 广告 → 关广告/领取 → 等回到 {page}")
            return "ok"
        sc.click_at(pos[0], pos[1], f"{label}入口(坐标)")
    else:
        if entry is None:
            raise TypeError("play_ad 需要 entry=模板名 或 pos=(x,y)")
        hit = sc.find(entry)
        if hit is None:
            return "no_entry"
        sc.click(hit, f"{label}入口({entry})")
        if sc.dry:
            return "ok"

    # 等「点击被接受」: 广告层出现(跳卡/关闭/奖励/领取) 或 业务页消失(正在跳转)
    #   ⚠ 判据故意不用「入口按钮消失」: free_sweep 的入口是算坐标的、没有消失信号。
    t0 = now()
    taken = False
    while now() - t0 < appear:
        st = sc.look(AD_SKIP, claim, AD_REWARDED, AD_CLOSE, page)
        if st[AD_SKIP] or st[claim] or st[AD_REWARDED] or st[AD_CLOSE]:
            taken = True
            break
        if st[page] is None:
            taken = True          # 业务页已让位 → 已在跳转
            break
        time.sleep(1.0)
    if not taken:
        log(f"{label}: 点击后 {appear:.0f}s 内既无广告层、业务页也没动 → 点击疑似未生效")
        return "no_ad"

    res = ad_flow(sc, page=page, timeout=timeout, claim=claim)
    if sc.wait(page, ready) is not None:
        return "ok"
    if res == "gone":
        # 广告层已消失、业务页却没回 → 既不是正常超时、也不是点击没生效。
        # 实测就是「次数用尽」(免费钮变灰 → page 模板失配) → 归到 no_entry, 让用例当正常收尾。
        log(f"{label}: 广告层已消失且业务页({page})未回 → 疑似次数用尽/被游戏收掉")
        return "no_entry"
    log(f"{label}: 广告流程({res}) 后 {ready:.0f}s 内未见业务页({page})")
    return "timeout" if res == "timeout" else res


def claim_if_present(sc: Screen, *, th: float = TH_STRICT) -> bool:
    """「恭喜获得」→ 点领取。命中并点击返回 True。"""
    hit = sc.find(CLAIM, th=th)
    if hit is None or hit[2] < th:
        return False
    sc.click(hit, "领取")
    return True


# ---------------------------------------------------------------- CLI


@dataclass
class Args:
    dry: bool = False
    max: int | None = None       # 最多做几次(None=未指定 → n_times 用各用例的 default)
    times: int | None = None     # 显式次数（覆盖 max，用于可多次的用例）
    all: bool = False            # 做到次数用尽
    type: str | None = None      # 目标类型（如 guild_donate 的 gold/diamond/both）
    no_back: bool = False        # 不自动回首页
    yes: bool = False            # 少问一句（无交互时用）
    json_out: bool = False       # --json：stdout 只打一行结构化结果（见 Result）
    timeout: float = 900.0       # 硬看门狗（秒）
    extra: dict = field(default_factory=dict)

    def n_times(self, default: int = 1) -> int:
        """实际执行次数：--all 由用例给出上限，--times 优先于 --max。

        ⚠ default 只有在 max/times 都未指定时才生效 —— 2026-10-11 修复:
        旧版 max 硬默认 1, `self.max or default` 里 default 永远轮不到,
        guild_donate 的「默认各 3 次」因此实际只捐 1 次。
        """
        if self.times is not None:
            return self.times
        return self.max or default


CORE_FLAGS = {
    "--dry": "只识别/演练，不点击（零副作用）",
    "--max": "最多做几次（默认 1，或用例自定默认）",
    "--times": "显式指定次数（优先于 --max）",
    "--all": "做到次数用尽",
    "--type": "目标类型（用例自定义，如 gold/diamond/both）",
    "--no-back": "结束后不自动回首页",
    "--yes": "不经确认直接执行（默认即如此，保留给未来交互）",
    "--json": "stdout 只输出一行结构化结果 JSON（供 AI/脚本调用；人类日志走 stderr）",
    "--timeout": "总时长看门狗秒数（默认 900）",
}


def parse_args(argv: list[str] | None = None, *, extra: tuple[str, ...] = (),
               extra_kv: tuple[str, ...] = (), default_max: int = 1,
               default_timeout: float = 900.0) -> Args:
    """统一 CLI 解析（零依赖，手写以支持 `--times=2` 与 `--times 2` 两种写法）。

    extra: 用例自定义的**布尔**开关，例如 ("--no-wish", "--snap")；
    extra_kv: 用例自定义的**带值**开关，例如 ("--station",) → args.extra["station"]。
    default_max: 未传 --max 时的默认次数（如 free_sweep 默认 5 轮）。
    default_timeout: 未传 --timeout 时的看门狗秒数（多轮长用例要放宽，如 endless 6 轮）。
    """
    a = Args(max=default_max, timeout=default_timeout)
    argv = list(sys.argv[1:] if argv is None else argv)
    i = 0
    while i < len(argv):
        tok = argv[i]
        key, _, inline = tok.partition("=")
        val = inline if "=" in tok else None

        def take() -> str:
            nonlocal i
            if val is not None:
                return val
            i += 1
            if i >= len(argv):
                raise SystemExit(f"{key} 需要一个值")
            return argv[i]

        if key == "--dry":
            a.dry = True
        elif key == "--max":
            a.max = int(take())
        elif key == "--times":
            a.times = int(take())
        elif key == "--all":
            a.all = True
        elif key == "--type":
            a.type = take()
        elif key == "--no-back":
            a.no_back = True
        elif key == "--yes" or key == "-y":
            a.yes = True
        elif key == "--json":
            a.json_out = True
        elif key == "--timeout":
            a.timeout = float(take())
        elif key in extra:
            a.extra[key.lstrip("-").replace("-", "_")] = True
            i += 1
            continue
        elif key in extra_kv:
            a.extra[key.lstrip("-").replace("-", "_")] = take()
        elif key.startswith("-"):
            raise SystemExit(f"未知参数 {key}（可用: {', '.join([*CORE_FLAGS, *extra, *extra_kv])}）")
        else:
            raise SystemExit(f"多余参数 {tok}")
        i += 1
    return a


def run_case(name: str, title: str, fn, *, plan: str = "", prefix: str = "",
             lock_ttl: float = 600.0, th: float = TH, need_home: bool = False,
             argv: list[str] | None = None, extra: tuple[str, ...] = (),
             extra_kv: tuple[str, ...] = (),
             default_max: int = 1, default_timeout: float = 900.0) -> int:
    """用例统一入口：解析参数 → 开屏 → 单实例锁 → 跑 → 超时留证 → 收尾回首页。

    fn(sc, args) -> bool  返回「这次任务是否达成目标」。
    退出码: 0 成功 / 1 未达成 / 2 环境问题(没窗口等) / 3 已有实例在跑 / 4 超时。

    --json 模式下，stdout 只在最后打**一行**结构化结果（Result），人类日志全走 stderr。
    """
    args = parse_args(argv, extra=extra, extra_kv=extra_kv, default_max=default_max,
                      default_timeout=default_timeout)
    _bot.configure_mouse(args.dry)
    banner(title, plan=plan, dry=args.dry)
    log(f"参数 dry={args.dry} max={args.max} times={args.times} all={args.all} "
        f"type={args.type} no_back={args.no_back} extra={args.extra or '-'}")

    global CURRENT
    res = Result(name, title, args.dry, now())
    CURRENT = res
    try:
        code = _run_locked(name, fn, args, prefix=prefix, lock_ttl=lock_ttl,
                           th=th, need_home=need_home)
    finally:
        CURRENT = None

    if args.dry and code == 1:      # dry 只是演练：没点成不算失败
        log("（dry 演练，未点击 → 不计失败）")
        code = 0

    log(f"结束 code={code}" + ("（dry 演练，未点击）" if args.dry else ""))
    if args.json_out:
        # stdout 只此一行：AI/脚本直接 json.loads(get_output())
        print(json.dumps(res.as_dict(code == 0, code), ensure_ascii=False), flush=True)
    return code


def _run_locked(name: str, fn, args: Args, *, prefix: str, lock_ttl: float,
                th: float, need_home: bool) -> int:
    """run_case 的主体（开屏 → 锁 → 跑 → 留证 → 收尾）。返回退出码。"""
    try:
        sc = open_screen(dry=args.dry, th=th, prefix=prefix, timeout=args.timeout)
    except RuntimeError as e:
        log(f"[fail] {e}")
        if CURRENT is not None:
            CURRENT.error = str(e)
        return 2

    code = 0
    aborted = False                          # 急停: 必须跳过收尾(收尾也要点击 → 会连环抛)
    with single_instance(name, lock_ttl, dry=args.dry) as got:
        if not got:
            if CURRENT is not None:
                CURRENT.error = "已有实例在跑"
            return 3
        try:
            if need_home and not is_home(sc):
                log("当前不在首页 → 先回首页")
                if not goto_home(sc):
                    return 1
            ok = bool(fn(sc, args))
            code = 0 if ok else 1
        except CaseTimeout:
            log(f"[timeout] 用例超过 {args.timeout:.0f}s 看门狗 → 留证并收尾")
            sc.shot(f"{name}_timeout")
            if CURRENT is not None:
                CURRENT.error = "timeout"
            code = 4
        except KeyboardInterrupt:
            log("⛔ 被中断(急停: Ctrl+C) → 中止本次运行")
            code = 5
            aborted = True
        except FailSafeException:
            # ⭐ 2026-10-14 急停必须**独立识别**: 旧代码落到下面的 except Exception →
            #   记成「未达成」；而鼠标停在角落期间**每次点击都立即抛** → 批量跑时
            #   后面每个用例都在 ~12s 连环崩(实测 活跃度/奖励领取/社区奖励 三连崩)。
            #   改用急停专用退出码 5（批量跑器据此中止后续），并跳过收尾。
            log("⛔ 急停触发（鼠标甩到屏幕角落）→ 中止本次运行")
            if CURRENT is not None:
                CURRENT.error = "aborted(failsafe)"
            code = 5
            aborted = True
        except Exception as e:                    # 未预期异常：留证 + 仍走 finally 收尾
            import traceback
            log(f"[fail] 未预期异常 {type(e).__name__}: {e} → 留证并收尾")
            traceback.print_exc()
            sc.shot(f"{name}_crash")
            if CURRENT is not None:
                CURRENT.error = f"{type(e).__name__}: {e}"
            code = 1
        finally:
            if not aborted and not args.dry and not args.no_back:
                try:
                    goto_home(sc)
                except Exception as e:
                    # 点击护栏等运行时守卫也会在收尾时抛(2026-10-12) ——
                    # 收尾失败只记日志, 别把用例自身的失败信息顶掉
                    log(f"[warn] 收尾回首页失败: {type(e).__name__}: {e}")
    return code

    if args.dry and code == 1:      # dry 只是演练：没点成不算失败
        log("（dry 演练，未点击 → 不计失败）")
        code = 0

    log(f"结束 code={code}" + ("（dry 演练，未点击）" if args.dry else ""))
    return code
