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
from wb.kit import log  # noqa: E402

# S 徽标团块判据直接沿用 qa 已标定的四常量(真徽标 331px/18x21/fill 0.88)
S_CC_MIN, S_BBOX_MAX, S_FILL = qa.S_CC_MIN, qa.S_BBOX_MAX, qa.S_FILL
LIST_AREA = qa.LIST_AREA
ROW_ICON_X = qa.ROW_ICON_X


def s_rows(sc: kit.Screen, img) -> list[int]:
    """列表页带 S 徽标的行 → 行中心 y(客户区, 升序)。

    徽标悬浮在材料格 bbox 上沿, 且白品质 S 装没有绿格可依托 —— 所以直接在
    LIST_AREA 里扫橙色团块(面积/bbox/fill 三条 qa 已标定约束, 丢弃「相对格顶」
    那条因为不依赖格 bbox), 团块中心 y 即行位置。
    """
    x0, y0, w, h = _bot.ref_rect_to_client(*LIST_AREA, sc.w, sc.h)
    roi = (sc.grab() if img is None else img)[y0:y0 + h, x0:x0 + w]
    if roi.size == 0:
        return []
    r, g, b = (roi[:, :, i].astype(int) for i in (2, 1, 0))
    mask = ((r > 150) & (r - g > 60) & (r - b > 80)).astype(np.uint8)
    n, _lab, st, ce = cv2.connectedComponentsWithStats(mask, 8)
    ys = []
    for j in range(1, n):
        a = int(st[j, cv2.CC_STAT_AREA])
        bw, bh = int(st[j, cv2.CC_STAT_WIDTH]), int(st[j, cv2.CC_STAT_HEIGHT])
        if a < S_CC_MIN or bw > S_BBOX_MAX or bh > S_BBOX_MAX:
            continue
        fill = a / max(1, bw * bh)
        if fill >= S_FILL:
            ys.append(int(ce[j][1]) + y0)
    return sorted(set(ys))


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


def refine_row_s(sc: kit.Screen) -> int:
    """S 装一行: 全槽清零 → 绿槽(无则白槽)+1 → 自动选经验 → 快速进阶。

    返回成功进阶次数; -1 = 中途出错。每轮材料刷新, 直到没有可加的绿/白。
    """
    done = 0
    for rnd in range(1, qa.ROW_MAX + 1):
        img = sc.grab()
        gcols = qa.green_cols(sc, img)
        wcols = white_cols(sc, img)
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
            return -1
        # 二次确认弹窗(可能因「今日不再提示」被勾过而不出现) → 只点绿确认, 不碰勾选框
        for _ in range(6):
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
        sc.click_base(ROW_ICON_X, y, f"S行主图(y={y})")
        kit.nap(qa.NAP_OPEN)
        if qa.page(sc) != qa.DETAIL:
            log("⚠ 点开后不是详情页 → 停手(留证)")
            sc.shot("fail_detail_s")
            break
        got = refine_row_s(sc)
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
        total += run_tab(sc, tab, label, cap)
        log(f"页签「{label}」完成, 累计升蓝 {total} 次")
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
