import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2
from wb import bot, kit
from wb.cfg import SHOTS_DIR
from tools.cases import sweep_stage as sw

r = bot.find_game_window("雷霆战机", "")
print("窗口", r.w, r.h)
bot._ensure_foreground(r)
sc = kit.Screen(r, th=0.86, dry=False, prefix="probe_")
kit.goto_home(sc)
print("open_panel:", sw.open_panel(sc))
print("mode:", sw.detect_mode(sc))
print("tab4:", sw.select_tab4(sc))
img = sc.grab()
cv2.imwrite(str(SHOTS_DIR / "_probe_panel.png"), img)
print("sweep_btn:", sc.find("sweep_btn", sw.SWEEP_TH))
print("sweep_close:", sc.find("sweep_close", 0.93))
for t in ("sweep_double", "sweep_done", "stamina_entry"):
    print(t, sc.find(t))
