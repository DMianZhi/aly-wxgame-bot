"""核心实现：窗口截屏、模板匹配、拟人点击。合一模块，方便维护。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes  # noqa: F401  确保 ctypes.wintypes 可用
from ctypes import wintypes
import random
import sys
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import pyautogui

user32 = ctypes.windll.user32

# DPI 感知：否则在高分屏缩放下 GetClientRect/ClientToScreen 坐标全部错位
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

pyautogui.FAILSAFE = False   # ⚠ 不能用 pyautogui 的内置急停: 它把**四个角**都当急停点,
#   而**右上角 (W-1, 0) 正是系统「关闭/最大化」按钮的位置** —— 用户用电脑点一下关闭、
#   鼠标停在右上角, 之后 **每次 moveTo 都立即抛 FailSafeException**。
#   （2026-10-14 实测鼠标 (2559,0) 就连崩 4 个用例、每个 ~12s。）
#   → 改用下面 _failsafe_check(): **只认左上角**, 与设计原意（“鼠标甩到左上角”）一致。
pyautogui.MINIMUM_DURATION = 0.08
pyautogui.MINIMUM_SLEEP = 0.03

_WM_INPUTLANGCHANGEREQUEST = 0x0050   # 请求窗口切换输入语言
_KLF_ACTIVATE = 0x0001                # LoadKeyboardLayoutW 标志


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


_SCALE_CACHE: tuple | None = None      # (key, canvas) —— 见 _scaled_canvas


def _scaled_canvas(img: np.ndarray, cw: int, ch: int, w: int, h: int) -> np.ndarray:
    """整帧重采样结果**单槽缓存**（同一帧 + 同一候选尺寸只算一次）。

    ⚠️ 2026-10-15 性能（用户反馈「没有 loading，为什么每步还要等这么久」）：
       match_adaptive 对**每个候选尺寸**都要 resize 整帧（`_resize_candidates` 有 4~5 个），
       而未命中时要**遍历全部候选** —— 于是同一帧上连续查 N 个模板
       = N × 4~5 次「整帧 resize + 全图匹配」。实测 goto_home 一轮 21 次查询 = **29s**
       （日志里两次「返回」间隔 12~14s 就是这个）。
       同一帧 + 同一目标尺寸的结果是确定的 → 缓存最近一帧的缩放结果（key 含 id/shape），
       命中缓存即可省掉绝大部分 resize 开销。
    """
    global _SCALE_CACHE
    key = (id(img), img.shape[0], img.shape[1], cw, ch)
    c = _SCALE_CACHE
    if c is not None and c[0] == key:
        return c[1]
    canvas = cv2.resize(
        img, (cw, ch),
        interpolation=cv2.INTER_AREA if cw < w else cv2.INTER_LINEAR)
    _SCALE_CACHE = (key, canvas)
    return canvas


def match_adaptive(img: np.ndarray, tpl: np.ndarray, threshold: float,
                   pre=None):
    """窗口尺寸≠基准时多候选重采样取最高分，坐标自动映射回真实客户区。

    尺寸一致时走原路径，零额外开销。
    pre: 可选 (canvas, tpl) -> (canvas', tpl') 预处理钩子，在每个重采样候选上
    于匹配前调用（字形二值化等「必须先重采样再处理」的匹配走这里）。
    """
    h, w = img.shape[:2]
    cands = _resize_candidates(w, h)
    if len(cands) == 1 and cands[0] == (w, h):   # 尺寸就是基准尺寸，走原路径零开销
        return match_template(*(pre(img, tpl) if pre else (img, tpl)), threshold)
    order = list(range(len(cands)))
    hint = _GEOM_HINT.get((w, h))
    if hint is not None and hint < len(order):   # 上次成功的假设优先，命中即省下其他候选
        order.remove(hint)
        order.insert(0, hint)
    best = None
    best_i = 0
    for i in order:
        cw, ch = cands[i]
        canvas = img if (cw, ch) == (w, h) else _scaled_canvas(img, cw, ch, w, h)
        hit = match_template(*(pre(canvas, tpl) if pre else (canvas, tpl)), threshold)
        if hit is None:
            continue
        sx, sy = w / cw, h / ch
        got = (round(hit[0] * sx), round(hit[1] * sy), hit[2])
        if best is None or got[2] > best[2]:
            best, best_i = got, i
        # ⚠️ 2026-10-15 性能（用户反馈「没有 loading，为什么每步还要等这么久」）：
        #   旧条件是 `>= max(0.97, threshold+0.07)` —— 而实测命中分常年在
        #   **0.90~0.97**（颜色模板随皮肤漂移），于是**永远不提前结束**，
        #   每个模板都要遍历全部 4~5 个候选尺寸 → 单模板 ~0.2s，goto_home 一轮十几秒。
        #   改成「**命中即停**」：只要能过 threshold 就已经算找到（threshold 本身留了余量，
        #   TEMPLATE_MIN 另有专项下限），分数高低只影响置信**不影响坐标**，继续试探只会
        #   在更低的候选上重复做无用功。
        if best[2] >= threshold + 0.02:
            break
    if best is None:
        return None
    _GEOM_HINT[(w, h)] = best_i
    if (w, h) not in _SIZE_NOTED:
        _SIZE_NOTED.add((w, h))
        print(f"[窗口自适应] 客户区 {w}x{h} ≠ 模板基准 {REF_SIZE[0]}x{REF_SIZE[1]}，"
              f"按 {cands[best_i]} 归一后匹配（命中坐标已反映射）", file=sys.stderr)
    return best


# 部分模板强制最低分：广告「已获得奖励」在广告还在播时会被「N秒后可获得奖励」蹭到 0.87
TEMPLATE_MIN = {
    "ad_rewarded": 0.93,   # 到账 0.97~1.00 / 播放中 0.87，必须分得开
}

# ---------------------------------------------------------------- 文字字形识别
# 微信广告浮层每个广告皮肤都换底色/背景，颜色模板得分漂移 —— 2026-10-13 当日皮肤
# ad_rewarded_v3 只剩 0.91~0.92，被上面 0.93 闸死 → 广告永远关不掉（当天的
# 十几张 *_unknown 留证帧全是这一种病根）。而浮层上的**白色文字**（「关闭」「已
# 获得奖励」）跨皮肤不变，变的只是药丸底色和透出的背景 → 二值化后匹配即免疫换肤。
# 安全属性在文字层依然成立: 播放中「关闭」二字已经在了（左侧带倒计时数字），
# 但左药丸没有「已获得奖励」→ 闸门照样拦住（校准见 tools/selftest/ad_text_selftest.py）:
#   到账帧 ≥0.908 / 播放帧 ≤0.828（关闭）、≤0.802（已获得奖励，"N秒后可获得奖励"蹭分）。
TEXT_MATCH = {
    "ad_close": 0.86,
    "ad_rewarded": 0.86,
}
_TXT_Y_MAX = 300     # 浮层药丸只出现在顶部条（基准坐标 y≈100~170），其余涂黑防误配


def _bin_glyph(canvas: np.ndarray, tpl: np.ndarray):
    """白色字形二值化（match_adaptive 的 pre 钩子）。

    阈值 200 + 3x3 膨胀：留抗锯齿余量，把笔画填实（校准扫描结论 th=200/dilate，
    正负余量两侧最均衡）。画布 y>_TXT_Y_MAX 涂黑 —— 广告浮层之外游戏自己的
    「关闭」文字按钮不该参与匹配。
    """
    b = (cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY) >= 200).astype(np.uint8)
    b[_TXT_Y_MAX:] = 0
    t = (cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) >= 200).astype(np.uint8)
    k = np.ones((3, 3), np.uint8)
    return cv2.dilate(b, k) * 255, cv2.dilate(t, k) * 255


def find_on_frame(img: np.ndarray, name: str, threshold: float):
    """在一帧上找 name（Screen.look 与 find_in_game 的共用入口）。

    颜色变体取最高分；TEXT_MATCH 里的名字再走白色字形路径，**文字命中优先**
    （换肤免疫的通用路径），颜色变体兜底非文字皮肤（如 ✕ 图标）。
    """
    threshold = max(threshold, TEMPLATE_MIN.get(name, 0.0))
    best = None
    for tpl in _template_variants(name):
        hit = match_adaptive(img, tpl, threshold)
        if hit is not None and (best is None or hit[2] > best[2]):
            best = hit
    gate = TEXT_MATCH.get(name)
    if gate is not None:
        from .cfg import TEMPLATE_PATH
        t = cv2.imread(str(TEMPLATE_PATH(name + "_txt")))
        if t is not None:
            hit = match_adaptive(img, t, gate, pre=_bin_glyph)
            if hit is not None:
                return hit
    return best


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
    匹配逻辑统一走 find_on_frame（含白色文字路径）。
    """
    return find_on_frame(grab_window(rect), name, threshold)


