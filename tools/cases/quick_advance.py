#!/usr/bin/env python
"""用例: 快速进阶（把背包里的绿色装备当材料吃掉，循环到没有「绿≥2」的行）。

    链路:
    首页 --(warehouse_btn)--> 仓库(wh_title) --(wh_bag)--> 背包(bag_title)
    --(qa_entry 快速进阶)--> 列表页「选择快速进阶装备」(qa_title)
    四页签依次(战机/装甲/副武器/僚机, qa_tab_*):
        扫列表(视口内不够就上滑)找「有绿装」的行 → 点该行主图 → 详情页(qa_dtitle)
          ┌ 数量面板: 每槽「−」点到变灰(=0); 绿槽「+」×2 → qa_ok 确定
          │ qa_pickexp 选择经验 → qa_auto 自动选择 → qa_mok 确认
          │ qa_go 快速进阶(黄) → 二次确认弹窗 qa_confirm → 「恭喜获得」→ claim_btn 领取
          └ 回详情页(材料刷新成游戏默认值) → 重复, 直到绿槽数量 < 2
        详情页 X(sweep_close) → **直接回背包**(实测, 不回列表页)
        → 重新 qa_entry 进列表页 → 重新点页签(重进后页签回到战机)
    收尾: run_case 统一回首页

⚠ 绿装判据 = 材料格下方**数字牌底色**, 不是边框也不是图面: 边框只 2~3px, 且第 4 格
   (白框)的图面天然带绿色水晶 —— 按边框取样会把「白框绿图」误判成绿装(实测其顶边
   43 个绿像素 > 绿装格 22 个)。数字牌是 60x30 实心色块直接标品质: 实测 38% vs 0%。
   列表页的绿簇预筛故意放宽(≥1 簇) —— 详细判绿在详情页做(数字牌过硬), 认错顶多多进一次
   详情页, 不会漏(把白框绿图行点开, 里面自然没绿装, 榨不动直接退)。
⚠ 槽内数量**不读数字、不用 OCR**: 「−」点到底**停在 0 不回绕**, 所以「点几下 − 才变灰」
   就是该槽数量 —— 既清零又数出绿槽有几件, 一举两得。实测「+」封顶在持有数。
⚠ 「调整数量」与「确定」同位置同形状(只差字色) → 实测互命中 0.789, 查它抬到 TH_ADJ;
   页面标志靠 qa_dtitle(含 ? 图标) 与列表页 qa_title 区分(实测互不命中 0.593/0.549)。
⚠ 已访问去重: 绿装只剩 1 件的行**榨不干、仍留在列表里**, 会被反复选中 → 死循环。
   用「行内主图裁剪 + 逐像素平均差」记住访问过的行(上滑后行位置变, 但行内容不变)。
   ⚠ 不用模板匹配做这层去重: 低对比裁剪上 TM_CCOEFF_NORMED 会在任意位置假命中(老坑)。
⚠ 二次确认弹窗是「消耗金币/经验高于手动进阶」的提示 + 「今日不再提示」勾选框:
   **不勾**那个框(不替用户改游戏设置), 每轮都当它存在来处理; 但它也可能已被勾掉而不弹,
   所以点完 qa_go 后按「弹窗或结果页」二选一等(见 refine_row)。

用法:
    uv run python tools/cases/quick_advance.py [--max 6] [--dry]
    --max N  单个页签最多处理几行(防呆, 默认 6)
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot, kit  # noqa: E402
from wb.kit import log  # noqa: E402

TH = 0.86                # 通用阈值
TH_ADJ = 0.90            # 「调整数量」: 与「确定」同类同位置(互命中 0.789) → 抬高
TH_CLAIM = 0.92          # 「领取」: 多页同款(弹层实测 0.945) → 抬高
TH_ENTRY = 0.88          # 「快速进阶」入口绿键

REF = (814, 1507)        # 模板与坐标的实测帧尺寸
NAP_UI = 0.7             # 普通界面反应(用户明确要求加快 → 每次点击后都有 page() 复判兜底)
NAP_FAST = 0.08          # ± 连点间隔
NAP_OPEN = 1.2           # 点开详情页/关页
REFINE_SKIP = -2         # refine_row: 成本闸门不过 → 跳过该行(不是错误)
COST_IOU = 0.80           # 闸门门限。实测: 夹具金标准帧 1.000; 真机这版页面 0.857
# (字模取自 814 宽旧帧, 缩放后仍有差异); 不符价的帧远低于此。且闸门已改告警不拦,
# 门限只影响日志噪声, 不影响行为。
COST_RECT = (379, 810, 116, 30)   # 详情页「消耗资源」金币数字(基准坐标)
S_TH = 0.55              # S 徽标判据: 橙心占比下限(颜色判据, 非模板匹配)
# 现场标定(824x1518 真帧, 窗口 44x44 在格子左上附近 ±14/±18 扫描取最大橙心占比):
#   正: 现场详情「消耗装备」真 S 格 0.634 / 现场列表 S 行左上 0.816
#   负: 现场详情第2列 0.000 / 旧帧非S材料格 0.000 / 列表非S行(紫折角) 0.159
# 对比: 旧模板匹配法 正 0.540 vs 负 0.456(只差 0.09, 换张底图就翻) → 已废弃模板法。
BURST_DELAY = 0.04       # 连点期间把 sc.delay 压到这么小(± 连点用)
DRAIN_MAX = 40           # 单槽 − 最多点几下(防呆)
GREEN_MIN = 0.15         # 数字牌绿占比阈值(实测: 绿装格 37.9%/39.0%, 非绿格 0.0%)
LIST_GREEN_MIN = 60      # 列表页绿簇最小面积(预筛, 故意放宽)
ROW_GAP = 150            # 同一行多个绿簇的 y 归并容差(行距~160, 行内绿簇散布≤~90)
SCROLL_MAX = 10          # 单页签最多上滑几次(旧值 4 只够前 ~4 行 → 下面的行全看不到)
GATE_BLOCK = False       # 成本闸门是否拦截(False=只告警留证); 见 refine_row 里的说明
SAME_ROW_DIFF = 12.0     # 行裁剪「同一条」判定: 逐像素平均差阈值
ROW_MAX = 12             # 单行最多进阶几轮(防呆)

# ---- 实测坐标(_qa_s5_qty.png, 814x1507) ----
# 四列槽位: + 在 y=554、− 在 y=688, x 中心 114/211/307/403; 材料格 y 578..664
SLOT_X = tuple(_bot.client_to_ref(x, 0, *REF)[0] for x in (114, 211, 307, 403))
Y_PLUS = _bot.client_to_ref(0, 554, *REF)[1]
Y_MINUS = _bot.client_to_ref(0, 688, *REF)[1]
ROW_ICON_X = _bot.client_to_ref(120, 0, *REF)[0]   # 列表页行主图 x(点击打开该行)
ROW_SIG = _bot.client_to_ref(120 - 44, 0, *REF)[0]  # 行主图裁剪左边界(去重用)
ROW_SIG_W = 88
LIST_AREA = _bot.measured_rect(180, 262, 320, 940, REF)   # 列表页判绿装区(避开标题/页签)

HOME, WH, BAG, LIST, DETAIL, MAT, DIALOG, RESULT, UNKNOWN = (
    "HOME", "WH", "BAG", "LIST", "DETAIL", "MAT", "DIALOG", "RESULT", "?")

TABS = (("plane", "战机"), ("armor", "装甲"), ("sub", "副武器"), ("wing", "僚机"))

PLAN = """[dry] 计划:
  首页 --(warehouse_btn)--> 仓库 --(wh_bag)--> 背包 --(qa_entry)--> 列表页「选择快速进阶装备」
  四页签 战机/装甲/副武器/僚机, 每个页签:
      扫列表(视口内没有未处理的绿装行就上滑, 最多 4 次)
      有绿装行 → 点该行主图 → 详情页
          数量面板: 每槽「−」点到变灰(清零), 数出绿槽件数; 绿槽「+」×2 → 确定
          选择经验 → 自动选择 → 确认
          快速进阶(黄) → 二次确认弹窗(只点绿确认, 不动「今日不再提示」) → 领取
        材料刷新后重复, 直到绿槽 < 2(不再硬凑)
        详情页 X → 直接回背包 → 重进列表页 → 重点页签
  收尾: 统一回首页"""


# ----------------------------------------------------------------- 小工具

def _hit(st: dict, name: str, th: float = TH) -> bool:
    h = st.get(name)
    return h is not None and h[2] >= th


def _find(sc: kit.Screen, name: str, th: float = TH):
    """模板缺失时返回 None(不炸)，便于逐步补模板。"""
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def _tap(sc: kit.Screen, name: str, label: str, *, th: float = TH, tries: int = 3,
         wait: float = NAP_UI) -> bool:
    try:
        return sc.tap(name, th=th, tries=tries, wait=wait, label=label)
    except FileNotFoundError:
        log(f"✗ 模板 {name}.png 不存在")
        return False


def page(sc: kit.Screen) -> str:
    """当前页面: 结果页 > 二次确认弹窗 > 选料面板 > 详情页 > 列表页 > 背包 > 仓库 > 首页。

    判层顺序要紧: 「恭喜获得」是全屏暗幕会把底下标志压掉, 用 claim_btn 命中且
    qa_dtitle 不命中来认它; 二次确认弹窗只盖中间、标题栏还在, 必须先于详情页判。
    """
    st = sc.look("claim_btn", "qa_confirm", "qa_mtitle", "qa_dtitle", "qa_title",
                 "qa_entry", "bag_title", "wh_title", "warehouse_btn", "stage_btn")
    if _hit(st, "claim_btn", TH_CLAIM) and not _hit(st, "qa_dtitle"):
        return RESULT
    if _hit(st, "qa_confirm"):
        return DIALOG
    if _hit(st, "qa_mtitle"):
        return MAT
    if _hit(st, "qa_dtitle"):
        return DETAIL
    if _hit(st, "qa_title"):
        return LIST
    if _hit(st, "bag_title") or _hit(st, "qa_entry", TH_ENTRY):
        return BAG
    if _hit(st, "wh_title"):
        return WH
    if _hit(st, "stage_btn"):
        return HOME
    return UNKNOWN


# ----------------------------------------------------------------- 数量面板(颜色判态)

def _enabled(sc: kit.Screen, bx: int, by: int, img) -> bool:
    """± 按钮是否可用: 蓝(可用) / 灰(禁用)。通道顺序无关: 灰=三通道几乎相等。"""
    r = sc.roi(bx - 3, by - 3, 7, 7, img=img)
    if r.size == 0:
        return False
    px = r.reshape(-1, 3).mean(axis=0)
    mx, mn = float(px.max()), float(px.min())
    return (mx - mn) >= 16 and mx > 120


def _slot_minus(sc: kit.Screen, i: int) -> tuple[int, int]:
    """四列槽位里第 i 列的 − 按钮基准坐标。"""
    return SLOT_X[i], Y_MINUS


def drain_slot(sc: kit.Screen, i: int) -> int:
    """把第 i 槽清零, 返回该槽的**真实持有数**。

    读数优先走面板数字牌(panel_count) —— 不再靠「点到变灰」数点击数:
      · 这个面板的「−」在选满/选 0 时**都是亮蓝**, “变灰”根本不会出现 → 老逻辑一路点到
        DRAIN_MAX 封顶才停, 报出来的件数是假的(真机真帧: 持 1 件报 17、持 2 件报 40);
      · 老逻辑每下都要 grab 判一次色(真机 ≈1 秒/下) → 一格清零几十秒(用户嫌慢)。
    新法: 先读数 → 按读数**连点**那么多下(连点期间不取帧) → 复读确认归零(抗丢点击)。
    读不出数字(缺 4~9 字模) → 退回老逻辑(点到变灰, DRAIN_MAX 封顶), 行为与以前一致。
    """
    bx, by = _slot_minus(sc, i)
    keep = sc.delay                      # 注意: 可能是 (min,max) 范围元组, 别直接 min()
    bdelay = ((BURST_DELAY, BURST_DELAY) if isinstance(keep, (tuple, list)) else BURST_DELAY)
    got = panel_count(sc, i, sc.grab())
    if got is not None and got <= 0:
        return 0
    if got is not None:                  # —— 数字牌读得出来: 按读数连点
        n = got
        for _ in range(4):               # 最多 4 轮, 每轮至多 60 下(抗丢点击)
            if got is None or got <= 0:
                break
            sc.delay = bdelay
            try:
                for _ in range(min(got, 60)):
                    sc.click_base(bx, by, f"第{i + 1}槽 −")
            finally:
                sc.delay = keep
            got = panel_count(sc, i, sc.grab())
        if got == 0:
            log(f"第 {i + 1} 槽数字牌直读 {n} 件 → 连点清零")
            return n
        log(f"⚠ 第{i + 1}槽 数字牌读出 {n} 件, 连点后仍剩 {got} → 本行收手(不进阶)")
        return -1
    # —— 数字牌读不出(缺字模): 退回老逻辑, 点到变灰
    n = 0
    sc.delay = bdelay
    try:
        while n < DRAIN_MAX:
            if not _enabled(sc, bx, by, sc.grab()):
                break
            sc.click_base(bx, by, f"第{i + 1}槽 −")
            n += 1
    finally:
        sc.delay = keep
    # ★ 复核: 减到底该槽的数字牌应已归零。
    #   实测踩过: 「−」压根没点中时(面板没展开 / 坐标漂), 循环数出来的 n 是**假的**,
    #   用例还拿这个假数量去选绿槽 → 点进不该进的行、白点 +2 (用户抓到的就是这种)。
    if tile_green(sc, i, None) > 0.20:
        log(f"⚠ 第{i+1}槽 减了 {n} 下仍没变灰 → 「−」大概没点中(面板未展开/坐标漂) → 本行收手")
        return -1
    return n


PDIG_H = 32               # 面板数字字形归一化高度
PDIG_TH = 0.62            # 字模相关阈值(真帧实测命中 0.84~1.00, 次好 ≤0.53)
PDIG_RATIO = 1.25         # 还要比次好的高这么多倍(防「长得像」的字)
_PDIGS: dict | None = None


def _pdig_templates() -> dict:
    """面板数字字模 {数字: 灰度图} —— templates/qa_pdig<N>.png。"""
    global _PDIGS
    if _PDIGS is None:
        _PDIGS = {}
        for v in range(10):
            t = _tpl(f"qa_pdig{v}")
            if t is not None:
                _PDIGS[v] = (cv2.cvtColor(t, cv2.COLOR_BGR2GRAY) if t.ndim == 3
                             else t).astype(np.uint8)
    return _PDIGS


def _pdigit_score(glyph, tpl) -> float:
    """按高度归一后把两个字形**居中贴到等宽画布**再相关(宽度差也一并体现)。"""
    h = PDIG_H
    gw = max(3, int(round(glyph.shape[1] * h / glyph.shape[0])))
    tw = max(3, int(round(tpl.shape[1] * h / tpl.shape[0])))
    W = max(gw, tw) + 4
    a = np.zeros((h, W), np.float32)
    b = np.zeros((h, W), np.float32)
    a[:, (W - gw) // 2:(W - gw) // 2 + gw] = cv2.resize(glyph, (gw, h), interpolation=cv2.INTER_AREA)
    b[:, (W - tw) // 2:(W - tw) // 2 + tw] = cv2.resize(tpl, (tw, h), interpolation=cv2.INTER_AREA)
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0][0])


def panel_count(sc: kit.Screen, i: int, img) -> int | None:
    """读 ± 面板第 i 列数字牌的**真持有数**(读不出返回 None)。

    为什么只有这里能读到真数(2026-10-09 真机实测):
      · 面板里的数字是**清晰白色大字**(高 ~35px) —— 白字掩码只抓数字, 白像素占比 3%,
        连通域要么一个(单位数)要么空(空槽), 不像详情页默认态那样灰暗难分;
      · 「− 点到变灰」这条路**机制上就是坏的**: 该面板的「−」在选满/选 0 时都是亮蓝,
        “变灰”根本不会出现 → drain_slot 一路点到 DRAIN_MAX 才停, 报出来的件数是假的
        (真帧: 持 1 件报 17, 持 2 件报 40)。
    字模是**面板自己**的渲染 —— 详情页默认态的字形不同源(同一枚「1」与列表字模只有 0.275~0.542),
    所以别拿列表/详情页的字模去读这里。

    空槽(无字形)→ 0; 两位以上 → 10(反正 ≥2); 相关不过阈值 → None(交给下游 fail-open)。
    """
    x0, y0, w, h = _bot.ref_rect_to_client(*tile_rect(i), sc.w, sc.h)
    t = img[y0:y0 + h, x0:x0 + w]
    if t.size == 0:
        return None
    roi = t[int(h * 0.30):int(h * 0.86), int(w * 0.20):int(w * 0.80)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = ((hsv[:, :, 2].astype(int) >= 185) & (hsv[:, :, 1].astype(int) <= 80)).astype(np.uint8)
    n, _l, st, _c = cv2.connectedComponentsWithStats(m, 8)
    gs = [(int(a), int(b), int(ww), int(hh)) for a, b, ww, hh, ar in st[1:]
          if hh >= 10 and ar >= 60]
    if not gs:
        return 0
    if len(gs) >= 2:
        return 10
    a, b, ww, hh = gs[0]
    g = (m[b:b + hh, a:a + ww] * 255).astype(np.uint8)
    ranked = sorted(((_pdigit_score(g, t), v) for v, t in _pdig_templates().items()),
                    reverse=True)
    if not ranked:
        return None
    top, val = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if top < PDIG_TH or top < second * PDIG_RATIO:
        return None
    return val


def tile_rect(col: int) -> tuple[int, int, int, int]:
    """第 col 列材料格的基准口径矩形(实测帧: 四槽中心 114/211/307/403, 格顶 y=578, 格 92x86)。"""
    return _bot.measured_rect((114, 211, 307, 403)[col] - 46, 578, 92, 86, REF)


def tile_green(sc: kit.Screen, col: int, img) -> float:
    """第 col 列材料格的「绿色品质」占比(0~1) —— 看**数字牌底色**, 不看图面。

    为什么不用薄边框: 材料格边框只有 2~3px, 且第 4 格(白框)的图面天然带绿色水晶,
    按边框取样会把「白框绿图」误判成绿装(实测顶边 43 个绿像素 > 绿装格 22 个)。
    数字牌是一块 60x30 的实心色块, 直接标品质 —— 实测分离度 38%/0%, 干净得多。
    """
    x0, y0, w, h = _bot.ref_rect_to_client(*tile_rect(col), sc.w, sc.h)
    t = (sc.grab() if img is None else img)[y0:y0 + h, x0:x0 + w]
    if t.size == 0:
        return 0.0
    pill = t[h - 16:h - 2, 18:74]          # 数字牌中段(避开格子边框与四角装饰)
    r, g, b = pill[:, :, 2].astype(int), pill[:, :, 1].astype(int), pill[:, :, 0].astype(int)
    return float(((g > 100) & (g - r > 45) & (g - b > 40)).mean())


_TPL: dict[str, "np.ndarray | None"] = {}


def _tpl(name: str):
    """读 templates/<name>.png(带缓存)。缺失返回 None, 方便逐步补模板。"""
    if name not in _TPL:
        p = Path(__file__).resolve().parents[2] / "templates" / f"{name}.png"
        _TPL[name] = cv2.imread(str(p)) if p.exists() else None
    return _TPL[name]


def tile_s(sc: kit.Screen, col: int, img=None) -> float:
    """第 col 列材料格左上角有没有「橙色 S 徽标」→ 返回最大橙心占比(0~1)。

    用户约定: 带 S 徽标的格子不能当材料。
    坐标: 以格子左上角为基准, 徽标实际位置会高出格顶 ~20px 且逐页/逐行有十几像素浮动
    (实测也正因此, 固定窗口 + 粗步长会把最优窗口跳过去, 真 S 只剩 0.42 < 阈值)。
    所以: 橙色掩码只算一次 + 积分图 → 偏移按 1px 网格舋完整个 ±16px 搜索窗, 仍是毫秒级。
    """
    img = sc.grab() if img is None else img
    if img is None or getattr(img, "size", 0) == 0:
        return 0.0
    h, w = img.shape[:2]
    x0, y0, _, _ = tile_rect(col)
    size = max(26, round(44 * w / 845))
    k = max(1, round(size * 0.25))             # 只取中心核(边距 = 1/4 边长, 与标定一致)
    bx = round((x0 - 6) * w / 845)             # 徽标预期左上
    by = round((y0 - 12) * h / 1521)
    m = 16                                     # 搜索半径(px)
    X0, Y0 = max(0, bx - m), max(0, by - m)
    X1, Y1 = min(w, bx + m + size), min(h, by + m + size)
    reg = img[Y0:Y1, X0:X1]
    if reg.size == 0:
        return 0.0
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    hc, sc_, vc = (hsv[:, :, i].astype(int) for i in (0, 1, 2))
    orange = ((hc >= 8) & (hc <= 40) & (sc_ >= 110) & (vc >= 130)).astype(np.int32)
    # 积分图(自己用 cumsum 算: OpenCV 5 的 cv2.integral 不收这些 dtype) → 窗口橙像素数 O(1)
    cc = np.cumsum(np.cumsum(orange.astype(np.int64), 0), 1)
    ii = np.zeros((cc.shape[0] + 1, cc.shape[1] + 1), np.int64)
    ii[1:, 1:] = cc
    core = size - 2 * k
    if core <= 0:
        return 0.0
    best = 0.0
    for dy in range(-m, m + 1):
        y = by - Y0 + dy
        if y < 0 or y + size > orange.shape[0]:
            continue
        for dx in range(-m, m + 1):
            x = bx - X0 + dx
            if x < 0 or x + size > orange.shape[1]:
                continue
            x1, y1 = x + k, y + k
            x2, y2 = x1 + core, y1 + core
            s_ = ii[y2, x2] - ii[y1, x2] - ii[y2, x1] + ii[y1, x1]
            v = float(s_) / (core * core)
            if v > best:
                best = v
    return best


def green_cols(sc: kit.Screen, img) -> list[int]:
    """详情页里哪几列是**非 S 级**绿装。"""
    out = []
    for i in range(4):
        if tile_green(sc, i, img) < GREEN_MIN:
            continue
        sc_s = tile_s(sc, i, img)
        if sc_s >= S_TH:
            log(f"第 {i + 1} 列是 S 级装备(角标 {sc_s:.2f}) → 跳过, 不当材料")
            continue
        out.append(i)
    return out


def _white_mask(img):
    """白色数字掩码(数字是纯白, 底色是深蓝渐变)。"""
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    return ((r > 170) & (g > 170) & (b > 170) & (np.abs(r - b) < 60)).astype(np.uint8)


def cost_ok(sc: kit.Screen) -> bool:
    """详情页「消耗资源」金币是否正好 **5538**? —— 兜底闸门(用户明确要求)。

    不是 5538 就说明选的装备或数量不对, 这时**不能**点快速进阶(会白烧材料)。
    为什么用白字掩码 IoU 而不是模板匹配: 「5538」/「5536」这种只差一位的数,
    归一化相关仍有 ~0.9, 门限分不开; 掩码里差一位就丢 ~1/4 面积 → IoU 掉到 0.8 以下。
    闸门落在「选料面板确认后、快速进阶前」—— 这一步还没花任何金币/材料, 是免费检查点。
    """
    t = _tpl("qa_cost5538")
    if t is None:
        log("⚠ 成本闸门: 模板缺失 → 跳过检查")
        return True
    img = sc.grab()
    if img is None or img.size == 0:
        return False
    H, W = img.shape[:2]
    cands = []
    # 再算一份「按真帧尺寸(REF)」映射的 —— 离线自检替身窗口尺寸可能与夹具帧不一致,
    # 真机上两者一致(双份无损), 夹具下按帧算才对得上金标准。
    b0, b1, b2, b3 = COST_RECT
    ww = max(4, round(b2 * W / 845))
    hh = max(4, round(b3 * H / 1521))
    # ⚠ 必须做微搜索: 基准坐标换客户端时会舍入, 且**页面版本间 y 会漂** —— 实测这版
    #   「消耗资源/金币」行在 y≈787, 而 COST_RECT 的 y=810 在 y≈820 → 低 ~20px,
    #   结果对着一张明明是 5538 的真帧也判 False(闸门误报的真因)。
    #   x 方向 ±3px、y 方向 ±26px、1px 步长; IoU 只是小 ROI 上的位运算, 代价可忽略。
    for dy in range(-26, 27):
        y0 = max(0, round(b1 * H / 1521) + dy)
        for dx in (-3, -2, -1, 0, 1, 2, 3):
            x0 = max(0, round(b0 * W / 845) + dx)
            cands.append(img[y0:y0 + hh, x0:x0 + ww])
    ious = []
    for r in cands:
        if r.size == 0:
            continue
        rr = cv2.resize(t, (r.shape[1], r.shape[0]), interpolation=cv2.INTER_NEAREST) \
            if t.shape[:2] != r.shape[:2] else t
        a, b = _white_mask(r), _white_mask(rr)
        ious.append(float((a & b).sum()) / max(1, int((a | b).sum())))
    if not ious:
        return False
    iou = max(ious)
    log(f"成本闸门: 金币白字 IoU={iou:.3f} (需 ≥{COST_IOU})")
    return iou >= COST_IOU


# ----------------------------------------------------------------- 列表页扫描

def green_rows(sc: kit.Screen) -> list[int]:
    """列表页「有绿装」的行 → 可点击的行 y(客户区, 升序)。"""
    img = sc.grab()
    x0, y0, w, h = _bot.ref_rect_to_client(*LIST_AREA, sc.w, sc.h)
    roi = img[y0:y0 + h, x0:x0 + w]
    if roi.size == 0:
        return []
    r, g, b = (roi[:, :, i].astype(int) for i in (2, 1, 0))   # BGR
    mask = ((g > 130) & (g - r > 60) & (g - b > 60)).astype(np.uint8)
    n, _lab, st, ce = cv2.connectedComponentsWithStats(mask, 8)
    ys = sorted(float(ce[i][1]) for i in range(1, n) if st[i, 4] >= LIST_GREEN_MIN)
    groups: list[list[float]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= ROW_GAP:
            groups[-1].append(y)
        else:
            groups.append([y])
    # 取组中心(不是组内最小那个): 一行里绿簇可能散布 ~90px, 取中心才落在行带靠中间
    return [int(y0 + (g[0] + g[-1]) / 2) for g in groups]


def row_sig(sc: kit.Screen, y: int) -> np.ndarray:
    """行主图裁剪(以行为中心) —— 去重用的「这一行长什么样」。"""
    x0, _y0, w, h = _bot.ref_rect_to_client(ROW_SIG, 0, ROW_SIG_W, 88, sc.w, sc.h)
    top = max(0, y - h // 2)
    return sc.grab()[top:top + h, x0:x0 + w].copy()


def same_row(a: np.ndarray, b: np.ndarray) -> bool:
    """逐像素平均差(不用 TM_CCOEFF_NORMED: 低对比裁剪上会假命中 1.0)。"""
    if a.shape != b.shape or a.size == 0:
        return False
    return float(np.abs(a.astype(int) - b.astype(int)).mean()) < SAME_ROW_DIFF


def _scroll(sc: kit.Screen) -> None:
    """列表是自绘 canvas: 走 drag_base(自检可回放)。起手取 x=600(卡片空白区),
    避开右侧勾选框列(拖拽 mouseDown 会把它勾上)。

    滑动距离 500(旧 320 ≈ 1 行, 一页签十几行要滑太多次)。
    注意: 每次关详情会直接回背包 → 再进列表会**回到顶部**, 所以同一行要重滑
    (靠 row_sig 去重跳过), 上滑预算必须够覆盖一整个页签。
    """
    x = _bot.client_to_ref(600, 0, *REF)[0]
    sc.drag_base(x, _bot.client_to_ref(0, 1100, *REF)[1],
                 x, _bot.client_to_ref(0, 1100 - 500, *REF)[1], steps=12, pre=0.12)
    kit.nap(1.2)


def _green_tiles(sc: kit.Screen, img) -> list[tuple[int, tuple[int, int, int, int]]]:
    """列表页每个「绿材料格」(整格, 图面+数量板合并) → (中心 y, bbox)。

    踩过的坑(两次):
    1) 拿整格图面读数字 → 图面里的白高光比数字宽, 把数量 1 读成 ≥2;
    2) 改拿「绿色数量板」当锚点 → 板子不一定是底部那条, 第 1 行的绿格板在格子中部,
       数字在更下方 → 数量 5 被读成 <2。
    现在: 先 dilate 把格内碎片合并成一整格, 再**只在格子底部中央**读数字。
    """
    x0, y0, w, h = _bot.ref_rect_to_client(*LIST_AREA, sc.w, sc.h)
    roi = img[y0:y0 + h, x0:x0 + w]
    if roi.size == 0:
        return []
    r, g, b = (roi[:, :, i].astype(int) for i in (2, 1, 0))   # BGR
    mask = ((g > 130) & (g - r > 60) & (g - b > 60)).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))         # 合并格内图面+数量板
    n, _lab, st, ce = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        bx, by, bw, bh = (int(v) for v in st[i, :4])
        if st[i, 4] < LIST_GREEN_MIN * 3 or bh < 24 or bw < 24:
            continue
        if bw < sc.w * 0.055 or bh < sc.h * 0.036:               # 真格 ~65x91; 图面碎片 ~40x35
            continue
        if not 0.6 <= bw / max(1, bh) <= 2.6:                  # 格子大致方形
            continue
        out.append((int(ce[i][1]) + y0, (bx + x0, by + y0, bw, bh)))
    return out


def _badge_frac(box) -> float:
    """图块里最大「橙金徽标占比」(与详情页 tile_s 同一套颜色判据, ±4px 微搜索)。"""
    th, tw = box.shape[:2]
    if th < 24 or tw < 24:
        return 0.0
    size = max(16, int(min(th, tw) * 0.48))
    k = max(3, size // 4)
    hsv = cv2.cvtColor(box, cv2.COLOR_BGR2HSV)
    m = ((hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 40) & (hsv[:, :, 1] >= 110)
         & (hsv[:, :, 2] >= 130)).astype(np.float32)
    acc = np.zeros((m.shape[0] + 1, m.shape[1] + 1), np.float32)
    acc[1:, 1:] = m.cumsum(0).cumsum(1)
    best = 0.0
    for dy in range(0, min(9, max(1, th - size))):
        for dx in range(0, min(9, max(1, tw - size))):
            x1, y1 = dx + k, dy + k
            x2, y2 = x1 + size - 2 * k, y1 + size - 2 * k
            area = (x2 - x1) * (y2 - y1)
            if area <= 0:
                continue
            s = float(acc[y2, x2] - acc[y1, x2] - acc[y2, x1] + acc[y1, x1]) / area
            best = max(best, s)
    return best


_DIGIT_K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
DIGIT1_CORR = 0.65        # 与「1」字模相关 ≥ 此值 ⇒ 数量 = 1 ⇒ 跳过该行


def _digit_glyph(tile):
    """格子里的数量数字字形(高度归一化到 14), 定位失败返回 None。

    ⚠ 三样缺一不可(都踩过):
      1) 顶帽去数字板的缓慢渐变 → 否则整板被当字(bbox 被撑到 33~57px);
      2) 连通域高度 ≥ 8 → 否则板的倒角高光(2~3px 细亮线)混进来, 仍横跨全宽;
      3) 只取板中央 18%~82% → 否则两端装饰高光混进来。
    三样都做了, 定位跨帧一致: 数量 1 → 宽10/面积150, 数量 5 → 宽11/面积165。
    """
    th, tw = tile.shape[:2]
    band = tile[int(th * 0.72):int(th * 0.98), int(tw * 0.18):int(tw * 0.82)]
    if band.size == 0:
        return None
    g = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    m = (cv2.morphologyEx(g, cv2.MORPH_TOPHAT, _DIGIT_K) > 20).astype(np.uint8)
    _, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    bs = [(x, y, w, h) for x, y, w, h, a in st[1:] if h >= 8 and 2 <= w <= 26 and a >= 12]
    if not bs:
        return None
    x0 = min(b[0] for b in bs); x1 = max(b[0] + b[2] for b in bs)
    y0 = min(b[1] for b in bs); y1 = max(b[1] + b[3] for b in bs)
    p = 3
    crop = g[max(0, y0 - p):min(g.shape[0], y1 + p), max(0, x0 - p):min(g.shape[1], x1 + p)]
    if crop.size == 0:
        return None
    h, w = crop.shape
    c = cv2.resize(crop, (max(1, int(round(14 * w / max(1, h)))), 14),
                   interpolation=cv2.INTER_AREA).astype(np.float32)
    c -= c.mean(); s = float(c.std())
    return (c / s) if s > 1e-6 else None


_G1: list = []


def _digit1_tpl():
    """「1」字模(标准化后缓存)。字模文件存的是 14xN 原始灰度。"""
    if not _G1:
        t = _tpl("qa_digit1")
        g = None
        if t is not None:
            g = (cv2.cvtColor(t, cv2.COLOR_BGR2GRAY) if t.ndim == 3 else t).astype(np.float32)
            g -= g.mean(); s = float(g.std())
            g = (g / s) if s > 1e-6 else None
        _G1.append(g)
    return _G1[0]


def _count_ge2(tile) -> bool:
    """该格数量是否 ≥2 —— 用「与「1」字模的相关」判「是不是只有 1 件」。

    真机真帧实测: 「1」→ 1.000 / 0.872; 「5」→ 0.384 (2.3 倍余量, 阀值 0.65)。
    ⚠ 读不出来(定位失败/字模缺失)**放行**(fail-open): 漏掉一次能进阶的行,
      比多跑一趟详情更亏 —— 而详情那趟现在也便宜了(减到灰先读数, <2 立即退)。
    """
    tpl = _digit1_tpl()
    if tpl is None:
        return True
    g = _digit_glyph(tile)
    if g is None:
        return True
    W = max(tpl.shape[1], g.shape[1])
    A = np.zeros((14, W), np.float32); B = np.zeros((14, W), np.float32)
    A[:, :tpl.shape[1]] = tpl; B[:, :g.shape[1]] = g
    d = float(A.std() * B.std())
    c = float((A * B).mean() / d) if d > 1e-6 else 0.0
    return c < DIGIT1_CORR


LIST_COUNT_CHECK = True   # 列表页「数量≥2」预筛: 靠**确定性定位 + 字形相关**判「是不是只有 1 件」。
# 为什么之前一直关: 定位不稳时什么读法都不可靠 ——
#   按百分位阀值取 → 整块渐变数字板被算进来(bbox 撑到 33~57px, 「1」「5」一样宽);
#   只加顶帽 → 数字板倒角高光(2~3px 细亮线)也进来, 仍横跨全宽;
#   不限制到板中央 → 两端装饰高光混进来。
# 三样一起做才跨帧一致(见 _digit_glyph), 再用与「1」字模的相关判 ——
# 真帧实测: 「1」vs 字模 = 1.000 / 0.872, 「5」vs 字模 = 0.384 → 2.3 倍余量。


def usable_rows(sc: kit.Screen, img) -> list[int]:
    """列表页**可直接点进去**的行: 绿材料格不带 S 徽标(数量判定另说, 见上)。

    这一步就是为了不做「点进去才发现是 S」的多余动作。
    """
    res: list[int] = []
    for cy, (bx, by, bw, bh) in _green_tiles(sc, img):
        tile = img[by:by + bh, bx:bx + bw]
        if tile.size == 0:
            continue
        head = tile[:max(24, int(bh * 0.55)), :max(24, int(bw * 0.55))]   # 左上角
        s = _badge_frac(head)
        if s >= S_TH:
            log(f"列表页 y={cy}: 绿材料格带 S 徽标({s:.2f}) → 不进详情, 跳过")
            continue
        if LIST_COUNT_CHECK and not _count_ge2(tile):
            log(f"列表页 y={cy}: 绿材料格数量 <2 → 不进详情, 跳过")
            continue
        res.append(cy)
    return res


def pick_row(sc: kit.Screen, visited: list[np.ndarray]) -> int | None:
    """当前页签里找到「有绿装且没访问过」的行 y; 视口内没有就上滑再找。

    只在**列表页就达标**(非 S + 数量≥2)的行才会被选中 → 不白点详情页。
    """
    for s in range(SCROLL_MAX + 1):
        img = sc.grab()
        for y in usable_rows(sc, img):
            if not any(same_row(row_sig(sc, y), v) for v in visited):
                return y
        if s < SCROLL_MAX:
            log(f"视口内没有可用的绿装行 → 上滑第 {s + 1} 次")
            _scroll(sc)
    return None


# ----------------------------------------------------------------- 详情页一轮

def refine_row(sc: kit.Screen) -> int:
    """把一行榨到绿槽 < 2。返回成功进阶次数; -1 = 中途出错。"""
    done = 0
    for rnd in range(1, ROW_MAX + 1):
        img = sc.grab()
        cols = green_cols(sc, img)
        if not cols:
            log("本行已无绿装 → 榨干收手")
            return done
        # 必须先点「调整数量」把面板展开(± 只在面板展开后出现) ——
        # 本轮开头那次 grab 就是为此(判绿是在**展开前**的默认选中态上做的)
        if not _tap(sc, "qa_adj", "调整数量", th=TH_ADJ):
            return -1
        # ★ 面板展开后、点任何「−」**之前**先读数字牌 —— 这是唯一能拿到「真持有数」的地方。
        #   实测(2026-10-09 真机): drain 靠「− 点到变灰」数出来的件数是**假的**
        #   (真帧: 槽1 持有 1 件却报 17、槽2 持有 2 件报 40 = DRAIN_MAX 封顶) —— 这个
        #   面板的「−」在选满/选 0 时都是亮蓝, “变灰”根本不会出现。
        #   读出来 <2 就地收手: 一下「−」都不点(真机实测这样省掉一整轮清槽 ≈ 4 分钟)。
        read = {i: panel_count(sc, i, sc.grab()) for i in range(4)}
        log(f"面板读数(数字牌): { {i + 1: read[i] for i in range(4)} }")
        thin = [i for i in cols if read.get(i) is not None and read[i] < 2]
        if thin:
            log(f"⚠ 绿槽第 {thin[0] + 1} 列数字牌读出 {read[thin[0]]} 件(<2) "
                f"→ 一下「−」都不点, 关面板收手(不点进阶)")
            _tap(sc, "qa_ok", "确定(收手前关掉数量面板)")
            return done
        cnt = {i: drain_slot(sc, i) for i in range(4)}
        if any(v < 0 for v in cnt.values()):
            log("⚠ 槽位数量不可信(有槽没减成灰) → 本行不进阶, 直接退避免白点")
            return REFINE_SKIP
        gi = max(cols, key=lambda i: cnt.get(i, 0))
        log(f"第 {rnd} 轮: 各槽数量={ {i + 1: v for i, v in cnt.items()} } "
            f"绿槽=第 {gi + 1} 列({cnt.get(gi, 0)} 件)")
        if cnt.get(gi, 0) < 2:
            log(f"绿槽只剩 {cnt.get(gi, 0)} 件(<2) → 按约定收手(不硬凑)")
            _tap(sc, "qa_ok", "确定(收手前关掉数量面板)")
            return done
        # 绿槽 +2 —— **逐下复核「+」是否仍可用**, 而不是闭眼点两下。
        #
        # 为什么必须复核(用户抓到的两个问题都出在这):
        #   `drain_slot` 给出的件数是「点到变灰的点击数」, 不是读出来的数;
        #   一旦某个槽的「−」没被认成灰(或持有数 >DRAIN_MAX), 它就会报一个**假件数**
        #   (实测: 真帧上该槽只持有 1 件, drain 却报 40 = DRAIN_MAX 封顶)。
        #   旧代码拿这个假件数判「≥2」→ 对一个只有 1 件的绿槽照样点 +2 →
        #   游戏不接受 → 点「快速进阶」后没有「恭喜获得」→ 白跑一轮并终止整个页签。
        #
        # 为什么用「+」的可用态当准星(而不是读数字牌):
        #   详情页数字牌字形与列表页**不同源** —— 同一枚「1」跨帧与字模相关只有
        #   0.275~0.542(阈值 0.65); 数量板底色也不随件数变(真帧实测 绿1=0.53 / 绿2=0.47)。
        #   唯有「+」的可用/禁用是跨帧稳定的纯颜色信号(真帧 蓝 极差209 / 灰 极差4)。
        #   语义也正好: 绿槽已清零, +1 后「+」立刻变灰 ⇒ 该槽只持有 1 件 ⇒ 凑不出 +2。
        pcount = 0
        for _ in range(2):
            if not _enabled(sc, SLOT_X[gi], Y_PLUS, sc.grab()):
                break
            sc.click_base(SLOT_X[gi], Y_PLUS, f"绿槽(+1)第{gi + 1}列")
            pcount += 1
            kit.nap(NAP_FAST)
        if pcount < 2:
            log(f"⚠ 绿槽第 {gi + 1} 列只能凑到 {pcount} 件(<2, 已按「+」可用态复核) "
                f"→ 本行凑不出 +2, 关面板收手(不点进阶)")
            _tap(sc, "qa_ok", "确定(收手前关掉数量面板)")
            return done
        if not _tap(sc, "qa_ok", "确定(数量面板)"):
            return -1
        if not _tap(sc, "qa_pickexp", "选择经验"):
            return -1
        if not _tap(sc, "qa_auto", "自动选择"):
            return -1
        if not _tap(sc, "qa_mok", "确认(选料面板)"):
            return -1
        # ★ 兜底闸门: 消耗金币 != 5538 时告警留证(用户确认这批行本就该进阶,
        #   所以默认**只告警不拦**(GATE_BLOCK=False); 固定金额只是「超验幽灵」一件的价格,
        #   其他装备价格不同(实测 2019/1500 等)会把行全挡住。要收紧改 GATE_BLOCK=True)。
        if not cost_ok(sc):
            log(f"⚠ 第 {rnd} 轮成本不是 5538(告警) → 已留证")
            sc.shot(f"cost_mismatch_{rnd}", force=True)
            if GATE_BLOCK:
                return REFINE_SKIP
        if not _tap(sc, "qa_go", "快速进阶"):
            return -1
        # 二次确认弹窗(可能因「今日不再提示」被勾过而不出现) → 只点绿确认, 不碰勾选框
        for _ in range(6):
            if _find(sc, "qa_confirm") is not None:
                sc.click(_find(sc, "qa_confirm"), "确认(二次弹窗)")
                break
            if _find(sc, "claim_btn", TH_CLAIM) is not None:
                break
            kit.nap(0.8)
        if not _tap(sc, "claim_btn", "领取(恭喜获得)", th=TH_CLAIM, tries=4):
            log("✗ 进阶后没等到「恭喜获得」弹层 → 留证")
            sc.shot(f"fail_claim_{rnd}")
            return -1
        done += 1
    log("⚠ 单行轮数达上限 → 停手(防呆)")
    return done


# ----------------------------------------------------------------- 导航

def _close_any(sc: kit.Screen) -> bool:
    """把详情/列表/选料面板用 X 关掉(实测 X 从详情页直接回背包)。"""
    return _tap(sc, "sweep_close", "X关闭", tries=2, wait=NAP_OPEN)


def to_bag(sc: kit.Screen) -> bool:
    """从任意页回到背包页(残留弹层/结果页顺手收掉)。"""
    for _ in range(8):
        p = page(sc)
        log(f"当前页面: {p}")
        if p == BAG:
            return True
        if p in (DETAIL, LIST, MAT):
            _close_any(sc)
        elif p == RESULT:
            _tap(sc, "claim_btn", "领取(残留结果页)", th=TH_CLAIM)
        elif p == DIALOG:                       # 弹窗: 只敢点「取消」, 不点「确认」
            if not (_tap(sc, "cap_cancel", "取消(残留弹窗)", tries=1)
                    or _tap(sc, "gd_cancel", "取消(残留弹窗)", tries=1)):
                log("⚠ 二次确认弹窗上找不到取消键 → 停手, 不冒险点确认")
                sc.shot("stuck_dialog")
                return False
        elif p == WH:
            _tap(sc, "wh_bag", "仓库→背包")
        elif p == HOME:
            _tap(sc, "warehouse_btn", "首页→仓库")
        else:
            log("未知页面 → 停手")
            sc.shot("unknown_page")
            return False
    return False


def to_list(sc: kit.Screen, tab: str, label: str) -> bool:
    """从任意页进到列表页, 并点好页签。"""
    for _ in range(8):
        p = page(sc)
        log(f"当前页面: {p}")
        if p == LIST:
            _tap(sc, f"qa_tab_{tab}", f"页签「{label}」", tries=2, wait=NAP_OPEN)
            return True
        if p == BAG:
            if not _tap(sc, "qa_entry", "快速进阶入口", th=TH_ENTRY):
                return False
        elif p in (DETAIL, MAT):
            _close_any(sc)
        elif p == RESULT:
            _tap(sc, "claim_btn", "领取(残留结果页)", th=TH_CLAIM)
        elif p == DIALOG:
            if not (_tap(sc, "cap_cancel", "取消(残留弹窗)", tries=1)
                    or _tap(sc, "gd_cancel", "取消(残留弹窗)", tries=1)):
                sc.shot("stuck_dialog")
                return False
        elif p == WH:
            _tap(sc, "wh_bag", "仓库→背包")
        elif p == HOME:
            _tap(sc, "warehouse_btn", "首页→仓库")
        else:
            log("未知页面 → 停手")
            sc.shot("unknown_page")
            return False
    return False


# ----------------------------------------------------------------- 主流程

def run_tab(sc: kit.Screen, tab: str, label: str, cap: int) -> int:
    """处理一个页签: 反复「进列表 → 挑一行 → 榨干 → X 回背包」直到没有未处理的绿装行。"""
    n = 0
    visited: list[np.ndarray] = []
    for _ in range(cap):
        if not to_list(sc, tab, label):
            log(f"✗ 页签「{label}」进不去 → 停手")
            break
        y = pick_row(sc, visited)
        if y is None:
            log(f"页签「{label}」已无可处理的绿装行 → 关掉列表")
            _close_any(sc)
            break
        visited.append(row_sig(sc, y))
        x = _bot.ref_rect_to_client(ROW_ICON_X, 0, 1, 1, sc.w, sc.h)[0]
        sc.click_at(x, y, f"该行主图(页签「{label}」)")
        kit.nap(NAP_OPEN)
        if page(sc) != DETAIL:
            log("⚠ 点开后不是详情页 → 停手(留证)")
            sc.shot("fail_detail")
            break
        got = refine_row(sc)
        if got == REFINE_SKIP:
            log(f"页签「{label}」跳过该行(成本闸门不过) → 处理下一行")
            _close_any(sc)
            continue
        if got < 0:
            sc.shot("fail_refine")
            break
        n += got
        log(f"页签「{label}」本行进阶 {got} 次(累计 {n})")
        if not _close_any(sc):
            log("⚠ 详情页关不掉 → 停手")
            break
    return n


def run(sc: kit.Screen, args: kit.Args) -> bool:
    cap = int(args.max or 6)
    only = (args.type or "").strip()          # --type=僚机 只跑单页签(避开命令超时上限)
    tabs = [t for t in TABS if (not only) or only in (t[0], t[1])]
    if not tabs:
        log(f"⚠ --type={only} 不匹配任何页签(可选: {[t[1] for t in TABS]}) → 退出")
        return False
    if sc.dry:
        for n, note in (("warehouse_btn", "首页「仓库」入口"), ("wh_bag", "仓库页「背包」"),
                        ("qa_entry", "背包页「快速进阶」"), ("qa_title", "列表页标题"),
                        ("qa_dtitle", "详情页标题"), ("qa_adj", "「调整数量」"),
                        ("qa_ok", "数量面板「确定」"), ("qa_pickexp", "「选择经验」"),
                        ("qa_auto", "「自动选择」"), ("qa_mok", "选料面板「确认」"),
                        ("qa_go", "「快速进阶」黄键"), ("qa_confirm", "二次确认弹窗「确认」"),
                        ("claim_btn", "「领取」"), ("sweep_close", "关闭 X")):
            h = _find(sc, n)
            log(f"[dry] {n:14s} {note:16s} "
                + (f"命中 {h[:2]} score={h[2]:.3f}" if h else "未命中"))
        for tab, label in TABS:
            h = _find(sc, f"qa_tab_{tab}")
            log(f"[dry] 页签 {label:4s} "
                + (f"命中 {h[:2]} score={h[2]:.3f}" if h else "未命中"))
        log(f"[dry] 槽位(基准): x={SLOT_X} +y={Y_PLUS} −y={Y_MINUS}")
        log(f"[dry] 每页签最多处理 {cap} 行; 绿槽 <2 即收手; 不勾「今日不再提示」")
        log("[dry] 计划输出完毕(未点击)")
        return True

    if not to_bag(sc):
        return False
    sc.shot("bag_ready")
    total = 0
    for tab, label in tabs:
        log(f"========== 页签「{label}」 ==========")
        total += run_tab(sc, tab, label, cap)
        log(f"页签「{label}」完成, 累计进阶 {total} 次")
    log(f"页签跑完, 合计进阶 {total} 次")
    if total == 0:
        log("本次没有可进阶的绿装(可能已被清理干净) → 视为完成")
    return True


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "quick_advance", "快速进阶（消耗绿装，循环到无绿可进阶）", run,
        plan=PLAN, prefix="quickadv_", lock_ttl=3600, th=TH,
        need_home=True, default_max=6, default_timeout=2400,
    ))
