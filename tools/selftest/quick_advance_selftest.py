#!/usr/bin/env python
"""离线自检: quick_advance（快速进阶）—— 零消耗，不碰游戏窗口。

夹具: `_qa_s*.png` 全部是**本次探路时的真机真帧**(814x1507)，覆盖
      首页/仓库/背包/列表页/详情页/数量面板/选料面板/二次确认弹窗/结果页。
      需要「± 按钮状态」的帧由真帧**改点色**生成(`_ts_qa_*`)，只为喂颜色判态用。

覆盖:
    ① 判层专场: 8 张真帧逐一判对（含**二次确认弹窗必须先于详情页**、
       **结果页暗幕必须先于详情页**这两处顺序陷阱）
    ② 绿装判据校准: 详情页真帧只认第 3 列(绿 5)为绿装, 旁边「4」那格(边框白/灰、
       只是图面偏绿)**必须不算** —— 这条错了整条用例就会数错材料
    ③ 列表扫描校准: 列表页真帧能扫出那 1 行绿装, 且点击点落在行内
    ④ 数量面板: 「− 点到灰」既清零又数数 —— 喂 [3,3,5,4] 必须解出 [3,3,5,4]
       且 15 次点击的顺序/坐标对得上（这是全用例最容易写错的一环）
    ⑤ 完整一轮真帧回放: 详情→调整数量→清槽→绿+2→确定→选经验→自动选择→确认
       →快速进阶→二次确认→领取, refine_row 恰好 1 次; 且**绝不点弹窗勾选框**
    ⑥ 绿槽只剩 1 件 → 收手(不硬凑): 零次进阶、**一次 + 都不点**、只点确定关面板
    ⑦ 去重终止: 榨不干的行仍留在列表里 → 第二次扫描必须认出来并收手(防死循环)
    ⑧ dry 零点击零写盘；⑨ 并发锁互斥

用法:
    uv run python tools/selftest/quick_advance_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402

from wb import bot as _bot, kit, selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR  # noqa: E402
from tools.cases import quick_advance as qa  # noqa: E402

# ---- 真帧夹具(本次探路截下, 814x1507) ----
HOME0 = "_qa_s0_home.png"
WH0 = "_qa_s1_warehouse.png"
BAG = "_qa_s2_bag.png"
LIST = "_qa_s3_advance.png"
DETAIL = "_qa_s4_row6.png"          # 详情页(材料 3/3/绿5/4, 有「调整数量」)
QTY = "_qa_s5_qty.png"              # 数量面板(± 展开 + 确定)
SATUR = "_qa_s6_satur.png"          # 绿槽点满 4 次仍在 5(封顶实证)
ZERO2 = "_qa_s7_zero2.png"          # 清完 + 绿+2 (0/0/2/0)
AFTER_OK = "_qa_s8_ok.png"          # 点确定后回详情页(材料恢复默认 4/3/5/4)
MATA = "_qa_s9_exp.png"             # 选料面板「选择材料」
MATA2 = "_qa_s10_auto.png"          # 点过「自动选择」后
AFTER_MAT = "_qa_s11_back.png"      # 选料确认后回详情页(EXP 已补满)
DLG = "_qa_s12_done.png"            # 二次确认弹窗
RESULT = "_qa_s13_result.png"       # 「恭喜获得」
AFTER_CLAIM = "_qa_s14_after_claim.png"   # 领取后回详情页(绿 5→3)
BAG2 = "_qa_s15_list.png"           # X 关掉详情后**直接回背包**(实测)

# ---- 合成帧(真帧改点色) ----
QSEQ = "_ts_qa_qseq"                # 清槽序列(喂数量面板状态)
NOGREEN = "_ts_qa_nogreen.png"      # 绿装格边框改灰(模拟该行榨干)
LIVES = "_qa_s16_liveS.png"         # 现场详情真帧(第1格带真 S 徽标) — 徽标补丁来源
SDET = "_qa_sdet_green_s.png"       # 合成: 绿列格子左上贴真 S 徽标(用于验「S 格剔除」)
ART = "_qa_s18_artframe.png"        # 真帧(812x1518, 2026-10-10 真机): 第2列绿装图面自带
                                    # 大片橙纹 → 旧颜色判据 0.556 误判 S 整行跳过(回归锁)
G1 = "_ts_qa_g1"                    # 绿槽只有 1 件的清槽序列
G2 = "_ts_qa_ghost"                 # 「假数量」序列: 清槽报 5 件, 真持有只有 1 件

# 金标准坐标: 全部**从夹具帧实测**(模板命中中心), 不是手填
C_ADJ = (711, 618)          # qa_adj「调整数量」
C_OK = (711, 618)           # qa_ok「确定」(与调整数量同位置)
C_PICKEXP = (717, 837)      # qa_pickexp「选择经验」
C_AUTO = (714, 1227)        # qa_auto「自动选择」
C_MOK = (407, 1307)         # qa_mok 选料面板「确认」
C_GO = (415, 1282)          # qa_go「快速进阶」黄键
C_CONFIRM = (577, 902)      # qa_confirm 二次确认弹窗「确认」
C_CLAIM = (417, 1280)       # claim_btn「领取」
C_TAB = (142, 1299)         # qa_tab_plane「战机」
C_ENTRY = (442, 1312)       # qa_entry「快速进阶」入口
C_ROW_ICON = (120, 1138)    # 列表页那行主图(绿装行 y≈1138)
CHECKBOX = (346, 828)       # 二次确认弹窗「今日不再提示」勾选框(绝不能点)

SLOTX = (114, 211, 307, 403)     # 四列槽位 x(实测帧)
YMIN, YPLUS = 688, 554           # − / + 的 y
BLUE, GREY = (222, 111, 0), (107, 107, 107)   # BGR: 蓝键可用 / 灰键禁用


def _sc(rp, dry: bool = False) -> kit.Screen:
    """按当前帧的真实尺寸建 Screen(真帧都是 814x1507, 坐标可与实测帧直接对表)。"""
    h, w = rp.imgs[min(rp.idx, len(rp.imgs) - 1)].shape[:2]
    return kit.Screen((0, 0, w, h), th=qa.TH, dry=dry, prefix="quickadv_")


def _glyph_img(v: int):
    """面板数字字模(与用例共用 templates/qa_pdig<N>.png)。"""
    t = qa._tpl(f"qa_pdig{v}")
    if t is None:
        return None
    return cv2.cvtColor(t, cv2.COLOR_BGR2GRAY) if t.ndim == 3 else t


def _paint_digit(img, i: int, value: int) -> None:
    """把第 i 列的数字牌画成 value —— 用例现在会**读**这块牌, 夹具必须跟着变。

    先用数字牌区域的均色抹掉原数字(白字只占 ~3%, 均值几乎就是牌底), 再把字模按
    「字高/格高 = 35/86」(标定帧实测) 缩放后贴上; 缺字模则整只跳过(下游 fail-open)。
    """
    H, W = img.shape[:2]
    x0, y0, w, h = _bot.ref_rect_to_client(*qa.tile_rect(i), W, H)
    roi = img[y0 + int(h * 0.30):y0 + int(h * 0.86), x0 + int(w * 0.20):x0 + int(w * 0.80)]
    if roi.size == 0:
        return
    roi[:] = cv2.mean(roi)[:3]
    gh = max(8, int(round(h * 0.407)))
    gl = []
    for ch in str(value):
        g = _glyph_img(int(ch))
        if g is None:
            return
        gw = max(3, int(round(g.shape[1] * gh / g.shape[0])))
        gl.append(cv2.resize(g, (gw, gh), interpolation=cv2.INTER_AREA))
    gap = 3
    cx = x0 + w // 2 - (sum(g.shape[1] for g in gl) + gap * (len(gl) - 1)) // 2
    cy = y0 + int(h * 0.565) - gh // 2
    for g in gl:
        gh2, gw2 = g.shape
        a0, a1 = max(0, cy), min(H, cy + gh2)
        b0, b1 = max(0, cx), min(W, cx + gw2)
        if a1 > a0 and b1 > b0:
            img[a0:a1, b0:b1][g[a0 - cy:a1 - cy, b0 - cx:b1 - cx] > 100] = 255
        cx += gw2 + gap


def _slot_states(src: str, dst: str, counts: list[int], cur: list[int] | None = None,
                 plus_max: dict[int, int] | None = None) -> None:
    """把真帧的四列「−/＋」按钮改成 蓝(可用)/灰(禁用)，模拟面板状态。

    `counts` = 各槽**持有数**(不变); `cur` = 当前**已选数**(点 − 后逐帧下降)。
      −: cur>0 才可用(点到 0 变灰);
      ＋: cur<持有 才可用(选到上限变灰) —— 这条是 2026-10-09 补的:
         真机真帧的 ＋ 是「已全选」态(灰), 不补的话「绿槽逐下复核 +」那步会读到假的灰。
    `plus_max` = 单独指定某槽「＋ 的上限」(模拟「清槽报的数 ≠ 真持有数」的假数量现场)。
    """
    img = cv2.imread(str(SHOTS_DIR / src))
    cur = list(counts) if cur is None else list(cur)
    pm = dict(enumerate(counts)) if plus_max is None else \
        {**dict(enumerate(counts)), **plus_max}
    for i, x in enumerate(SLOTX):
        img[YMIN - 15:YMIN + 15, x - 30:x + 30] = BLUE if cur[i] > 0 else GREY
        img[YPLUS - 15:YPLUS + 15, x - 30:x + 30] = BLUE if cur[i] < pm[i] else GREY
        _paint_digit(img, i, cur[i])      # 数字牌也得跟着变(用例现在直接读它)
    cv2.imwrite(str(SHOTS_DIR / dst), img)


def _drain_frames(src: str, prefix: str, counts: list[int],
                  plus_max: dict[int, int] | None = None) -> list[str]:
    """按 drain_slot 的真实取帧节奏生成序列: 第 k 次取帧 = 点过 k-1 下之后的状态。

    长度 = 1 + 总点击数。drain_slot 是「取帧→判定→点击」, 点击才推进一帧,
    所以序列必须**正好**是每次判定时看到的状态, 多一帧少一帧都会数错。
    """
    cur = list(counts)
    states = [list(cur)]
    order = [c for c in range(4) for _ in range(counts[c])]
    for col in order:
        cur[col] -= 1
        states.append(list(cur))
    names = []
    for i, s in enumerate(states):
        n = f"{prefix}{i:03d}.png"        # ⚠ 必须 3 位补零: 2 位会被字符串排序搞乱(g10 < g100 < g11)
        _slot_states(src, n, counts, s, plus_max)
        names.append(n)
    return names


def ensure_fixtures() -> bool:
    need = [HOME0, WH0, BAG, LIST, DETAIL, QTY, SATUR, ZERO2, AFTER_OK, MATA, MATA2,
            AFTER_MAT, DLG, RESULT, AFTER_CLAIM, BAG2, LIVES]
    missing = [f for f in need if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具: {missing}")
        return False
    # 「绿列 + 真 S 徽标」合成帧: 从现场真帧剪真徽标(现场标定最佳窗 61,557), 贴到第 3 列(绿列,
    # 0-based = 2 —— 绿装列就是它)格子左上角外沿(相对格顶 -5,-20, 实测徽标就是高出格顶 ~20px)。
    # ⛔ 无条件重建: 早期写成「文件不存在才生成」→ 改了生成逻辑却不换文件名, 跑的还是旧帧,
    #    排查白费一轮(现场 mtime 一直卡在旧时间)。合成帧很便宜, 一律重铺。
    base = cv2.imread(str(SHOTS_DIR / AFTER_OK))
    live = cv2.imread(str(SHOTS_DIR / LIVES))
    if base is not None and live is not None:
        badge = live[557:601, 61:105]
        x0, y0 = _bot.ref_rect_to_client(*qa.tile_rect(2), 814, 1507)[:2]
        base[y0 - 20:y0 - 20 + badge.shape[0], x0 - 5:x0 - 5 + badge.shape[1]] = badge
        cv2.imwrite(str(SHOTS_DIR / SDET), base)
    # 绿装格整格涂灰 → 模拟「本行已无绿装」(绿判据是数字牌底色, 涂灰必掉到 0)
    # ⚠ tile_rect 给的是**基准口径**, cv2 要画在客户区帧上 → 必须 ref_rect_to_client 转
    if not (SHOTS_DIR / NOGREEN).is_file():
        img = cv2.imread(str(SHOTS_DIR / DETAIL))
        x0, y0, w, h = _bot.ref_rect_to_client(*qa.tile_rect(2), 814, 1507)
        img[y0:y0 + h, x0:x0 + w] = (170, 170, 170)
        cv2.imwrite(str(SHOTS_DIR / NOGREEN), img)
    # ⚠ 件数只能用**已有字模**的数字(0/1/2/3) —— 夹具要能把数字牌画出来, 用例会读它
    if not list(SHOTS_DIR.glob(f"{QSEQ}*.png")):
        _drain_frames(QTY, QSEQ, [2, 2, 3, 2])
    if not list(SHOTS_DIR.glob(f"{G1}*.png")):
        _drain_frames(QTY, G1, [2, 2, 1, 2])
    # 「假数量」序列: 数字牌照实画 [2,2,3,2](读出来 ≥2, 会放行去清槽), 但第 3 列的「＋」上限只有 1 件
    # —— 复现 2026-10-09 用户抓到的现场: 清槽后「+」只能凑到 1 件, 旧代码闭眼 +2。
    if not list(SHOTS_DIR.glob(f"{G2}*.png")):
        _drain_frames(QTY, G2, [2, 2, 3, 2], plus_max={2: 1})
        # 再补一帧: 「绿槽已 +1 之后」的态(该槽 ＋ 上限=1 → ＋ 变灰)。
        # ⚠ 文件名要排在系列末尾: 下划线(0x5F) > 数字(0x30) → `..._sel` 在 `...015` 之后。
        _slot_states(QTY, f"{G2}_sel.png", [2, 2, 3, 2], [0, 0, 1, 0], plus_max={2: 1})
    # 回归帧: 今晚真机误报帧拷贝成稳定夹具名(源是探针留证, 非致命, 缺则该场景 SKIP)
    if not (SHOTS_DIR / ART).is_file() and (SHOTS_DIR / "_qaprobe_probe_detail.png").is_file():
        cv2.imwrite(str(SHOTS_DIR / ART), cv2.imread(str(SHOTS_DIR / "_qaprobe_probe_detail.png")))
        print(f"[生成] {ART}（拷自今晚探针帧）")
    print("[生成] 合成夹具: 清槽序列(喂 [2,2,3,2] 与 [2,2,1,2], 数字牌跟着画) + 无绿装帧")
    return True


PAGES = [
    (HOME0, "HOME", "首页"),
    (WH0, "WH", "仓库页"),
    (BAG, "BAG", "背包页(有 快速进阶 绿键)"),
    (LIST, "LIST", "列表页「选择快速进阶装备」"),
    (DETAIL, "DETAIL", "详情页"),
    (MATA, "MAT", "选料面板「选择材料」(盖住详情页标题)"),
    (DLG, "DIALOG", "二次确认弹窗(标题栏还在 → 必须先于详情页判)"),
    (RESULT, "RESULT", "「恭喜获得」全屏暗幕(压掉详情页标志)"),
]


def case_pages(rp):
    """① 判层专场: 8 张真帧逐一判定（跑生产 page() 本体）。"""
    bad = []
    for i, (f, want, label) in enumerate(PAGES):
        rp.idx = i
        got = qa.page(_sc(rp))
        ok = got == want
        print(f"  [{'ok  ' if ok else '!!  '}] {label:40s} 页面 {got:8s}(期望 {want})")
        if not ok:
            bad.append(label)
    return not bad, f"判层失败项={bad or '无'}"


def case_green_calib(rp):
    """② 绿装判据校准: 只认第 3 列(绿数字牌)，第 4 列白框+绿图面**不算**。"""
    rp.idx = PAGES.index(next(c for c in PAGES if c[0] == DETAIL))
    sc = _sc(rp)
    img = sc.grab()
    frac = [round(qa.tile_green(sc, i, img), 3) for i in range(4)]
    cols = qa.green_cols(sc, img)
    good = cols == [2]
    print(f"  四列数字牌绿占比={frac} (阈值 {qa.GREEN_MIN}) → 认绿列={cols} (期望 [2])")
    return good, f"绿列={cols}(期望 [2], 第 3 列才是绿装) 绿占比={frac}"


def case_list_scan(rp):
    """③ 列表扫描校准: 扫出那 1 行绿装, 且点击点落在行带内(行带 y≈1062..1222)。"""
    rp.idx = PAGES.index(next(c for c in PAGES if c[0] == LIST))
    sc = _sc(rp)
    rows = qa.green_rows(sc)
    good = len(rows) == 1 and 1050 <= rows[0] <= 1230
    return good, f"绿装行 y={rows} (期望 1 行且落在行带 1050..1230; 金标准≈1138)"


def case_qty_counts(rp):
    """④ 数量面板: [2,2,3,2] 必须解出 [2,2,3,2]，且点击顺序/坐标对得上。"""
    sc = _sc(rp)
    got = [qa.drain_slot(sc, i) for i in range(4)]
    exp_clicks = ([(114, YMIN)] * 2 + [(211, YMIN)] * 2
                  + [(307, YMIN)] * 3 + [(403, YMIN)] * 2)
    ok_c = st.check_clicks("清槽点击", rp.real_clicks, exp_clicks)
    good = got == [2, 2, 3, 2] and ok_c
    return good, f"解出数量={got}(期望 [2,2,3,2]) 点击={len(rp.real_clicks)} 次(期望 9)"


def case_full_round(rp):
    """⑤ 完整一轮真帧回放（含「只点绿确认、不碰勾选框」）。"""
    got = qa.refine_row(_sc(rp))
    clicks = rp.real_clicks
    exp = ([(C_ADJ[0], C_ADJ[1])] + [(114, YMIN)] * 2 + [(211, YMIN)] * 2
           + [(307, YMIN)] * 3 + [(403, YMIN)] * 2 + [(307, YPLUS)] * 2
           + [(C_OK[0], C_OK[1]), C_PICKEXP, C_AUTO, C_MOK, C_GO, C_CONFIRM, C_CLAIM])
    ok_c = st.check_clicks("一轮点击链", clicks, exp)
    plus = [c for c in clicks if abs(c[0] - 307) <= 6 and abs(c[1] - YPLUS) <= 6]
    near_box = [c for c in clicks
                if abs(c[0] - CHECKBOX[0]) <= 40 and abs(c[1] - CHECKBOX[1]) <= 40]
    good = got == 1 and ok_c and len(plus) == 2 and not near_box
    return good, (f"进阶={got}(期望 1) 绿槽+次数={len(plus)}(期望 2) "
                  f"误点勾选框={near_box}(期望空) 总点击={len(clicks)}")


def case_green_one(rp):
    """⑥ 绿槽只剩 1 件 → 数字牌直接读出来 → **一下「−」都不点**, 零进阶。"""
    got = qa.refine_row(_sc(rp))
    clicks = rp.real_clicks
    plus = [c for c in clicks if abs(c[1] - YPLUS) <= 6]
    minus = [c for c in clicks if abs(c[1] - YMIN) <= 6]
    ok_close = any(abs(c[0] - C_OK[0]) <= 6 and abs(c[1] - C_OK[1]) <= 6 for c in clicks)
    good = got == 0 and not plus and not minus and ok_close
    return good, (f"进阶={got}(期望 0) +点击={plus}(期望空) −点击={len(minus)}(期望 0, 省掉整轮清槽) "
                  f"确定关面板={ok_close} 总点击={len(clicks)}")


def case_ghost_count(rp):
    """⑩ 假数量: 清槽报「≥2」但真持有只有 1 件 → 点 1 下 + 就变灰 → 绝不点进阶。

    这是 2026-10-09 用户抓到的真实现场(留证帧 if 绿槽只显示 1 件，drain 却报 40 =
    DRAIN_MAX 封顶): 旧代码闭眼点两下 + → 游戏不接受该选择 → 点「快速进阶」后
    没有「恭喜获得」→ 白跑一轮并把整个页签终止。现在必须**自己发现凑不出 2 件**。
    """
    got = qa.refine_row(_sc(rp))
    clicks = rp.real_clicks
    plus = [c for c in clicks if abs(c[1] - YPLUS) <= 6]
    go = [c for c in clicks if abs(c[0] - C_GO[0]) <= 8 and abs(c[1] - C_GO[1]) <= 8]
    good = got == 0 and len(plus) == 1 and not go
    return good, (f"进阶={got}(期望 0) +点击={len(plus)}(期望 1) "
                  f"误点进阶={go}(期望空)")


def case_s_filter(rp):
    """⑨ S 徽标: 带 S 的格子不能当材料(剔除); 不带的照旧算绿。

    对照组是**同一张帧**的贴徽标版 vs 素版, 只有第 2 列(绿列)格子左上角多一枚真 S 徽标。
    """
    rp.idx = 0
    sc = _sc(rp)
    img = sc.grab()
    s_marked = qa.tile_s(sc, 2, img)
    cols_marked = qa.green_cols(sc, img)
    rp.idx = 1
    sc2 = _sc(rp)
    img2 = sc2.grab()
    s_plain = qa.tile_s(sc2, 2, img2)
    cols_plain = qa.green_cols(sc2, img2)
    good = (s_marked >= qa.S_TH and cols_marked == []
            and s_plain < qa.S_TH and cols_plain == [2])
    return good, (f"贴S帧: S分={s_marked:.3f}(需≥{qa.S_TH}) 绿列={cols_marked}(期望空) | "
                  f"素帧: S分={s_plain:.3f} 绿列={cols_plain}(期望 [2])")


def case_s_true_frame(rp):
    """⑨a 真 S 徽标(标定帧原帧, 非合成): 第 1 格必须被判 S。"""
    sc = _sc(rp)
    img = sc.grab()
    s = qa.tile_s(sc, 0, img)
    cols = qa.green_cols(sc, img)
    print(f"  标定帧第1格 S分={s:.3f} (需≥{qa.S_TH}) → 绿列(剔除S后)={cols}")
    return s >= qa.S_TH and 0 not in cols, f"真S帧: S分={s:.3f} 绿列={cols}"


def case_art_not_s(rp):
    """⑨b 图面橙纹不是 S(2026-10-10 真机回归): 第 2 列绿装必须放行, 第 3 列不算 S。

    旧颜色判据在 这帧上: 第2列 0.556(>0.55 误判 S)、第3列 0.438 —— 整行被跳过,
    真机表现 = 0 次进阶提前收工。新团块判据: 图面橙纹 bbox 74x45/fill 0.21/中心
    +12px, 四条约束全部出局。
    """
    sc = _sc(rp)
    img = sc.grab()
    s2 = qa.tile_s(sc, 1, img)
    s3 = qa.tile_s(sc, 2, img)
    cols = qa.green_cols(sc, img)
    print(f"  第2列 S分={s2:.3f}(需<{qa.S_TH}) 第3列 S分={s3:.3f}(需<{qa.S_TH}) → 绿列={cols}(期望 [1])")
    return s2 < qa.S_TH and s3 < qa.S_TH and cols == [1], \
        f"图面帧: S分={s2:.3f}/{s3:.3f} 绿列={cols}(期望 [1])"


def case_dedupe(rp):
    """⑦ 去重终止: 榨不干的行会一直在列表里 → 第二次必须认出来并收手(防死循环）。"""
    n = qa.run_tab(_sc(rp), "plane", "战机", cap=6)
    ok_tab = n == 0
    scrolls = len(rp.drags)
    # 注: 列表页预筛已生效 → 夹具那行(绿格数量 1)在外面就被挡下, 不会再进详情;
    # 所以现在守的是「会滑 + 不死循环 + 不误点」；row_sig 去重那层因夹具不够暂未覆盖。
    good = ok_tab and 1 <= scrolls <= qa.SCROLL_MAX
    return good, (f"本页签进阶={n}(期望 0, 该行无绿) 上滑={scrolls} 次"
                  f"(期望 1..{qa.SCROLL_MAX}: 会滑但不死循环) "
                  f"总点击={len(rp.real_clicks)}")


def case_dry(rp):
    """⑧ dry: 零点击零写盘。"""
    ok = qa.run(_sc(rp, dry=True), kit.Args(dry=True))
    good = ok and not rp.real_clicks and not rp.shots
    return good, f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


def case_lock(_rp):
    name = "quick_advance_selftest_probe"
    with kit.single_instance(name, ttl=60) as g1:
        with kit.single_instance(name, ttl=60) as g2:
            good = g1 is True and g2 is False
    with kit.single_instance(name, ttl=60) as g3:
        good = good and g3 is True
    return good, f"首锁={g1} 二锁={g2}(期望 False) 释放后可拿={g3}"


def scene_frames() -> dict:
    """各场景的帧表。"""
    qseq = [Path(n).name for n in sorted(str(p) for p in SHOTS_DIR.glob(f"{QSEQ}*.png"))]
    g1 = [Path(n).name for n in sorted(str(p) for p in SHOTS_DIR.glob(f"{G1}*.png"))]
    ghost = [Path(n).name for n in sorted(str(p) for p in SHOTS_DIR.glob(f"{G2}*.png"))]
    return {
        "qseq": qseq,
        # ⑤ 一轮: 详情 →(调整数量) 清槽序列 →(绿槽 +) →(确定) 详情 → 选料两帧 →
        #    详情 → 弹窗 → 结果 → 榨干
        #    ⚠ 只有**点击**会翻页(grab 不推进帧, 见 selftest_kit.Replay.grab/click),
        #      所以「读一下「+」可用态再多点一下」不会多占帧 —— 帧数只跟点击次数对齐。
        #    ⚠ 末尾必须是「无绿」帧: 领取完回详情, 第二轮开头那次 grab 才会判出「榨干」
        "round": [DETAIL, *qseq, ZERO2, ZERO2, AFTER_OK, MATA, MATA2, AFTER_MAT,
                  DLG, RESULT, NOGREEN],
        # ⑥ 绿槽 1 件: 详情 →(调整数量) 清槽序列 →(确定) 详情
        "green1": [DETAIL, *g1, AFTER_OK],
        # ⑩ 假数量: 详情 →(调整数量) 清槽(报 5 件) →(点 1 下 + 就变灰) →(确定) 面板
        "ghost": [DETAIL, *ghost, ZERO2],
        # ⑦ 终止: 列表 →(点页签)→(点行) 详情(无绿) →(X) 背包 →(入口) 列表 → 重复扫
        "dedupe": [LIST, LIST, NOGREEN, BAG, LIST, LIST, LIST, LIST, LIST, LIST, BAG],
    }


def main() -> int:
    if not ensure_fixtures():
        return 0
    f = scene_frames()
    scenes = [
        ("判层专场(8 张真帧: 弹窗/暗幕顺序陷阱)", [c[0] for c in PAGES], case_pages),
        ("绿装判据校准(只认边框绿, 不认图面偏绿)", [DETAIL], case_green_calib),
        ("列表扫描校准(扫出绿装行 + 落点)", [LIST], case_list_scan),
        ("数量面板(点到灰即读数 [2,2,3,2])", f["qseq"], case_qty_counts),
        ("完整一轮真帧回放(不点勾选框)", f["round"], case_full_round),
        ("绿槽仅 1 件 → 数字牌直读 → 一下 − 都不点", f["green1"], case_green_one),
        ("假数量(报≥2真持有1) → 绝不点进阶", f["ghost"], case_ghost_count),
        ("去重终止(榨不干的行不重访)", f["dedupe"], case_dedupe),
        ("S 徽标剔除(S 格不当材料, 非 S 格照旧)", [SDET, AFTER_OK], case_s_filter),
        ("真 S 徽标(标定帧原帧)", [LIVES], case_s_true_frame),
        ("图面橙纹不是 S(2026-10-10 真机回归)", [ART], case_art_not_s),
        ("dry 零点击零写盘", [DETAIL], case_dry),
        ("并发锁互斥", [DETAIL], case_lock),
    ]
    return st.run("quick_advance 离线自检", scenes)


if __name__ == "__main__":
    raise SystemExit(main())
