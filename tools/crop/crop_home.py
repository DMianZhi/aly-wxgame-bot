"""用例: 主界面按钮批量裁剪 (23 张)。坐标基于 845x1521 校准截图。

用法:
    .venv/Scripts/python.exe tools/crop/crop_home.py [snap_20261006_163018.png]
产出:
    templates/*.png (23 张)
    shots/templates_montage.png / shots/crops.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

from wb.croplab import run_crop  # noqa: E402

DEFAULT_SHOT = "snap_20261006_153726.png"  # 校准源截图(主界面)

# name -> (x, y, w, h, 中文说明)  基于 845x1521 截图
CROPS = {
    # ---- 顶部导航（蓝方块+下方文字）----
    "nav_home":        (53, 174, 86, 87, "首页"),
    "nav_msg":         (151, 174, 86, 87, "消息"),
    "nav_active":      (246, 174, 86, 87, "活跃度(3)"),
    "nav_reward":      (350, 174, 86, 87, "奖励(2)"),
    "nav_noble":       (450, 174, 86, 87, "贵族"),
    "nav_treasure":    (632, 174, 141, 89, "寻宝(黄色星标横幅)"),
    # ---- 左侧活动栏 ----
    "shop":            (37, 323, 89, 87, "商城"),
    "newbie_gift":     (45, 462, 74, 63, "新手礼包"),
    "event_return":    (154, 462, 76, 63, "掠影返场"),
    "pass_card":       (37, 547, 89, 87, "畅玩卡"),
    "color_core":      (51, 669, 62, 56, "炫彩核心"),
    "final_entry":     (37, 751, 89, 87, "终极登场"),
    "star_explore":    (45, 963, 110, 45, "星际探索"),
    # ---- 右侧活动栏 ----
    "thunder_rally":   (618, 452, 91, 87, "雷霆集结"),
    "game_circle":     (716, 452, 91, 87, "游戏圈"),
    "truth_pour":      (618, 544, 91, 87, "真理倾泻"),
    "community_gift":  (716, 544, 91, 87, "社区奖励"),
    # 避开右上角脉冲红点徽章与外圈光效
    "login_reward":    (723, 666, 74, 60, "累计登录(签到用)"),
    "holiday_welfare": (723, 768, 74, 60, "假日福利"),
    # ---- 底部大按钮 ----
    "pilot_btn":       (261, 1212, 167, 91, "驾驶员"),
    "warehouse_btn":   (438, 1212, 159, 91, "仓库"),
    "endless_btn":     (51, 1339, 321, 97, "无尽模式"),
    "stage_btn":       (474, 1339, 326, 97, "闯关模式"),
}


def main() -> int:
    shot = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SHOT
    return run_crop(CROPS, tag="home", shot=shot)


if __name__ == "__main__":
    raise SystemExit(main())
