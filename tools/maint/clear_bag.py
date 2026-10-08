"""背包已满(如 512/500)自动清理 —— 实跑确认过的三步。

背包满时游戏弹「背包已满」, 盖在扫荡/闪击面板前, 挡住后续所有操作。

清理三步(数值为实跑实测):
  1) 装备合成: 首页 → 仓库 → 改造 → 白色装备 → **反复**自动合成 → 确认
     直到点「自动合成」没反应(没有可合成的白装)为止 —— 出 S 装备 **不代表**
     白装用完(自动合成的停止条件是「拿到 S 装备」或「资源不足」), 实测会剩一堆,
     所以必须循环点; 每轮都等「停止」出现再消失才算一轮结束。
  2) 矿石出售: 首页 → 仓库 → 背包 → 出售 → 立即出售   (实测 +85000 金币, 512→489)
     没有可出售的矿石时会进「装备出售」页, 此时直接返回。
  3) 经验合成: 首页 → 仓库 → 背包 → 经验合成 → 取消第 1/4 个勾选 → 合成 → 领取
     勾选框用「右侧列黄色方块」像素检测定位, 所以与行数/布局变化无关, 但
     **必须精确**: 实测第 4 个黄块中心 y=1092, 按目测的 1040 点会差 52px 漏掉一行。
     实测勾选项可能只有 3 个(有一行「数量不足」不参与), 所以取「检测到的第 1 个和
     最后一个」, 而不是写死索引 0/3。

被 sweep_stage / boss_mode 等复用:
    from clear_bag import clear_if_full
    clear_if_full(rect, log)

用法:
    uv run python tools/maint/clear_bag.py [--dry] [--force]
    --force: 不要求出现「背包已满」弹窗, 直接跑三步(维护/验证用)
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import cv2

from wb.bot import click_xy, find_game_window, find_in_game, grab_window
from wb.cfg import CONF

TH = 0.86
POPUP_X = (746, 240)      # 各弹层右上角 X(背包已满/背包/经验合成同一位置)


def _shot(rect, tag: str) -> None:
    out = os.path.join(ROOT, "shots", f"_{tag}.png")
    cv2.imwrite(out, grab_window(rect))
    print("saved", out)


def _find(name: str, rect, th: float = TH):
    return find_in_game(name, rect, th)


def _click(hit, rect, dry: bool, label: str = "") -> bool:
    if not hit:
        return False
    if label:
        print(f"    点 {label} ({hit[0]},{hit[1]}) s={round(hit[2], 3)}")
    click_xy(hit[0], hit[1], 2, (0.4, 0.8), rect, dry)
    return True


def _goto(rect, name: str, dry: bool, label: str, wait: float = 2.4,
          th: float = TH) -> bool:
    """找模板 → 点击 → 等一会。找不到返回 False。"""
    h = _find(name, rect, th)
    if not h:
        print(f"    未找到 {label}({name})")
        return False
    _click(h, rect, dry, label)
    time.sleep(wait)
    return True


def _wait(name: str, rect, secs: float, th: float = 0.90):
    """等某个模板出现, 返回命中。"""
    end = time.time() + secs
    while time.time() < end:
        h = _find(name, rect, th)
        if h:
            return h
        time.sleep(0.8)
    return None


def _checked_boxes(rect) -> list[tuple[int, int]]:
    """合成页右侧列的黄色方块 = 勾选中的行, 返回中心点(按 y 升序)。

    实测: 4 行都在时中心 y ≈ 418 / 609 / 830 / 1092(第 4 个不是 1040!)。
    """
    img = grab_window(rect)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (20, 120, 180), (35, 255, 255))
    mask[:, :640] = 0
    mask[:300, :] = 0
    mask[1280:, :] = 0
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area > 250 and 20 <= w <= 60 and 20 <= h <= 60:
            out.append((int(x + w / 2), int(y + h / 2)))
    return sorted(out, key=lambda p: p[1])


def _close_popups(rect, dry: bool, times: int = 2) -> None:
    """连点右上角 X 关掉残留弹层; 已在首页就不动(POPUP_X 在首页会点到「寻宝」)。"""
    for _ in range(times):
        if _find("stage_btn", rect, 0.90):
            return
        click_xy(POPUP_X[0], POPUP_X[1], 1, (0.4, 0.8), rect, dry)
        time.sleep(1.6)


def _to_home(rect, dry: bool, tries: int = 4) -> bool:
    """回首页(以 stage_btn 为首页标志, nav_home 在子页也会命中)。"""
    for _ in range(tries):
        if _find("stage_btn", rect, 0.90):
            return True
        _close_popups(rect, dry, 1)
        h = _find("nav_home", rect, 0.90)
        if h:
            _click(h, rect, dry, "首页")
        time.sleep(2.0)
    return bool(_find("stage_btn", rect, 0.90))


def _to_warehouse(rect, dry: bool) -> bool:
    """首页 → 仓库。"""
    for _ in range(3):
        if _find("wh_title", rect, 0.90):
            return True
        h = _find("warehouse_btn", rect, 0.90)
        if h:
            _click(h, rect, dry, "仓库")
            time.sleep(2.6)
        else:
            time.sleep(1.5)
    return bool(_find("wh_title", rect, 0.90))


def _ensure_warehouse(rect, dry: bool, log=None) -> bool:
    """确保当前在仓库页; 不在就关弹层 → 首页 → 仓库。每一步开始都调它。"""
    if _find("wh_title", rect, 0.90):
        return True
    _close_popups(rect, dry, 2)
    if _to_home(rect, dry) and _to_warehouse(rect, dry):
        return True
    if log:
        log("    未能回到仓库页")
    return False


def _autofuse_round(rect, dry: bool, log, n: int) -> str:
    """跑一轮自动合成。返回 'fused' / 'empty' / 'timeout'。

    ⚠️ 关键认知(用户指出): 「合成出 S 装备」**不等于**白色装备用完。
    自动合成的停止条件是「拿到 S 装备」或「资源不足」, 所以白装常常还剩一堆,
    必须反复点, 直到点了没反应(没有可合成的白装)为止。
    """
    _goto(rect, "eq_auto_go", dry, f"自动合成(第{n}轮)", wait=2.0)
    for _ in range(2):                        # 确认弹窗可能点不中 → 最多补点一次
        c = _find("eq_confirm", rect, 0.90)
        if not c:
            break
        _click(c, rect, dry, "确认开始")
        if _wait("eq_stop", rect, 4):
            break
    t0 = time.time()
    while time.time() - t0 < 8:               # 等「停止」出现 = 真的开跑了
        if _find("eq_stop", rect, 0.90):
            break
        time.sleep(1.0)
    else:
        return "empty"                        # 没开跑 = 没有可合成的白色装备了
    while time.time() - t0 < 150:             # 等它自己停
        if not _find("eq_stop", rect, 0.90):
            return "fused"
        time.sleep(1.5)
    log("    自动合成超时(停止键仍在) → 点停止收尾")
    _goto(rect, "eq_stop", dry, "停止")
    return "timeout"


def equip_synthesis(rect, log=print, dry: bool = False,
                    max_rounds: int = 40) -> bool:
    """仓库 → 改造 → 白色装备 → **反复**自动合成直到没有白装 → 返回仓库。

    max_rounds 只是防死循环的上限(每轮至少消耗 5 件白装)。
    """
    if not _ensure_warehouse(rect, dry, log):
        return False
    if not _goto(rect, "wh_alter", dry, "改造", wait=2.8):
        return False
    if not _find("eq_title", rect, 0.90):
        log("    未进「装备合成」页, 截图存档")
        _shot(rect, "clear_bag_equip_unknown")
        return False
    if _find("eq_tab_white", rect, 0.90):
        _goto(rect, "eq_tab_white", dry, "白色装备", wait=1.4)
    done = 0
    for n in range(1, max_rounds + 1):
        if _find("claim_btn", rect, 0.90):    # 上一轮若弹了「恭喜获得」先领掉
            _goto(rect, "claim_btn", dry, "恭喜获得-领取", wait=2.0)
        st = _autofuse_round(rect, dry, log, n)
        if st == "fused":
            done += 1
            continue
        log("    第 %d 轮: %s → 白装已清完" %
            (n, "没有可合成的白色装备" if st == "empty" else "超时中止"))
        break
    else:
        log("    已达 %d 轮上限(防死循环) → 结束" % max_rounds)
    log("    装备合成结束: 成功 %d 轮" % done)
    if _find("eq_back", rect, 0.90):
        _goto(rect, "eq_back", dry, "返回仓库", wait=2.4)
    return True


def sell_ores(rect, log=print, dry: bool = False) -> bool:
    """仓库 → 背包 → 出售 → 立即出售(无矿石则进装备出售页 → 返回)。"""
    if not _ensure_warehouse(rect, dry, log):
        return False
    _goto(rect, "wh_bag", dry, "背包", wait=2.8)
    if not _find("bag_title", rect, 0.90):
        log("    未打开背包")
        return False
    if not _goto(rect, "bag_sell", dry, "出售", wait=2.6):
        return False
    if _find("sell_title", rect, 0.90):
        _goto(rect, "sell_ok", dry, "立即出售", wait=2.8)
        log("    矿石已出售")
    else:
        # 实测: 没有可出售的矿石时点「出售」不会跳任何页, 仍是背包弹层
        log("    无「快速出售」弹窗 → 判定没有可出售的矿石")
    _close_popups(rect, dry, 1)      # 关掉背包弹层(若它还在)
    return True


def _make_and_claim(rect, dry: bool, log, tag: str) -> bool:
    """点「合成」并领「恭喜获得」。合成键变灰 = 本页没有可合成项。"""
    if not _find("make_go", rect, 0.90):
        log(f"    {tag}: 合成键变灰 → 本页无可合成项, 跳过")
        return False
    _goto(rect, "make_go", dry, f"{tag}-合成", wait=2.0)
    c = _wait("claim_btn", rect, 12)
    if c:
        _click(c, rect, dry, "恭喜获得-领取")
        time.sleep(2.0)
        return True
    log(f"    {tag}: 未见「恭喜获得」(可能没有可合成项)")
    return False


def exp_synthesis(rect, log=print, dry: bool = False) -> bool:
    """仓库 → 背包 → 经验合成: ① 魔方合成(先取消勾选) ② 残骸合成 → 合成。

    用户口径(两步在同一页, 底部两个页签):
      1) 「魔方合成」页签: 取消第 1、4 个勾选 → 点合成; 实测取消后合成键变灰
         (等于不消耗魔方), 所以这步通常只是确认跳过;
      2) 再点「残骸合成」页签 → 点「合成」→ 恭喜获得 → 领取。
    实测: 残骸合成点下去约 1.8s 直接弹「恭喜获得」, **没有二次确认**;
          合成完合成键变灰; 页签选中后 make_tab_relic 模板就不再命中(配色变了)。
    """
    if not _ensure_warehouse(rect, dry, log):
        return False
    _goto(rect, "wh_bag", dry, "背包", wait=2.8)
    if not _find("bag_title", rect, 0.90):
        return False
    if not _goto(rect, "bag_exp_syn", dry, "经验合成", wait=2.8):
        return False
    if not _find("make_title", rect, 0.90):
        log("    未进「经验合成」页")
        return False
    boxes = _checked_boxes(rect)
    if boxes:
        log(f"    魔方合成: 检测到勾选框 {boxes} → 取消首/末两个(不消耗魔方)")
        first, last = min(boxes, key=lambda b: b[1]), max(boxes, key=lambda b: b[1])
        for b in {(first[0], first[1]), (last[0], last[1])}:
            _click((b[0], b[1], 1.0), rect, dry, "取消勾选")
            time.sleep(1.2)
    else:
        log("    魔方合成: 没有勾选中的行")
    _make_and_claim(rect, dry, log, "魔方合成")
    if _goto(rect, "make_tab_relic", dry, "残骸合成页签", wait=1.8):
        _make_and_claim(rect, dry, log, "残骸合成")
    else:
        log("    未找到「残骸合成」页签, 跳过")
    _close_popups(rect, dry, 1)
    return True


def clear_if_full(rect, log=print, dry: bool = False, force: bool = False) -> bool:
    """检测到「背包已满」就按三步清理, 返回是否做过清理。

    force=True 时跳过弹窗检测, 直接跑三步。结束时会把游戏带回首页。
    """
    if not force and not _find("bag_full", rect):
        return False
    log("检测到「背包已满」→ 开始清理(三步)")
    if _find("bag_full", rect):
        _click((POPUP_X[0], POPUP_X[1], 1.0), rect, dry, "关闭背包已满弹窗")
        time.sleep(1.6)
    if not _to_home(rect, dry):
        log("    未能回到首页, 清理中止")
        return True
    if not _to_warehouse(rect, dry):
        log("    未找到仓库入口, 清理中止")
        _to_home(rect, dry)
        return True
    equip_synthesis(rect, log, dry)
    sell_ores(rect, log, dry)
    exp_synthesis(rect, log, dry)
    _close_popups(rect, dry)
    _to_home(rect, dry)
    log("背包清理完成, 已回首页")
    return True


def main() -> None:
    args = sys.argv[1:]
    dry = "--dry" in args
    force = "--force" in args
    rect = find_game_window(CONF.title_keyword, CONF.process_name)
    print(f"[{time.strftime('%H:%M:%S')}] 窗口 {rect} dry={dry} force={force}")
    if not clear_if_full(rect, print, dry, force):
        print("当前没有「背包已满」弹窗, 无需清理")


if __name__ == "__main__":
    main()