# --------------------------------------------------------------- 拟人点击

def configure_mouse(dry_run: bool) -> None:
    # 自定义急停(只认左上角)已接管 → 保持 pyautogui 内置四角急停**关闭**（见模块顶部说明）。
    # dry-run 本来就不动鼠标，无需特殊处理。
    pyautogui.FAILSAFE = False


FAILSAFE_PX = 4             # 鼠标落在左上角这么大范围内 = 急停手势


def _failsafe_check() -> None:
    """自定义急停：**只认屏幕左上角**（用户约定「鼠标甩到左上角」）。

    ⚠ 为什么不用 pyautogui.FAILSAFE: 它把**四个角**都当急停点, 而右上角 (W-1, 0)
      正是系统「关闭/最大化」按钮的位置 —— 用户用电脑点一下关闭、鼠标停在右上角,
      之后每次 moveTo 都立即抛 FailSafeException（2026-10-14 批量跑**连环崩 4 个用例**
      的真因: 实测鼠标 (2559,0)，每个用例 12s 就崩）。
    """
    try:
        x, y = pyautogui.position()
    except Exception:                        # 取不到位置就当没急停
        return
    if x <= FAILSAFE_PX and y <= FAILSAFE_PX:
        raise pyautogui.FailSafeException(
            f"急停: 鼠标在屏幕左上角 ({x},{y}) → 用户要求停止")


