import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2, numpy as np
from wb import bot, kit
from wb.cfg import SHOTS_DIR

def probe(path, label):
    img = cv2.imread(str(SHOTS_DIR / path))
    H, W = img.shape[:2]
    # 用 stamina_entry 模板定位（按帧宽缩放到模板尺度）
    tpl = cv2.imread(str(Path("templates") / "stamina_entry.png"))
    th, tw = tpl.shape[:2]
    best = None
    for s in (W / 845.0, W / 812.0, W / 814.0):
        r = cv2.resize(img, (int(W / s), int(H / s)), interpolation=cv2.INTER_AREA)
        if r.shape[0] < th or r.shape[1] < tw:
            continue
        res = cv2.matchTemplate(r, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, ml = cv2.minMaxLoc(res)
        if best is None or mx > best[0]:
            best = (mx, ml, s)
    sc_, (lx, ly), s = best
    cx, cy = (lx + tw / 2) * s, (ly + th / 2) * s
    x0, y0 = int(cx + 45 * W / 845), int(cy - 40 * H / 1521)
    roi = img[max(0, y0):y0 + int(55 * H / 1521), x0:x0 + int(175 * W / 845)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    yellow = ((hh >= 15) & (hh <= 40) & (ss > 120) & (vv > 150)).mean()
    print(f"[{label}] 帧{W}x{H} entry分{sc_:.3f} 中心({cx:.0f},{cy:.0f}) ROI({x0},{y0}) 黄占比={yellow:.2%}")

probe("_stam_home.png", "今日 292/120(超)")
probe("snap_20261012_home845.png", "昨日 15/120(正常)")
