"""局内战内「得分」读数器（世界竞赛 PVP 顶部中央那条）。

为什么单独开一个模块、不复用 wb/digits.py:
  wb/digits.py 服务的是「选择机友」页的 12×17 小字（细体），
  而战内得分是**另一套字体**（青蓝粗体 + 外发光，字形约 14×21）。
  实测三套字体的字形互不通用（同字错场景相关只有 0.4~0.6，而干净同字是 1.000）:
      ① 机友加成小字  ② 战内青色得分  ③ 战绩页大字
  所以模板必须各建各的，不能互相借。

为什么按「定间距切格」而不是连通域分割:
  数字带是等间距(18.2px)排列的，而战内数字带**外发光会把相邻字形连成一片**
  （实测按连通域切，7 位会粘成 6 个甚至 1 个 162px 的大块）。
  按格子切就绕开了分割问题——每格独立读，粘不粘都不影响。

读数只为一件事服务: 判断「得分是否 ≥ 400万」（达到就拖战机到顶部加速死亡）。
  ⇒ 所以不做全量 OCR，只做「首位数字 ≥ 4 吗」，并且**保守偏置**:
    证据不足时一律判「未达」，因为两类错误的代价不对称——
      误判「已达」(其实没到 400 万就去送死) = 直接输掉本来能赢的局；
      误判「未达」(其实到了但继续打)        = 只是多打一会儿，几乎无代价。

已知限制（不要乱补）:
  现有真帧只覆盖 {0,1,2,3,4,6,9} 七个字形，缺 {5,7,8}。
  来路不明的字形**不要**拿来凑数（曾有一份与 templates/digits 字形集重复、来源不明的
  templates/_digits/，dg3 出处不可查，2026-10-08 已清理；以后也别再造这类影子目录）：
  补错的代价是把 7/8/9 读成小数字 → 误判「未达」还好，反向就会误判「已达」。
  补齐需要再截一帧得分里含 5/7/8 的战内帧（要花一轮匹配）。

2026-10-08 实跑的三个教训（花了一轮匹配换来的，别再踩）:
  ① 假阳性拖顶：曾在一帧约 **300 万**时判出 ≥400万（同帧 read_score 是「读不出」），
     造成提前拖顶、白送胜势。根因两条：门槛 MARGIN 只有 0.06；格数按「所有非空格」计，
     闪效伪格会被算成第 8 位。现已收紧（MARGIN=0.12 + MIN_HI=0.70 + 连号计数），
     并要求**连续两次读数都判真**才允许拖顶（得分单调递增，真到了不会再掉回去）。
  ② 建模板时**不要**再乘 255：_norm() 是纯几何归一化，值域保持 0..255 不归一到 0..1。
     多乘一次 255 会 uint8 回绕 → 存进去的是垃圾图。症状好认：模板自相关只有 0.30。
  ③ 特效重的帧不能建库：局中战斗帧（光效/粒子满屏）切出的字形「4↔7 互为 0.87」，
     拿它补 dg7 会把 4 抢成 7。建库只用特效轻的帧（开局/结算）。
  附：本模块已用**独立帧**（未参与建模板，且特效最重的那一帧，真值 3734033）
     进了自检：逐字读不准（3133633），但 ≥400万 判据必须仍然判对 → 这才叫验证过。

用法:
    from wb.bscore import read_score, score_ge_4m
    if score_ge_4m(frame):   # 明确达到 400 万才为 True
        ...
    # 离线零消耗自证: uv run python wb/bscore.py --selftest
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "templates", "bdigits")

# --- 几何（基准帧 812×1518 = 当前客户区；游戏按高度等比、宽度居中，故 x 用「离画面中心的偏移」） ---
REF_W, REF_H = 812, 1518
BAND_Y0, BAND_Y1 = 76, 111        # 数字带上下缘（下缘压在发光装饰条之上, 否则条子会变成第 9 格）
X0_OFFSET = -146                  # 第 1 位数字左缘 = 画面中心 + (-146)
PITCH = 18.2                      # 数字等间距
MAX_DIGITS = 9
TH = 175                          # G 通道二值化阈值（青蓝字在高 G 上很亮）
CW, CH = 16, 20                   # 归一化画布
MARGIN = 0.12                     # 「首位≥4」需要领先的分数差（0.06 太松：实跑被一次画面闪效骗过）
MIN_HI = 0.70                     # 首位「高组」最佳分的下限（真字形通常 ≥0.85）

# 黄金夹具（真帧 + 已知真值，文件名就带着真值）—— 离线自证用，零消耗。
# 注意：**不能**直接用 endless_battle_end.png 当夹具——那是用例每跑一轮都会覆盖的落盘文件；
# 这里是拷出来的固定副本。
GOLDEN = [
    ("shots/bscore_4092602.png", 4092602, True),
    ("shots/bscore_3263612.png", 3263612, True),
    # 独立帧（实跑中抓的，未参与建模板）；含模板外的 7 → 只验 ≥400万 判据
    ("shots/bscore_3734033.png", 3734033, False),
]


def load_templates(tpl_dir: str = TPL_DIR) -> dict[str, np.ndarray]:
    out = {}
    for ch in "0123456789":
        p = os.path.join(tpl_dir, f"dg{ch}.png")
        if os.path.exists(p):
            g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if g is not None:
                out[ch] = g.astype(np.float32)
    return out


def _band(frame: np.ndarray, k: float) -> np.ndarray:
    """按 k 缩放 + 居中取数字带（G 通道）。"""
    h, w = frame.shape[:2]
    x0 = int(round(w / 2 + X0_OFFSET * k))
    y0, y1 = int(round(BAND_Y0 * k)), int(round(BAND_Y1 * k))
    x1 = min(w, x0 + int(round(MAX_DIGITS * PITCH * k)))
    y0, y1 = max(0, y0), min(h, y1)
    if not (0 <= x0 < x1 and y0 < y1):
        return np.zeros((1, 1), np.uint8)
    return frame[y0:y1, x0:x1, 1] if frame.ndim == 3 else frame[y0:y1, x0:x1]


def _glyphs(band: np.ndarray, k: float) -> list[np.ndarray | None]:
    """按定间距切格 → 每格的字形（去空白边）。"""
    pitch = PITCH * k
    n = min(MAX_DIGITS, max(1, int(band.shape[1] / pitch)))
    out = []
    for i in range(n):
        a, b = int(round(i * pitch)), int(round((i + 1) * pitch))
        cell = band[:, a:b]
        ys, xs = np.where(cell >= TH)
        if len(ys) < max(20, int(30 * k * k)):      # 墨迹太少 = 发光残影/装饰条, 不是数字
            out.append(None)
            continue
        out.append(cell[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy())
    return out


def _norm(p: np.ndarray) -> np.ndarray:
    """等比缩到画布内、居中底对齐（与 digits._norm 同为底对齐约定）。"""
    h, w = p.shape[:2]
    s = min(CH / max(h, 1), CW / max(w, 1))
    if s < 1:
        p = cv2.resize(p, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
        h, w = p.shape[:2]
    c = np.zeros((CH, CW), np.float32)
    c[CH - min(h, CH):, (CW - min(w, CW)) // 2:(CW - min(w, CW)) // 2 + min(w, CW)] = p[:CH, :CW]
    return c


def _scores(patch: np.ndarray, tpl: dict[str, np.ndarray]) -> dict[str, float]:
    """同尺寸比较（不滑窗——滑窗会让窄模板在宽字形内满分）。"""
    p = _norm(patch)
    return {ch: float(cv2.matchTemplate(p, t, cv2.TM_CCOEFF_NORMED)[0, 0]) for ch, t in tpl.items()}


def _run_cells(band: np.ndarray, k: float) -> tuple[int, list[np.ndarray]]:
    """从第 0 格起**连续**被占用的格数 + 这些字形。

    真分数是**左对齐**的：“3,734,033” 必占 0..6 格，不会在 8、9 格冒出一个孤格。
    因此只要遇到空格就停——孤立的发光残影/装饰条不进计数，也不会被当成数字拼到末尾。
    """
    gs = _glyphs(band, k)
    run = []
    for g in gs:
        if g is None:
            break
        run.append(g)
    return len(run), run


def read_score(frame: np.ndarray, tpl: dict[str, np.ndarray] | None = None) -> int | None:
    """读战内得分。读不出/不确定返回 None。"""
    tpl = tpl or load_templates()
    if not tpl:
        return None
    k = frame.shape[0] / REF_H
    _, cells = _run_cells(_band(frame, k), k)
    if not cells:
        return None
    digits = ""
    for g in cells:
        sc = _scores(g, tpl)
        ch = max(sc, key=sc.get)
        if sc[ch] < 0.55:                     # 认不出就不猜整数
            return None
        digits += ch
    try:
        return int(digits)
    except ValueError:
        return None


def score_ge_4m(frame: np.ndarray, tpl: dict[str, np.ndarray] | None = None) -> bool:
    """得分是否明确 ≥ 400万（保守：证据不足一律 False，见模块 docstring 的代价不对称）。

    先按**位数**粗筛（比逐字识别可靠得多）:
      位数 ≤ 6 → 必 < 100 万 → False
      位数 ≥ 8 → 必 ≥ 1000 万 → True（位数走「连号」计数，孤立伪格已挡掉）
      位数 = 7 → 才需要判首位 ≥ 4

    ⚠ 2026-10-08 实跑教训：本函数曾在**约 300 万**时返回 True（同帧 read_score 是「读不出」），
    造成提前拖顶、白送一局。根因：①「首位高组>低组」门槛只有 0.06，一次闪效落在首位格就能骗过；
    ② 格数用「所有非空格」计数，闪效伪格会被算成第 8 位。
    现收紧为 MARGIN=0.12 + 高组最佳分 ≥ MIN_HI + 连号计数，
    且**调用方**必须连续两次读数都判真才允许拖顶（见 endless_world.battle_watch）。
    """
    tpl = tpl or load_templates()
    if not tpl:
        return False
    k = frame.shape[0] / REF_H
    n, cells = _run_cells(_band(frame, k), k)
    if n <= 6:
        return False
    if n >= 8:
        return True
    sc = _scores(cells[0], tpl)
    hi = max((sc[c] for c in "456789" if c in sc), default=-2.0)
    lo = max((sc[c] for c in "0123" if c in sc), default=-2.0)
    return bool(hi >= MIN_HI and hi > lo + MARGIN)


def selftest() -> int:
    """用三帧战内真帧（4092602 / 3263612 / 3734033）验读数。零消耗，可反复跑。

    第三帧是 2026-10-08 实跑中抓的**独立帧**（未参与建模板，且是画面特效最重的时刻）：
    它含模板外的 7 → 逐字读不准（exact=False），但「≥400万」判据必须仍然判对。
    """
    tpl = load_templates()
    if not tpl:
        print(f"[fail] 没有战内数字模板, 先跑 tools/maint/build_bscore_digits.py (缺 {TPL_DIR})")
        return 1
    print(f"模板: {''.join(sorted(tpl))}  缺: {''.join(c for c in '0123456789' if c not in tpl) or '无'}")
    bad = 0
    for rel, truth, exact in GOLDEN:
        fp = os.path.join(ROOT, rel)
        if not os.path.exists(fp):
            print(f"  [skip] 缺夹具 {rel}")
            continue
        f = cv2.imread(fp)
        got = read_score(f, tpl)
        ok_r = (not exact) or got == truth          # exact=False 的帧含模板外字形, 只验判据不验逐字
        ok_g = score_ge_4m(f, tpl) == (truth >= 4_000_000)
        bad += (not ok_r) + (not ok_g)
        print(f"  {rel}: 真值{truth} 读出{got} "
              f"{'OK' if ok_r else ('仅验判据' if not exact else 'BAD')} | "
              f"≥400万 期望{truth >= 4_000_000} 判定{score_ge_4m(f, tpl)} {'OK' if ok_g else 'BAD'}")
    print(f"[{'ok' if not bad else 'fail'}] 战内得分读数 {len(GOLDEN) * 2 - bad}/{len(GOLDEN) * 2}")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(selftest())
    print(__doc__)
