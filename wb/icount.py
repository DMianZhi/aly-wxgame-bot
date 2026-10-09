"""道具数量徽标读数（第 4 套字形：金底深色数字）。

为什么单独一套
--------------
徽标数字的字体与既有两套都不通用（实测自匹配仅 0.42~0.72）：
  templates/digits   机友加成小字
  templates/bdigits  战内得分（bscore.py）
与顶部「12/20」计数也不是同款（跨源最佳 0.08）。→ 单独建 templates/idigits。

徽标 = 持有数量（已用真帧证实）
-------------------------------
战前准备页每个**已持有**道具的图标左上角有金底方块徽标，数字即持有数：
  11:03 帧：炽焰冲击 9 / 烈火 10 / 圣光 1 / 灰烬 7
  11:43 帧：炽焰冲击 9 / 烈火 13 / 圣光 1 / 灰烬 10
  两帧间用例各买 3 件 → 烈火 +3、灰烬 +3；没买到的炽焰冲击 9→9 不变 ✓
  「祝福」无徽标（推测为常驻/被动道具，不占数量）——所以**无徽标 ≠ 数量 0**，
  本模块对「找不到徽标」按 0 处理（沿用旧行为：照买，不多花钱也不少买）。

只用它判「够不够 3 件」
-----------------------
闪击需要各 3 件；已有 ≥3 再买就是白花钱。识别只认 templates/idigits 里已有的字形，
**认不出就当「≥3」不买**（保守不花钱，并把徽标存盘当补字形的素材）。
已知缺口：数字 4/5/6/8 无模板 → 本来就 ≥3（判对）；
「2」已从实跑真帧收割（2026-10-09）。

自检：python wb/icount.py --selftest
建库：python wb/icount.py --build     # 从已标注真帧收割字形
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TPL_DIR = ROOT / 'templates' / 'idigits'
SHOTS = ROOT / 'shots'

NEED = 3                                    # 闪击需要的件数
H = W = 28                                  # 字形归一化到 28×28
ACCEPT = 0.80                               # 同字形自匹配 0.90~1.00，跨数字 ≤0.68 → 0.80 落在空档
GOLD_LO, GOLD_HI = (15, 120, 150), (35, 255, 255)
BADGE_XMAX = 200                            # 徽标只在左列
INK_TH = 120                                # 徽标内数字是深色（金底）

_TPL: dict[str, np.ndarray] | None = None


# ------------------------------------------------------------------ 字形工具
def _norm(g: np.ndarray) -> np.ndarray:
    """等比缩到高 H、居中补到 W×W（宽高比保留 → 1 与 7/9 不会被拉成同一形状）。"""
    h, w = g.shape[:2]
    nw = max(1, int(round(w * H / h)))
    r = cv2.resize(g, (nw, H), interpolation=cv2.INTER_AREA)
    if r.shape[1] > W:
        r = cv2.resize(r, (W, H), interpolation=cv2.INTER_AREA)
    out = np.zeros((H, W), np.uint8)
    x = (W - r.shape[1]) // 2
    out[:, x:x + r.shape[1]] = r
    return out


def _ink(box: np.ndarray) -> np.ndarray:
    """徽标图 → 白字黑底二值图（徽标是金底深字）。"""
    g = cv2.cvtColor(box, cv2.COLOR_BGR2GRAY)
    return (g < INK_TH).astype(np.uint8) * 255


def _glyphs(bw: np.ndarray, min_w: int = 3, min_h: int = 10, pad: int = 2) -> list[np.ndarray]:
    """按列投影切出单个数字（去掉圆角/边框像素）。"""
    bw = bw.copy()
    bw[:pad, :] = bw[-pad:, :] = bw[:, :pad] = bw[:, -pad:] = 0
    cols = bw.sum(0) // 255
    runs, s = [], None
    for i, v in enumerate(cols):
        if v and s is None:
            s = i
        elif not v and s is not None:
            runs.append((s, i))
            s = None
    if s is not None:
        runs.append((s, len(cols)))
    out = []
    for a, c in runs:
        if c - a < min_w:
            continue
        sub = bw[:, a:c]
        rows = np.where(sub.sum(1) > 0)[0]
        if len(rows) < min_h:
            continue
        out.append(sub[rows[0]:rows[-1] + 1, :])
    return out


def templates() -> dict[str, np.ndarray]:
    global _TPL
    if _TPL is None:
        _TPL = {}
        if TPL_DIR.is_dir():
            for p in sorted(TPL_DIR.glob('dg*.png')):
                g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                if g is None:
                    continue
                # 极性按边缘（背景）色判定，别用均值：字小的图均值会低，会被误翻转
                border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
                dark_bg = float(np.median(border)) < 128
                g = (g > 127).astype(np.uint8) * 255 if dark_bg else (g < 128).astype(np.uint8) * 255
                ys, xs = np.where(g.sum(1) > 0)[0], np.where(g.sum(0) > 0)[0]
                if not len(ys) or not len(xs):
                    continue
                _TPL[p.stem[2:]] = _norm(g[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1])
    return _TPL


# ------------------------------------------------------------------ 定位与读数
def locate(frame: np.ndarray, x_max: int = BADGE_XMAX) -> list[tuple[int, int, int, int]]:
    """找所有金底徽标（左列近方块），按 y 升序。用像素检测定位，不硬编码坐标。"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, GOLD_LO, GOLD_HI)
    n, _lab, st, _cen = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for x, y, w, h, a in st[1:]:
        if x < x_max and 34 <= w <= 62 and 32 <= h <= 56 and a > 0.55 * w * h:
            out.append((int(x), int(y), int(w), int(h)))
    out.sort(key=lambda b: b[1])
    return out


