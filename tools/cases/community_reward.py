"""社区奖励 —— 游戏圈点赞/评论 + 桌面礼包领取（跨窗口用例）。

链路（用户口径 2026-10-12）:
    首页「社区奖励」→ 面板「前往」→ 微信游戏圈（独立窗口, 标题「微信游戏」）→
      点赞×2（往下滑, 再点一个） → 点评论图标 → 输入框打字「111」→ 发送 → 关抽屉 →
      右栏「去领取」→ 礼包中心「领取」→ 关抽屉 →
    触发桌面快捷方式「雷霆战机：集结.lnk」回游戏 → 关社区奖励面板 → 再次打开 →
      点两个「领取」→ 切「添加桌面」页签 → 「领取」→ 回首页

⚠ 公开操作: 点赞与评论对外可见。用例**先读面板状态**再动手, 已完成的任务不重复做,
   所以中途失败重跑不会重复发评论（面板状态是重新打开面板时刷新的, 故先重开再读）。

⚠ 跨窗口: 点赞/评论发生在微信游戏窗口, 与游戏窗口是两个不同 rect 的 Screen;
   两者共用 wb/kit.Screen, 模板按各自原生尺度裁（微信侧 2100x1312）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wb import bot as _bot  # noqa: E402
from wb import kit, wxcircle  # noqa: E402

TH = 0.86                 # 游戏侧（845x1521 基准模板）
TH_ENTRY = 0.84           # 入口图标: 模板次高仅 0.73, 但刚关面板的转场帧会轻微位移
                          # （实测同一模板 5 帧稳态 min=0.995, 转场帧跌到 0.866）
TH_WX = 0.90              # 微信侧图标: 真字形自匹配 1.000 / 次高仅 0.46 —— 0.90 余量极大
TH_WB = 0.88              # 微信侧按钮/输入框（同原生尺度, 留出 hover 态余量）

ENTRY = "community_gift"
# 面板判据：**多元素任一命中**（标题黄字 / 「前往」/ 右上X）
# ⚠ 2026-10-15 修（用户反馈 community_reward 失败）：面板**已改版** —— 旧模板 cg_mark
#   裁的是「区奖励」三字（还裁偏），在真帧上裸匹配仅 0.55 → 单一判据认不出"面板已打开"
#   → open_panel 白等 4.8s 就判 fail（而截图里面板明明开着）；紧接 goto_home 也不认这个
#   面板 → 「找不到返回键，停手」→ 后面所有用例连坐。
#   实测（739x1383 真帧）：cg_close(右上X) **0.979** / cg_go(前往) **0.972** —— 都是
#   面板特有且高置信，比标题字稳定得多。
PANEL_MARKS = ("cg_mark", "cg_go", "cg_close")
PANEL_X = (764, 428)      # 面板右上 X（基准坐标）
ROW_BTN = ((669, 1078), (669, 1209))   # 两行按钮槽位（基准）: 0=点赞 1=评论
TAB_CIRCLE, TAB_DESK, TAB_MINI = (187, 1315), (366, 1315), (548, 1315)
TAB_CIRCLE_WX = (268, 172)   # 微信窗口「游戏圈」页签（客户区坐标; 窗口尺寸稳定 2099x1312）
WX_FEED_X = 0.40             # 滚 feed 时鼠标放在窗口宽度 40% 处
WX_SIDE_X = 0.85             # 滚右侧礼包栏时放在 85% 处
MIN_LIKES = 2
COMMENT_TEXT = "111"
# ⚠ 「领取」按钮**两页不是同一个字形/尺寸**, 跨页套用必错（实测互匹配仅 0.68/0.80）:
#   游戏圈页 = 144x66; 添加桌面页 = 238x81。两套都得试。
CLAIM_TPLS = ("cg_claim", "cg_claim_desk")

PLAN = ("首页→社区奖励→(前往)→微信游戏圈→点赞×2→评论「111」→去领取→礼包中心领取→"
        "桌面快捷方式回游戏→重开面板→领取×2→添加桌面→领取→回首页")


# ---------------------------------------------------------------- 面板侧

def _row_y(sc, i: int) -> int:
    """第 i 行按钮的**当前客户区** y（用于判断模板命中属于哪一行）。"""
    return _bot.ref_to_client(ROW_BTN[i][0], ROW_BTN[i][1], sc.w, sc.h)[1]


def row_state(sc, i: int):
    """第 i 行的按钮类型: 'go'（未完成, 显示「前往」）/ 'claim'（可领）/ None。

    ⚠ 两处坑: ① 必须按 y 归属行 —— 两行按钮同款, 只判「有没有」会把第 2 行算到
      第 1 行头上(该做的任务被跳过); ② 所以得用 find_all 取**多个**命中,
      find 只回最佳那个(永远是第 1 行), 第 2 行永远判不出来。
    """
    y = _row_y(sc, i)
    for tpl, kind in (("cg_go", "go"), ("cg_claim", "claim")):
        for h in sc.find_all(tpl, TH, max_hits=4, gap_ratio=0.5):
            if abs(h[1] - y) <= 48:
                return kind
    return None


def panel_open(sc) -> bool:
    """面板是否已打开（见 PANEL_MARKS 注释：多元素任一命中，不赌单一标题模板）。"""
    st = sc.look(*PANEL_MARKS, th=TH)
    return any(st[m] is not None for m in PANEL_MARKS)


def open_panel(sc) -> bool:
    """进「社区奖励」面板（已在面板则直接成功）。"""
    if panel_open(sc):
        return True
    if not kit.is_home(sc):
        kit.goto_home(sc)
    h = None
    for k in range(3):                      # 转场瞬间图标会有轻微位移 → 重试几次
        h = sc.find(ENTRY, TH_ENTRY)
        if h is not None:
            break
        if k < 2:
            kit.nap(1.2)
    if h is None:
        sc.shot("cr_entry_fail")
        kit.log("[warn] 首页找不到「社区奖励」入口")
        return False
    sc.click(h, "社区奖励")
    for _ in range(4):
        kit.nap(1.2)
        if panel_open(sc):
            return True
    sc.shot("cr_panel_fail")
    return False


def close_panel(sc) -> bool:
    h = sc.find("cg_close", TH)
    if h is None:
        return False
    sc.click(h, "关闭社区奖励面板")
    kit.nap(1.6)
    return True


def _tap_go(sc, i: int) -> None:
    sc.click_base(ROW_BTN[i][0], ROW_BTN[i][1], f"前往#{i + 1}")
    kit.nap(1.0)


def claim_rows(sc, n: int = 2) -> int:
    """点面板上可领的「领取」；返回点到几个。

    ⚠ 用 find_all + 记住已点过的 y: 面板上有**两个**同款「领取」, find 永远只回
      最佳那个 —— 若它点完不变(领取失败/读秒), 直接循环会原地空点 n 次。
      gap_ratio 必须调小: 默认 0.8 的 NMS 半径(模板长边×0.8=105px)会
      连**相邻一行**一起涂黑, 第二行永远找不出来。
    两页(游戏圈/添加桌面)的按钮字形不同 → 外层逐个模板试(见 CLAIM_TPLS)。
    """
    done, used = 0, []
    for _ in range(n + 3):
        hit = None
        for tpl in CLAIM_TPLS:
            for h in sc.find_all(tpl, TH, max_hits=4, gap_ratio=0.5):
                if all(abs(h[1] - y) > 40 for y in used):
                    hit = h
                    break
            if hit is not None:
                break
        if hit is None:
            break
        sc.click(hit, f"领取#{done + 1}")
        kit.nap(2.0)
        if kit.claim_if_present(sc):        # 可能弹「恭喜获得」
            kit.nap(1.0)
        used.append(hit[1])
        done += 1
        if done >= n:
            break
    return done


# ---------------------------------------------------------------- 微信侧

def _wheel(wx, notches: int, *, side: bool = False, pause: float = 0.9) -> None:
    """在微信窗口里滚动；side=True 滚右侧礼包栏, 否则滚左侧 feed。"""
    x = int(wx.w * (WX_SIDE_X if side else WX_FEED_X))
    _bot.wheel_xy(x, int(wx.h * 0.5), notches, wx.rect, wx.dry)
    kit.nap(pause)


def wx_circle_page(wx) -> bool:
    """确保停在「游戏圈」页签, 且 feed 已出现。

    选中态再点一次无副作用（页签不会切走）, 所以**无条件点一次**比判状态更稳 ——
    页签选中/未选中的字色不同, 判态得多养一个模板, 收益不划算。
    """
    wx.click_at(*TAB_CIRCLE_WX, "游戏圈页签")
    kit.nap(1.8)
    # 先滚回 feed 顶部: 上一轮可能把 feed 停在半路, 而**已赞的图标会变红** ——
    # 灰空心的 wx_like 就一个都匹配不到, 会把「feed 已加载」误判成「没加载」。
    _wheel(wx, 12, pause=1.2)
    for _ in range(5):
        # 评论图标不会因点赞变色, 拿它当备用判据（任一命中即认为 feed 已就绪）
        if wx.find("wx_like", TH_WX) or wx.find("wx_comment", TH_WX):
            return True
        kit.nap(1.4)
    wx.shot("cr_circle_fail")
    return False


def wx_likes(wx, want: int = MIN_LIKES) -> int:
    """点 want 个赞。

    防重复两道: ① 每次点完往下滑, 并要求新命中点比上一个**下移 >60px**（换了一帖）;
    ② 已赞图标会变蓝 → wx_like（灰空心）不再命中。
    want 可用 `--likes=N` 改小: 当天已赞过 1 个后再跑, 传 1 就不会多点一帖。
    """
    done, prev_y = 0, None
    for _ in range(8):
        h = wx.find("wx_like", TH_WX)
        if h is not None and (prev_y is None or abs(h[1] - prev_y) > 60):
            wx.click(h, f"点赞#{done + 1}")
            kit.nap(1.6)
            prev_y, done = h[1], done + 1
            if done >= want:
                return done
            _wheel(wx, -5)                      # 往下翻, 换一帖
        else:
            _wheel(wx, -3)
    wx.shot("cr_like_fail")
    kit.log(f"[warn] 只点到 {done}/{want} 个赞")
    return done


def wx_comment(wx, text: str = COMMENT_TEXT) -> bool:
    """评论图标 → 输入框打字 → 发送 → 关评论抽屉。"""
    h = wx.find("wx_comment", TH_WX)
    if h is None:
        wx.shot("cr_cmt_icon_fail")
        return False
    wx.click(h, "评论图标")
    box = wx.wait("wx_comm_input", 8, th=TH_WB)
    if box is None:
        wx.shot("cr_cmt_box_fail")
        return False
    wx.click(box, "评论输入框")
    kit.nap(0.8)
    _bot.type_text(text, wx.rect, wx.dry)       # 键盘输入: 必须走 bot 层(自检替身)
    kit.nap(1.0)
    send = wx.wait("wx_comm_send", 6, th=TH_WB)
    if send is None:
        wx.shot("cr_cmt_send_fail")
        return False
    wx.click(send, "发送评论")
    kit.nap(2.0)
    # ⚠ 位置守卫: 抽屉的 X 在 y≈175, 而**窗口自身的 X 在 y≈56** —— 发完评论后抽屉常
    #   自动收起, 此时 find 会以 0.915 命中最像的「窗口关闭键」, 一点就把整个微信游戏
    #   窗口关掉(实测复现: 之后所有抓帧全黑)。y>100 直接排除掉它。
    x = wx.find("wx_comm_close", TH_WX)
    if x is not None and x[1] > 100:
        wx.click(x, "关闭评论抽屉")
        kit.nap(1.2)
    return True


def wx_gift_center(wx) -> bool:
    """右栏「去领取」→ 礼包中心「领取」→ 关抽屉。与点赞/评论独立, 失败不拖累主流程。"""
    hit = None
    for _ in range(10):
        hit = wx.find("wx_getgift", TH_WB)
        if hit is not None:
            break
        _wheel(wx, -3, side=True)
    if hit is None:
        wx.shot("cr_getgift_fail")
        kit.log("[warn] 右栏找不到「去领取」")
        return False
    wx.click(hit, "去领取")
    kit.nap(2.6)
    got = None
    for tpl, label in (("wx_gift_claim", "领取"), ("wx_gift_all", "一键领取")):
        got = wx.wait(tpl, 6, th=TH_WB)
        if got is not None:
            wx.click(got, f"礼包中心-{label}")
            kit.nap(2.0)
            break
    if got is None:
        wx.shot("cr_gift_claim_fail")
    x = wx.find("wx_gift_close", TH_WX)
    if x is not None and x[1] > 100:        # 同上: 排除窗口自身的关闭键(y≈56)
        wx.click(x, "关闭礼包中心")
        kit.nap(1.2)
    return got is not None


def do_wechat(game_sc, *, like: bool, comment: bool,
              likes: int = MIN_LIKES) -> bool:
    """点「前往」→ 微信游戏圈做任务 → （礼包）→ 返回。返回点赞/评论是否都达成。"""
    _tap_go(game_sc, 0 if like else 1)
    wx = wxcircle.wait_screen()
    if wx is None:
        game_sc.shot("cr_wx_nowin")
        kit.log("[warn] 微信游戏窗口没起来")
        return False
    ok = wx_circle_page(wx)
    if ok and like:
        ok = wx_likes(wx, likes) >= likes
    if ok and comment:
        ok = wx_comment(wx)
    if not ok:
        wx.shot("cr_wx_partial")
    wx_gift_center(wx)               # 礼包与点赞/评论独立
    return ok


# ---------------------------------------------------------------- 主流程

def run(sc, args) -> bool:
    if sc.dry:
        kit.log(f"[dry] 计划: {PLAN}")
        return True

    if not open_panel(sc):
        return False
    # 面板会停在上次的页签(它记得状态) → 先无条件切回「游戏圈」页, 否则下面判的是
    # 「添加桌面」那页的行, 点赞/评论任务会被当成「已完成」而静默跳过
    sc.click_base(*TAB_CIRCLE, "切换「游戏圈」页签")
    kit.nap(1.6)

    need_like = row_state(sc, 0) == "go"
    need_cmt = row_state(sc, 1) == "go"
    kit.log(f"面板任务: 点赞={'待做' if need_like else '已完成'} "
            f"评论={'待做' if need_cmt else '已完成'}")

    if (need_like or need_cmt) and not args.extra.get("skip_wx"):
        if not do_wechat(sc, like=need_like, comment=need_cmt,
                         likes=int(args.extra.get("likes") or MIN_LIKES)):
            kit.log("[warn] 游戏圈任务没全部达成, 仍继续尝试领奖")
        if not wxcircle.launch_game_lnk():
            kit.log("[warn] 桌面快捷方式不在, 请手动切回游戏")
        kit.nap(3.0)
        close_panel(sc)
        if not open_panel(sc):       # 重开面板才会刷新出「领取」
            return False

    if not args.extra.get("skip_claim"):
        kit.log(f"游戏圈页领取 {claim_rows(sc, 2)} 个")
        sc.click_base(*TAB_DESK, "切换「添加桌面」页签")
        kit.nap(1.8)
        if claim_rows(sc, 1) == 0:
            kit.log("[warn] 「添加桌面」页没找到可领的「领取」")

    close_panel(sc)
    if not args.no_back:
        kit.goto_home(sc)
    return True


if __name__ == "__main__":
    raise SystemExit(kit.run_case(
        "community_reward", "社区奖励（游戏圈点赞/评论 + 桌面礼包）", run,
        plan=PLAN, prefix="cr_", lock_ttl=900, th=TH,
        default_timeout=1200, extra=("--skip-wx", "--skip-claim"),
        extra_kv=("--likes",),
    ))
