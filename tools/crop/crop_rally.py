"""用例: 「十年集结」模板裁剪 (三层: 集结页 / 召集宝箱弹窗 / 弹幕面板)。

用法:
    uv run python tools/crop/crop_rally.py
产出:
    templates/ral_wish.png        集结页「发弹幕」按钮 (也当集结页标志)
    templates/ral_chest.png       集结页右下宝箱本体 (白盒; 红点掉了也认)
    templates/ral_back.png        「返回」按钮 (集集页与宝箱弹窗同款同位置 -> 靠页面标志分层)
    templates/ral_chest_title.png 弹窗标志「召集宝箱」
    templates/ral_lv15.png        Lv15 大宝箱 (未领态; 领取后箱盖打开 -> 不再命中 = 判已领)
    templates/ral_danmu_bar.png   弹幕面板标志 (标题条 + 关闭 X)
    templates/ral_send.png        弹幕面板第 1 条「发送」按钮
    shots/rally*_crops.csv / *_montage.png

坐标基于 812x1518 实测截图 (同 845x1521 基准尺度)。

⚠ 首页入口分两张卡: 寻宝正下方 **第一张是视频 banner (整帧都在动, 无固定文字, 点它无反应)**,
   可点的是**第二张「十年集结」金卡**。工具做成「先试视频卡 -> 验证未进页 -> 再试金卡」。
⚠ 「返回」按钮在集结页与召集宝箱弹窗里同款同位置 (700..795, 1405..1490), 单看模板分不出层级,
   必须用 ral_wish (集结页) / ral_chest_title (弹窗) 判断当前在哪一层。
⚠ 宝箱领完红点消失, 因此宝箱模板只裁白盒本体 (不含红点), 保证「红点没了也认」。
⚠ ral_back 在弹窗里分数略降 (0.894 vs 集结页 1.000) -> 判定阈值取 0.85 并靠页面标志确认层级。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

import cv2  # noqa: E402

from wb.cfg import SHOTS_DIR, TEMPLATES_DIR  # noqa: E402
from wb.croplab import _match_one, run_crop  # noqa: E402

PAGE = "_rec_rally_page.png"        # 十年集结页 (宝箱未领)
CHEST = "_rec_rally_chest.png"      # 召集宝箱弹窗 (Lv15 未领)
CHEST_OPEN = "_rec_rally_chest_open.png"  # 召集宝箱弹窗 (已领, 箱盖打开)
DANMU = "_rec_rally_danmu.png"      # 弹幕面板
HOME = "_rec_home_page.png"         # 旧首页帧(该位置是别的活动 -> 当负例)
HOME_RALLY = "_rec_home_rally.png"  # 本会话首页帧(含「十年集结」金卡)

# 首页入口: 活动卡会轮换(旧帧同位置是「雷霆集结/游戏圈」), 所以用**整张金卡**做首选入口,
# 几何偏移(寻宝下方第二张)当傅底。实测正例 1.000/0.997, 负例 ≤0.383。
CARD = (600, 418, 200, 116)      # 首页右侧「十年集结」金卡

# 集结页
TITLE = (238, 190, 352, 58)      # 「全服集结雷霆机长」标题(静态部分; 下方数字会变 -> 不裁)
WISH = (230, 1072, 195, 32)      # 「发弹幕」文字带(红点在 y<1070, 天然避开: 已发后仍 0.95)
CHEST_BOX = (560, 1140, 235, 100)  # 右下宝箱本体(白盒)
BACK = (658, 1404, 138, 88)      # 「返回」

# 召集宝箱弹窗
CHEST_TITLE = (230, 140, 352, 102)  # 「召集宝箱」
LV15 = (95, 550, 245, 245)        # Lv15 大宝箱 + 左下标

# 弹幕面板
DANMU_BAR = (45, 308, 715, 72)    # 标题条 「弹幕」 + 关闭 X
SEND = (612, 405, 150, 95)        # 第 1 条「发送」

NEG_LIMIT = 0.80  # 负例上限: 必须明显低于 0.85 判定线(0.62/0.65 这类弱响应属正常)

CROSS = [
    # (模板, 负例截图, 说明, 是否应命中)
    ("ral_lv15", CHEST_OPEN, "已领(箱盖打开) -> 不该命中", False),
    ("ral_wish", HOME, "首页 -> 不该命中", False),
    ("ral_title", HOME, "首页 -> 不该命中", False),
    ("ral_chest_title", CHEST, "弹窗标志 -> 该命中", True),
    ("ral_lv15", CHEST, "未领弹窗 -> 该命中", True),
    ("ral_title", CHEST, "弹窗层: 标题被替掉 -> 不该命中", False),
    ("ral_title", DANMU, "弹幕面板层: 标题仍可见 -> 该命中", True),
    ("ral_card", HOME_RALLY, "本会话首页 -> 该命中", True),
    ("ral_card", HOME, "旧首页(活动已轮换) -> 不该命中", False),
    ("ral_card", PAGE, "集结页 -> 不该命中", False),
]

REGION = [
    # (模板, 截图, 区域, 说明) 区域内不该命中: 防通用蓝底按钮串台
    ("ral_back", CHEST, (150, 1245, 230, 130), "弹窗「换一批」区域"),
    ("ral_wish", PAGE, (540, 1120, 270, 140), "集结页宝箱区域"),
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
    """跨页/跨状态区分度核验: 打印关键分数, 返回失败数。"""
    print("--- 跨页/跨状态核验 ---")
    bad = 0
    for name, shot, note, want_hit in CROSS:
        img = cv2.imread(str(SHOTS_DIR / shot))
        score, cx, cy = _match_one(img, TEMPLATES_DIR / f"{name}.png")
        ok = (score >= 0.90) if want_hit else (score <= NEG_LIMIT)
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else '!!  '}] {name:16s} vs {shot:26s} {score:.4f} ({note})")
    for name, shot, box, note in REGION:
        score = _region_score(shot, box, name)
        ok = score <= NEG_LIMIT
        bad += 0 if ok else 1
        print(f"[{'ok  ' if ok else '!!  '}] {name:16s} in {note:22s} {score:.4f} (区域内不该命中)")
    # ral_back 同款同位置: 集结页与弹窗都应命中
    for shot in (PAGE, CHEST):
        img = cv2.imread(str(SHOTS_DIR / shot))
        score, cx, cy = _match_one(img, TEMPLATES_DIR / "ral_back.png")
        print(f"[info] ral_back vs {shot:26s} {score:.4f} center=({cx},{cy}) (两层同款同位置)")
    return bad


def main() -> int:
    weak = 0
    weak += run_crop(
        {"ral_card": (*CARD, "首页「十年集结」金卡(入口)")},
        tag="rally_home", shot=HOME_RALLY, reuse=["stage_btn"],
    )
    weak += run_crop(
        {"ral_title": (*TITLE, "集结页标题「全服集结雷霆机长」"),
         "ral_wish": (*WISH, "集结页「发弹幕」"),
         "ral_chest": (*CHEST_BOX, "右下宝箱本体"),
         "ral_back": (*BACK, "「返回」(两层同款)")},
        tag="rally", shot=PAGE, reuse=["nav_treasure", "nav_home"],
    )
    weak += run_crop(
        {"ral_chest_title": (*CHEST_TITLE, "弹窗标志「召集宝箱」"),
         "ral_lv15": (*LV15, "Lv15 大宝箱(未领态)")},
        tag="rally_chest", shot=CHEST, reuse=["ral_back"],
    )
    weak += run_crop(
        {"ral_danmu_bar": (*DANMU_BAR, "弹幕面板标志(标题条+X)"),
         "ral_send": (*SEND, "第 1 条「发送」")},
        tag="rally_danmu", shot=DANMU, reuse=["ral_wish"],
    )
    bad = cross_check()
    print(f"=== 薄弱模板 {weak} / 跨页核验失败 {bad} ===")
    return weak + bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
