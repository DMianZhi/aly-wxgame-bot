"""用例: 「逐星补给」模板裁剪 (两层: 逐星长阶页 / 逐星补给面板)。

用法:
    uv run python tools/crop/crop_star.py
产出:
    templates/ss_entry.png   长阶页左下「逐星补给」入口文字 (页面标志 + 点击目标)
    templates/ss_beacon.png  长阶页「开始挑战」上方 ×5 装置 (含右上红点) —— **可领态才存在**
    templates/ss_claim5.png  补给面板「领5次」橙键 (也当面板标志)
    templates/ss_close.png   补给面板右上关闭 X
    shots/star_{stair,panel}_crops.csv / *_montage.png

校准源 (**845x1521 基准**，坐标表直接可用，不缩放):
    shots/snap_20261008_2107_stair.png  逐星长阶页 (×5 装置**可领**态: 装置 + 红点)
    shots/snap_20261008_2108_panel.png  逐星补给面板 (半透明压暗)

⚠ 本用例踩过的坑 (2026-10-08):
   * **ss_beacon 必须裁「可领」态**：装置**已领后整个消失**（不是变灰）→ 若裁自已领帧，
     模板在真正可领时反倒不命中（0.59）。裁剪源固定用 2107 那张可领帧。
   * **×5 装置带红点**：装置与红点同生同灭，红点含在模板里反而是最强的「今日可领」信号
     （实测可领 1.000 / 已领 0.59→不命中 / 其它页 ≤0.53）。
   * **面板是半透明压暗**：面板帧上 ss_entry 仍 0.97 命中 → 判层顺序必须 PANEL 先于 STAIR
     （用例里已钉死；本表只管裁模板）。
   * **按钮坐标目测会差 8px 点空**（首点 (551,957) 落进橙键上方空白）：全部按颜色测真实
     bbox 再裁 —— 橙键 (492,972,238,65) 中心 (611,1004)、蓝键 (138,969,248,70)。
   * 复用现成模板: 恭喜获得「领取」= claim_btn (0.994)、「返回」= wc_res_back (0.976)、
     「闯关模式」= stage_btn (0.997)、长阶横幅 = stage_stair (见 crop_stage.py 注)。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

import cv2  # noqa: E402

from wb.cfg import SHOTS_DIR, TEMPLATES_DIR  # noqa: E402
from wb.croplab import _match_one, run_crop  # noqa: E402

STAIR = "snap_20261008_2107_stair.png"   # 逐星长阶页(×5 装置可领态)
PANEL = "snap_20261008_2108_panel.png"   # 逐星补给面板

# 逐星长阶页 (基准坐标)
ENTRY = (62, 1048, 162, 55)      # 左下「逐星补给」文字(避开卡片装饰光)
BEACON = (388, 992, 122, 112)    # 「开始挑战」上方 ×5 装置(含右上红点 → 可领标记)

# 补给面板 (基准坐标)
CLAIM5 = (492, 972, 238, 65)     # 「领5次」橙键(含 ×5)
CLOSE = (758, 400, 42, 40)       # 右上关闭 X

# 跨页核验: 这 4 张模板在别的页面不许命中(通用阈值 0.86)
OTHERS = ["snap_20261006_160202.png",    # 闯关页(旧美术) —— 长阶页的上一级
          "snap_20261008_155847.png"]    # 首页
CROSS_MAX = 0.86


def cross_check() -> int:
    """逐模板跨页核验: 本页命中 1.000, 非本页必须 ≤ CROSS_MAX。

    防的是「好友」标题牌那种坑(通用元素在别的页 0.883 误命中) —— 判页标志一旦
    误命中, 用例就会在错的页面上按对的坐标瞎点。
    """
    bad = 0
    for shot in OTHERS:
        p = SHOTS_DIR / shot
        if not p.is_file():
            print(f"  [skip] 缺核验源 {shot}")
            continue
        img = cv2.imread(str(p))
        if img is None:
            continue
        if img.shape[:2] != (1521, 845):
            img = cv2.resize(img, (845, 1521))
        for name in ("ss_entry", "ss_beacon", "ss_claim5", "ss_close"):
            score, _, _ = _match_one(img, TEMPLATES_DIR / f"{name}.png")
            ok = score <= CROSS_MAX
            bad += 0 if ok else 1
            print(f"  [{'ok  ' if ok else '!!  '}] {name:10s} @ {shot[5:19]} = {score:.3f}"
                  f" (须 ≤{CROSS_MAX})")
    return bad


def main() -> int:
    weak = 0
    # 长阶页(×5 装置可领态 = 裁剪源的关键)
    weak += run_crop(
        {"ss_entry": (*ENTRY, "长阶页「逐星补给」入口(页面标志)"),
         "ss_beacon": (*BEACON, "长阶页 ×5 装置(含红点=今日可领)")},
        tag="star_stair", shot=STAIR, reuse=["stage_btn", "wc_res_back"],
    )
    # 补给面板
    weak += run_crop(
        {"ss_claim5": (*CLAIM5, "面板「领5次」橙键(含×5)"),
         "ss_close": (*CLOSE, "面板关闭 X")},
        tag="star_panel", shot=PANEL, reuse=["claim_btn"],
    )
    bad = cross_check()
    # 两态核对: ×5 装置模板在**已领**帧上必须不命中(装置整个消失)
    done = SHOTS_DIR / "snap_20261008_2110_stair_done.png"
    if done.is_file():
        img = cv2.imread(str(done))
        if img.shape[:2] != (1521, 845):
            img = cv2.resize(img, (845, 1521))
        s, _, _ = _match_one(img, TEMPLATES_DIR / "ss_beacon.png")
        ok = s < CROSS_MAX
        bad += 0 if ok else 1
        print(f"  [{'ok  ' if ok else '!!  '}] ss_beacon @ 已领帧 = {s:.3f}"
              f" (须 <{CROSS_MAX}: 装置消失→不命中)")
    print(f"=== 薄弱模板 {weak} / 跨页核验失败 {bad} ===")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
