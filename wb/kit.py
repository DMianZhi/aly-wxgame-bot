"""用例运行时脚手架（kit）—— 所有 tools/cases/*.py 共用的底座。

一个用例只该写「本页怎么认、点哪里、什么算成功」，其余都是样板：本模块把样板收干净。

对外能力
    log / banner      统一日志前缀（[HH:MM:SS]）
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
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import bot as _bot
from .cfg import APP_DIR, CONF, SHOTS_DIR

# ---------------------------------------------------------------- 阈值

TH = CONF.threshold      # 通用阈值(0.86)
TH_STRICT = 0.92         # 「领取/确定」这类多页同款键，抬阈值防串台
TH_LOOSE = 0.80          # 半透明弹层里的元素，分数略降

# ---------------------------------------------------------------- 日志


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def banner(title: str, *, plan: str = "", dry: bool = False) -> None:
    log(f"=== {title} ===")
    if dry and plan:
        for line in plan.strip().splitlines():
            log(line)


class CaseTimeout(RuntimeError):
    """用例总时长超限（看门狗）。"""


def nap(seconds: float) -> None:
    """等待（用例统一走这里；离线自检会把 sleep 变空转，避免真等）。"""
    time.sleep(seconds)


# ---------------------------------------------------------------- 单实例锁

LOCKS_DIR = APP_DIR / "shots"


@contextlib.contextmanager
def single_instance(name: str, ttl: float = 600.0, *, dry: bool = False):
    """同名用例互斥：已有实例在跑就退出（防重复花每日次数/重复领取）。

    锁 = shots/.<name>.lock，内容写 pid；超过 ttl 视为残留锁可接管（进程被 kill 等）。
    dry 模式不落锁（零副作用）。
    """
    lock = LOCKS_DIR / f".{name}.lock"
    if dry:
        yield True
        return
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age < ttl:
            log(f"已有实例在跑(锁 {lock.name} 年龄 {age:.0f}s < {ttl:.0f}s) → 退出，避免重复操作")
            yield False
            return
        log(f"锁已过期({age:.0f}s)，接管")
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
                 delay: tuple[float, float] = (0.4, 0.9)):
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
        if self.deadline is not None and time.time() > self.deadline:
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
            v = max(floor, _bot.TEMPLATE_MIN.get(n, 0.0))
            best = None
            for tpl in _bot._template_variants(n):
                h = _bot.match_adaptive(img, tpl, v)
                if h is not None and (best is None or h[2] > best[2]):
                    best = h
            out[n] = best
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
        end = time.time() + timeout
        while True:
            hit = self.find(name, th=th)
            if hit is not None:
                return hit
            if self.dry:
                return None
            if time.time() >= end:
                return None
            time.sleep(interval)

    def wait_gone(self, name: str, timeout: float, interval: float = 1.0):
        """等模板消失；返回是否消失。dry 不点击 → 只查一次。"""
        end = time.time() + timeout
        while True:
            if self.find(name) is None:
                return True
            if self.dry:
                return False
            if time.time() >= end:
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
        """
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
        return out


def open_screen(*, dry: bool = False, th: float = TH, prefix: str = "",
                timeout: float | None = 900.0) -> Screen:
    """定位游戏窗口并返回 Screen；找不到窗口抛 RuntimeError。"""
    rect = _bot.find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        raise RuntimeError("找不到游戏窗口（游戏没开或标题变了）")
    log(f"窗口 {rect}")
    return Screen(rect, th=th, dry=dry, prefix=prefix,
                  deadline=None if timeout is None else time.time() + timeout)


# ---------------------------------------------------------------- 首页


HOME_MARK = "stage_btn"     # 首页专属标志（nav_home 在寻宝/兑换/转盘子页也命中，不能用）
BACK_KEY = "ral_back"       # 子页通用返回键
HOME_CLOSE = "gd_close"     # 子页面板右上 X（面板类页面）


def is_home(sc: Screen) -> bool:
    return sc.find(HOME_MARK) is not None


def goto_home(sc: Screen, *, tries: int = 5, wait: float = 1.2) -> bool:
    """尽力回首页：点通用返回键，直到首页标志出现。dry 模式只记录。"""
    for i in range(tries):
        if is_home(sc):
            if i:
                log("已回首页")
            return True
        if sc.dry:
            log(f"[dry] 会点 返回键({BACK_KEY}) 回首页")
            return True
        back = sc.find(BACK_KEY)
        if back is None:
            log("[warn] 找不到返回键，停手（请手动回首页）")
            return False
        sc.click(back, f"返回(第{i + 1}次)")
        time.sleep(wait)
    return is_home(sc)


# ---------------------------------------------------------------- 通用弹窗流程

AD_SKIP = "jump_no"          # 跳过卡弹窗 → 选「不使用」
AD_REWARDED = "ad_rewarded"  # 奖励到账（≥0.93 才可点关闭）
AD_CLOSE = "ad_close"
CLAIM = "claim_btn"


