"""扫荡面板「材料计数」读取器（金色描边数字，第 4 套字形）。

背景
----
扫荡面板顶部 4 个材料图标的底部有金色 3 位计数（= 该材料的持有数）。
`select_material` 想「优先扫材料最少的那个」。旧前提「4 个计数按升序排列」
**2026-10-11 实测已不成立**（273/289/268/304 非升序，早前那次的 711<763<810<831
只是巧合）→ 于是不再盲点第 1 个，改为**直接读 4 个计数取真正最小值**。

字形（第 4 套，与既有 3 套都不同源）
------------------------------------
  templates/digits   机友「战力」小字
  templates/bdigits  战内得分（bscore.py）
  templates/idigits  道具徽标（金底深色数字，icount.py）
本套是**金底描边数字**（暗底金字+黑描边），跨源最佳匹配仅 0.81 → 单建 templates/mdigits。

关键坑
------
  - 金色会大量命中图标本体 → 只取「图标底部计数带」（参考尺度 y 434..478）并做
    尺寸过滤（字形高 12..18px、宽 4..16px、面积 ≥25）。
  - 字形高会随阈值/尺度在 14..17 波动 → 归一化时**按高度拉伸到固定 20px**（保宽高比），
    再水平居中贴到 18×20 画布；同类字体同高，这样比「原样居中对齐」稳。
  - 4 个计数的读取窗 xc±50 互不重叠（图标间距 121），不会读到隔壁图标的计数。
  - 不同帧尺度不一（814×1507 / 812×1518）→ 统一缩到参考尺度 814×44 再读。

用法
----
    from wb.mcount import read_row, argmin_material
    counts = read_row(frame)          # [157, 176, 172, 161]（读不出的位 None）
    i = argmin_material(frame)        # 计数最少的图标序号 1..4；None = 读不出

自检（零消耗，用 5 帧真值夹具）
    uv run python wb/mcount.py --selftest
建库
    uv run python tools/maint/build_mcount_digits.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "templates", "mdigits")
SHOTS = os.path.join(ROOT, "shots")

# 参考尺度（客户区基准）
REF_W, REF_H = 814, 1507
STRIP_Y = (434, 478)          # 计数条带（参考尺度 y）
STRIP_H = STRIP_Y[1] - STRIP_Y[0]
ICON_XS = (178, 299, 420, 541)   # 4 个材料图标中心（参考尺度 x）
HALF = 50                     # 每个图标读数窗 xc±HALF（互不重叠）
CW, CH = 18, 20               # 归一化画布（宽×高）
MIN_SCORE = 0.55              # 单字最高分低于此 → 认不出（返回 None）

# 黄金夹具：5 帧真值条带（参考尺度 814×44）+ 4 个计数真值
GOLDEN: list[tuple[str, tuple[int, int, int, int]]] = [
    ("gmc_1.png", (157, 176, 172, 161)),   # 源 __clean_panel.png
    ("gmc_2.png", (273, 289, 268, 304)),   # 源 __verify_tab.png
    ("gmc_3.png", (155, 167, 166, 156)),   # 源 _dbgtab4_dbg_panel_normal.png
    ("gmc_4.png", (262, 279, 258, 293)),   # 源 _dbgtab6_dbg_tab2_selected.png
    ("gmc_5.png", (155, 170, 166, 159)),   # 源 _sweep_stage_normal_stop3.png
]


# ------------------------------------------------------------------ 工具
def _gold_mask(bgr: np.ndarray) -> np.ndarray:
    """金色（暗底金字+黑描边）：R 高、G 中高、B 低。"""
    b = bgr[:, :, 0].astype(int)
    g = bgr[:, :, 1].astype(int)
    r = bgr[:, :, 2].astype(int)
    return (((r > 170) & (g > 120) & (b < 130)).astype(np.uint8) * 255)


def _norm(patch: np.ndarray) -> np.ndarray:
    """字形 → 归一化画布：按高度拉伸到 20px（保宽高比），再水平居中。"""
    h, w = patch.shape[:2]
    if h <= 0 or w <= 0:
        return np.zeros((CH, CW), np.uint8)
    nw = max(1, int(round(w * (CH / h))))
    interp = cv2.INTER_AREA if nw <= w else cv2.INTER_LINEAR
    g = cv2.resize(patch, (nw, CH), interpolation=interp)
    c = np.zeros((CH, CW), np.uint8)
    x0 = max(0, (CW - nw) // 2)
    c[:, x0:x0 + min(nw, CW)] = g[:, :min(nw, CW)]
    return c


def _glyph_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """计数带里按 x 升序的字形框，做尺寸过滤。"""
    n, _lab, st, _ = cv2.connectedComponentsWithStats(mask)
    out = []
    for x, y, w, h, a in st[1:]:
        if 4 <= w <= 16 and 12 <= h <= 18 and a >= 25:
            out.append((int(x), int(y), int(w), int(h)))
    return sorted(out)


def strip_of(frame: np.ndarray) -> np.ndarray:
    """取「图标计数带」并归一到参考尺度 814×44。"""
    H, W = frame.shape[:2]
    y0 = int(round(STRIP_Y[0] * H / REF_H))
    y1 = int(round(STRIP_Y[1] * H / REF_H))
    band = frame[y0:y1, :]
    if W != REF_W or band.shape[0] != STRIP_H:
        band = cv2.resize(band, (REF_W, STRIP_H), interpolation=cv2.INTER_AREA)
    return band


# ------------------------------------------------------------------ 模板
def load_templates(tpl_dir: str = TPL_DIR) -> dict[str, list[np.ndarray]]:
    """载入 templates/mdigits/dg<c>_1.png..dg<c>_N.png → {'0': [数组, ...]}。

    每个数字存**多个样本**（不是单模板）：本字体的渲染随徽标落点/抗锯齿波动，
    单模板（medoid）会漏掉离群样本（实测 medoid 版把 289 读成 283）；多模板取
    最大值则稳得多（留一法 60/60）。
    """
    out: dict[str, list[np.ndarray]] = {ch: [] for ch in "0123456789"}
    if not os.path.isdir(tpl_dir):
        return out
    for fn in sorted(os.listdir(tpl_dir)):
        if not (fn.startswith("dg") and fn.endswith(".png")):
            continue
        ch = fn[2:3]
        if ch not in out:
            continue
        g = cv2.imread(os.path.join(tpl_dir, fn), cv2.IMREAD_GRAYSCALE)
        if g is not None:
            out[ch].append(g.astype(np.float32))
    return {ch: v for ch, v in out.items() if v}


def _score(patch: np.ndarray, tpl: np.ndarray) -> float:
    """同尺寸归一化相关的最大值（画布同尺寸 → 只取一个位置，不滑窗）。"""
    if patch.shape[0] < tpl.shape[0] or patch.shape[1] < tpl.shape[1]:
        return -2.0
    sub = patch[:tpl.shape[0], :tpl.shape[1]]
    return float(cv2.matchTemplate(sub, tpl, cv2.TM_CCOEFF_NORMED).max())


def read_digit(patch: np.ndarray,
               tpls: dict[str, list[np.ndarray]] | None = None) -> tuple[str | None, float]:
    """归一化字形 → (数字, 最高分)。分数过低返回 (None, 最高分)。"""
    tpls = tpls if tpls is not None else load_templates()
    if not tpls:
        return None, -2.0
    g = _norm(patch).astype(np.float32)
    best_ch, best = None, -2.0
    for ch, group in tpls.items():
        v = max((_score(g, t) for t in group), default=-2.0)
        if v > best:
            best, best_ch = v, ch
    if best < MIN_SCORE:
        return None, best
    return best_ch, best


# ------------------------------------------------------------------ 读数
def read_badge(band: np.ndarray, xc: int,
               tpls: dict[str, list[np.ndarray]] | None = None) -> int | None:
    """读某个图标（中心 xc，参考尺度）底部的计数。读不出返回 None。"""
    x0 = max(0, xc - HALF)
    x1 = min(band.shape[1], xc + HALF)
    mask = _gold_mask(band[:, x0:x1])
    boxes = _glyph_boxes(mask)
    if not (1 <= len(boxes) <= 4):
        return None
    s = ""
    for x, y, w, h in boxes:
        ch, _ = read_digit(mask[y:y + h, x:x + w], tpls)
        if ch is None:
            return None
        s += ch
    return int(s) if s else None


def read_row(frame: np.ndarray) -> list[int | None]:
    """读 4 个材料图标的计数。"""
    band = strip_of(frame)
    tpls = load_templates()
    return [read_badge(band, xc, tpls) for xc in ICON_XS]


def argmin_material(frame: np.ndarray) -> int | None:
    """返回计数**最少**的图标序号（1..4）；读不出/并列取最小序号。"""
    vals = read_row(frame)
    known = [(v, i) for i, v in enumerate(vals, 1) if v is not None]
    if not known:
        return None
    return min(known, key=lambda t: (t[0], t[1]))[1]


# ------------------------------------------------------------------ 自检
def selftest() -> int:
    """用 5 帧真值夹具校验 4×5=20 个计数读数（零消耗，可反复跑）。"""
    if not load_templates():
        print("[fail] 没有数字模板，先跑 uv run python tools/maint/build_mcount_digits.py")
        return 1
    total = bad = miss = 0
    for name, truth in GOLDEN:
        p = os.path.join(SHOTS, name)
        if not os.path.exists(p):
            print(f"[skip] 缺少夹具 {p}")
            continue
        band = cv2.imread(p)   # 夹具本身就是参考尺度条带（814×44），直读
        tpls = load_templates()
        got = [read_badge(band, xc, tpls) for xc in ICON_XS]
        for i, want in enumerate(truth):
            total += 1
            if got[i] == want:
                continue
            bad += 1
            miss += got[i] is None
            print(f"  FAIL {name} #{i+1} 真值 {want} 读出 {got[i]}")
        print(f"  {name} 真值 {list(truth)} → 读出 {got}")
    print(f"[{'ok' if not bad else 'fail'}] 材料计数读数 {total - bad}/{total}"
          f"（认不出 {miss}）")
    return 0 if not bad else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print(__doc__)
