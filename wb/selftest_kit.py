"""离线回放脚手架 —— 零消耗验证用例自身的分支。

原理（沿用项目里已被验证的土办法，只是收进一个模块）:
    实测截图 = 「此刻的画面」；**点一下就切到下一帧**（点击驱动状态机）。
    把 wb.bot 的 grab_window / click_xy 换成回放替身，鼠标与写盘全部拦掉，
    于是用例自身的判页、护栏、重试、收尾都能在离线跑完 —— 不消耗游戏里的每日次数。

为什么必须这样测: 免费资源「一天一次」，实跑一次就没了；而最容易翻车的恰恰是
    判层顺序（半透明遮罩）、丢点击重试、付费键护栏这些**分支**，正好可以用回放穷举。

用法:
    from wb import selftest_kit as st

    def case_free(rp):
        ok = ft.one_turn(sc)             # 直接调用用例函数
        return ok and st.check_clicks("免费态", rp.real_clicks, [(400, 1290), (400, 1330)]), f"点击={rp.real_clicks}"

    st.run("free_turn 离线自检", [
        ("免费态→抽奖→领取", ["_rec_turn_page.png", "_rec_turn_claim.png", "_rec_turn_page_paid.png"], case_free),
    ])
"""
from __future__ import annotations

import contextlib
import sys
import time as _time
from pathlib import Path

from . import bot as _bot
from . import kit as _kit
from .cfg import SHOTS_DIR

RECT = (0, 0, 814, 1507)      # 用例内部只用到坐标, 替身点击里不会碰 rect 字段
# ⚠ 必须等于真帧尺寸(REF): 夹具帧是 814x1507 拆下来的真帧, 替身报别的尺寸会让
#   ref_rect_to_client 算错缩放(实测报 812x1518 → 成本 ROI 的 y 偏 6px → IoU 0.28)


class _ShimTime:
    """time 替身：sleep 空转（自检别真等）并把时长计入**虚拟时钟**，其余属性透传。

    虚拟时钟 = 真实时间 + 累计 sleep。让「广告播 12 秒」这类靠时间推进的
    分支能在毫秒内跑完，同时用例里的 timeout/deadline 逻辑保持原样。
    """

    def __init__(self, real):
        self._real = real
        self.vt = 0.0

    def sleep(self, d=0.0, *_a, **_k):
        self.vt += float(d)
        return None

    def now(self) -> float:
        return self._real.time() + self.vt

    def __getattr__(self, k):
        return getattr(self._real, k)


