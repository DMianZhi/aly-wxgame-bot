#!/usr/bin/env python
"""用例: 裁剪 超限模式 链路的模板 -> templates/。

链路(首页→闯关→BOSS→超限→类型详情页→超限挑战→局内):
    超限页: 标题(进页标志) + 四个空间站铭牌(点入各类型详情页)
    详情页: 底部「普通挑战/超限挑战」双按钮 + 右缘橙色切换箭头(6 boss 轮换)

源截图: shots/_exb_04_hyper.png  (超限模式页 812x1518)
        shots/_exh_02_card1.png  (详情页: 刺针·烈焰, 811x1516)
        shots/_exh_02_card0/2.png (详情页: 刺针·爆炎/雷鸣, 交叉验证按钮不串台)
        shots/__hyp4_01_dialog.png (确认弹窗「是否开始挑战?」811x1516)
        shots/__hyp3_03_after_2.png (黄金钥匙物品弹窗, 右上蓝X)

用法:
    uv run python tools/crop/crop_hyper.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb.bot import match_template  # noqa: E402

# name -> (源截图, x, y, w, h, 说明)
CROPS = {
    "hyper_title":       ("_exb_04_hyper.png",  250,  295, 320,  72, "超限页-「超限模式」标题(进页标志)"),
    "hyper_stn_drago":   ("_exb_04_hyper.png",   88,  575, 270,  85, "超限页-天龙座铭牌(装甲原晶)"),
    "hyper_stn_cygnus":  ("_exb_04_hyper.png",  502,  752, 272,  85, "超限页-白鸟座铭牌(副武器原晶)"),
    "hyper_stn_pegasus": ("_exb_04_hyper.png",   88, 1075, 270,  85, "超限页-天马座铭牌(战机原晶)"),
    "hyper_stn_andro":   ("_exb_04_hyper.png",  502, 1242, 272,  85, "超限页-仙女座铭牌(僚机原晶)"),
    # ⚠ 按钮别从 _exh_02_card1 里裁 —— 那帧(812宽)按钮上方紧贴奖励钥匙图标(蓝金主色)，
    #   265 宽的框必然裹进图标，匹配会命中图标而不是按钮(实测弹物品详情)。
    #   改从 _hyp_04_detail.png(811宽活帧)裁**文字区**：y 1371~1444、x 414~608，
    #   取 (416,1372,190,70) 避开与黄键的接缝；活帧已验证 1.000 / 无关帧 0.299。
    "hyper_chal":        ("_hyp_04_detail.png", 416, 1372, 190,  70, "详情页-超限挑战(橙,文字区)"),
    "hyper_switch":      ("_exh_02_card1.png",  775,  600,  36, 200, "详情页-切换boss(右缘橙箭头)"),
    # 确认弹窗黄键: 实测命中中心 (424,1002)@0.996 → 框居中裁; ⚠ 该帧右上 (761,538)
    # 还有**同款蓝X**(0.989) —— popup_blue_x 判定绝不能抢在 hyper_start 之前(真踩过坑)。
    "hyper_start":       ("__hyp4_01_dialog.png", 339,  968, 170,  68, "确认弹窗-挑战(黄键)"),
    "hyper_done":        ("_h5___h5_full0.png",  676, 1129,  50,  54, "详情页-挑战成功绿标(右卡右上斜角,已击败判据)"),
    "hyper_125":         ("_h5___h5_full0.png",  729,  643, 163,  30, "详情页-抗性面板「超限125%」行(出击前提)"),
    "popup_blue_x":      ("__hyp3_03_after_2.png", 739,  516,  44,  44, "物品弹窗-右上蓝X(通用关闭)"),
}

# 需要保证不串台的模板 (在另一张同布局详情帧里分数必须低)
DISTINCT = [
    ("hyper_chal",   "_exh_02_card0.png"),
    ("hyper_switch", "_exh_02_card2.png"),
    ("hyper_title",  "_exh_02_card0.png"),
    ("hyper_start",  "_hyp_04_detail.png"),   # 确认键不得窜到详情页(没弹窗时)
    ("popup_blue_x", "_hyp_04_detail.png"),   # X 不得在详情页误命中(否则乱关页面)
]


def main() -> int:
    out = ROOT / "templates"
    shots = ROOT / "shots"
    tpls: dict[str, np.ndarray] = {}
    bad = skipped = 0
    for name, (shot, x, y, w, h, label) in CROPS.items():
        img = cv2.imread(str(shots / shot))
        if img is None:
            print(f"[SKIP] 源截图已不在 shots/{shot} → 保留 templates/{name}.png 原样")
            skipped += 1
            continue
        tpl = img[y:y + h, x:x + w]
        cv2.imwrite(str(out / f"{name}.png"), tpl)
        tpls[name] = tpl
        hit = match_template(img, tpl, 0.0)
        ok = hit is not None and hit[2] >= 0.99
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else 'FAIL'}] {name:18s} ({x},{y},{w},{h}) {label:<26s} "
              f"自匹配 {hit[2]:.3f} @({hit[0]},{hit[1]})")

    print("\n串台检查(在同类详情帧里互查, 越低越好):")
    for a, other in DISTINCT:
        img = cv2.imread(str(shots / other))
        if img is None or a not in tpls:
            print(f"  [SKIP] {a} / {other} 缺文件")
            continue
        v = match_template(img, tpls[a], 0.0)
        flag = "ok  " if v[2] < 0.85 else "WARN"
        bad += 0 if flag == "ok  " else 1
        print(f"  [{flag}] {a} 在 {other} 里最高分 {v[2]:.3f} @({v[0]},{v[1]})")

    # 蒙太奇(等高拼接 + 黄字标签)
    H = 180
    tiles = []
    for name in CROPS:
        t = tpls[name]
        s = H / t.shape[0]
        t = cv2.resize(t, (max(1, int(t.shape[1] * s)), H))
        canvas = np.zeros((H + 22, t.shape[1], 3), np.uint8)
        canvas[22:, : t.shape[1]] = t
        cv2.putText(canvas, name, (2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 255, 255), 1, cv2.LINE_AA)
        tiles.append(canvas)
    mpath = shots / "hyper_crops_montage.png"
    gap = np.full((H + 22, 6, 3), 40, np.uint8)
    row: list[np.ndarray] = []
    for i, t in enumerate(tiles):
        row.append(t)
        if i < len(tiles) - 1:
            row.append(gap)
    cv2.imwrite(str(mpath), np.hstack(row))
    print(f"\n蒙太奇 {mpath}")
    if skipped:
        print(f"(跳过 {skipped} 项: 源截图已被清理, 模板保留不动)")
    print(f"OUTPUT={mpath.resolve()}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
