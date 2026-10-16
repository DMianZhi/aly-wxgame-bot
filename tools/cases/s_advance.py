#!/usr/bin/env python
"""用例: 快速进阶-S装升蓝(把 S 装从绿/白升到蓝, 2026-10-12 用户提出)。

与 quick_advance(消耗绿装)同一套链路, 三处不同:
    ① 选行相反: qa 挑「**不带** S 徽标」的绿装行当材料; 本用例挑「**带** S 徽标」
       的行当升级对象(S 装本身)。S 徽标用橙色团块几何直扫(不依赖材料格底色,
       这样绿品质/白品质的 S 装都能找到 —— qa 的 _green_tiles 只认绿格)。
    ② 面板策略相反: qa 清零后绿槽凑 **+2**; 本用例全槽清零后 **绿槽或白槽 +1**
       (用户口径: 全部减为 0 → 绿色或白色加 1 → 自动选择经验 → 快速进阶)。
    ③ 成本闸门只告警不拦(S 装进阶价与绿装 5538 不同, 本来就各不相同)。

    链路(与 qa 完全同款, 复用其全部函数):
    首页 → 仓库 → 背包 → qa_entry 快速进阶列表
    四页签(战机/装甲/副武器/僚机): 扫列表找带 S 徽标的行 → 点行主图 → 详情页
        数量面板: 四槽全部清零 → 绿槽(无则白槽)+1 → 确定
        选择经验 → 自动选择 → 确认 → 快速进阶 → 二次确认 → 领取 → 回详情页
        直到该行没有可加的绿/白材料 → X 回背包 → 下一行
    收尾: 统一回首页

用法:
    uv run python tools/cases/s_advance.py [--dry] [--max=N] [--json]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import cv2
import numpy as np

from tools.cases import quick_advance as qa  # noqa: E402
from wb import bot as _bot  # noqa: E402
from wb import kit  # noqa: E402
from wb.cfg import TEMPLATE_PATH  # noqa: E402
from wb.kit import log  # noqa: E402

_TPL_PATH = TEMPLATE_PATH("exp_over_text")

# S 徽标团块判据: 沿用 qa 的 bbox/fill 两条, 面积下限按直扫实测定(2026-10-12 真机:
# 列表页真徽标 area=141/136、fill 0.72/0.70, qa 的 S_CC_MIN=150 会误杀; 碎屑 95/0.57)
S_AREA_MIN = 120
S_FILL_MIN = 0.62
S_BBOX_MAX = qa.S_BBOX_MAX   # 徽标紧实: bbox 边长上限(沿 qa 标定 32)
LIST_AREA = qa.LIST_AREA
# ⚠ 2026-10-16 新增: S 徽标**专属扫描区**(主图格左上角那列)。
#   LIST_AREA 是**材料格**列(x 从 180 起), 而 S 徽标贴在主图格左上角(基准 x≈65)
#   → 拿 LIST_AREA 扫徽标永远扫不到, 只会把材料格里的橙色误当徽标。
#   基准 x 25~160 ↔ 客户区 x 21~144(739 宽帧): 含徽标 41~73、不含材料格 174+。
BADGE_AREA = _bot.measured_rect(25, 262, 135, 940, qa.REF)
WHITE_MIN = 0.08          # 详情页白材料槽: 整格「灰白像素占比」下限
                          # 真帧标定(2026-10-16 用户详情页截图): 白槽 0.153 / 三个空槽 0.000
LIST_STILL_DIFF = 2.0    # 列表区「上滑后画面没动」的像素均差阈值(0~255)
                         #   滚动成功时整屏位移 → 均差 >>20; 已到底时拖拽无位移 → ≈0
                         #   → 2.0 余量很大, 不需要精细标定
SCROLL_STILL_MAX = 3     # 连续这么多次上滑画面都没动 → 判定到底收工
                         #   ⚠ 2026-10-16 用户反馈「不是说改成 3~4 次滑动吗」：
                         #   本用例原先只抄了 qa 的「位置未变」到底判据，但它依赖 S 行检测
                         #   → 列表里 S 行「有徽标但无绿/白材料格」时 s_rows 返回空,
                         #   `if cur` 永不成立 → 一路滑满 SCROLL_MAX(11 次)。
                         #   实跑证据 logs/sadv_20261016-122648.log: 4 个页签共空滑 44 次。
                         #   现补上帧差(不依赖任何目标检测) + qa 的「无产出」两条兜底
                         #   → 到底后最多再滑 3~4 次就收工。
ROW_ICON_X = qa.ROW_ICON_X


def white_tiles(sc: kit.Screen, img) -> list[int]:
    """列表页「白色(白品质)材料格」的行 y(2026-10-12 标定, 2026-10-16 放宽)。

    白格 = 高亮团块 mn>140、area 120~900、bbox 24~56、近方形(0.6~2.6)。
    实测: 小格 33x30/330px(均值 BGR≈239,214,178 浅暖白 —— 旧「极差<45」的
    纯白判据把它卡掉了, 浅黄极差 61); 绿格(64x90)另一套 qa._green_tiles。

    ⚠ 2026-10-16 放宽 area 下限 250→120、bbox 上限 48→56(用户反馈
      「第四行就是 S 白装啊, 为什么不升」+ 战机页签截图实测):
      白材料格还有**大字牌**一种 —— 实测 bbox 51x51、亮像素 area 仅 146~217
      (牌面大面积是深色底, mn>140 的只是亮缘/数字), 旧下限 250 直接把它排除,
      于是「白品质 S 装」整行白丢。新参数下三张页签截图的全部候选均值仍是
      175~248 浅暖白(无误报), 覆盖 51x51 大字牌与小字牌两种。
    """
    x0, y0, w, h = _bot.ref_rect_to_client(*LIST_AREA, sc.w, sc.h)
    roi = (sc.grab() if img is None else img)[y0:y0 + h, x0:x0 + w]
    if roi.size == 0:
        return []
    b, g, r = roi[..., 0].astype(int), roi[..., 1].astype(int), roi[..., 2].astype(int)
    mn = np.minimum(np.minimum(b, g), r)
    m = (mn > 140).astype(np.uint8)
    n, _lab, st, ce = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for j in range(1, n):
        a = int(st[j, cv2.CC_STAT_AREA])
        bw, bh = int(st[j, cv2.CC_STAT_WIDTH]), int(st[j, cv2.CC_STAT_HEIGHT])
        if not (120 <= a <= 900 and 24 <= bw <= 56 and 24 <= bh <= 56):
            continue
        if not 0.6 <= bw / max(1, bh) <= 2.6:
            continue
        out.append(int(ce[j][1]) + y0)
    return out


def s_rows(sc: kit.Screen, img) -> list[int]:
    """列表页**可处理的 S 行** → 行中心 y(客户区, 升序)。

    双条件(2026-10-12 用户反馈: 别点进详情才发现没料, 列表页就要预筛):
      ① 该行有 S 徽标(橙色团块直扫, 不依赖绿格 —— 白品质 S 装没有绿格);
      ② 该行有绿格(qa._green_tiles)或白格(white_tiles) —— 行 ±25px 内。
    只有徽标没有绿/白材料的 S 行直接跳过, 不浪费详情页那套步骤。

    ⚠ 2026-10-16 两处修正(用户实跑 logs/sadv_20261016-131442.log + 3 张页签截图):
      ① 徽标扫描区原先错用 LIST_AREA(x 从 180 起) —— 那是**材料格**列, 而 S 徽标
         贴在**主图格左上角**(基准 x≈65) → 徽标整体在 ROI 之外, 一路扫不到,
         只偶尔把材料格里的橙色误当徽标(日志 "y=275/276 无绿/白材料格" 就是假阳性)。
         现改用 BADGE_AREA(基准 x 25~160)专扫徽标列。
      ② 返回值改为**行中心 y**(匹配到的材料格中心 y), 不再是徽标 y —— 徽标在行顶,
         直接拿去点主图会偏上 ~24px(客户区), 是「点两次都进不了详情页」的一半原因。
    """
    img = sc.grab() if img is None else img      # 归一化: 下面 qa._green_tiles 不接受 None
    x0, y0, w, h = _bot.ref_rect_to_client(*BADGE_AREA, sc.w, sc.h)
    roi = img[y0:y0 + h, x0:x0 + w]
    if roi.size == 0:
        return []
    r, g, b = (roi[:, :, i].astype(int) for i in (2, 1, 0))
    mask = ((r > 140) & (r - g > 40) & (r - b > 50)).astype(np.uint8)
    n, _lab, st, ce = cv2.connectedComponentsWithStats(mask, 8)
    badges = []
    for j in range(1, n):
        a = int(st[j, cv2.CC_STAT_AREA])
        bw, bh = int(st[j, cv2.CC_STAT_WIDTH]), int(st[j, cv2.CC_STAT_HEIGHT])
        if a < S_AREA_MIN or bw > S_BBOX_MAX or bh > S_BBOX_MAX:
            continue
        if a / max(1, bw * bh) >= S_FILL_MIN:
            badges.append(int(ce[j][1]) + y0)
    greens = [cy for cy, _ in qa._green_tiles(sc, img)]
    whites = white_tiles(sc, img)
    ys = []
    for by in badges:
        # ⚠ 参照系: 徽标悬浮在材料格**顶沿**(格 90 高), 绿簇中心 y ≈ 徽标 y + 45;
        #   白格小(30 高)中心 ≈ 徽标 y + 20。直接拿徽标 y 对格中心 y 会差 35~65px
        #   (2026-10-12 实测: 徽标 631 vs 绿格 666 被旧 ±25 容差错杀)。
        cand: list[tuple[int, int]] = []
        for gy in greens:
            d = abs((by + 45) - gy)
            if d <= 45:
                cand.append((d, gy))
        for wy in whites:
            d = abs((by + 20) - wy)
            if d <= 30:
                cand.append((d, wy))
        if cand:
            ys.append(min(cand)[1])       # 行中心 y ≈ 最近材料格中心(供点主图)
        else:
            log(f"列表页 y={by}: S 行但无绿/白材料格 → 列表页直接跳过(不点详情)")
    return sorted(set(ys))


def quality_cols(sc: kit.Screen, img) -> tuple[list[int], list[int]]:
    """详情页默认态(数量面板展开**前**)的 (绿槽列, 白槽列)。

    ⚠ 与 qa.green_cols 的三点不同(2026-10-12 真机实测):
      ① 必须在展开**前**判 —— 展开后数字牌位置漂移, pill 取样区全取空(绿分 0.000);
      ② 不排除 S 角标格 —— 本用例 S 装就是主角(qa 的语义「S 不当材料」会全跳,
         实测 S 装面板绿槽 tile_green=0.403, 远超 GREEN_MIN=0.15);
      ③ 白槽判据 = **整格**「灰白像素占比」>= WHITE_MIN(2026-10-16 真帧标定;
         旧「数字牌中段 pill」取样带落在格子外 → 有白材料的槽也全判「无材料」)。
    """
    gcols = [i for i in range(4) if qa.tile_green(sc, i, img) >= qa.GREEN_MIN]
    wcols = white_cols(sc, img)
    return gcols, wcols


GO_BAND = (345, 1295, 176, 26)   # 「快速进阶」键本体带(基准坐标)
GO_YELLOW_MIN = 0.30             # 黄键: 黄色像素占比下限(真帧: 黄键 0.70 / 灰键 0.00)


def go_ready(sc: kit.Screen, img=None) -> float:
    """详情页「快速进阶」键的**黄色像素占比** —— 黄键(可进阶)高; 灰键(禁用, 下方写
    「当前指定消耗的装备已无法进阶」) ≈ 0。

    真帧标定(2026-10-16 用户两张详情页截图): 黄键带均值 BGR(9,146,220) 黄占比 0.82 /
    灰键带均值 (149,149,149) 黄占比 0.00 → 阈值 0.30 分得极开。

    ⚠ 不能用模板分判「在场」: match_adaptive 的 _GEOM_HINT(上次命中的缩放候选优先
      + 命中即停)会让**同一帧**的得分依赖调用顺序 —— 自检实测: 灰键单跑 0.678,
      与黄键连跑就变 0.918(假阳性) → 判据会随上下文漂移。像素判色是确定性的。
    """
    im = sc.grab() if img is None else img
    x0, y0, w, h = _bot.ref_rect_to_client(*GO_BAND, sc.w, sc.h)
    t = im[y0:y0 + h, x0:x0 + w].astype(int)
    if t.size == 0:
        return 0.0
    b, g, r = t[:, :, 0], t[:, :, 1], t[:, :, 2]
    return float(((r > 190) & (g > 140) & (b < 110)).mean())


def white_cols(sc: kit.Screen, img) -> list[int]:
    """详情页**默认态**「白色品质」材料槽列 —— **整格**判: 灰白像素(mn>140 且极差<60)占比
    达 WHITE_MIN。

    ⚠ 2026-10-16 用户实跑暴露(日志 sadv_20261016-133320.log 13:33:51 段):
      旧判据取「数字牌中段 pill = t[h-16:h-2, 18:74]」+ mn>150 & 极差<45 & frac>=0.5,
      但 tile_rect 的格子实测在**上方 ~23px**(真帧: 格子客户区 y 523~597, 而 rect 是
      546~625) → pill 整条带落在**格子外的深色底**上 → 真有白材料的 col0 只算出 0.05,
      一路判「无绿/白材料」→ 刚进详情页就「收手」→ 白品质 S 装永远升不了。
      现改**整格**判 + 放宽到 mn>140/极差<60。真帧标定(详情页截图):
        白材料槽 col0 = 0.153; 三个空槽 = 0.000 / 0.000 / 0.000 → 阈值 0.08 余量充分。
    """
    out = []
    for col in range(4):
        x0, y0, w, h = _bot.ref_rect_to_client(*qa.tile_rect(col), sc.w, sc.h)
        t = (sc.grab() if img is None else img)[y0:y0 + h, x0:x0 + w]
        if t.size == 0:
            continue
        mn = np.min(t.astype(int), axis=2)
        mx = np.max(t.astype(int), axis=2)
        frac = float(((mn > 140) & (mx - mn < 60)).mean())
        if frac >= WHITE_MIN:
            out.append(col)
    return out


def _dismiss_exp_over(sc: kit.Screen, hit=None) -> None:
    """点掉「经验过多」提示条 —— 点**左侧蓝色「调整材料」**(=取消本次进阶)。

    ⛔ 绝不能点右侧绿色「继续进阶」: 那等于确认消耗“溢出经验(不返还)”。
       旧实现“扫绿色像素求均值”正好会把点击落在绿色「继续进阶」上 —— 危险, 已改。
    模板 = 提示条第一行固定文案, 命中中心 + 固定偏移 = 蓝键中心(真帧实测)。
    """
    if not EXP_OVER_TPL_OK:
        return
    if hit is None:
        hit = qa._find(sc, "exp_over_text", TH_EXPOVER)
    if hit is None:
        log("[warn] 没找到「经验过多」提示条(可能已自动消失)")
        return
    dx, dy = EXP_OVER_ADJ_DXY
    sc.click_base(int(hit[0] + dx), int(hit[1] + dy), "调整材料(取消经验过多提示)")
    kit.nap(1.5)


STOP_ALL = -3   # refine_row_s → run_tab/run: 「经验过多」→ 停止整个用例(用户口径)

# ⚠ 2026-10-14 修好(用户提供真帧 shots/_sadv_exp_over_bar.png)。曾经踩的坑:
#   旧 templates/exp_over_text.png **裁错了** —— 它其实是提示条上的蓝色「调整材料」按钮
#   (386x62), 而那颗键与「确认快速进阶所选装备到极限?」确认框里的蓝色「取消」长得几乎
#   一样 → 在确认框上以 0.9304 ≥ 0.90 命中 → 误判「经验过多」→ 用例在**第一个确认框就
#   提前结束**(用户反馈的真因)。
#   现改裁**提示条第一行固定文案**「本次进阶经验已超过进阶所需的经验，」(不含第二行会变
#   的“溢出N”数字); 真帧正验 1.0, 两个确认框帧反验均 None → 不互命。
EXP_OVER_TPL_OK = True      # False = 不判不点(模板坏时降级用)
TH_EXPOVER = 0.92           # 正帧 1.0 / 反帧 None → 取 0.92 留余量
# 提示条上「调整材料」(蓝) 相对**文字行中心**的偏移(基准系, 实测帧 835x1509)
EXP_OVER_ADJ_DXY = (-141, 189)


def _exp_over(sc: kit.Screen, img=None) -> bool:
    """「经验过多」提示条在场？(用户实测: 升蓝时经验够会弹, 此时继续=浪费)

    模板 = 提示条**第一行固定文案**; ⚠ 别再用旧版(裁成「调整材料」按钮), 详见
    EXP_OVER_TPL_OK 注释。
    """
    if not EXP_OVER_TPL_OK:
        return False
    frame = sc.grab() if img is None else img
    tpl = cv2.imread(str(_TPL_PATH))
    if tpl is None:
        return False
    return _bot.match_adaptive(frame, tpl, TH_EXPOVER) is not None


def refine_row_s(sc: kit.Screen) -> int:
    """S 装一行: 全槽清零 → 绿槽(无则白槽)+1 → 自动选经验 → 快速进阶。

    返回成功进阶次数; -1 = 中途出错。
    ⚠ 弹「经验过多」提示条 → 点掉并**停止整个用例**(2026-10-12 用户口径:
      经验已超出国标, 再升也是浪费)。
    """
    done = 0
    for rnd in range(1, qa.ROW_MAX + 1):
        # ⚠ 品质判色必须在面板展开**前**的默认态上做(展开后数字牌漂移)
        img = sc.grab()
        if _exp_over(sc, img):
            log("⚠ 「经验过多」提示在场 → 停止 S 装升蓝(本轮及后续全部放弃)")
            return STOP_ALL
        # ⚠ 2026-10-16 用户反馈「点进来又白退」: 「快速进阶」**灰键**时下方写着
        #   「当前指定消耗的装备已无法进阶」—— 该行压根升不了(真帧: 黄键带 0.82 /
        #   灰键带 0.00 黄占比)。先查黄键在不在, 不在就立刻收手,
        #   不再白走「调整数量 → 清零 → 加料 → 点键」整套(用户: 白点一次很浪费)。
        gs = go_ready(sc, img)
        if gs < GO_YELLOW_MIN:
            log(f"「快速进阶」黄键不在场(黄像素占比 {gs:.2f}) = 当前指定消耗的装备已无法进阶 → 本行收手")
            sc.shot("nogo_detail")
            return done
        gcols, wcols = quality_cols(sc, img)
        if not gcols and not wcols:
            log("本行已无绿/白材料 → 收手")
            # 留证(2026-10-16): 用户反馈过「列表页判有料 / 进详情却判无料」，存帧好下次对账
            sc.shot("nomaterial_detail")
            return done
        if not qa._tap(sc, "qa_adj", "调整数量", th=qa.TH_ADJ):
            return -1
        # 全部减为 0(用户口径) —— drain_slot 读数连点+复读归零
        cnt = {i: qa.drain_slot(sc, i) for i in range(4)}
        if any(v < 0 for v in cnt.values()):
            log("⚠ 槽位数量不可信(有槽没减成 0) → 本行不进阶, 直接退避免白点")
            return qa.REFINE_SKIP
        gi = gcols[0] if gcols else wcols[0]
        kind = "绿" if gcols else "白"
        log(f"第 {rnd} 轮: 全槽已清零 { {i + 1: v for i, v in cnt.items()} } "
            f"→ {kind}槽第 {gi + 1} 列 +1")
        # +1: 点前复核「+」可用(与 qa 同一套蓝/灰颜色判态)
        if not qa._enabled(sc, qa.SLOT_X[gi], qa.Y_PLUS, sc.grab()):
            log(f"⚠ {kind}槽第 {gi + 1} 列「+」不可用(该品质没材料了) → 关面板收手")
            qa._tap(sc, "qa_ok", "确定(收手前关掉数量面板)")
            return done
        sc.click_base(qa.SLOT_X[gi], qa.Y_PLUS, f"{kind}槽(+1)第{gi + 1}列")
        if not qa._tap(sc, "qa_ok", "确定(数量面板)"):
            return -1
        if not qa._tap(sc, "qa_pickexp", "选择经验"):
            return -1
        if not qa._tap(sc, "qa_auto", "自动选择"):
            return -1
        if not qa._tap(sc, "qa_mok", "确认(选料面板)"):
            return -1
        if not qa.cost_ok(sc):
            log("⚠ S 装进阶成本与绿装基准不同(告警, 不拦) → 已留证")
            sc.shot(f"cost_mismatch_s_{rnd}", force=True)
        if not qa._tap(sc, "qa_go", "快速进阶"):
            # ⚠ 「经验过多」提示条在选料确认后弹出、盖住详情页 → qa_go 找不到
            #   (2026-10-12 实测卡点)。先查它再放弃。
            if _exp_over(sc):
                log("⚠ 弹出「经验过多」提示 → 经验已够, 升蓝到此为止(停止整个用例)")
                _dismiss_exp_over(sc)
                return STOP_ALL
            return -1
        # 二次确认弹窗(可能因「今日不再提示」被勾过而不出现) → 只点绿确认, 不碰勾选框
        for _ in range(6):
            # 「经验过多」提示条也会在这个时机弹(变体路径) → 点掉并停整个用例
            if EXP_OVER_TPL_OK and qa._find(sc, "exp_over_text", TH_EXPOVER) is not None:
                log("⚠ 弹出「经验过多」提示 → 经验已够, 升蓝到此为止(停止整个用例)")
                _dismiss_exp_over(sc)
                return STOP_ALL
            c = qa._find(sc, "qa_confirm")
            if c is not None:
                sc.click(c, "确认(二次弹窗)")
                break
            if qa._find(sc, "claim_btn", qa.TH_CLAIM) is not None:
                break
            kit.nap(0.8)
        if not qa._tap(sc, "claim_btn", "领取(恭喜获得)", th=qa.TH_CLAIM, tries=4):
            log("✗ 升蓝后没等到「恭喜获得」弹层 → 留证")
            sc.shot(f"fail_claim_s_{rnd}")
            return -1
        done += 1
    log("⚠ 单行轮数达上限 → 停手(防呆)")
    return done


def _list_roi(sc: kit.Screen, img) -> np.ndarray:
    """列表区像素(供帧差到底判据), 与 s_rows 用同一 ROI。"""
    x0, y0, w, h = _bot.ref_rect_to_client(*LIST_AREA, sc.w, sc.h)
    return img[y0:y0 + h, x0:x0 + w].astype(np.int16)


def pick_s_row(sc: kit.Screen, visited: list[np.ndarray]) -> int | None:
    """找「带 S 徽标且没访问过」的行; 视口内没有就上滑再找。

    到底检测有**三条**互不排斥的判据(任一命中即收工, 2026-10-16 补齐):
      ① 位置判据: 上滑后 S 行位置纹丝不动 → 到底(依赖 S 行检测, 命中最早);
      ② 帧差判据: 连续 SCROLL_STILL_MAX 次上滑后列表区画面几乎无变化 → 到底
                  (不依赖任何目标检测);
      ③ 无产出: 连续 qa.DRY_SCROLL_GIVEUP 次滑屏都没出现可处理的新行 → 到底
                (与 qa.pick_row 同语义, 保证两用例行为一致)。
    ⚠ 只写 ① 会被短路: 列表里 S 行全是「有徽标但无绿/白材料格」时 s_rows 返回
      **空列表** → `if cur` 永不成立 → prev_ys 一直 None → 一路滑满 SCROLL_MAX=11 次
      (用户实跑 logs/sadv_20261016-122648.log: 4 个页签共空滑 44 次, 多花 ~2 分钟)。
    """
    prev_ys: list[int] | None = None
    prev_roi: np.ndarray | None = None
    still = 0                                # 连续「画面没动」的滑屏次数
    dry = 0                                  # 连续「没有可处理新行」的滑屏次数
    for s in range(qa.SCROLL_MAX + 1):
        img = sc.grab()
        cur = s_rows(sc, img)                # 本屏可处理的 S 行(不可处理的已在内部打日志)
        ys = [y for y in cur
              if not any(qa.same_row(qa.row_sig(sc, y), v) for v in visited)]
        if ys:
            return ys[0]
        if s >= qa.SCROLL_MAX:
            break                            # 预算用完, 别再滚了
        roi = _list_roi(sc, img)
        if cur and prev_ys and all(abs(a - b) <= 8 for a, b in zip(cur, prev_ys)):
            log("① 上滑后 S 行位置未变 → 列表已到底, 提前收工")
            return None
        if cur:
            prev_ys = cur
        moved = (prev_roi is not None and roi.shape == prev_roi.shape
                 and float(np.abs(roi - prev_roi).mean()) >= LIST_STILL_DIFF)
        still = 0 if moved else still + 1
        prev_roi = roi
        if still >= SCROLL_STILL_MAX:
            log(f"② 连续 {still} 次上滑画面未动 → 列表已到底, 收工")
            return None
        dry += 1
        if dry >= qa.DRY_SCROLL_GIVEUP:
            log(f"③ 连续 {dry} 次滑屏没有可处理的新行 → 判定到底, 收工")
            return None
        log(f"视口内没有可处理的 S 行 → 上滑第 {s + 1} 次")
        qa._scroll(sc)
    return None


def run_tab(sc: kit.Screen, tab: str, label: str, cap: int) -> int:
    """处理一个页签: 反复「进列表 → 挑 S 行 → 升蓝 → X 回背包」。"""
    n = 0
    visited: list[np.ndarray] = []
    for _ in range(cap):
        if not qa.to_list(sc, tab, label):
            log(f"✗ 页签「{label}」进不去 → 停手")
            break
        y = pick_s_row(sc, visited)
        if y is None:
            log(f"页签「{label}」已无可处理的 S 行 → 关掉列表")
            qa._close_any(sc)
            break
        visited.append(qa.row_sig(sc, y))
        # ⚠ 两个坑(2026-10-12 实测): ① 上滑惯性滚动会吃掉点击; ② page() 在
        #   转场瞬帧上抖动(列表页被判 HOME) —— 所以点击后**轮询等详情页**
        #   (最多 3s), 落空再等稳重找重点一次。
        entered = False
        xrow = _bot.ref_rect_to_client(ROW_ICON_X, 0, 1, 1, sc.w, sc.h)[0]
        for attempt in range(2):
            # ⚠ 2026-10-16: 这里原先写 sc.click_base(ROW_ICON_X, y) —— 但 y 是
            #   **客户区**坐标(s_rows 算出来的), click_base 又会拿它当基准坐标再换算一次
            #   → 双重缩放, 点位上浮 ~20px(实跑日志: 想点 y=275, 实际落在 y=256),
            #   正好落在行上沿缝隙 → 「点两次都进不了详情页」。qa.run_tab 用的是
            #   click_at + 客户区 x, 这里对齐它。
            sc.click_at(xrow, y, f"S行主图(y={y}, 第{attempt + 1}次)")
            deadline = kit.time.time() + 3.0
            while kit.time.time() < deadline:
                if qa.page(sc) == qa.DETAIL:
                    entered = True
                    break
                kit.nap(0.6)
            if entered:
                break
            log("⚠ 点后 3s 没进详情页(滚动动画/转场抖动) → 等稳重找再点")
            kit.nap(1.2)
            img2 = sc.grab()
            ys2 = [yy for yy in s_rows(sc, img2)
                   if not any(qa.same_row(qa.row_sig(sc, yy), v) for v in visited[:-1])]
            if not ys2:
                break
            y = ys2[0]
        if not entered:
            log("⚠ 两次点行都没进详情页 → 停手(留证)")
            sc.shot("fail_detail_s")
            break
        got = refine_row_s(sc)
        if got == STOP_ALL:
            # 2026-10-12 用户口径: 经验已满 = 所有 S 装都升不了, **后面的页签也不必跑了**
            log(f"⚠ 页签「{label}」因「经验过多」停手 → X 回背包, 后续页签全部跳过")
            qa._close_any(sc)
            return STOP_ALL
        if got == qa.REFINE_SKIP:
            log(f"页签「{label}」跳过该行 → 处理下一行")
            qa._close_any(sc)
            continue
        if got < 0:
            log(f"✗ 页签「{label}」某行中途出错 → 停手(留证)")
            sc.shot("fail_refine_s")
            break
        n += got
        log(f"该行升蓝 {got} 次(本页签累计 {n})")
        qa._close_any(sc)
    return n


PLAN = """[dry] 计划:
  首页 → 仓库 → 背包 → 快速进阶列表
  四页签 战机/装甲/副武器/僚机, 每个页签:
      扫列表找**带 S 徽标**的行(S 装本体, 橙色团块几何判据) → 点行主图 → 详情页
          数量面板: 四槽**全部清零** → 绿槽(无则白槽)**+1** → 确定
          选择经验 → 自动选择 → 确认
          快速进阶 → 二次确认(只点绿确认) → 领取 → 回详情页
        直到该行没有可加的绿/白材料 → X 回背包 → 下一行
  收尾: 统一回首页"""


def run(sc: kit.Screen, args: kit.Args) -> bool:
    if sc.dry:
        log("[dry] 计划输出:")
        log(PLAN)
        log(f"[dry] 槽位(基准): x={qa.SLOT_X} +y={qa.Y_PLUS} −y={qa.Y_MINUS}")
        return True
    if not qa.to_bag(sc):
        log("✗ 进不了背包 → 停手")
        return False
    cap = max(1, args.max or 1)
    total = 0
    for tab, label in qa.TABS:
        log(f"========== 页签「{label}」 ==========")
        got = run_tab(sc, tab, label, cap)
        if got == STOP_ALL:
            log(f"⚠ 「经验过多」→ 直接收工(后续页签全部跳过), 累计升蓝 {total} 次")
            break
        total += got
        log(f"页签「{label}」完成, 累计升蓝 {total} 次")
        if got < 0:
            log("⚠ 页签返回异常 → 停止后续页签")
    log(f"页签跑完, 合计升蓝 {total} 次")
    if total == 0:
        log("本次没有可升蓝的 S 装(可能都升完了) → 视为完成")
    return True


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "s_advance", "快速进阶-S装升蓝（全槽清零→绿/白+1→自动选经验→快速进阶）", run,
        plan=PLAN, prefix="sadv_", lock_ttl=3600, th=qa.TH,
        need_home=True, default_max=6, default_timeout=2400,
    ))
