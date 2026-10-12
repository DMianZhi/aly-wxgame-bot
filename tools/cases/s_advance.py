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
ROW_ICON_X = qa.ROW_ICON_X


def white_tiles(sc: kit.Screen, img) -> list[int]:
    """列表页「白色材料格」的行 y(2026-10-12 真机标定)。

    白格 = 高亮团块 mn>140、area 250~800、bbox 24~48、近方形(0.6~2.6)。
    实测: 白格 33x30/330px(均值 BGR≈239,214,178 浅暖白 —— 旧「极差<45」的
    纯白判据把它卡掉了, 浅黄极差 61); 绿格(64x90)另一套 qa._green_tiles。
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
        if not (250 <= a <= 800 and 24 <= bw <= 48 and 24 <= bh <= 48):
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
    """
    x0, y0, w, h = _bot.ref_rect_to_client(*LIST_AREA, sc.w, sc.h)
    roi = (sc.grab() if img is None else img)[y0:y0 + h, x0:x0 + w]
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
        near_g = any(abs((by + 45) - gy) <= 45 for gy in greens)
        near_w = any(abs((by + 20) - wy) <= 30 for wy in whites)
        if near_g or near_w:
            ys.append(by)
        else:
            log(f"列表页 y={by}: S 行但无绿/白材料格 → 列表页直接跳过(不点详情)")
    return sorted(set(ys))


def quality_cols(sc: kit.Screen, img) -> tuple[list[int], list[int]]:
    """详情页默认态(数量面板展开**前**)的 (绿槽列, 白槽列)。

    ⚠ 与 qa.green_cols 的三点不同(2026-10-12 真机实测):
      ① 必须在展开**前**判 —— 展开后数字牌位置漂移, pill 取样区全取空(绿分 0.000);
      ② 不排除 S 角标格 —— 本用例 S 装就是主角(qa 的语义「S 不当材料」会全跳,
         实测 S 装面板绿槽 tile_green=0.403, 远超 GREEN_MIN=0.15);
      ③ 白槽判据 = 数字牌中段三通道高且接近(白底), 阈值待白装真帧标定。
    """
    gcols = [i for i in range(4) if qa.tile_green(sc, i, img) >= qa.GREEN_MIN]
    wcols = white_cols(sc, img)
    return gcols, wcols


def white_cols(sc: kit.Screen, img) -> list[int]:
    """数量面板里「白色品质」的槽列(品质数字牌中段判白)。

    与 qa.green_cols 同一取样区(数字牌中段), 判据换成白: 三通道都高且接近。
    """
    out = []
    for col in range(4):
        x0, y0, w, h = _bot.ref_rect_to_client(*qa.tile_rect(col), sc.w, sc.h)
        t = (sc.grab() if img is None else img)[y0:y0 + h, x0:x0 + w]
        if t.size == 0:
            continue
        pill = t[h - 16:h - 2, 18:74]
        if pill.size == 0:
            continue
        r, g, b = (pill[:, :, i].astype(int) for i in (2, 1, 0))
        mn = np.minimum(np.minimum(r, g), b)
        mx = np.maximum(np.maximum(r, g), b)
        frac = float(((mn > 150) & (mx - mn < 45)).mean())
        if frac >= 0.5:
            out.append(col)
    return out


def _dismiss_exp_over(sc: kit.Screen) -> None:
    """点掉「经验过多」提示条(右侧绿色确认键, 与文字同层)。"""
    img = sc.grab()
    b, g, r = img[..., 0].astype(int), img[..., 1].astype(int), img[..., 2].astype(int)
    green = (g > 140) & (g - r > 50) & (g - b > 50)
    ys, xs = np.where(green)
    if len(ys) > 500:
        sc.click_base(int(xs.mean()), int(ys.mean()), "确定(经验过多提示)")
        kit.nap(1.5)
    else:
        log("[warn] 没找到提示条上的确认键(可能已自动消失)")


STOP_ALL = -3   # refine_row_s → run_tab/run: 「经验过多」→ 停止整个用例(用户口径)


def _exp_over(sc: kit.Screen, img=None) -> bool:
    """「经验过多」提示条在场？(用户实测: 升蓝时经验够会弹, 此时继续=浪费)"""
    frame = sc.grab() if img is None else img
    tpl = cv2.imread(str(_TPL_PATH))
    if tpl is None:
        return False
    r = _bot.match_adaptive(frame, tpl, 0.90)
    return r is not None


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
        gcols, wcols = quality_cols(sc, img)
        if not gcols and not wcols:
            log("本行已无绿/白材料 → 收手")
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
            if qa._find(sc, "exp_over_text", 0.90) is not None:
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


def pick_s_row(sc: kit.Screen, visited: list[np.ndarray]) -> int | None:
    """找「带 S 徽标且没访问过」的行; 视口内没有就上滑再找(到底检测同 qa)。"""
    prev_ys: list[int] | None = None
    for s in range(qa.SCROLL_MAX + 1):
        img = sc.grab()
        ys = [y for y in s_rows(sc, img)
              if not any(qa.same_row(qa.row_sig(sc, y), v) for v in visited)]
        if ys:
            return ys[0]
        cur = s_rows(sc, img)
        if cur and prev_ys and all(abs(a - b) <= 8 for a, b in zip(cur, prev_ys)):
            log("上滑后 S 行位置未变 → 列表已到底, 提前收工")
            return None
        if cur:
            prev_ys = cur
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
        for attempt in range(2):
            sc.click_base(ROW_ICON_X, y, f"S行主图(y={y}, 第{attempt + 1}次)")
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
            log(f"⚠ 页签「{label}」因「经验过多」停手 → X 回背包, 整个用例结束")
            qa._close_any(sc)
            return n
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