class Replay:
    """点击驱动状态机的假 I/O（可选时间驱动：holds）。

    holds = {帧下标: 秒}: 该帧停留这么多**虚拟秒**后自动切下一帧 ——
    用来模拟「广告播完」「动画推进」这类不靠点击、靠时间推进的转移。

    idx=0 也可以设 holds（帧 0 的起点在**首次取帧时**闸定，不是场景构造那一刻）——
    早期版本的 `_enter` 初值是 0.0，导致 now-0 恒超时、holds[0] 形同没有，已修。
    """

    def __init__(self, frames: list[str], *, shots: Path = SHOTS_DIR,
                 holds: dict[int, float] | None = None):
        import cv2

        self.paths = [shots / f for f in frames]
        self.imgs = [cv2.imread(str(p)) for p in self.paths]
        self.idx = 0
        self.holds = holds or {}
        self.clock = None                                # 由 replay() 注入虚拟时钟
        self._enter = None                               # 当前帧的进入时刻（首次取帧时闸定）
        self._t0 = None                                  # 首次取帧的虚拟时刻（时间一律记相对值）
        self.events: list[tuple[int, int, str]] = []     # (x, y, 点击时所在帧)；截图记 x=-1
        self.times: list[float] = []                     # 与 events 对齐的**相对**虚拟秒
        self.drags: list[tuple[int, int, int, int]] = []  # (x1,y1,x2,y2) 游戏内坐标
        self.drag_times: list[float] = []                # 相对虚拟秒（断言「第几秒才动手」用）

    def _now(self) -> float:
        """相对虚拟秒。

        不能直接记 clock()：它 = 真实时间 + 虚拟累计 → 是 epoch 级别的大数，
        拿它做断言（如 >= 35）会永远成立 → 断言形同虚设（自检里最危险的假绿）。
        """
        if self.clock is None:
            return 0.0
        if self._t0 is None:
            self._t0 = self.clock()
        return self.clock() - self._t0

    # ---- 替身 ----------------------------------------------------
    def _tick(self) -> None:
        """时间驱动：当前帧停够 holds 秒就自动翻页。

        ⚠ `_enter` 首次取帧时才闸定：时钟是 `真实时间 + 虚拟` 的 **epoch 级大数**，
        若先把 `_enter` 初始化成 0.0，则第一次 `now - 0 >= hold` 恒真 →
        **holds[0] 的帧一取就被跳过**（实测：场景想要的「首帧停在未达标」直接失效）。
        旧写法害得 endless 自检的场景①看着 PASS、其实没测到「未达不拖」。
        """
        if self.clock is None:
            return
        now = self.clock()
        if self._enter is None:                  # 首次取帧：帧起点 = 此刻
            self._enter = now
            return
        hold = self.holds.get(self.idx)
        if hold and now - self._enter >= hold:
            self.idx += 1
            self._enter = now

    def grab(self, _rect):
        self._tick()
        self._now()          # 闸定场景起点（首个取帧）→ 之后的时间都是相对值
        return self.imgs[min(self.idx, len(self.imgs) - 1)]

    def click(self, x, y, *_a, **_k):
        self.events.append((x, y, self.frame))
        self.times.append(self._now())
        self.idx += 1
        self._enter = self.clock() if self.clock else None

    def drag(self, x1, y1, x2, y2, *_a, **_k):
        """拖拽替身：不碰真实鼠标，只记账（拖拽同样会改变画面 → 当作一次状态转移）。"""
        self.drags.append((x1, y1, x2, y2))
        self.drag_times.append(self._now())
        self.events.append((x1, y1, f'drag:{self.frame}'))
        self.times.append(self._now())
        self.idx += 1
        self._enter = self.clock() if self.clock else None

    def configure_mouse(self, *_a, **_k):
        return None

    # ---- 观察 ----------------------------------------------------
    @property
    def frame(self) -> str:
        return self.paths[min(self.idx, len(self.paths) - 1)].name

    @property
    def real_clicks(self) -> list[tuple[int, int]]:
        return [(x, y) for x, y, _ in self.events if x >= 0]

    @property
    def shots(self) -> list[str]:
        return [tag for x, _, tag in self.events if x < 0]

    @property
    def click_frames(self) -> list[str]:
        return [tag for x, _, tag in self.events if x >= 0]

    def __repr__(self) -> str:
        return f"<Replay {len(self.real_clicks)} clicks / {[f.name for f in self.paths]}>"


class FakeRect:
    """离线自检用的假窗口矩形（只需 x/y/w/h/hwnd 字段，够 find_in_game / click_xy 用）。"""

    def __init__(self, x: int = 0, y: int = 0, w: int = 812, h: int = 1518, hwnd: int = 0):
        self.x, self.y, self.w, self.h, self.hwnd = x, y, w, h, hwnd

    def __iter__(self):        # 兼容「裸 tuple 矩形」的写法
        return iter((self.x, self.y, self.x + self.w, self.y + self.h))


def bare_case(cls, **attrs):
    """自检专用：绕过用例 __init__（那里会真实找窗口、真实 ALT 置前）造一个用例实例。

    只适用于把 rect/dry 等状态放在 self 上的类式用例；构造后 _focus 被替换成空操作，
    否则自检会真的按 ALT、真的抢前台。
    """
    obj = cls.__new__(cls)
    obj.rect = FakeRect()
    for k, v in attrs.items():
        setattr(obj, k, v)
    obj._focus = lambda *_a, **_k: None
    return obj


