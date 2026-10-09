#!/usr/bin/env python
"""离线自检: 坐标几何（基准 ↔ 客户区）—— 零消耗，不碰游戏窗口、不需要夹具。

为什么单独一个套件: 「点歪」是本项目最隐蔽的故障——模板/常量都不报错，只是慢慢偏，
窗口越小偏得越狠（601 宽时基准 x=740 直接点到窗外）。这里把几何本身钉死，
任何一次「顺手改成整图等比」都会立刻 FAIL。

真值来源（不是推导出来的，是从**真实帧**上量出来的）:
  * 845x1521 → (755,1296): battle_skill 模板在 845 帧上的命中
  * 812x1518 → (738,1293): 同一模板在 812 帧上的命中（.998 分）
  * 601x1143 → (546, 977): 601 帧上按钮颜色环圆心量出
  * 三帧顶部标题栏实测都是 77px（固定像素，不随窗口缩放）—— 这是整件事的根因

覆盖:
  ① 真帧校准点逐点断言（≤1px）
  ② 基准→客户区→基准 往返恒等（标定尺寸上不许漂）
  ③ 标题栏不缩放: y=77 在任何尺寸下都映射成 77
  ④ croplab.scale_crops 与 bot 用**同一套几何**（裁剪落点 == 点击落点）
  ⑤ 尺寸相同 → 原样返回；退化输入（高=标题栏）不炸
  ⑥ 端到端: Screen.click_base 的 dry 计划 == 换算结果（咽喉收口有效）
  ⑦ 「命中+偏移」的偏移量随窗口缩放（导弹猎场闪击键的定位方式）
  ⑧ 用例常量口径审计: 矩形一律 (x,y,w,h) 基准、宽高为正、在 812 标定帧上往返恒等

用法:
    uv run python tools/selftest/geom_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import kit, selftest_kit as st  # noqa: E402
from wb import croplab  # noqa: E402
from wb.bot import (CLIENT_TITLE_H, REF_SIZE, WinRect, client_to_ref,  # noqa: E402
                    map_point,  # noqa: E402
                    map_rect, ref_rect_to_client, ref_to_client, scale_delta)

TOl = 1  # 校准点允许误差(px)

# 真值: (尺寸, 基准坐标, 该尺寸下实测落点)
TRUTH = [
    ((845, 1521), (755, 1296), (755, 1296)),
    ((812, 1518), (755, 1296), (738, 1293)),
    ((601, 1143), (755, 1296), (546, 977)),
]
# 常量标定口径: 812x1518 实帧上量出的点（项目里 90/127 张实帧是这个尺寸）
CALIB = (812, 1518)


def case_truth(_rp):
    """① 三个真帧校准点。"""
    bad = []
    for (w, h), base, want in TRUTH:
        got = ref_to_client(*base, w, h)
        d = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        print(f"    {w}x{h}: 基准{base} → {got}  实测{want}  差{d}px")
        if d > TOl:
            bad.append(f"{w}x{h} 差{d}px")
    return not bad, f"3 个真帧校准点全部 ≤{TOl}px" if not bad else f"偏了: {bad}"


def case_roundtrip(_rp):
    """② 标定尺寸上往返恒等；换尺寸后再回来也不许漂。"""
    pts = [(0, 0), (77, 77), (156, 345), (406, 1040), (754, 1444), (811, 1517)]
    bad = []
    for p in pts:
        ref = client_to_ref(*p, *CALIB)
        back = ref_to_client(*ref, *CALIB)
        if abs(back[0] - p[0]) > TOl or abs(back[1] - p[1]) > TOl:
            bad.append(f"{p}→{ref}→{back}")
        # 侧向验证: 经别的尺寸来回也不漂
        for size in ((845, 1521), (601, 1143), (810, 1514)):
            c = ref_to_client(*ref, *size)
            r2 = client_to_ref(*c, *size)
            if abs(r2[0] - ref[0]) > TOl or abs(r2[1] - ref[1]) > TOl:
                bad.append(f"{ref}→{size}→{r2}")
    print(f"    {len(pts)} 个点 × 1 标定尺寸 + 3 个异尺寸往返")
    return not bad, "往返恒等" if not bad else f"漂了: {bad[:3]}"


def case_titlebar(_rp):
    """③ 标题栏固定 77px: y=77 在任意尺寸下都映射成 77。"""
    bad = []
    for size in ((845, 1521), (812, 1518), (601, 1143), (810, 1514), (900, 1400)):
        y = map_point(0, CLIENT_TITLE_H, CALIB, size)[1]
        if y != CLIENT_TITLE_H:
            bad.append(f"{size}→y={y}")
    print(f"    标题栏底线 y={CLIENT_TITLE_H} 在 5 种尺寸下不变")
    return not bad, "标题栏不缩放" if not bad else f"标题栏被缩放了: {bad}"


def case_croplab_same_geom(_rp):
    """④ 裁剪落点 == 点击落点（同一个 map_rect）。"""
    crops = {
        "a": croplab.Crop(156, 345, 90, 60, "左上图标"),
        "b": croplab.Crop(620, 1383, 120, 80, "右下按钮"),
        "c": croplab.Crop(754, 1444, 60, 60, "右下角"),
    }
    bad = []
    for size in ((601, 1143), (845, 1521), (810, 1514)):
        scaled = croplab.scale_crops(crops, CALIB, size)
        for n, c in crops.items():
            want = map_rect(c.x, c.y, c.w, c.h, CALIB, size)
            got = (scaled[n].x, scaled[n].y, scaled[n].w, scaled[n].h)
            if got != want:
                bad.append(f"{n}@{size} 裁剪{got} vs 点击{want}")
        print(f"    {size}: " + " ".join(
            f"{n}=({scaled[n].x},{scaled[n].y})+{scaled[n].w}x{scaled[n].h}"
            for n in crops))
    return not bad, "裁剪与点击同一套几何" if not bad else f"两套几何: {bad[:2]}"


def case_edge(_rp):
    """⑤ 同尺寸恒等 + 退化输入不炸。"""
    crops = {"a": croplab.Crop(156, 345, 90, 60, "x")}
    same = croplab.scale_crops(crops, CALIB, CALIB)
    ok1 = same is crops or (same["a"].x, same["a"].y) == (156, 345)
    degenerate = map_point(10, 100, (812, 77), (600, 77))     # 客户区高=0
    zero_wh = ref_rect_to_client(0, 0, 0, 0, 601, 1143)       # 宽高 0 → 至少 1
    ok2 = degenerate[1] == CLIENT_TITLE_H and zero_wh[2] >= 1 and zero_wh[3] >= 1
    print(f"    同尺寸恒等={ok1}  退化 map_point={degenerate}  零宽高→{zero_wh}")
    return ok1 and ok2, "恒等/退化都稳" if ok1 and ok2 else "同尺寸或退化输入有问题"


def case_click_base(_rp):
    """⑥ 端到端: click_base 计划落点 == 换算结果。"""
    base = (156, 345)
    bad = []
    for size in ((601, 1143), (845, 1521), (810, 1514)):
        sc = kit.Screen(WinRect(0, 0, size[0], size[1], hwnd=0), th=0.88, dry=True)
        sc.click_base(*base, "材料最少")
        want = ref_to_client(*base, *size)
        got = sc.planned[-1][1:3]
        print(f"    {size}: 计划{got} 期望{want}")
        if abs(got[0] - want[0]) > 0 or abs(got[1] - want[1]) > 0:
            bad.append(f"{size} 计划{got}≠{want}")
    return not bad, "click_base 与几何一致" if not bad else f"咽喉没走同一套: {bad}"


def case_delta(_rp):
    """⑦ 「命中+偏移」的偏移量必须跟着缩放（导弹猎场闪击键就是这种定位）。

    真值: 601 帧上卡片标题(120,827) → 闪击键(421,1003)，偏移(301,176)；
    同一张卡在 845 基准下这个偏移应该放到 (408,238)。
    """
    bad = []
    cases = [
        ((601, 1143), (601, 1143), (301, 176)),
        ((601, 1143), (845, 1521), (408, 238)),
        ((601, 1143), (812, 1518), (407, 238)),
    ]
    for src, dst, want in cases:
        got = scale_delta(301, 176, src, dst)
        d = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        print(f"    偏移(301,176) {src}→{dst}: 得{got} 期望{want} 差{d}px")
        if d > 1:
            bad.append(f"{src}→{dst} {got}≠{want}")
    # 与 map_point 的自洽性: 两点差值应等于 scale_delta（容 1px: 绝对坐标各自取整后相减，
    # 与「先相减再取整」天然可能差 1 —— 不是 bug，别把这条拧成 0 容忍度）
    for size in ((601, 1143), (845, 1521), (810, 1514)):
        a = map_point(120, 827, (601, 1143), size)
        b = map_point(120 + 301, 827 + 176, (601, 1143), size)
        want = scale_delta(301, 176, (601, 1143), size)
        d = max(abs((b[0] - a[0]) - want[0]), abs((b[1] - a[1]) - want[1]))
        if d > 1:
            bad.append(f"{size}: 两点差{(b[0]-a[0], b[1]-a[1])} vs scale_delta{want} 差{d}px")
    return not bad, "偏移随窗口缩放（绝对位置无关）" if not bad else f"偏移算错: {bad}"


def case_constants(_rp):
    """⑧ 用例里的「实帧量出的常量」口径审计。

    全项目矩形只有**一种口径**: `(x,y,w,h)` 基准、用 `sc.roi(*r)` 消费
    —— 以前「四角点 (x0,y0,x1,y1)」与「位置+尺寸」两种写法并存，混用时宽高会算成负数、
    ROI 静默变空（friend_stamina 的 BADGE、star_supply 的 COUNTER 都踩过）。
    这里对项目里**真实常量**逐个断言: 宽高为正 + 在 812 标定帧上往返恒等。
    """
    from tools.cases import (endless_world as ew, free_treasure as ft,
                             friend_stamina as fs, guild_donate as gd,
                             star_supply as ss, sweep_stage as sw)
    bad = []

    def pt(name, base, want812):
        back = ref_to_client(*base, 812, 1518)
        if back != want812:
            bad.append(f"{name}: {base} →812 得{back} 期望{want812}")

    def into(name, r, want812):
        """矩形常量：(x,y,w,h) 基准 —— 812 帧上必须复原成 want812。"""
        x, y, w, h = r
        if w <= 0 or h <= 0:
            bad.append(f"{name}: 宽高非正 ({x},{y},{w},{h}) —— ROI 会静默变空")
            return
        got = map_rect(x, y, w, h, REF_SIZE, (812, 1518))
        if got != want812:
            bad.append(f"{name}: {r} →812 得{got} 期望{want812}")

    # 矩形常量（唯一口径: (x,y,w,h) 基准，消费端 sc.roi(*r)）
    into("friend.BADGE", fs.BADGE, (590, 1358, 62, 56))
    into("star.COUNTER", ss.COUNTER, (700, 203, 112, 67))
    into("guild.CHK", gd.CHK, (331, 791, 34, 34))
    # 点常量
    for i, x in enumerate((156, 299, 440, 582)):
        pt(f"sweep.MAT_ICONS[{i}]", sw.MAT_ICONS[i], (x, 345))
    pt("sweep.BLANK", sw.BLANK, (420, 620))
    pt("treasure.POKE_XY", ft.POKE_XY, (406, 1040))
    pt("endless.PLANE_FROM", ew.PLANE_FROM, (406, 1180))
    pt("endless.PLANE_TO", ew.PLANE_TO, (406, 225))
    return not bad, ("常量在 812 标定帧上往返恒等且口径正确" if not bad
                     else f"口径问题: {bad}")


if __name__ == "__main__":
    st.run_one("geom 坐标几何自检", [
        ("① 真帧校准点", [], case_truth),
        ("② 往返恒等", [], case_roundtrip),
        ("③ 标题栏不缩放", [], case_titlebar),
        ("④ croplab 与 bot 同几何", [], case_croplab_same_geom),
        ("⑤ 同尺寸恒等/退化", [], case_edge),
        ("⑥ click_base 端到端", [], case_click_base),
        ("⑦ 命中+偏移随窗口缩放", [], case_delta),
        ("⑧ 用例常量口径审计(唯一口径 x,y,w,h)", [], case_constants),
    ])
