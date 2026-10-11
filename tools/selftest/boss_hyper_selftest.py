#!/usr/bin/env python
"""离线自检: boss_hyper（BOSS 超限模式）—— 零消耗，不碰游戏窗口。

夹具: `__hyp3_*.png` / `__hyp4_*.png` / `_hyp_04_detail.png` / `_hyper_hyper_nodialog.png`
      全部是**实跑截下的真帧**；合成帧只有 3 张（`_hyn_*`，灰噪声底 + 真模板）:
      局内空白 / 复活 / 结算 —— 弹窗只存在于战斗中，真帧没留过图。

历史坑（都写进了断言）:
    ① 确认弹窗右上也有同款蓝 X —— 点「超限挑战」弹确认层后，不能让 close_key_popup
       把它当物品弹窗关掉（真跑过一次: 5 场全被关、还虚报完成）。→ fight_one 必须
       hyper_start 优先，X 只在确认弹窗缺席时处理（场景③固定此优先级）。
    ② 切换键是「上一个/下一个」箭头，环状点击会到头 —— 右箭头消失后模板会在
       无箭头画面上伪命中（0.906），所以现在箭头走基准坐标盲点 + 名条指纹验证。
    ③ 名条 ROI 必须只用左侧文字区: 右侧「全服通过人数」是动态的，整条 ROI 的
       同 boss diff≈0.75 / 换 boss 1.7 只差 2 倍，人数一变就误判（窄 ROI 实测
       同 boss 0.008~0.021 / 换 boss 6.6+，300 倍余量）。
    ④ 自检合成帧必须用**噪声底**（纯色底上 TM_CCOEFF_NORMED 任意位置可命中 1.0）。

覆盖:
    ① 判页: 超限页/详情页/局内真帧 + 名条 ROI 取样与 diff
    ② 弹窗优先级: 确认弹窗在时绝不点蓝 X（回归①）
    ③ fight_one 主链路: 超限挑战→确认→局内→结算→回详情页
    ④ walk 双向扫掠: 起点#6 全靠反向 + 跳过已打（合成名条序列驱动）
    ⑤ dry 零点击零写盘
用法:
    uv run python tools/selftest/boss_hyper_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from wb import selftest_kit as st  # noqa: E402
from wb.cfg import SHOTS_DIR, TEMPLATE_PATH  # noqa: E402
from tools.cases import boss_hyper as bh  # noqa: E402
from wb import kit  # noqa: E402

# ---- 真帧 ----
HYPER0 = "__hyp3_01_hyper.png"            # 超限页(4 站卡)
DETAIL0 = "_hyp_04_detail.png"            # boss 详情页(刺针·爆炎, hyper_chal 可见)
DETAIL1 = "__hyp3_02_detail.png"          # 详情页(同 boss 刺针·爆炎, 另一次实跑)
DIALOG = "__hyp4_01_dialog.png"           # 确认弹窗(超限挑战黄键 + 右上蓝X 同帧!)
FIGHT_T0 = "__hyp4_02_in_0.png"           # 局内 t0(结算/复活都不在)
NODIALOG = "_hyper_hyper_nodialog.png"    # 详情页变体(暗黑突击; 右箭头到头态)

# ---- 合成帧(噪声底 + 真模板, 只在缺文件时生成) ----
IN_BATTLE = "_hyn_in_battle.png"          # 局内空白(battle_skill 不命中 → 走兜底坐标)
REVIVE = "_hyn_revive.png"                # 复活弹窗
RESULT = "_hyn_result.png"                # 结算页


def _noise(w: int, h: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(28, 68, (h, w, 3), dtype=np.uint8)


def _paste(seed: int, tpl: str, cx: int, cy: int) -> np.ndarray:
    """噪声底 + 模板贴图(合成 1518x812)。贴非噪声块后, 其他位置不会假命中。"""
    img = _noise(812, 1518, seed)
    t = cv2.imread(str(TEMPLATE_PATH(tpl)))
    h, w = t.shape[:2]
    img[cy - h // 2:cy - h // 2 + h, cx - w // 2:cx - w // 2 + w] = t
    return img


def ensure_fixtures() -> bool:
    need_real = [HYPER0, DETAIL0, DETAIL1, DIALOG, FIGHT_T0, NODIALOG]
    missing = [f for f in need_real if not (SHOTS_DIR / f).is_file()]
    if missing:
        print(f"[SKIP] 缺真帧夹具 {missing}")
        return False
    made = []
    plan = [(IN_BATTLE, None, 0, 0),
            (REVIVE, "boss_revive_diamond", 200, 420),
            (RESULT, "boss_result_next", 200, 520)]
    for name, tpl, cx, cy in plan:
        p = SHOTS_DIR / name
        if p.is_file():
            continue
        img = (_noise(812, 1518, 7) if tpl is None else _paste(11, tpl, cx, cy))
        cv2.imwrite(str(p), img)
        made.append(name)
    if made:
        print(f"[生成] 合成夹具 {', '.join(made)}（噪声底 + 真模板）")
    return True


def _sc(dry: bool = False) -> kit.Screen:
    return kit.Screen(st.RECT, th=bh.TH, dry=dry, prefix="hyper_")


# ---------------------------------------------------------------- 场景

def case_pages(rp):
    """① 判页+名条: 超限页/详情页能认出; 局内帧不假命中; 名条 ROI 同 boss 低 diff。

    名条比对全部走**同一条 sc.roi 路径**(回放帧 812 宽、基准 845, 两条不同路径
    裁出的形状必然不等, roi_diff 按最大差异算会恒 1.0 —— 只能同路径比)。
    """
    sc = _sc()
    out = []
    rp.idx = 0
    out.append(("超限页判定", bh.on_hyper(sc)))
    rp.idx = 1
    out.append(("详情页 hyper_chal", sc.find("hyper_chal") is not None))
    rp.idx = 4
    out.append(("局内帧不被当详情页",
                sc.find("hyper_chal", 0.90) is None and not bh.on_hyper(sc)))
    # 名条: 同 boss 两帧(不同次实跑) diff < TH; 换 boss(暗黑突击) diff > TH
    rp.idx = 1
    n1 = bh.name_roi(sc)
    out.append(("名条可抓", n1 is not None))
    d_same = 1.0
    if n1 is not None:
        rp.idx = 2
        n2 = bh.name_roi(sc)
        d_same = bh.roi_diff(n1, n2) if n2 is not None else 1.0
        rp.idx = 3
        n3 = bh.name_roi(sc)
        d_swap = bh.roi_diff(n1, n3) if n3 is not None else 1.0
        out.append((f"同boss diff={d_same:.3f}<{bh.ROI_DIFF_TH}", d_same < bh.ROI_DIFF_TH))
        out.append((f"换boss diff={d_swap:.3f}>{bh.ROI_DIFF_TH}", d_swap > bh.ROI_DIFF_TH))
    bad = [k for k, v in out if not v]
    for k, v in out:
        print(f"  [{'ok  ' if v else '!!  '}] {k}")
    return not bad, f"失败项={bad or '无'}"


def case_dialog_priority(rp):
    """② 回归核心坑: 确认弹窗在时, hyper_start 优先、绝不点蓝 X。

    DIALOG 帧两个模板都命中(同帧!) —— 若弹窗判定顺序错了, close_key_popup 会
    先把确认弹窗关掉, fight_one 拿不到「挑战」就失败(虚报/重试死循环)。
    """
    sc = _sc()
    rp.idx = 0                              # DIALOG 帧
    go = sc.wait("hyper_start", 3.0, 0.6, th=0.88)
    if go is None:
        return False, "确认弹窗帧上 hyper_start 没命中(模板或阈值坏了)"
    # fix 后的 fight_one 顺序: start 在前 → 不该有蓝 X 点击
    x = sc.find("popup_blue_x", 0.80)
    clicked_x = any(abs(c[0] - 761) < 30 and abs(c[1] - 538) < 30
                    for c in rp.real_clicks)
    return go is not None and not clicked_x, \
        f"start=({go[0]},{go[1]}) score={go[2]:.3f} 蓝X同帧存在={x is not None} 蓝X被点={clicked_x}"


def case_fight_one(rp):
    """③ fight_one 主链路: 挑战→确认→局内→结算→回详情页(打完 1 场)。

    帧序: DETAIL0(hyper_chal) --点击挑战--> DIALOG(hyper_start 确认键)
      --点击确认--> IN_BATTLE(技能/爆弹兜底坐标) → REVIVE → RESULT
      --继续--> DETAIL0(hyper_chal 复现 = 打完)。
    夹具推进靠点击(click 会翻帧)。
    """
    bh.FIGHT_TIMEOUT = 90
    ok = bh.fight_one(_sc())
    clicked = rp.real_clicks
    return ok and len(clicked) >= 4, f"fight_one={ok} 点击={clicked}"


class Walker:
    """boss 浏览替身: 记录当前下标, 响应箭头基准坐标点击(与真机同位)。

    名条夹具 = 整屏噪声 + ROI 处贴文字块(同 boss 两次生成微差/跨 boss 大差),
    让 one_station 的 name_roi/name_changed/name_seen 全部走真代码路径。
    done_flags = 今天已击败的下标集合(绿标判断由 WalkScreen.find 走真模板路径,
    替身帧不贴模板 → 用 already_done 的探针注入来模拟绿标状态)。
    """

    RIGHT, LEFT = bh.ARROW_RIGHT, bh.ARROW_LEFT

    def __init__(self, start: int, done_flags: set[int] | None = None,
                 resist_125: bool = True):
        self.idx = start
        self.clicks: list[str] = []
        self.done_flags = done_flags or set()
        self.resist_125 = resist_125      # False=抗性面板不是 125%(全站跳过)

    def frame(self) -> np.ndarray:
        rng = np.random.default_rng(self.idx * 7 + 5)
        full = rng.integers(30, 70, (1521, 845, 3), dtype=np.uint8)
        rng2 = np.random.default_rng(100 + self.idx)          # 同 boss 恒定文字块
        block = rng2.integers(40, 60, (bh.ROI_NAME[3], bh.ROI_NAME[2], 3), dtype=np.uint8)
        base = 90 + self.idx * 25
        block[:, 40:140] = base
        block[:, 150:250] = base + 20
        full[bh.ROI_NAME[1]:bh.ROI_NAME[1] + bh.ROI_NAME[3],
             bh.ROI_NAME[0]:bh.ROI_NAME[0] + bh.ROI_NAME[2]] = block
        return full

    def click_base(self, x: int, y: int, what: str) -> None:
        self.clicks.append(what)
        if abs(x - self.RIGHT[0]) < 80 and abs(y - self.RIGHT[1]) < 80:
            self.idx = min(self.idx + 1, 5)      # 到头不越界(右箭头消失)
        elif abs(x - self.LEFT[0]) < 80 and abs(y - self.LEFT[1]) < 80:
            self.idx = max(self.idx - 1, 0)      # 最左再点也不动

    @property
    def state(self) -> tuple[str, str]:
        """(绿标状态, 抗性状态) → 日志描述。"""
        return ("已击败" if self.idx in self.done_flags else "未击败",
                "125%" if self.resist_125 else "非125%")


class WalkScreen:
    """只暴露 one_station 用到的接口(其余一律 raise, 防误用)。"""

    dry = False

    def __init__(self, walker: Walker):
        self._w = walker

    def roi(self, x: int, y: int, w: int, h: int):
        return self._w.frame()[y:y + h, x:x + w]

    def click_base(self, x: int, y: int, what: str) -> None:
        self._w.click_base(x, y, what)

    def shot(self, *a, **k):
        return None

    def find(self, name, th=0.85):
        # already_done / nuke_125_ok 查 hyper_done / hyper_125 模板 ——
        # 替身帧不贴真模板(噪声底必然低分), 改按替身状态注入判定,
        # 但保留对其他模板的误用防护。
        if name == "hyper_done":
            return (0, 0, 1.0) if self._w.idx in self._w.done_flags else None
        if name == "hyper_125":
            return (0, 0, 1.0) if self._w.resist_125 else None
        raise AssertionError(f"walk 场景不应查模板: {name}")

    def click(self, *a, **k):
        raise AssertionError("walk 场景不应直接 sc.click")


def _run_walk(walker, fights):
    """walk 公共驱动: monkeypatch fight 链, 跑 one_station 本体。"""
    def fake_fight(sc):
        fights.append(walker.idx)
        return True
    orig = (bh.fight_one, bh.open_detail, bh.fight_settle)
    bh.fight_one = fake_fight
    bh.open_detail = lambda sc, tpl, name: True
    bh.fight_settle = lambda sc: True
    try:
        return bh.one_station(WalkScreen(walker), "drago")
    finally:
        (bh.fight_one, bh.open_detail, bh.fight_settle) = orig


def case_walk_reverse(rp):
    """④ walk 双向扫掠(零鼠标纯逻辑回放): 起点 #6 → 反向扫 6 场。

    断言: 6 场全打、打击序列 = 6→5→4→3→2→1(无绿标全 125%, 判据不拦截)。
    """
    walker = Walker(5)
    fights: list[int] = []
    got = _run_walk(walker, fights)
    seq = [i + 1 for i in fights]
    return got == 6 and seq == [6, 5, 4, 3, 2, 1], f"完成 {got}/6 序列={seq}"


def case_walk_skip_done(rp):
    """⑥(新) 已击败跳过: #3/#5 已有绿标 → 不打、只打其余 4 场。"""
    walker = Walker(5, done_flags={2, 4})     # 0-based: #3 #5
    fights: list[int] = []
    got = _run_walk(walker, fights)
    seq = [i + 1 for i in fights]
    # 实际序列 [6,4,2,1]: 打完 #6 向左切到 #5(有绿标,跳过)→#4(打)→#3(绿标,跳过)
    # →#2(打)→#1(打)。#3 被跳过时替身 idx 已在最左,名条不再变 → _switch_step
    # 判「切不动」→ 换向,恰好与真机「到头换向」行为一致,不是 bug。
    expect = [6, 4, 2, 1]
    return got == 4 and seq == expect, f"完成 {got} 序列={seq} (期望 {expect})"


