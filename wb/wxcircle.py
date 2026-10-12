"""微信游戏圈 —— 「社区奖励」跨窗口任务的公共层。

背景（2026-10-12 实探）:
    「社区奖励」的点赞/评论要跳到 **微信游戏** 顶层窗口。它不是微信主程序
    (WeChat.exe) 的窗口，而是与游戏**同一个进程**的独立顶层窗口, 标题就叫
    「微信游戏」, 客户区约 2099x1312。用 bot.find_game_window("微信游戏") 即可定位。

与 kit.Screen 的关系:
    微信窗口本身就直接套 kit.Screen —— 模板匹配/点击/dry/留证 全部复用, 无需另造一套。
    原因: match_adaptive 的候选里含「原生尺寸」一路, 按原生尺度裁的模板(wx_like 30x30)
    会在原生候选上 ~1.00 命中(实测), 而游戏那套 845x1521 基准照常不受影响。

为什么 .lnk 也放这里:
    从微信窗口回游戏最稳的方式是**触发桌面快捷方式**「雷霆战机：集结.lnk」(用户口径),
    而不是去点微信窗口的关闭键 —— 小游戏窗口关掉后未必回到游戏前台。
    收在本模块便于离线自检整体替换(自检时绝不能真的去 startfile)。
"""
from __future__ import annotations

import os
import time

from . import bot as _bot
from . import kit

WX_TITLE = "微信游戏"          # 微信小游戏容器窗口标题
LNK_PATH = r"C:\Users\21908\Desktop\雷霆战机：集结.lnk"
MIN_W = 1200                   # 微信窗口客户区最小宽度(排除小尺寸误命中)


def find_window():
    """定位「微信游戏」窗口；没有返回 None。"""
    return _bot.find_game_window(WX_TITLE, "")


def wait_screen(*, timeout: float = 25.0, th: float = 0.80, prefix: str = "wx_",
                dry: bool = False):
    """等微信游戏窗口出现；超时返回 None。

    点「前往」到窗口真正可交互实测约 3~6 秒，广告/冷启动会更久，故给 25 秒。
    """
    end = kit.now() + timeout
    while True:
        rect = find_window()
        if rect is not None and rect.w >= MIN_W:
            kit.log(f"微信游戏窗口 {rect}")
            return kit.Screen(rect, th=th, dry=dry, prefix=prefix)
        if kit.now() >= end:
            return None
        time.sleep(1.0)


def launch_game_lnk(path: str = LNK_PATH) -> bool:
    """触发桌面快捷方式把游戏窗口调回前台；返回快捷方式是否存在。"""
    if not os.path.exists(path):
        return False
    os.startfile(path)          # noqa: S606 - 用户指定的固定快捷方式
    return True