def _ensure_foreground(rect: WinRect) -> bool:
    """前台守卫：游戏窗口不在前台就置前，避免点击落到别的窗口上。

    SetForegroundWindow 对后台进程常静默失败(实测点广告关闭时点了个空)，
    所以先 SetWindowPos 提到 z 序顶再重试几次；窗口最小化才 ShowWindow 还原。
    重试仍失败则升级到 **ALT 键技巧**：Windows 前台锁只允许「刚刚有过输入」的进程
    抢前台，假按一下 ALT 就能骗过它。

    返回是否真的前置成功(2026-10-11 起: 失败时调用方必须拒绝点击, 见 click_xy)。

    ⚠ 2026-10-09 实跑教训：endless 用例老代码自带一版 `_focus()`(就是这个 ALT 技巧)，
    迁移时我一度判定它「冗余（click_xy 已调 _ensure_foreground）」而删掉 —— 结果第 1 轮
    的点击被静默丢掉（日志只有那句 warn，页面没动，白跑一轮）。孤本技巧不能想当然删。
    ⚠ 2026-10-12 实跑教训：用户正在用电脑时(前台锁死)所有重试+ALT 全失败, 旧版只打
    warn 照样点 → 点击全打到无关窗口上(桌面/别的应用)。现在返回 False, click_xy 拦截。
    """
    user32 = ctypes.windll.user32
    if user32.GetForegroundWindow() == rect.hwnd:
        return True
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
            return True
        if i == 2:                                  # 常规重试已连续失败 → 上 ALT 键技巧
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.ShowWindow(rect.hwnd, SW_RESTORE)
            user32.SetForegroundWindow(rect.hwnd)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.35)
            if user32.GetForegroundWindow() == rect.hwnd:
                time.sleep(0.15)
                return True
    print("[warn] 游戏窗口未能置于前台，点击可能落在其他窗口上；请手动点一下游戏窗口",
          file=sys.stderr)
    return False


def _point_on_game(rect: WinRect, sx: int, sy: int) -> bool:
    """点击点 (屏幕坐标) 的最顶层窗口是否仍是游戏窗口（或其子窗口）。"""
    pt = wintypes.POINT(int(sx), int(sy))
    win = user32.WindowFromPoint(pt)
    if not win:
        return False
    root = user32.GetAncestor(win, 2)               # GA_ROOT
    return bool(root) and root == rect.hwnd


def wheel_xy(cx: int, cy: int, notches: int, rect: WinRect, dry_run: bool = False,
             *, pause: float = 0.05) -> None:
    """在窗口内 (cx,cy) 处滚动滚轮（微信游戏圈翻帖/翻右栏用；需逐格, 一次滚太远会跳）。

    notches>0 向上、<0 向下，一格 = WHEEL_DELTA(120)。与 click_xy 共用同一个前台护栏。
    ⚠ 必须走这一层: 用例里直接调 pyautogui 会绕过离线自检的替身, 自检时就会真滚鼠标。
    """
    if dry_run or notches == 0:
        return
    x, y = cx + rect.x, cy + rect.y
    _guard_click(rect, x, y)
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    step = 120 if notches > 0 else -120
    for _ in range(abs(int(notches))):
        user32.mouse_event(0x0800, 0, 0, step, 0)      # MOUSEEVENTF_WHEEL
        time.sleep(pause)


