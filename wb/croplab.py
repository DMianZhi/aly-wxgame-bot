"""croplab — 模板裁剪实验共享库。

四个 crop_* 用例脚本共用的逻辑全部下沉到这里：
  - 源截图选取（显式指定或自动取 shots/ 最新）
  - 等比坐标换算（参考尺寸 -> 实际截图尺寸）
  - 裁剪落盘 templates/<name>.png
  - 坐标表 CSV
  - 带中文标注的蒙太奇核对图
  - 自匹配 / 实时窗口匹配 / 指定源匹配三种校验
  - 同类元素区分度矩阵（多模板互不串台）

用例脚本只保留：CROPS 坐标表 + REUSE 复用列表 + main()。
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 让 tools/ 下的用例脚本无需配置 sys.path 即可导入 wb
if str(APP_DIR := Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from wb.bot import find_game_window, grab_window, map_rect  # noqa: E402
from wb.cfg import CONF, SHOTS_DIR, TEMPLATES_DIR  # noqa: E402

WEAK_THRESHOLD = 0.90   # 实时匹配低于此分算薄弱
SELF_THRESHOLD = 0.99   # 自匹配低于此分算坏模板
DISTINCT_MARGIN = 0.05  # 区分度矩阵: 自身与次高的最小差值
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"


# ---------------------------------------------------------------- 数据结构
@dataclass
class Crop:
    """一条裁剪定义: 参考坐标 + 中文名。"""
    x: int
    y: int
    w: int
    h: int
    label: str


# ---------------------------------------------------------------- 源截图
def latest_shot() -> Path:
    """shots/ 里最新的 snap_*.png，没有则报错。"""
    files = sorted(SHOTS_DIR.glob("snap_*.png"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit("shots/ 里没有 snap_*.png，先跑: uv run python main.py snap")
    return files[-1]


def load_source(explicit: Path | None = None) -> tuple[Image.Image, Path]:
    """加载源截图: 显式路径优先, 否则自动取最新。"""
    path = explicit if explicit and explicit.exists() else latest_shot()
    img = Image.open(path)
    print(f"源截图: {path.name} ({img.size[0]}x{img.size[1]})")
    return img, path


# ---------------------------------------------------------------- 裁剪
def scale_crops(crops: dict[str, Crop], ref_size: tuple[int, int],
                img_size: tuple[int, int]) -> dict[str, Crop]:
    """参考尺寸下的坐标表 -> 实际截图尺寸。尺寸一致时原样返回。

    不能按整图等比缩：顶部 77px 标题栏是固定像素、不跟随缩放，整图等比会把 y 整体裁偏。
    共用 wb/bot.py::map_rect —— 与运行期的「基准→客户区」是**同一套几何**，
    否则标定出来的模板与 click_base 的落点会错位。

    即使只差 2px 也照样算（不再设「差别太小就跳过」的容差）：容差会让裁剪走一个口径、
    点击走另一个口径 —— 同一个尺寸两个结果，正是过去踩过的坑。
    """
    dw, dh = img_size
    if abs(dw - ref_size[0]) > 4 or abs(dh - ref_size[1]) > 4:
        print(f"!! 截图尺寸 {dw}x{dh} ≠ 参考 {ref_size[0]}x{ref_size[1]}："
              "按「标题栏固定 77px + 按客户区高等比」换算，裁完务必看蒙太奇核对")
    out: dict[str, Crop] = {}
    for name, c in crops.items():
        x, y, w, h = map_rect(c.x, c.y, c.w, c.h, ref_size, img_size)
        out[name] = Crop(x, y, w, h, c.label)
    return out


def crop_all(src: Image.Image, crops: dict[str, Crop]) -> list[tuple[str, Crop, Image.Image]]:
    """执行裁剪并落盘 templates/<name>.png，越界项跳过并告警。"""
    W, H = src.size
    TEMPLATES_DIR.mkdir(exist_ok=True)
    tiles: list[tuple[str, Crop, Image.Image]] = []
    for name, c in crops.items():
        if c.x < 0 or c.y < 0 or c.x + c.w > W or c.y + c.h > H:
            print(f"!! {name} 越界({W}x{H})，跳过")
            continue
        im = src.crop((c.x, c.y, c.x + c.w, c.y + c.h))
        im.save(TEMPLATES_DIR / f"{name}.png")
        tiles.append((name, c, im))
    return tiles


def save_csv(crops: dict[str, Crop], path: Path) -> None:
    """坐标表落盘（已换算后的坐标），可复现/微调后重裁。"""
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["name", "x", "y", "w", "h", "label"])
        for name, c in crops.items():
            wr.writerow([name, c.x, c.y, c.w, c.h, c.label])


# ---------------------------------------------------------------- 蒙太奇
def montage(tiles: list[tuple[str, Crop, Image.Image]], out: Path, cols: int = 5) -> None:
    """带中文标注的核对图（深底 + 青色文字，直观显示每张裁了什么）。"""
    try:
        font = ImageFont.truetype(FONT_PATH, 15)
    except OSError:
        font = ImageFont.load_default()
    cw = max(im.width for _, _, im in tiles) + 16
    ch = max(im.height for _, _, im in tiles) + 30
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (28, 28, 32))
    d = ImageDraw.Draw(sheet)
    for i, (name, c, im) in enumerate(tiles):
        x, y = (i % cols) * cw, (i // cols) * ch
        sheet.paste(im, (x + 8, y + 8))
        d.text((x + 8, y + 10 + im.height), f"{c.label} [{name}]",
               fill=(120, 220, 255), font=font)
    sheet.save(out)


# ---------------------------------------------------------------- 校验
def _match_one(target: np.ndarray, tpl_path: Path) -> tuple[float, int, int]:
    """单模板对目标图匹配, 返回 (score, cx, cy)。模板过大返回 (-1, 0, 0)。"""
    tpl = cv2.imread(str(tpl_path))
    if tpl is None or tpl.shape[0] > target.shape[0] or tpl.shape[1] > target.shape[1]:
        return -1.0, 0, 0
    res = cv2.matchTemplate(target, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    th, tw = tpl.shape[:2]
    return float(score), loc[0] + tw // 2, loc[1] + th // 2


def live_target() -> tuple[np.ndarray | None, str]:
    """PrintWindow 抓当前游戏窗口; 窗口不在则返回 None。"""
    rect = find_game_window(CONF.title_keyword, CONF.process_name)
    if rect is None:
        return None, "no-window"
    return grab_window(rect), "live"


def verify(tiles: list[tuple[str, Crop, Image.Image]], src_path: Path,
           target: np.ndarray | None, tag: str,
           min_score: float = WEAK_THRESHOLD) -> list[str]:
    """逐模板匹配校验, 打印分数, 返回薄弱名单。target 为 None 时回退源截图自匹配。"""
    fallback = cv2.imread(str(src_path))
    tgt, use_tag = (target, tag) if target is not None else (fallback, "src-self")
    print(f"--- 校验 [{use_tag}] (阈值 {min_score}) ---")
    weak: list[str] = []
    for name, c, _im in tiles:
        score, cx, cy = _match_one(tgt, TEMPLATES_DIR / f"{name}.png")
        ok = score >= min_score
        if not ok:
            weak.append(name)
        print(f"[{'ok  ' if ok else 'weak'}] {name:18s} score={score:.4f} "
              f"center=({cx},{cy})")
    return weak


def distinct_matrix(names: list[str], zones: dict[str, tuple[int, int, int, int]],
                    target: np.ndarray) -> bool:
    """区分度矩阵: 每个模板必须在自己 zone 得分显著最高。

    zones 为 {name: (x,y,w,h)}（实际截图坐标）。返回是否全部合格。
    防止同类元素（空间站铭牌等）共享公共图案导致模板串台。
    """
    if len(names) < 2:
        return True
    print(f"--- 区分度矩阵 ({len(names)}x{len(names)}) 边距阈值 {DISTINCT_MARGIN} ---")
    all_ok = True
    H, W = target.shape[:2]
    for i, tpl_name in enumerate(names):
        scores: list[float] = []
        for (zx, zy, zw, zh) in (zones[n] for n in names):
            pad = 60
            x0, y0 = max(0, zx - pad), max(0, zy - pad)
            x1, y1 = min(W, zx + zw + pad), min(H, zy + zh + pad)
            region = target[y0:y1, x0:x1]
            tpl = cv2.imread(str(TEMPLATES_DIR / f"{tpl_name}.png"))
            if tpl is None or region.size == 0:
                scores.append(-1.0)
                continue
            res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
            scores.append(float(res.max()))
        best_idx = max(range(len(scores)), key=lambda k: scores[k])
        own = scores[i]
        second = sorted(scores)[-2]
        margin = own - second
        ok = best_idx == i and margin >= DISTINCT_MARGIN
        all_ok &= ok
        cells = " ".join(f"{s:.3f}" for s in scores)
        print(f"[{'ok' if ok else '!!'}] {tpl_name}: 自身={own:.3f} "
              f"次高={second:.3f} 差={margin:+.3f} | {cells}")
    return all_ok


def reuse_check(reuse_names: list[str], target: np.ndarray, min_score: float = 0.95) -> None:
    """跨页复用校验: 其他页的模板在当前页面是否仍能命中。"""
    if not reuse_names or target is None:
        return
    print(f"--- 跨页复用校验 (阈值 {min_score}) ---")
    for name in reuse_names:
        score, cx, cy = _match_one(target, TEMPLATES_DIR / f"{name}.png")
        verdict = "复用OK" if score >= min_score else "需另裁"
        print(f"[{verdict}] {name}: score={score:.4f} center=({cx},{cy})")


# ---------------------------------------------------------------- 汇总输出
def run_crop(
    crops: dict[str, tuple[int, int, int, int, str]],
    *,
    tag: str = "home",
    shot: str | None = None,
    ref_size: tuple[int, int] | None = None,
    min_score: float = 0.90,
    stations: list[str] | None = None,
    reuse: list[str] | None = None,
) -> int:
    """一体化裁剪用例入口: 载图->裁剪->落盘->CSV->蒙太奇->校验->输出报告。

    tag: 产物前缀 (shots/<tag>_crops.csv / <tag>_crops_montage.png)
    shot: 校准源截图文件名 (shots/ 下), 必须显式指定（最新 snap 可能是任何页面）
    返回薄弱模板数(0=全过)。stations/reuse 传空则跳过对应校验。
    """
    import cv2  # noqa: PLC0415

    if shot is None:
        raise SystemExit("用例必须显式指定校准源 shot=（最新 snap 可能是任何页面）")
    src_img, src_path = load_source(SHOTS_DIR / shot)
    scaled = scale_crops(
        {n: Crop(*v) for n, v in crops.items()},
        ref_size or src_img.size,
        src_img.size,
    )
    tiles = crop_all(src_img, scaled)
    mpath = SHOTS_DIR / f"{tag}_crops_montage.png"
    cpath = SHOTS_DIR / f"{tag}_crops.csv"
    save_csv(scaled, cpath)
    montage(tiles, mpath)

    live, live_tag = live_target()
    assert live is not None
    same_page = live.shape[:2] == (src_img.height, src_img.width)
    weak = verify(tiles, src_path, None, "src-self", min_score=min_score)
    if live is not None:
        scores = [_match_one(live, TEMPLATES_DIR / f"{n}.png")[0] for n, _, _ in tiles]
        avg = sum(scores) / len(scores)
        note = ("同页实时验证" if any(s >= min_score for s in scores)
                else "实时画面非本校准页, 以下仅供参考")
        print(f"--- 实时画面 [{live_tag}] 平均分 {avg:.3f} ({note}) ---")
    src_np = cv2.imread(str(src_path))
    assert src_np is not None
    if stations:
        # zone 必须是**换算后**的坐标：distinct_matrix 是拿 src_np(实际尺寸) 算的，
        # 直接传原始 crops 会在「截图≠参考尺寸」时整片错位（旧代码的隐症）。
        distinct_matrix(stations,
                        {n: (scaled[n].x, scaled[n].y, scaled[n].w, scaled[n].h)
                         for n in stations}, src_np)
    if reuse:
        reuse_check(reuse, src_np, min_score=0.95)
    report(tiles, weak, mpath, cpath)
    return len(weak)


def report(tiles: list[tuple[str, Crop, Image.Image]], weak: list[str],
           montage_path: Path, csv_path: Path) -> None:
    """统一收尾: 模板数/薄弱项 + OUTPUT 行（系统识别产物的唯一机制）。"""
    print(f"模板数={len(tiles)} 薄弱={weak if weak else '无'}")
    print(f"OUTPUT={montage_path.resolve()}")
    print(f"OUTPUT={csv_path.resolve()}")
    for name, _, _ in tiles:
        p = TEMPLATES_DIR / f"{name}.png"
        if p.exists():
            print(f"OUTPUT={p.resolve()}")