def crop(frame: np.ndarray, b: tuple[int, int, int, int], inset: int = 3) -> np.ndarray:
    """从金块框内缩裁切：只留金底+数字，不带页面底色（否则切字会被底色污染）。"""
    x, y, w, h = b
    return frame[y + inset:y + h - inset, x + inset:x + w - inset]


def read(box: np.ndarray) -> tuple[int | None, float]:
    """徽标图 → (数量, 置信度)。任一位认不出 → (None, 该位最佳分)。"""
    gl = _glyphs(_ink(box))
    if not gl:
        return None, 0.0
    tpl = templates()
    if not tpl:
        return None, 0.0
    val, conf = '', 1.0
    for g in gl:
        ng = _norm(g)
        best, bk = -1.0, None
        for k, t in tpl.items():
            s = float(cv2.matchTemplate(ng, t, cv2.TM_CCOEFF_NORMED)[0][0])
            if s > best:
                best, bk = s, k
        if best < ACCEPT:
            return None, best
        val += bk
        conf = min(conf, best)
    return int(val), conf


def held(frame: np.ndarray, row_y: int, tol: int = 110) -> tuple[int | None, float, bool]:
    """按行 y 取该行道具的持有数 → (数量|None, 置信度, 是否找到徽标)。

    找不到徽标 → (None, 0.0, False)：视为 0 件（旧行为照买）。
    找到徽标但认不出 → (None, conf, True)：保守不买，同时存图留证。
    """
    best = None
    for b in locate(frame):
        cy = b[1] + b[3] / 2
        d = abs(cy - row_y)
        if d <= tol and (best is None or d < best[0]):
            best = (d, b)
    if best is None:
        return None, 0.0, False
    b = best[1]
    box = crop(frame, b)
    n, conf = read(box)
    if n is None:
        import time
        p = SHOTS / f'_icount_unknown_{int(time.time())}.png'
        SHOTS.mkdir(exist_ok=True)
        cv2.imwrite(str(p), cv2.resize(box, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC))
    return n, conf, True


def need(n: int | None, want: int = NEED) -> int:
    """按持有数算还需买几件：≥want 不买；不足则补到 want；None → 按 0 件（照买）。"""
    return max(0, want - (0 if n is None else n))


def price_txt(label: str) -> str:
    return label


# ------------------------------------------------------------------ 建库（收割字形）
LABELED = (
    ('_endless_r2_prep.png', ('9', '10', '1', '7')),
    ('_endless_r1_prep.png', ('9', '13', '1', '10')),
    # r3：2026-10-09 现抓（列表滚动位置不同 → 顺带验一次行→徽标映射）
    #   大图目视核过：9 / 13 / 2 / 10，其中「2」是圣光（本次新增字形）
    ('_endless_r3_prep.png', ('9', '13', '2', '10')),
)


def build() -> int:
    """从已标注真帧收割字形写入 templates/idigits（已有字形不覆盖）。"""
    TPL_DIR.mkdir(parents=True, exist_ok=True)
    have = {p.stem[2:] for p in TPL_DIR.glob('dg*.png')}
    got: dict[str, np.ndarray] = {}
    for name, exp in LABELED:
        p = SHOTS / name
        f = cv2.imread(str(p))
        if f is None:
            print(f'  跳过（读不到）: {p}')
            continue
        badges = locate(f)
        if len(badges) != len(exp):
            print(f'  ✗ {name}: 徽标 {len(badges)} 个，标注 {len(exp)} 个 → 不一致')
            return 1
        for (x, y, w, h), lbl in zip(badges, exp):
            gl = _glyphs(_ink(f[y:y + h, x:x + w]))
            if len(gl) != len(lbl):
                print(f'  ✗ {name}@{y}: 切出 {len(gl)} 位，标注「{lbl}」{len(lbl)} 位')
                return 1
            for d, g in zip(lbl, gl):
                if d not in have and d not in got:
                    got[d] = g
    if not got:
        print(f'  无新字形（已有 {sorted(have)}）')
        return 0
    for d, g in sorted(got.items()):
        cv2.imwrite(str(TPL_DIR / f'dg{d}.png'), g)
        print(f'  写入 {TPL_DIR / f"dg{d}.png"}  shape={g.shape}')
    print(f'  字形集 = {sorted(have | set(got))}')
    return 0


