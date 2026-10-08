"""无尽模式-世界竞赛（默认 6 次）。

链路
  1) 限时小组赛（常显，可能不存在）：hs_group_done→跳过；hs_group→点→立即参加→关X
  2) 首页 → 无尽模式 → 世界竞赛 → 参赛💎20 → 选加成<700 机友 → 出击
  3) 战前准备：买「炽焰冲击/烈火/灰烬」各 3（道具名锚点 + 同行绿键检测定位价格键）
     → 闪击→（道具不足时弹确认框）→确认→进局；
     闪击次数用尽时游戏只闪一条「世界竞赛已无闪击次数，请选择单次匹配」→ 自动改用「匹配」
  4) 局内轮询：opp_dead(锁存) / 得分≥400万 / 超时 → 拖战机到顶部加速死亡
  5) 结算：本次得分页「继续」→ 战绩页（挑战胜利/失败）「返回」→ 回到世界竞赛页 → 下一轮

注意：
  - 「闪击」是**有次数上限**的（据用户确认**每天 0 点重置**），次数用尽后点闪击只会闪一条
    「世界竞赛已无闪击次数，请选择单次匹配」（见 Case._burst_* 注释）→ 退路是点「匹配」。
  - 结算页/战绩页的按钮是「继续」和「返回」，**不是** claim_btn（claim_btn 属于奖励中心）——
    之前用 claim_btn 定位，这两页会一路空转到超时。

用法
  uv run python tools/cases/endless_world.py [--rounds 6] [--dry]

已知待办
  - 局内得分读数已可用（wb/bscore.py + templates/bdigits，战内青蓝粗体单独一套模板）:
    现有源帧只覆盖 {0,1,2,3,4,6,9}, 缺 {5,7,8} → score_ge_4m 走保守偏置（证据不足一律判「未达」）。
    补齐要再截一帧「得分里含 5/7/8」且**特效轻**（开局/结算）的战内帧，别拿局中光效帧凑数
    （实测局中帧切出的 4↔7 互为 0.87，会把 4 读成 7）。
  - 拖顶未必能快速结束战斗：2026-10-08 实跑中拖顶两次后战局仍持续 4 分钟以上（最后裸胜）。
    下次实跑要观察：是拖顶本身无效，还是对手/结算面板的关系。
  - prep_buy_* 旧模板名与实物错位（prep_buy_ash 实为祝福），本用例改用锚点同行定位

2026-10-08 实跑教训（已修，别改回去）
  - SCORE_GE_4M 曾在一帧约 300 万时误判为真 → 提前拖顶。现在**必须连续两次读数都判真**
    才允许拖顶（得分单调递增，真到 400 万不会再掉回去；闪效只能骗一次）。
    代价不对称：多等一次约 10s，误拖一次约等于送掉一局。

战前准备列表的两个坑（都踩过，别再犯）
  1) 道具列表被底部「本周超频装备」面板压住：初始只能看到 祝福/炽焰冲击/烈火/圣光，
     灰烬(y≈1035) 半掩在面板上沿之下。
  2) 该列表是 canvas 自绘，**pyautogui.scroll 完全无效**（实测滚 5 格行位纹丝不动），
     必须用拖拽滑动（见 Case.scroll_list）。
  3) 道具模板裁的是「图标」，其垂直中心与同行价格键并不严格对齐
     （实测 炽焰冲击 -6px / 烈火 +31px / 灰烬 +1px），所以点击前要用绿键检测
     重新定位价格键中心（见 Case.find_buy_btn），不要直接拿锚点 y 去点。
  4) 同排的绿色价格键长得一模一样，prep_buy_* / prep_buy_btn 这类「按钮模板」
     命中分数极高但**分不淸是哪一排**（实测同一个模板在 455/794/920 三处都 >0.98），
     拿它定位就是静默指错位置 → 必须靠道具名锚点锁行。
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402

from wb import bscore                        # noqa: E402
from wb import bot                           # noqa: E402
from wb import digits                        # noqa: E402
from wb.cfg import CONF, SHOTS_DIR           # noqa: E402

ROWS = (432, 598, 764, 930, 1095)            # 选择机友页 5 行中心 y
BUY_X = 702                                  # 战前准备页价格键 x（各行同列）
BUY_COL = (615, 800)                         # 价格键所在像素列区间（绿键检测用）
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


class Case:
    last_win = None
    def __init__(self, dry: bool, allow_capped: bool = False):
        self.dry = dry
        self.allow_capped = allow_capped
        self.rect = bot.find_game_window(CONF.title_keyword, CONF.process_name)
        if self.rect is None:
            print('[ERR] 找不到游戏窗口', flush=True)
            sys.exit(2)
        bot.configure_mouse(dry)
        self._focus()

    # ---------- 基础 ----------
    def _focus(self, force=False):
        """ALT 键技巧强制置前；前台被抢会让点击静默丢失。"""
        u = ctypes.windll.user32
        if not force and u.GetForegroundWindow() == self.rect.hwnd:
            return
        u.keybd_event(0x12, 0, 0, 0)
        u.ShowWindow(self.rect.hwnd, 9)
        u.SetForegroundWindow(self.rect.hwnd)
        u.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.35)

    def log(self, *a):
        print(' ', *a, flush=True)

    def find(self, tpl, th=0.88):
        return bot.find_in_game(tpl, self.rect, th)

    def grab(self):
        return bot.grab_window(self.rect)

    def snap(self, name):
        if self.dry:                       # dry = 只看计划、零副作用（不落盘）
            return
        cv2.imwrite(str(SHOTS_DIR / name), self.grab())

    def tap_xy(self, x, y, wait=1.6, label=''):
        self.log(f'点 {label} ({x},{y})')
        if not self.dry:
            self._focus()
            bot.click_xy(x, y, 3, (0.4, 0.7), self.rect, self.dry)
        time.sleep(wait)

    def tap(self, tpl, th=0.88, wait=1.6, tries=3, label=None):
        for _ in range(tries):
            c = self.find(tpl, th)
            if c:
                self.log(f'点 {label or tpl} ({c[0]},{c[1]}) s={c[2]:.3f}')
                if not self.dry:
                    self._focus()
                    bot.click_xy(c[0], c[1], 3, (0.4, 0.7), self.rect, self.dry)
                time.sleep(wait)
                return True
            time.sleep(0.6)
        self.log(f'✗ 未找到 {label or tpl}')
        return False

    def is_home(self):
        return bool(self.find('stage_btn', 0.90))

    def to_home(self, tries=5):
        for _ in range(tries):
            if self.is_home():
                self.log('已在首页')
                return True
            c = self.find('nav_home', 0.90)
            if c:
                self.tap_xy(c[0], c[1], 1.8, '首页')
            else:
                time.sleep(1.2)
        return self.is_home()

    # ---------- 1) 限时小组赛（常显） ----------
    def activate_group(self):
        self.to_home()                       # 必须先在首页，否则模板判定无意义
        if self.find('hs_group_done', 0.90):
            self.log('限时小组赛: 已参加 → 跳过')
            return 'done'
        if not self.find('hs_group', 0.90):
            self.log('限时小组赛: 本次活动不存在 → 跳过')
            return 'absent'
        self.log('限时小组赛: 未参加 → 激活')
        self.tap('hs_group', 0.90, 2.6, label='限时小组赛')
        if not self.tap('grp_join', 0.90, 2.8, label='立即参加'):
            return 'fail'
        self.snap('endless_grp_join.png')
        if self.tap('grp_x', 0.88, 2.2, label='关闭弹层'):
            pass
        self.to_home()
        return 'ok'

    # ---------- 2) 进世界竞赛 ----------
    def enter_arena(self):
        # 上一轮结算后「返回」会停在世界竞赛页 → 直接用，省一轮绕首页的导航
        if not self.find('wc_title', 0.88):
            self.to_home()
            if not self.find('wc_title', 0.88):        # 不在世界竞赛页才导航（重试友好）
                if not self.tap('endless_btn', 0.90, 2.6, label='无尽模式'):
                    return False
                if not self.tap('endless_wc_btn', 0.90, 2.6, label='世界竞赛'):
                    return False
        for i in range(3):                             # 参赛→选择机友页，点击可能被吞
            if not self.tap('wc_join20', 0.92, 3.0, label='参赛💎20'):
                return False
            if self.find('cap_go', 0.90):              # 「挑战币已达上限」模态框
                self.log('⚠ 今日挑战币已达上限（本次挑战不获得挑战币）')
                if not self.allow_capped:
                    self.log('  放弃本轮（省钱）→ 点取消；如需验证脚本加 --allow-capped')
                    self.tap('cap_cancel', 0.90, 2.2, label='取消')
                    return 'capped'
                self.tap('cap_go', 0.90, 3.0, label='继续(允许无挑战币)')
            if self.find('sel_go', 0.90) or self.find('prep_title', 0.90):
                return True
            self.log('  未进入选择机友页 → 重试')
        return False

    # ---------- 3) 选机友（加成<700） ----------
    def pick_mate(self):
        f = self.grab()
        if not self.find('sel_go', 0.90):
            return False
        target = None
        for i, yc in enumerate(ROWS):
            ge4, sc = digits.first_digit_ge(f, yc)      # 首位≥7 ⇔ 加成≥700
            self.log(f'  行{i + 1} yc={yc} 首位≥7={ge4} 读数={digits.read_row(f, yc)}')
            if not ge4 and target is None and sc is not None:
                target = yc
        if target is None:
            self.log('  没有加成<700 的机友 → 用最后一行')
            target = ROWS[-1]
        row0 = self.grab()[target - 70:target + 70, 60:740].astype('int16')
        for x in (400, 300, 600, 480):
            self.tap_xy(x, target, 1.5, f'选机友行y={target}')
            d = np.abs(self.grab()[target - 70:target + 70, 60:740].astype('int16') - row0).mean()
            self.log(f'    行区变化={d:.1f}')
            if d > 3 or self.dry:
                break
        return self.tap('sel_go', 0.90, 3.2, label='出击')

    # ---------- 4) 买道具 + 闪击 ----------
    def scroll_list(self, dy=300):
        """战前准备的道具列表是 canvas 自绘：滚轮无效，只能拖拽滑动。

        起点取 x=300（道具名/描述列，不是价格键列），万一被判成点按也不会买到东西。
        拖拽走 bot.drag_xy（用例里不直接 import pyautogui，否则离线自检会真动鼠标）。
        """
        if self.dry:
            time.sleep(0.4)
            return
        bot.drag_xy(300, 820, 300, 820 - dy, self.rect, self.dry, steps=12, pre=0.12)
        time.sleep(1.2)

    def find_buy_btn(self, row_y, tol=80):
        """价格列里的绿色价格键，取中心 y 最接近 row_y 的那个。

        道具模板裁的是图标，垂直中心和价格键不严格对齐（见文件头注释），
        直接拿锚点 y 去点会踩到按钮边缘甚至面板上。返回按钮中心 y 或 None。
        """
        f = self.grab()
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (45, 80, 80), (85, 255, 255))[:, BUY_COL[0]:BUY_COL[1]]
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

    def buy_items(self):
        ok = 0
        for anchor, label, need, thr in BUY_ANCHORS:
            c = None
            for _ in range(4):
                c = self.find(anchor, thr)
                if c:
                    break
                self.log(f'  未见 {label} → 拖拽列表上滑（滚轮对该列表无效）')
                self.scroll_list(300)
            if not c:
                self.log(f'✗ 定位不到 {label}（滑到底仍不可见）')
                continue
            self.log(f'  买 {label} ×{need}（锚点 y={c[1]}）')
            for k in range(need):
                by = self.find_buy_btn(c[1]) or c[1]
                self.tap_xy(BUY_X, by, 1.3, f'{label} 第{k + 1}次 (价格键 y={by})')
            ok += 1
        return ok

    # ---------- 瞬闪提示（瞬时浮层）探测 ----------
    # 实测：闪击被拒时会闪一条「世界竞赛已无闪击次数，请选择单次匹配」，只亮 ~0.5s，
    # 而且 **PrintWindow 抓不到它**（21ms/帧连拍 3s，帧间最大变化仅 50px）——
    # 只有全屏合成截图（pyautogui.screenshot）能抓到。
    # 做法：时间中位数当背景 → 取「变亮」的正向最大投影 → 把瞬态浮层从静止界面里剥出来。
    def _burst_start(self):
        import threading
        import pyautogui
        t = {'stop': False, 'frames': []}
        reg = (self.rect.x, self.rect.y, self.rect.w, self.rect.h)

        def _shoot():
            while not t['stop']:
                try:
                    im = pyautogui.screenshot(region=reg)
                    t['frames'].append(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
                except Exception:
                    return

        t['th'] = threading.Thread(target=_shoot, daemon=True)
        t['th'].start()
        return t

    def _burst_stop(self, t, tag=None):
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
        path = SHOTS_DIR / f'{tag}_toast_{time.strftime("%H%M%S")}.png'
        cv2.imwrite(str(path), cv2.resize(crop, None, fx=2.2, fy=2.4,
                                          interpolation=cv2.INTER_CUBIC))
        return x0, y0, x1, y1, path

    def do_flash(self):
        """点「闪击」进局。

        返回 'ok'（已进局）/ 'rejected'（游戏侧无闪击次数，抓到瞬闪提示）
            / 'no_btn'（没有闪击按钮）/ 'no_effect'（点了没反应）。
        """
        if not self.find('prep_flash', 0.90):
            self.log('✗ 战前准备页没有「闪击」按钮')
            return 'no_btn'
        burst = self._burst_start()
        time.sleep(0.35)
        self.tap('prep_flash', 0.90, 2.2, label='闪击')
        self.snap('endless_fdlg.png')
        if self.find('fdlg_cnt_title', 0.90):                      # 部分道具不足确认框
            self.log('  出现「部分战斗道具数量不足」确认框')
            self.tap('fdlg_cnt_ok', 0.90, 2.0, label='确认继续闪击')
        elif not self.find('fdlg_title', 0.88):
            t = self._burst_stop(burst, 'endless_flash')
            if t:
                self.log(f'⚠ 闪击被拒：瞬闪提示 bbox=({t[0]},{t[1]})-({t[2]},{t[3]})，证据 {t[4]}')
                self.log('  → 世界竞赛闪击次数已用尽（每天 0 点重置），按设定改用「匹配」')
                return 'ok' if self.do_match() else 'rejected'
            if self.find('prep_title', 0.88):
                self.log('⚠ 点了闪击但页面无变化、也没抓到提示（窗口可能被遮挡）')
                return 'no_effect'
        self._burst_stop(burst)
        return 'ok' if self.tap('fdlg_go', 0.90, 3.0, label='闪击(对话框)') else 'no_effect'

    def do_match(self, timeout=55.0):
        """闪击次数用尽时的退路：点「匹配」。

        实测：点匹配 → 战前准备页上盖一层「匹配中 SEARCHING + 23s 倒计时」（约 30s）
        → 找到对手 → 进「资源加载中」→ 开打。匹配成不成都不弹窗，
        唯一可辨的信号是「是否离开战前准备页」。
        """
        if not self.find('prep_match', 0.90):
            self.log('✗ 战前准备页没有「匹配」按钮')
            return False
        self.tap('prep_match', 0.90, 3.0, label='匹配')
        self.snap('endless_match.png')
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not self.find('prep_title', 0.90):
                self.log(f'  [{time.time() - t0:.0f}s] 已离开战前准备页 → 进局')
                return True
            time.sleep(2.0)
        self.log(f'  ✗ {timeout:.0f}s 仍在战前准备页（匹配没找到对手？）')
        return False

    # ---------- 5) 局内 ----------
    def drag_to_top(self, hold=9.0, rounds=2):
        """按住战机拖到屏幕顶部并保持 → 加速死亡。（走 bot.drag_xy, 见其注释）"""
        for i in range(rounds):
            self.log(f'拖战机到顶部加速死亡({i + 1}/{rounds})')
            if self.dry:
                time.sleep(0.4)
                continue
            bot.drag_xy(406, 1180, 406, 225, self.rect, self.dry, hold=hold, duration=0.7)
            if self.find('claim_btn', 0.90):
                return

    def battle_watch(self):
        t0 = time.time()
        hint = False
        last = 0.0
        prev_hit = False
        while time.time() - t0 < BATTLE_MAX:
            f = self.grab()
            if not hint and self.find('opp_dead', 0.92):
                hint = True
                self.log(f'[{time.time() - t0:.0f}s] 对手已击败 ✓ → 收尾')
            if time.time() - t0 - last >= SCORE_POLL:
                last = time.time() - t0
                sc = bscore.read_score(f)
                hit = bscore.score_ge_4m(f)
                # 得分单调递增 → 真到 400 万就不会再掉回去；闪效误判只能骗一次。
                # 代价不对称：多等一次 ≈10s，误拖一次 ≈ 送掉一局。（2026-10-08 实跑教训）
                confirm = hit and prev_hit
                if hit and not confirm:
                    self.log('⚠ 首次判 ≥400万，等下一次读数复核（防闪效误判）')
                prev_hit = hit
                self.log(f'[{last:.0f}s] 得分={sc if sc is not None else "读不出"} '
                         f'≥400万={hit}{"（已复核）" if confirm else ""} 对手已击败={hint}')
                if confirm:
                    self.log('得分连续两次 ≥400万 → 拖顶收尾（保住胜势）')
                    break
            if self.find('claim_btn', 0.90):
                self.log(f'[{time.time() - t0:.0f}s] 已结束（结算弹层）')
                return 'settled'
            if hint:
                break
            time.sleep(1.0)
        else:
            self.log(f'[{BATTLE_MAX:.0f}s] 超时（得分没到 400 万）→ 强制收尾')
        self.snap('endless_battle_end.png')
        self.drag_to_top()
        return 'finish'

    def settle(self, timeout=180.0):
        """结算：本次得分页「继续」→ 战绩页（挑战胜利/失败）「返回」→ 世界竞赛页。

        2026-10-08 实跑确认：结算页按钮是「继续」、战绩页是「返回」，
        用 claim_btn（奖励中心那个）定位会两页都空转到超时。
        """
        t0 = time.time()
        self.last_win = None
        while time.time() - t0 < timeout:
            win = self.find('wc_res_win', 0.90)
            lose = self.find('wc_res_lose', 0.90)
            # 必须有胜负标题才算战绩页：wc_res_back（返回按钮）的素材被多页复用
            # （实测在世界竞赛页/无尽页/战前准备页都能 0.98+ 命中），单凭它判页会误入。
            if (win or lose) and self.find('wc_res_back', 0.90):
                self.last_win = win is not None
                self.log(f'战绩页：{"挑战胜利 ★" if win else ("挑战失败" if lose else "胜负未识别")}')
                self.snap('endless_result.png')
                self.tap('wc_res_back', 0.90, 3.0, label='返回')
                return True
            if self.find('wc_settle_go', 0.90):                     # 本次得分页
                self.snap('endless_settle.png')
                self.tap('wc_settle_go', 0.90, 3.0, label='继续')
                continue
            if self.find('claim_btn', 0.90):                        # 兼容其它结算样式
                self.tap('claim_btn', 0.90, 2.2, tries=1, label='领取')
                continue
            if self.find('wc_title', 0.88):                         # 已回到世界竞赛页
                return True
            time.sleep(1.0)
        self.log('✗ 等结算超时')
        return False

    # ---------- 单轮 ----------
    DRY_PLAN = ('无尽模式 → 世界竞赛 → 参赛💎20 → 选加成<700 的机友 → 出击 → 战前准备买'
                '炽焰冲击/烈火/灰烬 各×3（名字锚点定位同行价格键）→ 闪击(次数用尽则改「匹配」)'
                '→ 进局 → 得分≥400万(复核两次)或超时 → 拖战机到顶部 → 结算页「继续」'
                '→ 战绩页「返回」→ 回世界竞赛页')

    def plan_dry(self):
        """dry 演练：只出计划、零点击。

        dry 下点击不生效 → 页面不会跳转，跨页步骤（选机友/买道具/闪击）无从规划，
        只能演练当前屏能看见的锚点。因此按项目惯例以**成功**收尾（不计失败）。
        """
        for tag, th, what in [('endless_btn', 0.90, '首页·「无尽模式」入口'),
                              ('wc_join20', 0.92, '世界竞赛·「参赛💎20」'),
                              ('prep_flash', 0.90, '战前准备·「闪击」')]:
            hit = self.find(tag, th)
            self.log(f'[dry] {what}: ' + (f'在屏 @({hit[0]},{hit[1]}) score={hit[2]:.3f}'
                                          if hit else '不在屏（跨页步骤，dry 下不点）'))
        self.log(f'[dry] 计划: {self.DRY_PLAN}')
        self.log('[dry] 局内判据/收尾分支可零消耗验证: tools/selftest/endless_world_selftest.py')

    def one_round(self, idx, rounds):
        print(f'===== 第 {idx}/{rounds} 次无尽 =====', flush=True)
        if self.dry:
            self.plan_dry()
            return True
        if idx == 1:
            self.activate_group()
        st = self.enter_arena()
        if st == 'capped':
            return False
        if not st:
            self.log('✗ 进入世界竞赛失败')
            return False
        self.snap(f'endless_r{idx}_sel.png')
        if not self.pick_mate():
            self.log('✗ 选机友/出击失败')
            return False
        self.snap(f'endless_r{idx}_prep.png')
        self.buy_items()
        st = self.do_flash()
        if st == 'rejected':
            self.log('✗ 本轮无法闪击：世界竞赛闪击次数已用完（提示「请选择单次匹配」）')
            return False
        if st != 'ok':
            self.log(f'✗ 闪击失败: {st}')
            return False
        self.log('已进局 → 观察')
        self.snap(f'endless_r{idx}_battle.png')
        self.battle_watch()
        ok = self.settle()
        self.log(f'第 {idx} 次结束: 链路{"完成" if ok else "未确认"}' +
                 ('' if self.last_win is None else ('（挑战胜利）' if self.last_win else '（挑战失败）')))
        return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--allow-capped', action='store_true',
                    help='挑战币达上限时仍继续（无挑战币收益，仅用于验证脚本）')
    args = ap.parse_args()
    case = Case(args.dry, args.allow_capped)
    done = 0
    for i in range(1, args.rounds + 1):
        try:
            if case.one_round(i, args.rounds):
                done += 1
        except Exception as e:                                   # noqa: BLE001
            case.log(f'第 {i} 次异常: {type(e).__name__} {e}')
            case.snap(f'endless_r{i}_err.png')
    print(f'完成 {done}/{args.rounds}', flush=True)
    case.to_home()
    return 0 if done == args.rounds else 1


if __name__ == '__main__':
    sys.exit(main())
