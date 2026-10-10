"""核心实现：窗口截屏、模板匹配、拟人点击。合一模块，方便维护。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes  # noqa: F401  确保 ctypes.wintypes 可用
import random
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import pyautogui

# DPI 感知：否则在高分屏缩放下 GetClientRect/ClientToScreen 坐标全部错位
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

pyautogui.FAILSAFE = True   # 紧急停止：把鼠标甩到屏幕左上角 (0,0)
pyautogui.MINIMUM_DURATION = 0.08
pyautogui.MINIMUM_SLEEP = 0.03


# --------------------------------------------------------------- 窗口与截屏

@dataclass
class WinRect:
    x: int  # 客户区左上角的屏幕坐标（点击换算基准）
    y: int
    w: int  # 客户区尺寸（= 截图尺寸）
    h: int
    hwnd: int = 0  # 窗口句柄（PrintWindow / 前台守卫用）


def find_game_window(title_keyword: str, process_name: str = "") -> Optional[WinRect]:
    """按 标题关键字 + 进程名 找游戏窗口，返回最大可见窗口矩形（物理像素）。

    优先级：标题+进程都命中 > 仅进程命中（标题可能变化）> 仅标题命中。
    过程名过滤可排除浏览器里同名标签页窗口（如 Edge 的 msedge 进程）。
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    )
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)

    by_title: list[WinRect] = []
    by_proc: list[WinRect] = []
    by_both: list[WinRect] = []
    title_kw = title_keyword or ""
    proc_kw = (process_name or "").lower()

    def _proc_name(hwnd) -> str:
        """取窗口所属进程的 exe 文件名（小写），失败返回空串。"""
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(handle)
        return ""

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        cr = ctypes.wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(cr)):
            return True
        if cr.right <= 120 or cr.bottom <= 120:  # 过滤工具条等小窗口
            return True
        pt = ctypes.wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        rect = WinRect(pt.x, pt.y, cr.right, cr.bottom, hwnd=hwnd)
        t_hit = bool(title_kw) and title_kw in buf.value
        p_hit = bool(proc_kw) and _proc_name(hwnd) == proc_kw
        if t_hit and p_hit:
            by_both.append(rect)
        elif t_hit:
            by_title.append(rect)
        elif p_hit:
            by_proc.append(rect)
        return True

    user32.EnumWindows(cb, 0)
    pool = by_both or (by_proc if proc_kw else []) or by_title
    if not pool:
        return None
    return max(pool, key=lambda r: r.w * r.h)


def grab_window(rect: WinRect) -> np.ndarray:
    """PrintWindow 抓取窗口客户区画面（窗口被遮挡也能抓到本身内容）。"""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    w, h = rect.w, rect.h

    # DPI 感知：按窗口句柄取真实物理尺寸（有些系统返回逻辑像素）
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        pass

    hdc = user32.GetWindowDC(rect.hwnd)
    if not hdc:
        raise RuntimeError("GetWindowDC 失败，窗口可能已关闭")
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    # PW_RENDERFULLCONTENT=2: 强制直渲染窗口内容（Chromium/硬件加速窗口必需）
    ok = user32.PrintWindow(rect.hwnd, mem, 2)

    class BMIHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_ulong), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                    ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_ulong),
                    ("biSizeImage", ctypes.c_ulong), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_ulong),
                    ("biClrImportant", ctypes.c_ulong)]

    class BMI(ctypes.Structure):
        _fields_ = [("bmiHeader", BMIHEADER), ("bmiColors", ctypes.c_ulong * 3)]

    bmi = BMI()
    bmi.bmiHeader.biSize = ctypes.sizeof(BMIHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)  # DIB_RGB_COLORS

    img = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR).copy()

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(rect.hwnd, hdc)
    if not ok:
        raise RuntimeError("PrintWindow 失败")
    return img


# --------------------------------------------------------------- 模板匹配