# ------------------------------------------------------------------ 自检（真帧断言）
def selftest() -> int:
    tpl = templates()
    bad = 0
    if not tpl:
        print(f'✗ 无模板（{TPL_DIR}）→ 先跑 --build', file=sys.stderr)
        return 1
    missing = [n for n, _ in LABELED if not (SHOTS / n).exists()]
    if len(missing) == len(LABELED):
        print(f'SKIP 缺真帧夹具（需实跑截帧）: {", ".join(missing)}')
        return 0
    print(f'字形集 {sorted(tpl)}（{len(tpl)} 个）')
    for name, exp in LABELED:
        f = cv2.imread(str(SHOTS / name))
        if f is None:
            print(f'SKIP {name}（缺夹具）')
            continue
        badges = locate(f)
        if len(badges) != len(exp):
            print(f'✗ {name} 徽标数 {len(badges)} ≠ {len(exp)}')
            bad += 1
            continue
        vals = []
        for b in badges:
            n, conf = read(crop(f, b))
            vals.append(n)
            if n is None:
                print(f'✗ {name}@{b[1]} 未识别（conf={conf:.3f}）')
                bad += 1
        want = [int(e) for e in exp]
        ok = vals == want
        print(('✓' if ok else '✗') + f' {name}: 读到 {vals}，期望 {want}')
        bad += 0 if ok else 1
    # 跨字形分离度（负向对照：任一字形不能被别的字形骗到 ACCEPT 以上）
    worst = 0.0
    for k, t in tpl.items():
        for k2, t2 in tpl.items():
            if k == k2:
                continue
            worst = max(worst, float(cv2.matchTemplate(t, t2, cv2.TM_CCOEFF_NORMED)[0][0]))
    sep_ok = worst < ACCEPT
    print(('✓' if sep_ok else '✗') + f' 跨字形最大相似 {worst:.3f} < ACCEPT {ACCEPT}')
    bad += 0 if sep_ok else 1
    # ── 购买决策（≥3 不买是本次需求）
    cases = [(9, 0), (13, 0), (7, 0), (3, 0), (2, 1), (1, 2), (0, 3), (None, 3), (10, 0)]
    for n, want in cases:
        got = need(n)
        ok = got == want
        print(('✓' if ok else '✗') + f' need({n}) = {got}，期望 {want}')
        bad += 0 if ok else 1
    # held(): 真帧按行取数 + 无徽标行的兑底
    f0 = cv2.imread(str(SHOTS / LABELED[0][0]))
    if f0 is not None:
        for row, want in ((525, 9), (679, 10), (987, 7)):
            n, conf, found = held(f0, row)
            ok = found and n == want and conf >= ACCEPT
            print(('✓' if ok else '✗') + f' held(y={row}) = {n}(conf={conf:.3f},found={found})，期望 {want}')
            bad += 0 if ok else 1
        n, conf, found = held(f0, 400)          # 离最近徽标 125px > tol 110 → 视为无徽标（按 0 件）
        ok = n is None and not found
        print(('✓' if ok else '✗') + f' held(y=400 无徽标) = {n}(found={found})，期望 (None, False)')
        bad += 0 if ok else 1
    # 真帧计数的购买决策：两张帧的三个待买道具都是 ≥3 → 一件都不买（省钱）
    for name, exp in LABELED:
        f = cv2.imread(str(SHOTS / name))
        vals = [read(crop(f, b))[0] for b in locate(f)]
        buy = [need(v) for v in vals[:2] + vals[3:]]        # 徽标序 = 炽焰冲击/烈火/圣光/灰烬，圣光不买
        ok = buy == [0, 0, 0]
        print(('✓' if ok else '✗') + f' {name}: 待买三件持有 {vals[:2] + vals[3:]} → 需买 {buy}（期望全 0）')
        bad += 0 if ok else 1
    if bad:
        print(f'\nFAIL {bad} 项')
        return 1
    print('\nPASS icount 全绿')
    return 0


if __name__ == '__main__':
    if '--build' in sys.argv:
        raise SystemExit(build())
    if '--selftest' in sys.argv:
        raise SystemExit(selftest())
    print(__doc__)