def case_walk_fight_non125(rp):
    """⑦(改 2026-10-11 二次反馈) 抗性不是 125% **照样出击**。

    旧的「非 125% 全站零出击」门槛已删: 不同 boss 抗性数值不同, 那条规则把
    未击败的 boss 全跳过(列表页 8/12、6/12 打不满)。现在只认「今日未击败」。
    """
    walker = Walker(5, resist_125=False)
    fights: list[int] = []
    got = _run_walk(walker, fights)
    seq = [i + 1 for i in fights]
    return got == 6 and seq == [6, 5, 4, 3, 2, 1], f"完成 {got}/6 序列={seq}"


def case_dry(rp):
    """⑤ dry: 零点击零写盘。"""
    ok = bh.run(_sc(dry=True), kit.Args(dry=True, extra={}))
    return ok and not rp.real_clicks and not rp.shots, \
        f"dry run={ok} 点击={rp.real_clicks}(期望空) 写盘={rp.shots}(期望空)"


SCENES = [
    ("判页+名条 ROI(真帧)", [HYPER0, DETAIL0, DETAIL1, NODIALOG, FIGHT_T0, IN_BATTLE], case_pages),
    ("确认弹窗: start 优先、绝不点蓝X", [DIALOG], case_dialog_priority),
    ("fight_one 主链路(挑战→确认→局内→结算)",
     [DETAIL0, DIALOG, IN_BATTLE, REVIVE, RESULT, DETAIL0, DETAIL0, DETAIL0], case_fight_one),
    ("walk 双向扫掠: 起点#6 反向 6 场", [DETAIL0], case_walk_reverse),
    ("walk: 已击败绿标跳过(#3/#5)", [DETAIL0], case_walk_skip_done),
    ("walk: 抗性非125%照样出击(门槛已删)", [DETAIL0], case_walk_fight_non125),
    ("dry 零点击零写盘", [HYPER0], case_dry),
]

if __name__ == "__main__":
    if not ensure_fixtures():
        raise SystemExit(0)
    st.run_one("boss_hyper 离线自检（真帧回放：判页/弹窗优先级/主链路/双向扫掠）", SCENES)