@contextlib.contextmanager
def replay(frames: list[str], *, holds: dict[int, float] | None = None):
    """替换 wb.bot 的取帧/点击 + kit 的 sleep + cv2 落盘；退出时还原。"""
    import cv2

    rp = Replay(frames, holds=holds)
    shim = _ShimTime(_time)
    orig = (_bot.grab_window, _bot.click_xy, _bot.configure_mouse, _bot.drag_xy, _kit.time, cv2.imwrite)
    _bot.grab_window = rp.grab
    _bot.click_xy = rp.click
    _bot.configure_mouse = rp.configure_mouse
    _bot.drag_xy = rp.drag
    _kit.time = shim
    rp.clock = shim.now
    # 留证截图不真落盘，只记账（自检必须零副作用）
    cv2.imwrite = lambda path, _img: (rp.events.append((-1, -1, f"shot:{Path(path).name}")), True)[1]
    try:
        yield rp
    finally:
        (_bot.grab_window, _bot.click_xy, _bot.configure_mouse, _bot.drag_xy,
         _kit.time, cv2.imwrite) = orig


def scene(name: str, frames: list[str], fn, *, quiet: bool = False,
          holds: dict[int, float] | None = None) -> str:
    """跑一个场景。frames 缺夹具 → SKIP（不计入分母）。fn(rp) -> (ok, note)。"""
    missing = [f for f in frames if not (SHOTS_DIR / f).exists()]
    if missing:
        print(f"[SKIP] {name} —— 缺夹具 {missing}")
        return "skip"
    with replay(frames, holds=holds) as rp:
        try:
            ok, note = fn(rp)
        except Exception as e:  # 自检要把异常当 FAIL，而不是炸掉整个套件
            import traceback

            traceback.print_exc()
            ok, note = False, f"异常 {type(e).__name__}: {e}"
    tag = "PASS" if ok else "FAIL"
    if not quiet or not ok:
        print(f"[{'ok  ' if ok else 'FAIL'}] {name} —— {note}")
    return "pass" if ok else "fail"


def check_clicks(tag: str, got, expect, tol: int = 6) -> bool:
    """坐标级断言（±tol 像素）。"""
    if len(got) != len(expect):
        print(f"[!!] {tag}: 点击次数 {len(got)} != 期望 {len(expect)}  got={got} exp={expect}")
        return False
    bad = [(g, e) for g, e in zip(got, expect)
           if abs(g[0] - e[0]) > tol or abs(g[1] - e[1]) > tol]
    if bad:
        print(f"[!!] {tag}: 坐标不符 {bad} (tol={tol})  got={got} exp={expect}")
        return False
    print(f"[ok] {tag}: 点击 {got} 与期望一致")
    return True


def expect_shot(tag: str, rp: Replay, want: bool) -> bool:
    got = bool(rp.shots)
    if got != want:
        print(f"[!!] {tag}: 留证截图 {rp.shots} (期望{'有' if want else '无'})")
        return False
    return True


def run(title: str, scenes, holds: dict[int, float] | None = None) -> int:
    """跑一组场景并汇总。返回退出码（有 FAIL → 1）。

    scenes 项可以是 (name, frames, fn)，也可以带第 4 项 (name, frames, fn, holds)
    —— 每个场景的时序往往不同（有的要停在某帧、有的要等它翻页），共用一个 holds 会互相干扰。
    """
    print(f"=== {title} ===")
    res = [scene(s[0], s[1], s[2], holds=(s[3] if len(s) > 3 else holds)) for s in scenes]
    p, f, s = res.count("pass"), res.count("fail"), res.count("skip")
    print(f"=== 结果: PASS {p} / FAIL {f} / SKIP {s} (分母排除 SKIP) ===")
    return 1 if f else 0


def run_one(title: str, scenes, holds: dict[int, float] | None = None) -> None:
    """脚本尾部用: raise SystemExit(selftest_kit.run(title, scenes))"""
    raise SystemExit(run(title, scenes, holds=holds))


def no_click_on(tag: str, rp: Replay, frame: str) -> bool:
    """断言：停留在某帧期间**一次都没点**（用于「广告播放期绝不点屏幕」）。"""
    bad = [f for f in rp.click_frames if f == frame]
    if bad:
        print(f"[!!] {tag}: 在 {frame} 上发生了 {len(bad)} 次点击(期望 0)")
        return False
    print(f"[ok] {tag}: 停留在 {frame} 期间零点击")
    return True


def need(*frames: str) -> bool:
    """夹具齐不齐（个别场景想手动跳过时用）。"""
    return all((SHOTS_DIR / f).exists() for f in frames)


def main_argv() -> list[str]:
    return sys.argv[1:]