def match_template(screen: np.ndarray, tpl: np.ndarray, threshold: float):
    """在 screen 中找 tpl 最佳位置。返回 (中心x, 中心y, 置信度) 或 None（窗口内坐标）。"""
    if tpl.shape[0] > screen.shape[0] or tpl.shape[1] > screen.shape[1]:
        return None
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None
    th, tw = tpl.shape[:2]
    return (max_loc[0] + tw // 2, max_loc[1] + th // 2, float(max_val))


# --------------------------------------------------------------- 窗口自适应
# 模板基准客户区：templates/*.png 全部是在这个尺寸的画面里裁出来的。
# 客户区尺寸一变（用户拖窗口 / 显示器缩放变了 / 换机器），游戏画布会按比例缩放，
# 固定 1:1 的模板匹配就会失配甚至静默指错位置。实测：
#   画布缩到 0.8×(676x1217) 时首页模板 1.0 → 0.42~0.58；放到 1.10× 时 → 0.67~0.81（已不能点）。
#   注意“窗口变窄”未必会缩放画布：游戏按高度等比、宽度裁切居中，
#   845x1521 → 813x1519 时画布只缩了 0.13%，裸匹配仍能到 0.96，但落点整体左移约 15px。
# 所以匹配前先把画面重采样回基准尺寸，命中坐标再反映射回真实客户区。
REF_SIZE: tuple[int, int] = (845, 1521)
MEASURED: tuple[int, int] = (812, 1518)   # 项目里绝大多数真帧的尺寸（常量多在此帧上量出）
CLIENT_TITLE_H = 77             # 微信小游戏顶部自绘标题栏高度（固定设备像素，不随窗口缩放）
_GEOM_HINT: dict[tuple[int, int], int] = dict()  # (W,H) -> 上次命中的候选序号（下次先用它）
_SIZE_NOTED: set[tuple[int, int]] = set()     # 已提示过的尺寸，只提示一次


def map_point(x: int, y: int, src: tuple[int, int], dst: tuple[int, int]) -> tuple[int, int]:
    """把在 src 尺寸帧上标定的点换算到 dst 尺寸帧（标题栏固定不缩放）。

    全项目**唯一**的几何换算，ref_to_client / client_to_ref / croplab.scale_crops
    都走这里 —— 免得同一个公式在三处各写一遍、改一处忘一处。
        s  = (dst_h - TITLE) / (src_h - TITLE)
        x' = (x - src_w/2) * s + dst_w/2    # 按高等比 + 宽度居中（两边同时留边/裁切）
        y' = TITLE + (y - TITLE) * s
    """
    sw, sh = src
    dw, dh = dst
    s = (dh - CLIENT_TITLE_H) / max(1, sh - CLIENT_TITLE_H)
    return (round((x - sw / 2) * s + dw / 2),
            round(CLIENT_TITLE_H + (y - CLIENT_TITLE_H) * s))


def map_rect(x: int, y: int, w: int, h: int,
             src: tuple[int, int], dst: tuple[int, int]) -> tuple[int, int, int, int]:
    """矩形版的 map_point（宽高按同一 s 缩放，保证不出现 0 宽高）。"""
    s = (dst[1] - CLIENT_TITLE_H) / max(1, src[1] - CLIENT_TITLE_H)
    bx, by = map_point(x, y, src, dst)
    return bx, by, max(1, round(w * s)), max(1, round(h * s))


def scale_delta(dx: int, dy: int, src: tuple[int, int], dst: tuple[int, int]) -> tuple[int, int]:
    """在 src 帧上量的**相对偏移** → dst 帧。

    用于「模板命中 + 偏移」定位（锚点随画面自适应，偏移也得跟着缩放）:
    两帧里两个相邻点的位移只差一个 s，常量项（居中/标题栏）相消，所以只看增量。
    不缩放就是隐形 bug: 812 上量的 300px 偏移，到 601 宽只应该走 222px。
    """
    s = (dst[1] - CLIENT_TITLE_H) / max(1, src[1] - CLIENT_TITLE_H)
    return round(dx * s), round(dy * s)


def ref_to_client(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    """基准坐标（845x1521 下标出来的点）-> 当前客户区坐标。

    为什么不能拿基准坐标当点击坐标：游戏画布是**按高等比 + 宽度居中裁切**渲染的，
    而顶部 77px 标题栏是固定像素、不跟着缩放 —— 窗口越小，基准坐标偏得越离谱。
    实测（真值分别由模板命中 / 颜色环圆心量出），下面三个尺寸误差都 <=1px:
        845x1521 -> (755,1296)    812x1518 -> (738,1293)    601x1143 -> (546, 977)
    """
    return map_point(x, y, REF_SIZE, (w, h))


def client_to_ref(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    """当前客户区坐标 → 基准坐标（与 ref_to_client 互逆；标定常量时用）。

    用于把「在某张实帧上量出来的坐标」归一到基准尺寸：实帧是 812x1518 就用 812x1518 当 (w,h)。
    这样常量进代码前统一成基准口径，click_base/roi 再换到实时窗口 —— 在标定尺寸上往返恒等，
    换到别的窗口尺寸才算得准。
    """
    return map_point(x, y, (w, h), REF_SIZE)


def ref_rect_to_client(x: int, y: int, w: int, h: int,
                       cw: int, ch: int) -> tuple[int, int, int, int]:
    """基准矩形 -> 当前客户区矩形（供像素判态/区域裁剪用），宽高按同一 s 缩放。"""
    return map_rect(x, y, w, h, REF_SIZE, (cw, ch))


def measured_rect(x: int, y: int, w: int, h: int,
                  frame: tuple[int, int]) -> tuple[int, int, int, int]:
    """在 frame 这张实帧上量出的矩形 (x,y,w,h) -> **基准矩形**。

    矩形在全项目只有**一种口径**: `(x, y, 宽, 高)`、基准空间、用 `sc.roi(*r)` 消费。
    以前允许「四角点 (x0,y0,x1,y1)」并存，消费端写 `sc.roi(x0,y0,x1-x0,y1-y0)` ——
    两种写法混用时会算出负数宽高、ROI 静默变空（friend_stamina / star_supply 都踩过）。
    把「取宽高」这一步收进这里，调用点就再也没有手算的机会。
    """
    return map_rect(x, y, w, h, frame, REF_SIZE)


def _resize_candidates(w: int, h: int) -> list[tuple[int, int]]:
    """把当前画面重采样回基准坐标系的候选尺寸（去重；identity 优先）。"""
    rw, rh = REF_SIZE
    if (w, h) == (rw, rh):
        return [(w, h)]
    cands = [(rw, rh)]                                       # ①拉伸铺满
    for s in (rw / w, rh / h):                               # ②③等比缩放(留边)
        cands.append((round(w * s), round(h * s)))
    k = (rw / w + rh / h) / 2                                # ④两者折中
    cands.append((round(w * k), round(h * k)))
    cands.append((w, h))                                     # ⑤原像素不缩放：微信广告「已获得奖励/关闭」
                                                             #   等原生浮层按固定像素渲染，不随游戏画布缩放
    out: list[tuple[int, int]] = []
    for c in cands:
        if c[0] < 32 or c[1] < 32 or c in out:
            continue
        out.append(c)
    return out


def match_adaptive(img: np.ndarray, tpl: np.ndarray, threshold: float):
    """窗口尺寸≠基准时多候选重采样取最高分，坐标自动映射回真实客户区。

    尺寸一致时走原路径，零额外开销。
    """
    h, w = img.shape[:2]
    cands = _resize_candidates(w, h)
    if len(cands) == 1 and cands[0] == (w, h):   # 尺寸就是基准尺寸，走原路径零开销
        return match_template(img, tpl, threshold)
    order = list(range(len(cands)))
    hint = _GEOM_HINT.get((w, h))
    if hint is not None and hint < len(order):   # 上次成功的假设优先，命中即省下其他候选
        order.remove(hint)
        order.insert(0, hint)
    best = None
    best_i = 0
    for i in order:
        cw, ch = cands[i]
        canvas = img if (cw, ch) == (w, h) else cv2.resize(
            img, (cw, ch),
            interpolation=cv2.INTER_AREA if cw < w else cv2.INTER_LINEAR)
        hit = match_template(canvas, tpl, threshold)
        if hit is None:
            continue
        sx, sy = w / cw, h / ch
        got = (round(hit[0] * sx), round(hit[1] * sy), hit[2])
        if best is None or got[2] > best[2]:
            best, best_i = got, i
        if best[2] >= max(0.97, threshold + 0.07):   # 命中够硬，省下其余假设
            break
    if best is None:
        return None
    _GEOM_HINT[(w, h)] = best_i
    if (w, h) not in _SIZE_NOTED:
        _SIZE_NOTED.add((w, h))
        print(f"[窗口自适应] 客户区 {w}x{h} ≠ 模板基准 {REF_SIZE[0]}x{REF_SIZE[1]}，"
              f"按 {cands[best_i]} 归一后匹配（命中坐标已反映射）")
    return best


# 部分模板强制最低分：广告「已获得奖励」在广告还在播时会被「N秒后可获得奖励」蹭到 0.87
TEMPLATE_MIN = {
    "ad_rewarded": 0.93,   # 到账 0.97~1.00 / 播放中 0.87，必须分得开
}


def _template_variants(name: str):
    """同名模板的多个变体：<name>.png, <name>_v2.png, ...

    有的元素会换皮（典型：微信广告的「已获得奖励 / 关闭」不同广告样式不同），
    保留旧版当兼容、新版加变体，任一命中即可。
    """
    from .cfg import TEMPLATE_PATH

    out, missing = [], False
    for suffix in ("", "_v2", "_v3", "_v4"):
        p = TEMPLATE_PATH(name + suffix)
        t = cv2.imread(str(p)) if p.is_file() else None
        if t is not None:
            out.append(t)
        elif suffix == "":
            missing = True
    if missing:
        raise FileNotFoundError(
            f"模板 {TEMPLATE_PATH(name)} 不存在或无法读取，请先放入模板图"
        )
    return out


def find_in_game(name: str, rect: WinRect, threshold: float):
    """在游戏窗口截图中找模板 templates/<name>.png（含 _v2/_v3 变体）。

    返回 (cx, cy, score) 或 None，取所有变体里的最高分。
    部分模板强制更高阈值(见 TEMPLATE_MIN)：如广告「已获得奖励」在广告还在播时
    会被「N秒后可获得奖励」蹭到 0.87，若用默认 0.86 会提前点关闭，
    触发「暂未获得奖励 是否继续观看视频」弹窗。
    """
    threshold = max(threshold, TEMPLATE_MIN.get(name, 0.0))
    img = grab_window(rect)
    best = None
    for tpl in _template_variants(name):
        hit = match_adaptive(img, tpl, threshold)
        if hit is not None and (best is None or hit[2] > best[2]):
            best = hit
    return best


# --------------------------------------------------------------- 拟人点击

def configure_mouse(dry_run: bool) -> None:
    pyautogui.FAILSAFE = not dry_run  # dry-run 是无头测试，别让 FAILSAFE 误触发


def _ensure_foreground(rect: WinRect) -> None:
    """前台守卫：游戏窗口不在前台就置前，避免点击落到别的窗口上。

    SetForegroundWindow 对后台进程常静默失败(实测点广告关闭时点了个空)，
    所以先 SetWindowPos 提到 z 序顶再重试几次；窗口最小化才 ShowWindow 还原。
    重试仍失败则升级到 **ALT 键技巧**：Windows 前台锁只允许「刚刚有过输入」的进程
    抢前台，假按一下 ALT 就能骗过它。

    ⚠ 2026-10-09 实跑教训：endless 用例老代码自带一版 `_focus()`(就是这个 ALT 技巧)，
    迁移时我一度判定它「冗余（click_xy 已调 _ensure_foreground）」而删掉 —— 结果第 1 轮
    的点击被静默丢掉（日志只有那句 warn，页面没动，白跑一轮）。孤本技巧不能想当然删。
    """
    user32 = ctypes.windll.user32
    if user32.GetForegroundWindow() == rect.hwnd:
        return
    SW_RESTORE, HWND_TOP = 9, 0
    SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002
    VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
    if user32.IsIconic(rect.hwnd):
        user32.ShowWindow(rect.hwnd, SW_RESTORE)
    user32.SetWindowPos(rect.hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)
    for i in range(6):
        user32.SetForegroundWindow(rect.hwnd)
        time.sleep(0.2)
        if user32.GetForegroundWindow() == rect.hwnd:
            time.sleep(0.15)
            return
        if i == 2:                                  # 常规重试已连续失败 → 上 ALT 键技巧
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.ShowWindow(rect.hwnd, SW_RESTORE)
            user32.SetForegroundWindow(rect.hwnd)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.35)
            if user32.GetForegroundWindow() == rect.hwnd:
                time.sleep(0.15)
                return
    print("[warn] 游戏窗口未能置于前台，点击可能落在其他窗口上；请手动点一下游戏窗口")


def drag_xy(x1: int, y1: int, x2: int, y2: int, rect: WinRect, dry_run: bool = False,
            *, hold: float = 0.0, steps: int = 12, step_pause: float = 0.03,
            duration: float = 0.0, pre: float = 0.0) -> None:
    """按住 (x1,y1) 拖到 (x2,y2)——游戏内坐标（窗口修正同 click_xy）。

    为什么必须放在这里而不是用例里 import pyautogui:
      ① 拖拽是游戏交互，应该和点击一样只有一处（改坐标映射、加护栏时不会漏）；
      ② 用例里直接调 pyautogui 会绕过离线自检的替身 → 自检时**真动鼠标**（很危险）。

    steps/step_pause: 分步挪动（列表滑动用它，游戏要看到连续位移）；
    duration: 单次平滑移动（拖战机用它，保持与实跑一致的手感）。
    无论如何收尾一定会松键（finally）。
    """
    if dry_run:
        return
    _ensure_foreground(rect)
    sx, sy = x1 + rect.x, y1 + rect.y
    ex, ey = x2 + rect.x, y2 + rect.y
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.1, 0.25))
    if pre:
        time.sleep(pre)
    pyautogui.mouseDown()
    try:
        if duration > 0:
            pyautogui.moveTo(ex, ey, duration=duration)
        else:
            for k in range(1, max(1, steps) + 1):
                pyautogui.moveTo(sx + (ex - sx) * k / steps, sy + (ey - sy) * k / steps)
                time.sleep(step_pause)
        if hold:
            time.sleep(hold)
    finally:
        pyautogui.mouseUp()


def click_xy(cx: int, cy: int, jitter: int, delay: tuple[float, float],
             rect: WinRect, dry_run: bool) -> None:
    """拟人单击：随机偏移 + 随机时长移动 + 随机停顿。坐标含窗口修正。

    2026-10-10 用户两轮要求加快, 现为「真人快速点击」风格: 移动 0.08~0.16s、
    点前停顿 0.02~0.05s —— 随机区间保留(防「过于规律」的风控), 只压时长。
    """
    _ensure_foreground(rect)
    jx = cx + rect.x + random.randint(-jitter, jitter)
    jy = cy + rect.y + random.randint(-jitter, jitter)
    if dry_run:
        return
    pyautogui.moveTo(jx, jy, duration=random.uniform(0.08, 0.16))
    time.sleep(random.uniform(0.02, 0.05))
    pyautogui.click()
    time.sleep(random.uniform(*delay))
