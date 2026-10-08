"""小字数字读取器(为「选择机友」的加成判定而生, 可复用于其它读数场景)。

背景: 「选择机友」页每行有「总分数 723% + <加成> %」和下方小字「战力 NNNNN」。
加成 = 战力 ÷ 100, 规则是「选第一个加成 < 700 的行」, 等价于判断战力首位数字 < 7。

为什么不用通用 OCR:
  1. 不想引第三方依赖(项目零依赖风格);
  2. 连通域 + 等尺寸模板比对在这类「同一字体同一字号」的读数上更可控,
     而且模板和判定都能离线自证(见 selftest), 不依赖每日次数。

关键坑(实测踩过, 改回滑窗就复现):
  **窄模板会在宽字形内部滑窗满分**——用 `matchTemplate(...).max()` 时, 8px 宽的
  「1」模板能在「7」的竖笔画里找到 1.0 的匹配, 于是 74188 被读成 14188。
  所以统一把字形「居中贴到底部对齐的定尺寸画布」后按同尺寸比对, 不再滑窗。

用法:
    from wb.digits import is_ge700, first_digit_ge
    if is_ge700(frame, yc):        # yc = 该行「战力」小字的 y 中心(帧坐标)
        ...

自检(零消耗, 用存档真帧 + 已知真值):
    uv run python wb/digits.py --selftest
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "templates", "digits")

CW, CH = 16, 20          # 归一化画布(实测字形约 12×17, 「1」更窄)
GOLDEN = os.path.join(ROOT, "shots", "b_selrow4_0.png")   # 选择机友真帧(黄金夹具)
# 黄金夹具的 5 行「战力」小字中心 y(帧坐标, 812×1518)+ 真值
GOLDEN_ROWS = [(432, "75690"), (598, "74188"), (764, "74066"),
               (930, "53806"), (1095, "40125")]


def _norm(patch: np.ndarray) -> np.ndarray:
    """把字形居中、底对齐贴到 CW×CH 黑底画布, 返回 float32 灰度。"""
    h, w = patch.shape[:2]
    c = np.zeros((CH, CW), np.uint8)
    x0 = max(0, (CW - w) // 2)
    y0 = max(0, CH - h)
    c[y0:y0 + min(h, CH), x0:x0 + min(w, CW)] = patch[:min(h, CH), :min(w, CW)]
    return c.astype(np.float32)


def load_templates(tpl_dir: str = TPL_DIR) -> dict[str, np.ndarray]:
    """载入 templates/digits/dg0.png..dg9.png → {'0': 灰度, ...}。"""
    out = {}
    for ch in "0123456789":
        p = os.path.join(tpl_dir, f"dg{ch}.png")
        if os.path.exists(p):
            g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if g is not None:
                out[ch] = g.astype(np.float32)
    return out


def _score(patch: np.ndarray, tpl: np.ndarray) -> float:
    """同尺寸(或模板更小)时的归一化相关; 只取对齐位置, 不滑窗。"""
    if patch.shape[0] < tpl.shape[0] or patch.shape[1] < tpl.shape[1]:
        return -2.0
    sub = patch[:tpl.shape[0], :tpl.shape[1]]
    return float(cv2.matchTemplate(sub, tpl, cv2.TM_CCOEFF_NORMED).max())


def _glyphs(gray: np.ndarray, yc: int, x0: int = 494, x1: int = 566,
            y_off: tuple[int, int] = (58, 88)) -> list[tuple[int, int, int, int]]:
    """取「战力」小字那行的数字字形框(自动切分粘连), 按 x 升序。

    只保留 x0..x1 区间内的连通域, 避开左边的「战力」二字和右边的装饰。
    """
    ya, yb = yc + y_off[0], yc + y_off[1]
    if ya < 0 or yb > gray.shape[0]:
        return []
    band = gray[ya:yb, x0:x1]
    _, m = cv2.threshold(band, 110, 255, cv2.THRESH_BINARY)
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    out = []
    for x, y, w, h, a in st[1:]:
        if a <= 20 or h < 12 or not (2 <= x <= x1 - x0 - 2):
            continue
        if w > 18:                                  # 相邻数字粘连 → 按 ~12.5px 均分
            k = max(1, round(w / 12.5))
            sw = w / k
            for j in range(k):
                out.append((x0 + int(x + j * sw), ya + y, int(sw), h))
        else:
            out.append((x0 + x, ya + y, w, h))
    return sorted(out)


def first_digit_ge(frame: np.ndarray, yc: int,
                   digits: str = "789") -> tuple[bool, dict[str, float]]:
    """该行「战力」首位数字是否落在 digits 里(默认 {7,8,9} ⇔ 加成 ≥ 700)。

    返回 (判定, 各数字得分)。用 argmax 比较, 不依赖绝对阈值。
    """
    tpl = load_templates()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    gs = _glyphs(gray, yc)
    if not gs:
        return False, {}
    x, y, w, h = gs[0]
    p = _norm(gray[y:y + h, x:x + w])
    sc = {ch: round(_score(p, t), 3) for ch, t in tpl.items()}
    hi = max((sc[c] for c in digits if c in sc), default=-2.0)
    lo = max((sc[c] for c in sc if c not in digits), default=-2.0)
    return hi > lo, sc


def is_ge700(frame: np.ndarray, yc: int) -> bool:
    """该行加成是否 ≥ 700(⇔ 战力首位数字 ≥ 7)。"""
    return first_digit_ge(frame, yc)[0]


def read_row(frame: np.ndarray, yc: int) -> str:
    """读整行 5 位战力(仅供诊断; 选中行高亮会换色, 读数可能偏差)。"""
    tpl = load_templates()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    out = ""
    for x, y, w, h in _glyphs(gray, yc):
        p = _norm(gray[y:y + h, x:x + w])
        out += max(tpl, key=lambda c: _score(p, tpl[c]))
    return out


def selftest() -> int:
    """用黄金夹具(真帧)校验「首位 ≥7」判定。零消耗, 可反复跑。"""
    if not os.path.exists(GOLDEN):
        print(f"[skip] 缺少黄金夹具 {GOLDEN}")
        return 0
    frame = cv2.imread(GOLDEN)
    if not load_templates():
        print("[fail] 没有数字模板, 先跑 tools/maint/build_digits.py")
        return 1
    bad = 0
    for yc, truth in GOLDEN_ROWS:
        want = truth[0] in "789"
        got, sc = first_digit_ge(frame, yc)
        hi = max((sc[c] for c in "789" if c in sc), default=-2.0)
        lo = max((sc[c] for c in sc if c not in "789"), default=-2.0)
        ok = got == want
        bad += not ok
        print(f"  行 y={yc} 真值{truth} 首位={truth[0]} 判定≥700={got} "
              f"(≥7:{hi:.3f} <7:{lo:.3f}) {'OK' if ok else 'FAIL'}")
    print(f"[{'ok' if not bad else 'fail'}] 首位≥7 判定 {len(GOLDEN_ROWS)-bad}/{len(GOLDEN_ROWS)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print(__doc__)