def ad_flow(sc: Screen, *, page: str, timeout: float = 120.0, claim: str = CLAIM,
            interval: float = 2.0) -> str:
    """广告/免广告两种形态的通用状态机（8 个用例共用）。

    点完「免费/看广告」后调用。循环处理：
        jump_no(跳过卡弹窗)        → 点「不使用」，保住道具
        ad_rewarded + ad_close     → 点关闭（ad_rewarded ≥0.93 才认，防广告还在播就点）
        claim_btn(「恭喜获得」)     → 点领取
        已领取且回业务页            → 结束
    page: 业务页标志模板名（领取后回到它即算成功）。
    返回 'claimed' | 'page'（没领但已回业务页）| 'timeout'。
    """
    t0 = time.time()
    claimed = False
    while time.time() - t0 < timeout:
        st = sc.look(AD_SKIP, claim, AD_REWARDED, AD_CLOSE, page)
        log(f"t={time.time() - t0:5.1f} jump_no={st[AD_SKIP] is not None} "
            f"claim={st[claim] is not None} ad_reward={st[AD_REWARDED] is not None} "
            f"ad_close={st[AD_CLOSE] is not None} {page}={st[page] is not None}")

        if st[AD_SKIP] is not None:
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
        elif claimed and st[AD_CLOSE] is None:
            return "page"
        time.sleep(interval)
    return "timeout"


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
    max: int = 1                 # 最多做几次（免费资源一轮只有 1 次）
    times: int | None = None     # 显式次数（覆盖 max，用于可多次的用例）
    all: bool = False            # 做到次数用尽
    type: str | None = None      # 目标类型（如 guild_donate 的 gold/diamond/both）
    no_back: bool = False        # 不自动回首页
    yes: bool = False            # 少问一句（无交互时用）
    timeout: float = 900.0       # 硬看门狗（秒）
    extra: dict = field(default_factory=dict)

    def n_times(self, default: int = 1) -> int:
        """实际执行次数：--all 由用例给出上限，--times 优先于 --max。"""
        if self.times is not None:
            return self.times
        return self.max or default


CORE_FLAGS = {
    "--dry": "只识别/演练，不点击（零副作用）",
    "--max": "最多做几次（默认 1）",
    "--times": "显式指定次数（优先于 --max）",
    "--all": "做到次数用尽",
    "--type": "目标类型（用例自定义，如 gold/diamond/both）",
    "--no-back": "结束后不自动回首页",
    "--yes": "不经确认直接执行（默认即如此，保留给未来交互）",
    "--timeout": "总时长看门狗秒数（默认 900）",
}


def parse_args(argv: list[str] | None = None, *, extra: tuple[str, ...] = (),
               extra_kv: tuple[str, ...] = (), default_max: int = 1) -> Args:
    """统一 CLI 解析（零依赖，手写以支持 `--times=2` 与 `--times 2` 两种写法）。

    extra: 用例自定义的**布尔**开关，例如 ("--no-wish", "--snap")；
    extra_kv: 用例自定义的**带值**开关，例如 ("--station",) → args.extra["station"]。
    default_max: 未传 --max 时的默认次数（如 free_sweep 默认 5 轮）。
    """
    a = Args(max=default_max)
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
             default_max: int = 1) -> int:
    """用例统一入口：解析参数 → 开屏 → 单实例锁 → 跑 → 超时留证 → 收尾回首页。

    fn(sc, args) -> bool  返回「这次任务是否达成目标」。
    退出码: 0 成功 / 1 未达成 / 2 环境问题(没窗口等) / 3 已有实例在跑 / 4 超时。
    """
    args = parse_args(argv, extra=extra, extra_kv=extra_kv, default_max=default_max)
    _bot.configure_mouse(args.dry)
    banner(title, plan=plan, dry=args.dry)
    log(f"参数 dry={args.dry} max={args.max} times={args.times} all={args.all} "
        f"type={args.type} no_back={args.no_back} extra={args.extra or '-'}")

    try:
        sc = open_screen(dry=args.dry, th=th, prefix=prefix, timeout=args.timeout)
    except RuntimeError as e:
        log(f"[fail] {e}")
        return 2

    code = 0
    with single_instance(name, lock_ttl, dry=args.dry) as got:
        if not got:
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
            code = 4
        except KeyboardInterrupt:
            log("被中断(急停: 鼠标甩左上角 / Ctrl+C) → 收尾")
            code = 1
        finally:
            if not args.dry and not args.no_back:
                goto_home(sc)

    if args.dry and code == 1:      # dry 只是演练：没点成不算失败
        log("（dry 演练，未点击 → 不计失败）")
        code = 0

    log(f"结束 code={code}" + ("（dry 演练，未点击）" if args.dry else ""))
    return code
