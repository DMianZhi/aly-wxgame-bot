"""用例: 「战队捐献」模板裁剪 (三层: 首页战队入口 / 战队页捐献入口 / 捐献页与支付键)。

用法:
    uv run python tools/crop/crop_guild.py
产出:
    templates/gd_entry.png         首页「战队」入口 (六边形天平 + 战队文字; 避开右上红点)
    templates/gd_donate_entry.png  战队页右下「捐献」按钮 (也当战队页标志)
    templates/gd_title.png         捐献页标题「战队捐献」(页面标志)
    templates/gd_gold_btn.png      左卡「金币捐献」黄色支付键 (金币图标 + 2000)
    templates/gd_diamond_btn.png   右卡「钻石捐献」黄色支付键 (钻石图标 + 50)
    templates/gd_close.png         捐献页右上角关闭 X
    templates/gd_confirm_title.png 确认弹窗标志「确定要进行」(钻石/金币共用前缀)
    templates/gd_confirm_ok.png    确认弹窗「确定」黄键
    templates/gd_cancel.png        确认弹窗「取消」蓝键
    templates/gd_chk_off.png       「今日不再提示」勾选框-未勾选(靛蓝空格)
    templates/gd_chk_on.png        「今日不再提示」勾选框-已勾选(整块黄)
    templates/gd_no_cnt_title.png  提示层「捐献次数不足」(绿确认键那种, 半透明不挡底下页标志)
    templates/gd_no_cnt_ok.png     提示层「确认」绿键
    shots/guild*_crops.csv / *_montage.png

坐标基于 812x1518 实测截图 (同 845x1521 基准尺度)。

⚠ 钻石捐献**有二级确认弹窗**(「确定要进行钻石捐献吗?」+ 今日不再提示 + 取消/确定💎50),
   弹窗是半透明遮罩: 底下的 gd_title 仍 1.000、gd_gold_btn/gd_diamond_btn 仍 0.999,
   → 单靠这些标志**分不出弹窗层**, 必须用 gd_confirm_title 单独判层(否则会在弹窗上继续点支付键)。
   勾选框用**颜色**判态比模板更稳: 未勾 B≈219/R≈18, 已勾 R≈255/G≈252/B=0。

⚠ 本用例踩过的坑 (2026-10-08):
   * **支付键位置**: 左卡「2000」/右卡「50」黄色键实测 bbox 左 (109,1094,235,70) 中心 (226,1129)、
     右 (495,1094,235,71) 中心 (612,1129)。先前按几何猜测点在 y=1005..1082 (卡片中部图标行),
     点的是**卡片正中而非按钮** → 毫无反应, 误判成「窗口/前台问题」。教训: 支付键必须先按颜色
     (橙黄渐变 R>215/G 130..215/B<110) 测出真实 bbox, 再裁模板, 不靠目测。
   * 捐献成功弹层 = 「恭喜获得 / 战队贡献币 20 / 领取」: 领取键可复用 templates/claim_btn.png
     (实测 0.980), 因此本用例不另裁。
   * 战队页与捐献页右下角「返回」同款同位置 → 复用 templates/ral_back.png (两页均 0.986)。
   * 首页标志只能用 stage_btn(闯关模式, 0.992); nav_home 在本页 0.840 但子页常 0.97+ 不可用。
   * 战队入口右上角有红点(捐献提醒) → gd_entry 只裁左侧(六边形左半 + 战队文字), 红点掉了也认。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

import cv2  # noqa: E402

from wb.bot import find_game_window, grab_window  # noqa: E402
from wb.cfg import CONF, SHOTS_DIR, TEMPLATES_DIR  # noqa: E402
from wb.croplab import _match_one, run_crop  # noqa: E402

HOME = "_gd0_home.png"            # 首页(战队入口)
GUILD = "_gd2_guildpage.png"      # 战队页(捐献入口)
DONATE = "_gd10_after_claim.png"  # 捐献页(金币捐过 1 次, 左卡 2/3)
POPUP = "_gd9_popup_claim.png"    # 捐献成功弹层(恭喜获得)

# 首页「战队」入口: 只裁「战队」两字带(x660..738 / y1040..1076)。
# 为何不裁整个六边形: 战队页左上角是**同款同尺寸**的神庭徽记, 整徽记当模板在战队页得 0.81~0.84
# (判定线 0.86, 余量太薄); 文字带在战队页/捐献页/弹层都只有 0.68~0.72, 余量 0.14+。
# 同时严格避开右上角红点(x740..800, y1063..1108) -> 红点掉了模板仍命中。
ENTRY = (660, 1040, 78, 36)

# 战队页「捐献」按钮 (右中, 八角形蓝底)
DONATE_ENTRY = (622, 958, 156, 100)

# 捐献页
TITLE = (243, 300, 340, 92)     # 「战队捐献」四字(避开右侧 ? )
GOLD_BTN = (109, 1094, 235, 70)  # 金币捐献支付键(含金币图标+2000)
DIAMOND_BTN = (495, 1094, 235, 71)  # 钻石捐献支付键(含钻石图标+50)
CLOSE = (735, 320, 50, 52)      # 右上关闭 X

# 确认弹窗(_gd12_t4: 钻石捐, 勾选框未勾 / _gd13: 点过勾选框)
CONFIRM_SRC = "_gd12_t4.png"
CHK_ON_SRC = "_gd13_chk_on.png"
NOCNT_SRC = "_guild_nopopup_diamond.png"   # 「钻石捐献次数不足」提示层(绿「确认」)
CONFIRM_TITLE = (243, 712, 150, 48)  # 「确定要进行」(钻石/金币弹窗同前缀)
CONFIRM_OK = (462, 870, 130, 60)     # 「确定💎50/🪙2000」黄键(裁左侧文字带)
CANCEL = (172, 873, 150, 55)         # 「取消」蓝键文字带
CHK = (331, 791, 34, 34)             # 「今日不再提示」勾选框
NOCNT_TITLE = (345, 722, 182, 46)    # 「捐献次数不足」(钻石/金币弹层共用后半段)
NOCNT_OK = (345, 883, 135, 48)       # 「确认」绿键文字带

NEG_LIMIT = 0.80  # 负例上限: 必须明显低于 0.85 判定线

CROSS = [
    # (模板, 负例截图, 说明, 是否应命中)
    ("gd_entry", GUILD, "战队页 -> 不该命中", False),
    ("gd_entry", DONATE, "捐献页 -> 不该命中", False),
    ("gd_donate_entry", HOME, "首页 -> 不该命中", False),
    ("gd_donate_entry", DONATE, "捐献页 -> 不该命中", False),
    ("gd_title", HOME, "首页 -> 不该命中", False),
    ("gd_title", GUILD, "战队页 -> 不该命中", False),
    ("gd_title", POPUP, "弹层(全屏遮罩) -> 不该命中", False),
    ("gd_gold_btn", GUILD, "战队页 -> 不该命中", False),
    ("gd_diamond_btn", HOME, "首页 -> 不该命中", False),
    ("gd_close", HOME, "首页 -> 不该命中", False),
    ("gd_confirm_title", DONATE, "捐献页(无弹窗) -> 不该命中", False),
    ("gd_confirm_title", HOME, "首页 -> 不该命中", False),
    ("gd_confirm_title", POPUP, "恭喜获得弹层 -> 不该命中", False),
    ("gd_confirm_ok", DONATE, "捐献页 -> 不该命中", False),
    ("gd_cancel", DONATE, "捐献页 -> 不该命中", False),
    ("gd_no_cnt_title", DONATE, "捐献页 -> 不该命中", False),
    ("gd_no_cnt_title", HOME, "首页 -> 不该命中", False),
    ("gd_no_cnt_title", CONFIRM_SRC, "钻石确认弹窗 -> 不该命中", False),
    ("gd_no_cnt_ok", DONATE, "捐献页 -> 不该命中", False),
    ("gd_no_cnt_ok", GUILD, "战队页 -> 不该命中", False),
    # 注: gd_chk_off 不列入负例核验 —— 一个「纯蓝色小方块」模板在捐献页/弹层会到处误命中
    # (0.81 @ 邀请好友旁 / 0.84 @ 弹层角落)。所以工具里勾选框**用颜色判态**
    # (未勾 B≈219/R≈18 vs 已勾 R≈255/G≈252/B=0), 模板仅留档。
    # 正例
    ("gd_entry", HOME, "首页 -> 该命中", True),
    ("gd_donate_entry", GUILD, "战队页 -> 该命中", True),
    ("gd_title", DONATE, "捐献页 -> 该命中", True),
    ("gd_gold_btn", DONATE, "捐献页左卡 -> 该命中", True),
    ("gd_diamond_btn", DONATE, "捐献页右卡 -> 该命中", True),
    ("gd_close", DONATE, "捐献页 -> 该命中", True),
    ("gd_confirm_title", CONFIRM_SRC, "确认弹窗 -> 该命中", True),
    ("gd_confirm_ok", CONFIRM_SRC, "确认弹窗「确定」 -> 该命中", True),
    ("gd_cancel", CONFIRM_SRC, "确认弹窗「取消」 -> 该命中", True),
    ("gd_chk_off", CONFIRM_SRC, "未勾选态 -> 该命中", True),
    ("gd_no_cnt_title", NOCNT_SRC, "次数不足提示层 -> 该命中", True),
    ("gd_no_cnt_ok", NOCNT_SRC, "次数不足「确认」绿键 -> 该命中", True),
]

REGION2 = [
    # 勾选框两态互斥(颜色判态比模板稳, 但模板也要能分开)
    ("gd_chk_on", CONFIRM_SRC, CHK, "未勾选弹窗里不该命中已勾模板"),
    ("gd_chk_off", CHK_ON_SRC, CHK, "已勾选弹窗里不该命中未勾模板"),
]

REGION = [
    # (模板, 截图, 区域, 说明) 区域内不该命中: 防金币/钻石支付键互相串台
    ("gd_gold_btn", DONATE, (495, 1094, 235, 71), "右卡(钻石键)区域"),
    ("gd_diamond_btn", DONATE, (109, 1094, 235, 70), "左卡(金币键)区域"),
    ("gd_entry", HOME, (0, 1000, 600, 300), "首页左下(非战队入口区)"),
]


def _region_score(shot: str, box: tuple[int, int, int, int], name: str) -> float:
    img = cv2.imread(str(SHOTS_DIR / shot))
    x, y, w, h = box
    region = img[y:y + h, x:x + w]
    tpl = cv2.imread(str(TEMPLATES_DIR / f"{name}.png"))
    if tpl is None or region.size == 0 or tpl.shape[0] > h or tpl.shape[1] > w:
        return -1.0
    return float(cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED).max())


def cross_check() -> int:
    """跨页/跨卡区分度核验: 打印关键分数, 返回失败数。"""
    print("--- 跨页/跨卡核验 ---")
    bad = 0
    for name, shot, note, want_hit in CROSS:
        img = cv2.imread(str(SHOTS_DIR / shot))
        score, cx, cy = _match_one(img, TEMPLATES_DIR / f"{name}.png")
        ok = (score >= 0.90) if want_hit else (score <= NEG_LIMIT)
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else '!!  '}] {name:18s} vs {shot:22s} {score:.4f} ({note})")
    for name, shot, box, note in REGION:
        score = _region_score(shot, box, name)
        ok = score <= NEG_LIMIT
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else '!!  '}] {name:18s} in {note:22s} {score:.4f} (区域内不该命中)")
    for name, shot, box, note in REGION2:
        score = _region_score(shot, box, name)
        ok = score <= NEG_LIMIT
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else '!!  '}] {name:18s} in {note:24s} {score:.4f} (勾选框两态互斥)")
    # 复用件: 返回 / 领取键
    for name, shot in (("ral_back", GUILD), ("ral_back", DONATE), ("claim_btn", POPUP)):
        img = cv2.imread(str(SHOTS_DIR / shot))
        score, cx, cy = _match_one(img, TEMPLATES_DIR / f"{name}.png")
        print(f"[info] {name:18s} vs {shot:22s} {score:.4f} center=({cx},{cy}) (复用件)")
    print("[info] 勾选框用颜色判态(蓝=未勾 / 黄=已勾), 不做模板核验")
    return bad


def main() -> int:
    weak = 0
    weak += run_crop(
        {"gd_entry": (*ENTRY, "首页「战队」入口(避开红点)")},
        tag="guild_home", shot=HOME, reuse=["stage_btn", "nav_treasure"],
    )
    weak += run_crop(
        {"gd_donate_entry": (*DONATE_ENTRY, "战队页「捐献」按钮")},
        tag="guild_page", shot=GUILD, reuse=["ral_back", "nav_home"],
    )
    weak += run_crop(
        {"gd_confirm_title": (*CONFIRM_TITLE, "确认弹窗标志「确定要进行」"),
         "gd_confirm_ok": (*CONFIRM_OK, "弹窗「确定」黄键"),
         "gd_cancel": (*CANCEL, "弹窗「取消」蓝键"),
         "gd_chk_off": (*CHK, "勾选框-未勾选")},
        tag="guild_confirm", shot=CONFIRM_SRC, reuse=["gd_title", "gd_gold_btn"],
    )
    weak += run_crop(
        {"gd_no_cnt_title": (*NOCNT_TITLE, "提示层「捐献次数不足」"),
         "gd_no_cnt_ok": (*NOCNT_OK, "提示层「确认」绿键")},
        tag="guild_nocnt", shot=NOCNT_SRC, reuse=["gd_title", "gd_gold_btn"],
    )
    weak += run_crop(
        {"gd_chk_on": (*CHK, "勾选框-已勾选")},
        tag="guild_chk_on", shot=CHK_ON_SRC, reuse=["gd_confirm_title"],
    )
    weak += run_crop(
        {"gd_title": (*TITLE, "捐献页标题「战队捐献」"),
         "gd_gold_btn": (*GOLD_BTN, "左卡「金币捐献」2000 支付键"),
         "gd_diamond_btn": (*DIAMOND_BTN, "右卡「钻石捐献」50 支付键"),
         "gd_close": (*CLOSE, "捐献页关闭 X")},
        tag="guild_donate", shot=DONATE, reuse=["ral_back", "stage_btn"],
    )
    # 弹层: 领取键复用 claim_btn (0.980), 不另裁 -> 只做核对
    _ = find_game_window(CONF.title_keyword, CONF.process_name)
    _ = grab_window
    bad = cross_check()
    print(f"=== 薄弱模板 {weak} / 跨页核验失败 {bad} ===")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