def type_text(text: str, rect: WinRect, dry_run: bool = False, *, interval: float = 0.15) -> None:
    """向窗口输入文本（聊天/评论框）。只支持可直接键入的 ASCII；中文需 IME, 用例不涉及。

    调用前会确认窗口在前台（否则键盘输入会打进别的窗口）。与 click_xy 同理,
    必须收在这一层 —— 自检要能整体替换掉它，避免离线回放真的往当前窗口敲字。
    """
    if dry_run:
        return
    _guard_click(rect, rect.x + rect.w // 2, rect.y + rect.h // 2)
    time.sleep(0.25)
    pyautogui.write(text, interval=interval)


def ime_english(rect: WinRect, dry_run: bool = False) -> bool:
    """把目标窗口的输入语言切到「英语(美国)」(HKL 0x0409)，幂等，返回是否成功。

    ⚠ 实测坑（2026-10-13 兑换码用例）：中文输入法下 type_text 可能被抾持成汉字
    （实测输入框出现过 `8SJFTSTY篇N` → 游戏报「无效兑换码」）。
    IMM32 在这里**无效**：ImmGetContext 返回 0（游戏自绘输入框没有 IME 上下文）。
    改用 PostMessage(WM_INPUTLANGCHANGEREQUEST, hkl_en) 请求目标窗口换输入语言
    —— 实测 HKL 0x804 → 0x409，可靠且幂等（不会像单击 Shift 那样反向切回中文）。
    """
    if dry_run:
        return False
    _ensure_foreground(rect)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
        user32.LoadKeyboardLayoutW.restype = wintypes.HKL
        hkl = user32.LoadKeyboardLayoutW("00000409", _KLF_ACTIVATE)   # 英语(美国)
        if not hkl:
            return False
        hwnd = user32.GetForegroundWindow()
        user32.PostMessageW(wintypes.HWND(hwnd), _WM_INPUTLANGCHANGEREQUEST,
                            0, ctypes.c_void_p(hkl))
        time.sleep(0.4)
        return True
    except Exception:
        return False


def clear_text(rect: WinRect, dry_run: bool = False) -> None:
    """清空当前输入框（全选 + 删除）。与 type_text 同理，键盘输入只走这一层。

    游戏「输入文字」弹窗**会保留上一轮的文字**（实测：不清空 → 多轮输入累积成乱码），
    所以每轮输入前必须清一次。
    """
    if dry_run:
        return
    _guard_click(rect, rect.x + rect.w // 2, rect.y + rect.h // 2)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")


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
    sx, sy = x1 + rect.x, y1 + rect.y
    ex, ey = x2 + rect.x, y2 + rect.y
    _guard_click(rect, sx, sy)   # 拖拽同样不许点进无关窗口(2026-10-12)
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


def _guard_click(rect: WinRect, sx: int, sy: int) -> None:
    """点击护栏(2026-10-12): 前置失败后再验证点击点最顶层窗口。

    用户正在用电脑时前台锁死, 前置必然失败 —— 旧版只打 warn 照样点,
    实测点击全打到桌面/无关窗口上(差点误点别的东西)。现在直接拒绝点击:
    用例会以未预期异常收场(code=1 + 留证), 绝不点进无关窗口。
    """
    if _ensure_foreground(rect):
        return
    if not _point_on_game(rect, sx, sy):
        raise RuntimeError(
            f"点击护栏: 游戏窗口不在点击点({sx},{sy})的最顶层"
            "(被其它窗口盖住/Windows 前台锁定) → 已拒绝点击, 防止点进无关窗口; "
            "请把游戏窗口置前或等电脑空闲后再跑")


def click_xy(cx: int, cy: int, jitter: int, delay: tuple[float, float],
             rect: WinRect, dry_run: bool) -> None:
    """拟人单击：随机偏移 + 随机时长移动 + 随机停顿。坐标含窗口修正。

    2026-10-10 用户两轮要求加快, 现为「真人快速点击」风格: 移动 0.08~0.16s、
    点前停顿 0.02~0.05s —— 随机区间保留(防「过于规律」的风控), 只压时长。
    """
    jx = cx + rect.x + random.randint(-jitter, jitter)
    jy = cy + rect.y + random.randint(-jitter, jitter)
    if dry_run:
        return
    _failsafe_check()                        # 自定义急停(只认左上角, 见模块顶部说明)
    _guard_click(rect, jx, jy)
    pyautogui.moveTo(jx, jy, duration=random.uniform(0.08, 0.16))
    time.sleep(random.uniform(0.02, 0.05))
    pyautogui.click()
    time.sleep(random.uniform(*delay))
