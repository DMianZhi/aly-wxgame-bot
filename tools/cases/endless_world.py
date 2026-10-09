#!/usr/bin/env python
"""用例: 无尽模式-世界竞赛（默认 6 次/日）。

链路
  1) 限时小组赛（常显，可能不存在）：hs_group_done→跳过；hs_group→点→立即参加→关X
  2) 首页 → 无尽模式 → 世界竞赛 → 参赛💎20 → 选加成<700 机友 → 出击
  3) 战前准备：买「炽焰冲击/烈火/灰烬」各 3（道具名锚点 + 同行绿键检测定位价格键）
     → 闪击→（道具不足时弹确认框）→确认→进局；
     闪击次数用尽时游戏只闪一条「世界竞赛已无闪击次数，请选择单次匹配」→ 自动改用「匹配」
  4) 局内轮询：opp_dead(锁存) / 得分≥400万(复核两次) → 拖战机到顶部收尾；
     **超时不拖顶**（实测拖顶并不加速死亡；分数没到 400 万就拖＝提前送死白送一局）
  5) 结算：本次得分页「继续」→ 战绩页（挑战胜利/失败）「返回」→ 回到世界竞赛页 → 下一轮

注意：
  - 「闪击」是**有次数上限**的（据用户确认**每天 0 点重置**），次数用尽后点闪击只会闪一条
    「世界竞赛已无闪击次数，请选择单次匹配」（见 do_flash 注释）→ 退路是点「匹配」。
  - 结算页/战绩页的按钮是「继续」和「返回」，**不是** claim_btn（claim_btn 属于奖励中心）——
    之前用 claim_btn 定位，这两页会一路空转到超时。
  - 时间一律走 kit.now() / kit.nap()，**本模块不许 import time**：离线自检把 kit.time 换成
    带虚拟时钟的替身，直接 import time 会绕过它 → 自检里真等（局内上限 210s 就是痛点）。

用法
  uv run python tools/cases/endless_world.py [--times 6] [--allow-capped] [--dry] [--no-back]

已知待办
  - 局内得分读数已可用（wb/bscore.py + templates/bdigits，战内青蓝粗体单独一套模板）:
    现有源帧只覆盖 {0,1,2,3,4,6,9}, 缺 {5,7,8} → score_ge_4m 走保守偏置（证据不足一律判「未达」）。
    补齐要再截一帧「得分里含 5/7/8」且**特效轻**（开局/结算）的战内帧，别拿局中光效帧凑数
    （实测局中帧切出的 4↔7 互为 0.87，会把 4 读成 7）。
  - 拖顶未必能快速结束战斗：2026-10-08 实跑中拖顶两次后战局仍持续 4 分钟以上（最后裸胜）。
    下次实跑要观察：是拖顶本身无效，还是对手/结算面板的关系。
  - prep_buy_* 旧模板名与实物错位（prep_buy_ash 实为祝福），本用例改用锚点同行定位
  - pick_mate 里「读不出字形的行」也算候选（沿袭旧语义：旧版 `sc is not None` 对空 dict 恒真
    → 那条护栏等于没有）。要改成「必须有读数才候选」得先拿真帧验证，别顺手改。

2026-10-08 实跑教训（已修，别改回去）
  - SCORE_GE_4M 曾在一帧约 300 万时误判为真 → 提前拖顶。现在**必须连续两次读数都判真**
    才允许拖顶（得分单调递增，真到 400 万不会再掉回去；闪效只能骗一次）。
    代价不对称：多等一次约 10s，误拖一次约等于送掉一局。

战前准备列表的两个坑（都踩过，别再犯）
  1) 道具列表被底部「本周超频装备」面板压住：初始只能看到 祝福/炽焰冲击/烈火/圣光，
     灰烬(y≈1035) 半掩在面板上沿之下。
  2) 该列表是 canvas 自绘，**pyautogui.scroll 完全无效**（实测滚 5 格行位纹丝不动），
     必须用拖拽滑动（见 scroll_list）。
  3) 道具模板裁的是「图标」，其垂直中心与同行价格键并不严格对齐
     （实测 炽焰冲击 -6px / 烈火 +31px / 灰烬 +1px），所以点击前要用绿键检测
     重新定位价格键中心（见 find_buy_btn），不要直接拿锚点 y 去点。
  4) 同排的绿色价格键长得一模一样，prep_buy_* / prep_buy_btn 这类「按钮模板」
     命中分数极高但**分不淸是哪一排**（实测同一个模板在 455/794/920 三处都 >0.98），
     拿它定位就是静默指错位置 → 必须靠道具名锚点锁行。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402

from wb import bscore                        # noqa: E402
from wb import bot as _bot                   # noqa: E402
from wb import digits                        # noqa: E402
from wb import kit                           # noqa: E402
from wb.cfg import SHOTS_DIR                 # noqa: E402
from wb.kit import log                       # noqa: E402

# ---------------------------------------------------------------- 阈值

TH = 0.86            # 通用阈值（sc 默认）
TH_KEY = 0.90        # 绝大多数按键/页签/入口（实测命中 0.97~1.00，次高均 <0.60）
TH_LOOSE = 0.88      # 低对比元素：关闭 X(grp_x) / 标题牌(wc_title, fdlg_title)
TH_JOIN = 0.92       # 「参赛💎20」（同页有相似键，要抬阈值）
TH_DEAD = 0.92       # 局内「对手已击败」角标

# ---------------------------------------------------------------- 常量

# 下面这些当年都在 812x1518 实帧上量 → 先归一到基准（bot.client_to_ref），
# 运行时由 kit.Screen 统一换算到当时的窗口。否则窗口一改小（实测见过 601）整列都读偏。
ROWS = tuple(_bot.client_to_ref(0, y, 812, 1518)[1] for y in (432, 598, 764, 930, 1095))
BUY_X = _bot.client_to_ref(702, 0, 812, 1518)[0]
BUY_COL = tuple(_bot.client_to_ref(x, 0, 812, 1518)[0] for x in (615, 800))
PLANE_FROM = _bot.client_to_ref(406, 1180, 812, 1518)   # 战机 ≈ 底边居中
PLANE_TO = _bot.client_to_ref(406, 225, 812, 1518)      # 拖到屏幕上部
ROW_X0, ROW_X1, ROW_HALF = 60, 740, 70                  # 选机友行条带（**基准口径**）
BUY_ANCHORS = (                              # (锚点模板, 说明, 需求数, 阈值)
    ('prep_it_flame', '炽焰冲击💎20', 3, 0.90),
    ('prep_it_fire', '烈火💰200', 3, 0.90),
    # 灰烬用「整行」模板当锚点：prep_it_ash(图标) 本身质量差——
    # 实测已滚动帧只 0.885、未滚动帧完全不命中；prep_row_ash 已滚动 0.987 / 未滚动 0.777，
    # 阈值 0.90 刚好把「滚到能看到」和「被底部面板压住」分开。
    ('prep_row_ash', '灰烬💰800', 3, 0.90),
)
BATTLE_MAX = 210.0                           # 局内最长等待秒数（兜底：正常由得分≥400万/对手已击败触发收尾）
SCORE_POLL = 10.0                            # 得分轮询间隔（逐格读数比模板匹配贵，没必要每秒读）
TOAST_BRIGHT = 150                           # 瞬闪提示探测：相对背景的亮度增量阈值
TOAST_ZONE = (180, 1340)                     # 只在中间区找瞬闪提示：上方计时器、下方按键都会闪


# ---------------------------------------------------------------- 页面导航

def is_home(sc: kit.Screen) -> bool:
    """首页判定：只用 stage_btn（nav_home 在无尽/世界竞赛等子页也命中）。"""
    return sc.find("stage_btn", TH_KEY) is not None


def to_home(sc: kit.Screen, tries: int = 5) -> bool:
    """尽力回首页：点底部导航的「首页」图标。

    ⚠ 这里**没有**直接用 kit.goto_home（它点 ral_back 通用返回键）：实测在世界竞赛页
    nav_home 0.975 / ral_back 只有 0.867（勉强过 0.86 线）、结算页 ral_back 0.000。
    endless 途经的页面都带底部导航栏 → 用 nav_home 才稳。
    若日后实跑确认 ral_back 在这些页也稳，再考虑并回 kit、少一处例外。
    """
    for i in range(tries):
        if is_home(sc):
            log("已在首页" if i == 0 else "已回首页")
            return True
        c = sc.find("nav_home", TH_KEY)
        if c is not None:
            sc.click(c, f"首页(第{i + 1}次)")
            kit.nap(1.8)
        else:
            kit.nap(1.2)
    return is_home(sc)


# ---------------------------------------------------------------- 1) 限时小组赛

def activate_group(sc: kit.Screen) -> str:
    """限时小组赛（常显，可能不存在）。返回 done/absent/ok/fail。"""
    to_home(sc)                          # 必须先在首页，否则模板判定无意义
    if sc.find("hs_group_done", TH_KEY):
        log("限时小组赛: 已参加 → 跳过")
        return "done"
    if not sc.find("hs_group", TH_KEY):
        log("限时小组赛: 本次活动不存在 → 跳过")
        return "absent"
    log("限时小组赛: 未参加 → 激活")
    sc.tap("hs_group", th=TH_KEY, wait=2.6, label="限时小组赛")
    if not sc.tap("grp_join", th=TH_KEY, wait=2.8, label="立即参加"):
        return "fail"
    sc.shot("grp_join")
    sc.tap("grp_x", th=TH_LOOSE, wait=2.2, label="关闭弹层")
    to_home(sc)
    return "ok"


# ---------------------------------------------------------------- 2) 进世界竞赛

def enter_arena(sc: kit.Screen, allow_capped: bool) -> bool | str:
    """进世界竞赛页并点「参赛💎20」→ 选择机友页。返回 True / False / "capped"。"""
    # 上一轮结算后「返回」会停在世界竞赛页 → 直接用，省一轮绕首页的导航
    if not sc.find("wc_title", TH_LOOSE):
        to_home(sc)
        if not sc.find("wc_title", TH_LOOSE):        # 不在世界竞赛页才导航（重试友好）
            if not sc.tap("endless_btn", th=TH_KEY, wait=2.6, label="无尽模式"):
                return False
            if not sc.tap("endless_wc_btn", th=TH_KEY, wait=2.6, label="世界竞赛"):
                return False
    for _ in range(3):                               # 参赛→选择机友页，点击可能被吞
        if not sc.tap("wc_join20", th=TH_JOIN, wait=3.0, label="参赛💎20"):
            return False
        if sc.find("cap_go", TH_KEY):                # 「挑战币已达上限」模态框
            log("⚠ 今日挑战币已达上限（本次挑战不获得挑战币）")
            if not allow_capped:
                log("  放弃本轮（省钱）→ 点取消；如需验证脚本加 --allow-capped")
                sc.tap("cap_cancel", th=TH_KEY, wait=2.2, label="取消")
                return "capped"
            sc.tap("cap_go", th=TH_KEY, wait=3.0, label="继续(允许无挑战币)")
        if sc.find("sel_go", TH_KEY) or sc.find("prep_title", TH_KEY):
            return True
        log("  未进入选择机友页 → 重试")
    return False


# ---------------------------------------------------------------- 3) 选机友（加成<700）

def row_strip(sc: kit.Screen, y_base: int):
    """选机友页某一行的像素条带（**基准口径**：x/y 走同一套换算）。

    旧版是「客户区行 + 基准 x」双口径：读数字（digits 只吃客户区行号）与取条带用两套行号，
    传参时很容易混（窗口一改小就整列读偏）。统一到基准后，行号转换只剩 _bot.ref_to_client 一处。
    """
    return sc.roi(ROW_X0, y_base - ROW_HALF, ROW_X1 - ROW_X0, ROW_HALF * 2)


def pick_mate(sc: kit.Screen) -> bool:
    """选一个加成<700 的机友（读「战力」首位≥7 判加成≥700）→ 点行 → 出击。"""
    f = sc.grab()
    if not sc.find("sel_go", TH_KEY):
        return False
    target = None
    for i, y_base in enumerate(ROWS):
        y_c = _bot.ref_to_client(0, y_base, sc.w, sc.h)[1]   # digits 只吃客户区行号
        ge4, _scores = digits.first_digit_ge(f, y_c)         # 首位≥7 ⇔ 加成≥700
        log(f"  行{i + 1} 基准y={y_base} 客户区y={y_c} 首位≥7={ge4} "
            f"读数={digits.read_row(f, y_c)}")
        # 注: 不校验 _scores 非空（沿袭旧语义，见文件头待办）—— 读不出字形的行也算候选
        if not ge4 and target is None:
            target = y_base
    if target is None:
        log("  没有加成<700 的机友 → 用最后一行")
        target = ROWS[-1]
    row0 = row_strip(sc, target).astype("int16")
    for x in (400, 300, 600, 480):
        sc.click_base(x, target, f"选机友行 基准y={target}")
        kit.nap(1.5)
        d = float(np.abs(row_strip(sc, target).astype("int16") - row0).mean())
        log(f"    行区变化={d:.1f}")
        if d > 3 or sc.dry:
            break
    return sc.tap("sel_go", th=TH_KEY, wait=3.2, label="出击")


# ---------------------------------------------------------------- 4) 买道具 + 闪击

def scroll_list(sc: kit.Screen, dy: int = 300) -> None:
    """战前准备的道具列表是 canvas 自绘：滚轮无效，只能拖拽滑动。

    起点取 x=300（道具名/描述列，不是价格键列），万一被判成点按也不会买到东西。
    拖拽走 sc.drag_base（用例里不直接 import pyautogui，否则离线自检会真动鼠标）。
    """
    if sc.dry:
        kit.nap(0.4)
        return
    sc.drag_base(300, 820, 300, 820 - dy, steps=12, pre=0.12)
    kit.nap(1.2)


def find_buy_btn(sc: kit.Screen, row_y: int, tol: int = 80):
    """价格列里的绿色价格键，取中心 y 最接近 row_y 的那个（返回**客户区** y 或 None）。

    道具模板裁的是图标，垂直中心和价格键不严格对齐（见文件头注释），
    直接拿锚点 y 去点会踩到按钮边缘甚至面板上。
    """
    f = sc.grab()
    bx0, _, bw, _ = _bot.ref_rect_to_client(BUY_COL[0], 0, BUY_COL[1] - BUY_COL[0], 1,
                                            sc.w, sc.h)
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (45, 80, 80), (85, 255, 255))[:, bx0:bx0 + bw]
    rows = mask.sum(axis=1)
    runs, st = [], None
    for y, v in enumerate(rows):
        if v > 30 and st is None:
            st = y
        elif v <= 30 and st is not None:
            if y - st > 25:
                runs.append((st + y) // 2)
            st = None
    if not runs:
        return None
    best = min(runs, key=lambda c: abs(c - row_y))
    return best if abs(best - row_y) <= tol else None


def buy_items(sc: kit.Screen) -> int:
    """按 BUY_ANCHORS 各买 need 件（锚点锁行 → 同行绿键定位价格键）。返回成功种数。"""
    ok = 0
    for anchor, label, need, thr in BUY_ANCHORS:
        c = None
        for _ in range(4):
            c = sc.find(anchor, thr)
            if c:
                break
            log(f"  未见 {label} → 拖拽列表上滑（滚轮对该列表无效）")
            scroll_list(sc, 300)
        if not c:
            log(f"✗ 定位不到 {label}（滑到底仍不可见）")
            continue
        log(f"  买 {label} ×{need}（锚点 y={c[1]}）")
        for k in range(need):
            by = find_buy_btn(sc, c[1]) or c[1]
            # 价格键 x 是基准常量，y 来自帧内检测（已是客户区行）→ 只换算 x
            sc.click_at(_bot.ref_to_client(BUY_X, 0, sc.w, sc.h)[0], by,
                        f"{label} 第{k + 1}次 (价格键 y={by})")
            kit.nap(1.3)
        ok += 1
    return ok


# ---------------------------------------------------------------- 瞬闪提示（瞬时浮层）探测
# 实测：闪击被拒时会闪一条「世界竞赛已无闪击次数，请选择单次匹配」，只亮 ~0.5s，
# 而且 **PrintWindow 抓不到它**（21ms/帧连拍 3s，帧间最大变化仅 50px）——
# 只有全屏合成截图（pyautogui.screenshot）能抓到。
# 做法：时间中位数当背景 → 取「变亮」的正向最大投影 → 把瞬态浮层从静止界面里剥出来。
def _burst_start(sc: kit.Screen) -> dict:
    import threading

    import pyautogui
    t = {'stop': False, 'frames': []}
    reg = (sc.rect.x, sc.rect.y, sc.rect.w, sc.rect.h)

    def _shoot():
        while not t['stop']:
            try:
                im = pyautogui.screenshot(region=reg)
                t['frames'].append(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
            except Exception:                                    # noqa: BLE001
                return

    t['th'] = threading.Thread(target=_shoot, daemon=True)
    t['th'].start()
    return t


def _burst_stop(t: dict, tag: str | None = None):
    """停止连拍。给了 tag 就分析瞬态浮层，返回 (x0,y0,x1,y1,证据图) 或 None。"""
    t['stop'] = True
    t['th'].join(timeout=4)
    fs = t['frames']
    if tag is None or len(fs) < 6:
        return None
    arr = np.stack(fs).astype(np.int16)
    # 整页跳转（点下去真的换页了）不是「瞬闪提示」，直接放过：
    # 实测点结算页「继续」后全屏都变了，不排掉就会把整个页面当成提示。
    if (np.abs(arr[-1] - arr[0]).max(axis=0) >= TOAST_BRIGHT).mean() > 0.25:
        return None
    med = np.median(arr, axis=0)
    up = np.clip(arr - med, 0, 255).max(axis=0).astype(np.uint8)
    up[:TOAST_ZONE[0]] = 0                 # 排除顶部计时器/底部按键的闪烁
    up[TOAST_ZONE[1]:] = 0
    mask = up >= TOAST_BRIGHT
    ys = np.where(mask.sum(axis=1) > 25)[0]
    if not len(ys):
        return None
    y0, y1 = int(ys.min()), int(ys.max())
    xs = np.where(mask[y0:y1 + 1].sum(axis=0) > 0)[0]
    x0, x1 = int(xs.min()), int(xs.max())
    if (x1 - x0) < 80 or not 12 <= (y1 - y0) <= 200:   # 太窄/太矮→闪烁；太高→整页变化
        return None
    pad = 10
    crop = up[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    path = SHOTS_DIR / f'{tag}_toast_{kit.time.strftime("%H%M%S")}.png'
    cv2.imwrite(str(path), cv2.resize(crop, None, fx=2.2, fy=2.4,
                                      interpolation=cv2.INTER_CUBIC))
    return x0, y0, x1, y1, path


def _left_prep(sc: kit.Screen) -> bool:
    """是否已走出「战前准备 → 闪击面板 → 道具不足弹框」这串页面（= 进局了）。

    实跑实测的页面链（2026-10-09，证据 shots/_endless_r2_prep.png 与 _endless_fdlg.png）:
        战前准备页（prep_title / prep_flash）--点「闪击」--> 闪击面板（fdlg_go）
        --点面板大「闪击」--> 「部分战斗道具数量不足」弹框（fdlg_cnt_title）
        --点绿「确认」--> 进局
    任何一环的锚点还在，就说明没进局；局内右下技能键 battle_skill 在屏则直接判进局。
    """
    if sc.find('battle_skill', 0.90):                 # 局内锚点（wb/battle.py 同款）
        return True
    return not (sc.find('fdlg_cnt_title', TH_KEY)     # 道具不足弹框
                or sc.find('prep_flash', TH_KEY)      # 战前准备页·「闪击」按钮
                or sc.find('prep_title', TH_KEY)      # 战前准备页·标题
                or sc.find('fdlg_go', TH_KEY))        # 闪击面板·大「闪击」按钮


def do_flash(sc: kit.Screen) -> str:
    """点「闪击」进局。

    返回 'ok'（已进局）/ 'rejected'（游戏侧无闪击次数，抓到瞬闪提示）
        / 'no_btn'（没有闪击按钮）/ 'no_effect'（点了没反应）。

    ⚠ 2026-10-09 实跑暴露的真 bug（用例自带，非迁移引入）:
      ① 「部分战斗道具数量不足，无法生效 是否继续闪击?」确认框是**点下闪击面板上
         那颗大「闪击」按钮之后**才弹的。旧写法把它放在「第一下点击之前」检查 →
         永远查不到 → 弹框无人处理 → 用例以为「已进局」，对着准备页空转满 210s
         （日志里连续「得分=读不出」就是它）。
      ② `fdlg_title` 截的是**页面标题**「闪击·世界竞赛」而非对话框标题 → 在战前准备页
         恒命中(0.995)，把「有没有弹框」误判成「有」，连带「点了没反应/瞬闪提示」分支
         被跳过（当时日志里一句提示都没打，才这么难查）。现在不再用它。
      ③ 进局不再「点完就当成功」，而是看 `_left_prep()`（局内锚点或三个准备页锚点全消失）。
    """
    if not sc.find('prep_flash', TH_KEY):
        log('✗ 战前准备页没有「闪击」按钮')
        return 'no_btn'
    burst = _burst_start(sc)
    kit.nap(0.35)
    # 状态机（每步后复查是否已进局）:
    #   战前准备页 → 点「闪击」；闪击面板 → 点大「闪击」；道具不足弹框 → 点绿「确认」
    for _ in range(6):
        if sc.find('fdlg_cnt_title', TH_KEY):
            log('  出现「部分战斗道具数量不足」确认框 → 点「确认」继续闪击')
            sc.tap('fdlg_cnt_ok', th=TH_KEY, wait=2.2, label='确认继续闪击')
        elif sc.find('prep_flash', TH_KEY):
            sc.tap('prep_flash', th=TH_KEY, wait=2.2, label='闪击(战前准备页)')
        elif sc.find('fdlg_go', TH_KEY):
            sc.tap('fdlg_go', th=TH_KEY, wait=2.5, label='闪击(闪击面板)')
        else:
            break                                     # 三个锚点都不在 → 已进局
        if _left_prep(sc):
            break
    sc.shot('fdlg')
    if _left_prep(sc):
        _burst_stop(burst)
        return 'ok'
    t = _burst_stop(burst, 'endless_flash')
    if t:
        log(f'⚠ 闪击被拒：瞬闪提示 bbox=({t[0]},{t[1]})-({t[2]},{t[3]})，证据 {t[4]}')
        log('  → 世界竞赛闪击次数已用尽（每天 0 点重置），按设定改用「匹配」')
        return 'ok' if do_match(sc) else 'rejected'
    log('⚠ 点了闪击但页面无变化、也没抓到提示（窗口可能被遮挡？）')
    return 'no_effect'


def do_match(sc: kit.Screen, timeout: float = 55.0) -> bool:
    """闪击次数用尽时的退路：点「匹配」。

    实测：点匹配 → 战前准备页上盖一层「匹配中 SEARCHING + 23s 倒计时」（约 30s）
    → 找到对手 → 进「资源加载中」→ 开打。匹配成不成都不弹窗，
    唯一可辨的信号是「是否离开战前准备页」。
    """
    if not sc.find('prep_match', TH_KEY):
        log('✗ 战前准备页没有「匹配」按钮')
        return False
    sc.tap('prep_match', th=TH_KEY, wait=3.0, label='匹配')
    sc.shot('match')
    t0 = kit.now()
    while kit.now() - t0 < timeout:
        if not sc.find('prep_title', TH_KEY):
            log(f'  [{kit.now() - t0:.0f}s] 已离开战前准备页 → 进局')
            return True
        kit.nap(2.0)
    log(f'  ✗ {timeout:.0f}s 仍在战前准备页（匹配没找到对手？）')
    return False


# ---------------------------------------------------------------- 5) 局内

def drag_to_top(sc: kit.Screen, hold: float = 9.0, rounds: int = 2) -> None:
    """按住战机拖到屏幕顶部并保持。（走 sc.drag_base，见其注释）

    ⚠ 2026-10-09 实跑实测：拖顶**并不加速死亡**（拖完战局又打了 3 分多钟，>210s 超时才放弃）。
    所以只在「明确 ≥400万」或「对手已击败」时调用；**不再当超时兜底**。
    """
    for i in range(rounds):
        log(f'拖战机到顶部加速死亡({i + 1}/{rounds})')
        if sc.dry:
            kit.nap(0.4)
            continue
        sc.drag_base(*PLANE_FROM, *PLANE_TO, hold=hold, duration=0.7)
        if sc.find('claim_btn', TH_KEY):
            return


def battle_watch(sc: kit.Screen) -> str:
    """局内轮询：对手已击败 / 得分≥400万(需复核) / 超时 → 收尾。返回结束原因。

    ⚠ 2026-10-09 实跑改掉两处（都是「没到 400 万就往顶部拖」这个病）:
      ① `score_ge_4m` 假阳性 → 真实 166 万时就判「已达」→ 提前拖顶。判分已收紧（见 wb/bscore.py），
         这里再加一道：**每一次「判到 400万」的帧都留证**（_endless_ge4m.png），下次再假阳性可离线查。
      ② 超时兜底**不再拖顶**：实测拖顶并不加速死亡（拖完后战局又打了 3 分多钟），
         也就是说「超时拖一下」没有任何收益，却带来「分数没到就提前送死」的风险。
         现在只有**明确 ≥400万**才拖顶；超时只记日志，交给 settle 继续等战局自然结束。
    """
    if sc.dry:
        log('[dry] 局内轮询只出计划（不取帧、不判分、不空转）')
        return 'dry'
    t0 = kit.now()
    hint = False
    drag = False                                     # 只有「明确 ≥400万」或「对手已击败」才置 True
    na_shot = False                                  # 本局是否已留证「读不出」帧（每局只存一张）
    last = 0.0
    prev_hit = False
    while kit.now() - t0 < BATTLE_MAX:
        f = sc.grab()
        if not hint and sc.find('opp_dead', TH_DEAD):
            hint = True
            log(f'[{kit.now() - t0:.0f}s] 对手已击败 ✓ → 收尾')
        el = kit.now() - t0
        if el - last >= SCORE_POLL:
            last = el
            score = bscore.read_score(f)
            hit = bscore.score_ge_4m(f)
            # 得分单调递增 → 真到 400 万就不会再掉回去；闪效误判只能骗一次。
            # 代价不对称：多等一次 ≈10s，误拖一次 ≈ 送掉一局。（2026-10-08 实跑教训）
            confirm = hit and prev_hit
            if score is None and not na_shot:
                na_shot = True
                # 留证「读不出」的真帧：库里缺 {5,7,8} 三个字形 → 得分含这三个字时必读不出。
                # 攒到一帧特效轻的就能拿去补齐模板（不要用特效重的帧建库，见 wb/bscore.py ③）。
                sc.shot('score_NA')
            if hit and not confirm:
                log('⚠ 首次判 ≥400万，等下一次读数复核（防闪效误判）')
                sc.shot('ge4m')                      # 留证：判到 400 万的帧（含误判）都存下来
            prev_hit = hit
            log(f'[{el:.0f}s] 得分={score if score is not None else "读不出"} '
                f'≥400万={hit}{"（已复核）" if confirm else ""} 对手已击败={hint}')
            if confirm:
                log('得分连续两次 ≥400万（已复核）→ 拖顶收尾（保住胜势）')
                drag = True
                break
        if sc.find('claim_btn', TH_KEY):
            log(f'[{kit.now() - t0:.0f}s] 已结束（结算弹层）')
            return 'settled'
        if hint:
            drag = True
            break
        kit.nap(1.0)
    else:
        log(f'[{BATTLE_MAX:.0f}s] 超时（得分没到 400 万）→ 不拖顶（拖顶＝提前送死风险），'
            '交给结算继续等战局自然结束')
    sc.shot('battle_end')
    if not drag:                                     # 超时兜底不拖顶（见函数 docstring ②）
        return 'timeout'
    drag_to_top(sc)
    return 'finish'


def settle(sc: kit.Screen, timeout: float = 180.0) -> tuple[bool, bool | None]:
    """结算：本次得分页「继续」→ 战绩页（挑战胜利/失败）「返回」→ 世界竞赛页。

    返回 (是否结算完成, 是否胜利 | None)。
    2026-10-08 实跑确认：结算页按钮是「继续」、战绩页是「返回」，
    用 claim_btn（奖励中心那个）定位会两页都空转到超时。
    必须有胜负标题才算战绩页：wc_res_back（返回按钮）的素材被多页复用
    （实测在世界竞赛页/无尽页/战前准备页都能 0.98+ 命中），单凭它判页会误入。
    """
    t0 = kit.now()
    win = None
    while kit.now() - t0 < timeout:
        w = sc.find('wc_res_win', TH_KEY)
        lose = sc.find('wc_res_lose', TH_KEY)
        if (w or lose) and sc.find('wc_res_back', TH_KEY):
            win = w is not None
            log(f'战绩页：{"挑战胜利 ★" if win else "挑战失败"}')
            sc.shot('result')
            sc.tap('wc_res_back', th=TH_KEY, wait=3.0, label='返回')
            return True, win
        if sc.find('wc_settle_go', TH_KEY):                     # 本次得分页
            sc.shot('settle')
            sc.tap('wc_settle_go', th=TH_KEY, wait=3.0, label='继续')
            continue
        if sc.find('claim_btn', TH_KEY):                        # 兼容其它结算样式
            sc.tap('claim_btn', th=TH_KEY, wait=2.2, tries=1, label='领取')
            continue
        if sc.find('wc_title', TH_LOOSE):                       # 已回到世界竞赛页
            return True, win
        kit.nap(1.0)
    log('✗ 等结算超时')
    return False, win


# ---------------------------------------------------------------- 单轮 / 入口

DRY_PLAN = ('无尽模式 → 世界竞赛 → 参赛💎20 → 选加成<700 的机友 → 出击 → 战前准备买'
            '炽焰冲击/烈火/灰烬 各×3（名字锚点定位同行价格键）→ 闪击(次数用尽则改「匹配」)'
            '→ 进局 → 得分≥400万(复核两次)才拖战机到顶部（未达/超时都不拖）'
            '→ 结算页「继续」→ 战绩页「返回」→ 回世界竞赛页')


def plan_dry(sc: kit.Screen) -> None:
    """dry 演练：只出计划、零点击。

    dry 下点击不生效 → 页面不会跳转，跨页步骤（选机友/买道具/闪击）无从规划，
    只能演练当前屏能看见的锚点。因此按项目惯例以**成功**收尾（不计失败）。
    """
    for tag, th, what in [('endless_btn', TH_KEY, '首页·「无尽模式」入口'),
                          ('wc_join20', TH_JOIN, '世界竞赛·「参赛💎20」'),
                          ('prep_flash', TH_KEY, '战前准备·「闪击」')]:
        hit = sc.find(tag, th)
        log(f'[dry] {what}: ' + (f'在屏 @({hit[0]},{hit[1]}) score={hit[2]:.3f}'
                                 if hit else '不在屏（跨页步骤，dry 下不点）'))
    log(f'[dry] 计划: {DRY_PLAN}')
    log('[dry] 局内判据/收尾分支可零消耗验证: tools/selftest/endless_world_selftest.py')


def one_round(sc: kit.Screen, idx: int, rounds: int, allow_capped: bool) -> bool:
    log(f'===== 第 {idx}/{rounds} 次无尽 =====')
    if idx == 1:
        activate_group(sc)
    st = enter_arena(sc, allow_capped)
    if st == 'capped':
        return False
    if not st:
        log('✗ 进入世界竞赛失败')
        return False
    sc.shot(f'r{idx}_sel')
    if not pick_mate(sc):
        log('✗ 选机友/出击失败')
        return False
    sc.shot(f'r{idx}_prep')
    buy_items(sc)
    st = do_flash(sc)
    if st == 'rejected':
        log('✗ 本轮无法闪击：世界竞赛闪击次数已用完（提示「请选择单次匹配」）')
        return False
    if st != 'ok':
        log(f'✗ 闪击失败: {st}')
        return False
    log('已进局 → 观察')
    sc.shot(f'r{idx}_battle')
    why = battle_watch(sc)
    log(f'局内结束原因: {why}')
    ok, win = settle(sc)
    log(f'第 {idx} 次结束: 链路{"完成" if ok else "未确认"}' +
        ('' if win is None else ('（挑战胜利）' if win else '（挑战失败）')))
    return ok


def run(sc: kit.Screen, args: kit.Args) -> bool:
    rounds = max(1, args.n_times(6))
    allow_capped = bool(args.extra.get('allow_capped'))
    if sc.dry:
        plan_dry(sc)
        return True
    done = 0
    for i in range(1, rounds + 1):
        # CaseTimeout（看门狗）必须往上抛：由 run_case 统一留证 + 收尾，别在这里吞掉
        try:
            if one_round(sc, i, rounds, allow_capped):
                done += 1
        except kit.CaseTimeout:
            raise
        except Exception as e:                                   # noqa: BLE001
            log(f'第 {i} 次异常: {type(e).__name__} {e}')
            sc.shot(f'r{i}_err')
    log(f'完成 {done}/{rounds}')
    return done == rounds


if __name__ == '__main__':
    raise SystemExit(kit.run_case(
        'endless_world', '无尽模式-世界竞赛', run,
        plan=DRY_PLAN + '（默认 6 次/日，单轮最长约 7 分钟）', prefix='endless_',
        lock_ttl=3600, th=TH, extra=('--allow-capped',), default_max=6,
        # 6 轮 ×（局内上限 210s + 导航/结算）远超 kit 默认 900s 看门狗 → 放宽到 100 分钟
        default_timeout=6000.0,
    ))
