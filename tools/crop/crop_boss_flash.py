"""用例: 裁剪 BOSS 模式「闪击」链路的按钮模板 -> templates/。

与 crop_boss.py(BOSS 列表页) 互补, 这里覆盖「闪击」流程各步:
    站内闪击 -> 闪击对话框(次数/确认) -> 钻石确认弹窗 -> 局内阵亡复活 -> 结算页

源截图: shots/_boss2_station.png    (站内挑战页)
        shots/_boss6_afterflash.png  (闪击对话框)
        shots/_boss10_afterconfirm.png(钻石确认弹窗, 绿键=确认)
        shots/_boss16_before_revive.png(局内阵亡复活弹窗, 绿键=钻石复活20)
        shots/_boss18_state_result_0.png(结算页 继续)
坐标基于这些截图实测(窗口 813x1519, 与模板基准 845x1521 的缩放差 0.13%, 可忽略)。

用法:
    uv run python tools/crop/crop_boss_flash.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from wb.bot import match_template  # noqa: E402

# name -> (源截图, x, y, w, h, 说明)
CROPS = {
    "boss_flash":         ("_diag_now.png",           201, 1384, 214, 68, "站内-闪击(橙)"),
    "boss_flash_go":      ("_boss6_afterflash.png",     259, 1109, 324, 76, "闪击对话框-闪击(确认)"),
    "boss_flash_close":   ("_boss6_afterflash.png",     730,  360,  46, 46, "闪击对话框-关闭X"),
    "boss_confirm_ok":    ("_boss10_afterconfirm.png",  459,  879, 236, 68, "钻石确认弹窗-确认(绿)"),
    "boss_revive_diamond":("_boss16_before_revive.png", 157,  786, 236, 54, "局内阵亡-复活(钻石20,绿)"),
    "boss_result_next":   ("_boss18_state_result_0.png",279, 1297, 283, 90, "结算页-继续"),
    "boss_equipup_ok":    ("_bossmode_fight_timeout.png", 302,  999, 235, 68, "装备UP选择弹窗-确认(绿)"),
    "boss_equipup_title": ("_bossmode_fight_timeout.png", 309,  496, 220, 114, "装备UP选择弹窗-标题(区分两个绿键)"),
    "boss_noattempts":    ("_bossmode_nodialog_drago.png", 52, 660, 710, 150, "次数耗尽提示(含弹窗边框, 强区分)"),
    "boss_equipup_btn":   ("_bossmode_unknown_cygnus.png",652, 1230, 112, 76, "站内-装备UP键(站内页独有标记)"),
    "boss_back":          ("_diag_now.png",           641, 1418, 172, 83, "站内/列表-返回(蓝,取最右)"),
}

# 需要保证互不串台的模板对(同色系按钮最容易误匹配)
DISTINCT = [("boss_confirm_ok", "boss_revive_diamond"),   # 都是绿键
            ("boss_equipup_ok", "boss_revive_diamond"),   # 都是绿键
            ("boss_flash", "boss_flash_go")]              # 都是橙键


def main() -> int:
    out = ROOT / "templates"
    shots = ROOT / "shots"
    tpls: dict[str, "cv2.Mat"] = {}
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
        print(f"[{'ok  ' if ok else 'FAIL'}] {name:20s} ({x},{y},{w},{h}) {label:<22s} "
              f"自匹配 {hit[2]:.3f} @({hit[0]},{hit[1]})")

    print("\n串台检查(同色键互查, 越低越好):")
    for a, b in DISTINCT:
        img = cv2.imread(str(shots / CROPS[b][0]))
        if img is None or a not in tpls:
            print(f"  [SKIP] {a} / {CROPS[b][0]} 缺文件")
            continue
        v = match_template(img, tpls[a], 0.0)
        flag = "ok  " if v[2] < 0.85 else "WARN"
        print(f"  [{flag}] {a} 在 {CROPS[b][0]} 里最高分 {v[2]:.3f}")
    if skipped:
        print(f"(跳过 {skipped} 项: 源截图已被清理, 模板保留不动)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
