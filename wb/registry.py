"""用例注册表 —— 全项目「有哪些脚本」的单一事实源。

新增一个用例 = ① 在对应目录丢一个 .py ② 在本文件登记一行。
之后 smoke 的清单校验、README 的清单表（tools/maint/docs.py 生成）全都读这里，
不会再出现「加了用例但文档/冒烟清单忘了改」这类漂移。

分组（tools/ 下的四个子目录）
    daily     15 个每日用例   tools/cases/     —— 一个用例一个文件，失败不互相影响
    crop      11 个裁剪工具   tools/crop/      —— 改坐标/加模板后重跑即可整页重裁
    selftest  14 个测试       tools/selftest/  —— 13 份离线回放自检 + 冒烟
    maint      7 个维护工具   tools/maint/     —— 运行期辅助/体检/文档生成

字段
    quota  每日额度（"-" 表示不限或非每日）
    flags  支持的开关（通用: --dry 永远有）
    kit    是否已迁到 wb/kit（渐进迁移标记；未迁的老用例仍能独立跑）
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DAILY, CROP, SELFTEST, MAINT = "daily", "crop", "selftest", "maint"
GROUP_DIR = {DAILY: "cases", CROP: "crop", SELFTEST: "selftest", MAINT: "maint"}
GROUP_TITLE = {DAILY: "每日用例", CROP: "裁剪工具", SELFTEST: "测试/自检", MAINT: "维护工具"}


@dataclass(frozen=True)
class Entry:
    name: str
    title: str
    group: str
    repo: str            # 相对仓库根的路径
    quota: str = "-"
    flags: str = "--dry"
    note: str = ""
    kit: bool = False


def _e(name: str, title: str, group: str, *, quota: str = "-", flags: str = "--dry",
       note: str = "", kit: bool = False) -> Entry:
    return Entry(name, title, group, f"tools/{GROUP_DIR[group]}/{name}.py",
                 quota=quota, flags=flags, note=note, kit=kit)


# --------------------------------------------------------------- 每日用例（14）
CASES = [
    _e("free_stamina", "免费体力", DAILY, quota="4/日", flags="--dry --max=N", kit=True,
       note="点击生效判据=「免费」按钮消失(非页面变化)；弹窗在场不重复点入口"),
    _e("free_sweep", "免费扫荡卡", DAILY, quota="5/日", flags="--dry --max=N", kit=True,
       note="卡4 的免费按钮无模板 → 由卡图标中心下移 128px 算出；只吃第 4 个免费位"),
    _e("free_gift", "商城免费礼包", DAILY, quota="1/日", kit=True,
       note="免广告直发 / 看广告两形态都要兼容"),
    _e("free_explore", "星际探索", DAILY, flags="--dry --max=N", kit=True,
       note="整页阈值 0.90；exp_claim 须 ≥0.93；弹窗开着但无领取键=次数耗尽"),
    _e("sweep_stage", "扫荡关卡", DAILY, quota="普通5/5+英雄5/5",
       flags="--max N --material N --dry", kit=True,
       note="⭐ 材料最少优先(4 图标按计数升序→默认第 1 个) + 双倍奖励(每关每日限次→无翻倍换关，连续 3 关才收工) + ensure_context 防误关面板 + 背包满先清理再重进"),
    _e("boss_mode", "BOSS 闪击", DAILY, quota="3/站/轮 × 4 站",
       flags="--station <站> --dry", kit=True,
       note="四站轮转；「次数耗尽」提示可叠任意页→prompt 最优先；装备UP键列表页误命中→阈值 0.92；战斗间隙回站内页需连续 3 次才算打完"),
    _e("missile_hunt", "导弹猎场闪击", DAILY, quota="2/日(游戏默认，消耗体力)",
       flags="--dry", kit=True,
       note="活动关卡页两张卡「闪击」键**同款**(0.998/0.978) → 用卡标题 mh_title 锚定 + 偏移(601 帧上量得 301,176，按窗口缩放)；残留对话框直接闪击；「次数已耗尽」提示叠在活动关卡页上→prompt 最优先；对话框「闪击 N 次」不擅改(改次数=改消耗)"),
    _e("free_treasure", "寻宝", DAILY, flags="--dry --max=2", kit=True,
       note="装备宝箱 + 高级装备宝箱两张卡的免费广告，各扣 1 次；广告中绝不点屏幕"),
    _e("free_turn", "转盘", DAILY, quota="1/日", flags="--dry --max=1", kit=True,
       note="⭐ 只在 turn_daily ≥0.85 时点；「购买💎30」是冷却付费键，绝不点"),
    _e("free_star", "兑换星辉", DAILY, quota="1/日", flags="--dry --max=1", kit=True,
       note="认「带红点的四角金币」；底栏「转盘」红点与本用例无关，别被带偏"),
    _e("free_rally", "十年集结", DAILY, quota="宝箱+弹幕各1/日", flags="--dry --no-wish", kit=True,
       note="⭐ 首页「寻宝下方第一张卡」是活动卡翻页区 → 翻出金卡才能点进集结页"),
    _e("guild_donate", "战队捐献", DAILY, quota="金 3/日 + 钻 3/日",
       flags="--type gold|diamond|both --times N --all [--dry]", kit=True,
       note="入口在卡片**底部黄键**(226,1129 / 612,1129)，点卡片正中无效；半透明遮罩判层；丢点击重试不重复捐"),
    _e("friend_stamina", "好友体力", DAILY, quota="1/日(30/30 封顶)",
       flags="--dry --max=N", kit=True,
       note="入口=首页「无尽模式」正上排最左的**小人 icon**(friend_btn)；回礼弹窗「成功向好友送出了体力」确认后 +150 体力(可超上限)；满 30/30 后再点**无任何弹层**(静默无效，不是「次数不足」提示层) → 用键上红角标(像素计数)区分「丢点击」与「今日已无待收」；键外观收赠前后**逐像素相同**(差 0.0)不能判已领；「好友」标题牌是**通用标题牌**(其它页 0.883 误命中) → 页面标志用 fr_counter"),
    _e("star_supply", "逐星补给", DAILY, quota="领5次=50信标/次 + 信标×5 各1/日",
       flags="--dry --times N --no-back", kit=True,
       note="入口=闯关页「逐星长阶」横幅(stage_stair，美术会轮换→只裁文字)→左下「逐星补给」(ss_entry)"
            "→面板「领5次」(ss_claim5，**×1/×5 是领几次不是价格，每次 10 逐星信标**，领5次花 50 → 得 5×(黑匣密钥30+金币3000))"
            "→恭喜获得「领取」(claim_btn 复用)→面板 X(ss_close)→长阶页 ×5 装置(ss_beacon，可领带红点/已领**装置整个消失**)"
            "→逐星信标×5；领5次是消耗动作默认只做 1 次且**无覆盖层不重试**(防重复消耗)，×5 免费可重试；"
            "面板半透明压暗(ss_entry 在面板下仍 0.97)→判层必须 PANEL 先于 STAIR；按钮坐标目测差 8px 就点空→用颜色测 bbox"),
    _e("endless_world", "无尽模式-世界竞赛", DAILY, quota="6/日",
       flags="--times N --allow-capped [--dry] [--no-back]", kit=True,
       note="闪击次数用尽会自动改用「匹配」；挑战币达上限默认放弃(必须 --allow-capped 才跑)；"
            "战前准备买道具前先读图标左上角金徽标的持有数(wb/icount.py，实测徽标=持有数)："
            "已有 ≥3 不买(省钱)，1/2 补到 3，无徽标按 0 照买，徽标认不出保守不买(存图留证)；"
            "得分≥400万 由 wb/bscore.py 逐字读数驱动拖顶收尾(需连续两次复核；读数不可信一律判未达)；"
            "拖顶时机：明确≥400万(复核两次)或超时兜底(保留原设计)；判分收紧后不再出现假阳性提前拖；"
            "回首页用 nav_home 而**非** kit.goto_home 的 ral_back（实测世界竞赛页 nav_home 0.975 vs "
            "ral_back 0.867、结算页 ral_back 0.000）；时间走 kit.now/nap（自检虚拟时钟可拦）；"
            "dry 出计划且 exit=0（点击不生效→跨页步骤不规划，无法真验流程）"),
]

# --------------------------------------------------------------- 裁剪工具（11）
CROPS = [
    _e("crop_home", "首页模板裁剪", CROP, flags="-", note="首页组 + 弹窗（如体力弹窗）"),
    _e("crop_stage", "闯关/扫荡模板裁剪", CROP, flags="-", note="扫荡面板、关卡页、材料图标"),
    _e("crop_boss", "BOSS 列表页裁剪", CROP, flags="-", note="BOSS 入口/空间站名/仓库键"),
    _e("crop_boss_flash", "BOSS 闪击链路裁剪", CROP, flags="-",
       note="站内闪击→对话框→钻石确认→局内复活→结算页"),
    _e("crop_rift", "星际探索裁剪", CROP, flags="-", note="探索页/领取/快速探索/关闭"),
    _e("crop_treasure", "寻宝裁剪", CROP, flags="-", note="寻宝页页签 + 两张宝箱卡"),
    _e("crop_turn", "转盘裁剪", CROP, flags="-",
       note="⭐ turn_daily(免费) 与 turn_paid(付费30💎) 必须留足区分度"),
    _e("crop_exchange", "兑换星辉裁剪", CROP, flags="-", note="兑换页页签 + 红点四角金币"),
    _e("crop_guild", "战队捐献裁剪", CROP, flags="-", note="含确认弹窗/勾选框/次数不足提示层"),
    _e("crop_rally", "十年集结裁剪", CROP, flags="-", note="首页活动卡 + 集结页 + 弹幕面板"),
    _e("crop_star", "逐星补给裁剪", CROP, flags="-",
       note="长阶页入口/×5 装置(**必须裁可领态**: 已领后装置整个消失) + 补给面板领5次键/X；"
            "两源图分两次 run_crop，另做跨页核验(4 模板在闯关页/首页须 ≤0.86)"),
]

# --------------------------------------------------------------- 测试/自检（12）
SELFTESTS = [
    _e("free_turn_selftest", "转盘离线自检", SELFTEST, kit=True,
       note="7 用例：导航/已在页/免费态/冷却护栏/dry 零副作用/领取/并发锁"),
    _e("free_star_selftest", "兑换星辉离线自检", SELFTEST, kit=True,
       note="6 用例：导航/已在页/金币→领取→校验/已领护栏/dry 零副作用/并发锁"),
    _e("free_treasure_selftest", "寻宝离线自检", SELFTEST, kit=True,
       note="4 用例：广告中零点击(安全属性)/广告播完才关/按 x 升序双宝箱/dry/并发锁；"
            "广告与领取帧为模板合成，底帧为实测帧"),
    _e("free_stamina_selftest", "免费体力离线自检", SELFTEST, kit=True,
       note="5 用例：首页假阳性帧(合成 stamina_close 0.897≈实测 0.904)旧判在场/新判不在场＋收尾零点击"
            "＋首页仍点体力入口＋真弹窗仍判在场(灰键 0.73 非免费)＋次数耗尽全链路点真 X 收尾；"
            "修 POPUP_TH=0.95（默认 0.86 会把首页轮播误判成弹窗）"),
    _e("free_rally_selftest", "十年集结离线自检", SELFTEST, kit=True,
       note="6 用例：全链路 9 点逐步比对金标准 / 已领跳过 / 未知页中止 / dry / --no-wish / 并发锁"),
    _e("boss_mode_selftest", "BOSS 闪击离线自检", SELFTEST, kit=True,
       note="11 用例：12 张真帧判页（跑生产 page() 本体）＋导航/别站兜回/次数用尽跳过 ＋局内状态机(复活>装备UP>结算)＋技能周期补点＋站内停留 2 次不算打完/3 次算完 ＋dry＋并发锁；局内 3 帧为深底+真模板合成"),
    _e("guild_donate_selftest", "战队捐献离线自检", SELFTEST, kit=True,
       note="6 用例（7 张真帧）：四层半透明遮罩判层 + 勾选框颜色三态 + 全链路 10 点比对金标准"
            " + 丢点击重试(领取只点 1 次) + 次数用尽收层 + 未知页零点击 + dry + 并发锁"),
    _e("sweep_stage_selftest", "扫荡关卡离线自检", SELFTEST, kit=True,
       note="14 用例：模式识别/切换＋导航＋4星页签(选中零点击/未选中点中心+20)＋材料最少优先(#1 点落 156,345、0=全部零点击)＋单轮(双倍+跳过卡不使用+关弹层)＋无翻倍换关＋连续 3 关收工＋背包满重进＋面板误关复查＋异尺寸(RECT=601)换算闸门＋dry＋并发锁"),
    _e("endless_world_selftest", "无尽模式(世界竞赛)离线自检", SELFTEST, kit=True,
       note="7 用例：①局内未达不拖→达标**复核一轮**才拖（首个达标读数 t≈23s、真拖 t≈34s）"
            "②首个读数就达标后回落 → 不许提前拖（只在超时兜底 t≈46s）③全程未达标走超时兜底"
            "④结算页「继续」→战绩页「返回」坐标与胜负 ⑤已回世界竞赛页零点击 ⑥dry 零副作用"
            "⑦并发锁；⚠ 定时帧 holds[0] 曾被 selftest_kit 瞬跳（已修）+ 断言曾用 epoch 比 BM"
            "（已改相对时刻）→ 两处假绿均已修，负向对照（FORCE 恒真/恒假）两项都 FAIL"),
    _e("friend_stamina_selftest", "好友体力离线自检", SELFTEST, kit=True,
       note="7 用例（4 张当天真帧）：回礼弹窗**只压中屏**(fr_counter/fr_onekey 在弹窗下仍 1.000)"
            " → 钉死「先弹窗后页面」判层顺序 + 红角标颜色三态 + 全链路 4 点金标准 + 残留弹窗先收掉"
            "/今日已满静默降级(不报错) + 丢点击重试到上限报失败 + 未知页零点击 + dry + 并发锁"),
    _e("star_supply_selftest", "逐星补给离线自检", SELFTEST, kit=True,
       note="8 用例（4 张当天真帧 + 2 张恭喜获得帧）：×5 装置「可领(带红点)/已领(装置整个消失)」两态"
            " + **面板半透明压暗**下 ss_entry 仍 0.97 → 钉死「先面板后长阶页」判层顺序"
            " + 领5次全链 4 点金标准(入口/领5次/领取/关闭) + 领5次**无覆盖层且计数未变→不重试**(防重复消耗)"
            " + 计数变了视为已领 + ×5 装置不在→跳过不报错 + 装置丢点击重试 + 未知页零点击 + dry + 并发锁"),
    _e("geom_selftest", "坐标几何离线自检", SELFTEST, kit=True,
       note="8 用例（无需夹具）：3 个**真帧**校准点(845→755,1296 / 812→738,1293 / 601→546,977)≤1px"
            " ＋基准↔客户区往返恒等 ＋标题栏 77px 不缩放 ＋croplab 裁剪与 click_base 点击同几何"
            " ＋同尺寸恒等/退化输入 ＋click_base 端到端 ＋「命中+偏移」的偏移随窗口缩放"
            " ＋用例常量口径审计(四角点 vs 位置+尺寸，混了 ROI 会静默变空)。"
            "锁「点歪」「ROI 恒空」两类回归：改成整图等比/混用口径立刻 FAIL"),
    _e("missile_hunt_selftest", "导弹猎场闪击离线自检", SELFTEST, kit=True,
       note="9 用例（7 张真机真帧 601x1143）：判页专场(含提示层优先/局内帧必须判 unknown)"
            " ＋两张卡同款闪击键归属(取离卡标题最近的 421,1003，不选另一张的 421,455)"
            " ＋导航 2 点 ＋次数用尽只点绿确认后跳过(不算失败) ＋残留对话框直接闪击"
            " ＋真局内帧不误判收工(且技能走**真模板**命中 546,977) ＋回活动关卡页连续 3 次才算完"
            " ＋dry ＋并发锁；局内 2 帧为灰底+真模板合成"),
    _e("smoke", "冒烟测试", SELFTEST, flags="-",
       note="配置/合成匹配/窗口枚举/点击 dry-run/注册表与脚本一致性"),
]

# --------------------------------------------------------------- 维护工具（7）
MAINT_TOOLS = [
    _e("live_check", "模板体检", MAINT, flags="[snap]",
       note="每张模板 vs 当前画面逐一评分，找 stale 模板/报当前页"),
    _e("battle_watch", "局内监控", MAINT, flags="--dry",
       note="战斗拖拽 + 血量监控（阵亡前留证）"),
    _e("close_popup", "弹窗压制", MAINT, flags="-", note="识别并关掉挡路弹窗"),
    _e("clear_bag", "背包清理", MAINT, flags="--force",
       note="背包满 → 金币去售卖 / 装备白装循环自动合成(到点不动为止) / "
            "经验合成(魔方取消勾选 + 残骸合成)；已 hook 进 sweep_stage"),
    _e("docs", "文档清单生成", MAINT, flags="--check",
       note="按 wb/registry.py 重写 README 的用例清单/结构树（--check 只校验同步）"),
    _e("build_digits", "重建机友加成小字模板", MAINT, flags="--shot x.png --truth ... --skip 930 --dry",
       note="源: 选择机友页 5 行战力真值；**高亮行必须 --skip**（配色不同会污染模板）；"
            "源数据无 3 → templates/digits 缺 dg3，未补（乱补会把 7/8/9 读成 3，是危险方向）"),
    _e("build_bscore_digits", "重建战内得分数字模板", MAINT, flags="--add shots/x.png=5012345 --dry",
       note="战内青蓝粗体是**独立字体**，不能拿 tools/maint/build_digits.py（机友小字）那套凑；"
            "现有源帧只覆盖 {0,1,2,3,4,6,9}, 缺 {5,7,8}"),
]

REGISTRY = {g: lst for g, lst in
            ((DAILY, CASES), (CROP, CROPS), (SELFTEST, SELFTESTS), (MAINT, MAINT_TOOLS))}
ALL = [*CASES, *CROPS, *SELFTESTS, *MAINT_TOOLS]


def by_group(group: str) -> list[Entry]:
    return REGISTRY[group]


def counts() -> dict[str, int]:
    """各分组实际条目数。

    docstring 里手写的那四个数字、以及 README 里的清单表，真值都来自这里；
    smoke 会拿它与 docstring 对照 —— 手写数字改漏了就 FAIL。
    """
    return {g: len(by_group(g)) for g in (DAILY, CROP, SELFTEST, MAINT)}


def entry(name: str) -> Entry:
    for e in ALL:
        if e.name == name:
            return e
    raise KeyError(name)


def ids(group: str | None = None) -> list[str]:
    return [e.name for e in (by_group(group) if group else ALL)]


def root() -> Path:
    return Path(__file__).resolve().parent.parent


def missing_files() -> list[str]:
    """登记了但文件不在（说明改名/挪目录后忘了更新注册表）。"""
    r = root()
    return [e.repo for e in ALL if not (r / e.repo).is_file()]


def unregistered() -> list[str]:
    """目录里有但没登记的脚本（说明新增用例忘了登记）。"""
    r = root()
    reg = {e.repo.replace("\\", "/") for e in ALL}
    out = []
    for group, d in GROUP_DIR.items():
        for p in sorted((r / "tools" / d).glob("*.py")):
            rel = p.relative_to(r).as_posix()
            if rel not in reg and not p.name.startswith("_"):
                out.append(rel)
    return out


def render_table(group: str) -> str:
    """渲染某组的 Markdown 清单（README / tools/maint/docs.py 用）。"""
    rows = [f"### {GROUP_TITLE[group]}（`tools/{GROUP_DIR[group]}/`，{len(by_group(group))} 个）",
            "",
            "| # | 用途 | 脚本 | 每日额度 | 开关 | 要点 |",
            "|---|---|---|---|---|---|"]
    for i, e in enumerate(by_group(group), 1):
        flags = e.flags.replace("|", "\\|")      # 表格里竖线必须转义
        rows.append(f"| {i} | {e.title} | `uv run python {e.repo}` | {e.quota} "
                    f"| `{flags}` | {e.note} |")
    return "\n".join(rows)


def render_structure() -> str:
    """渲染 README 的「结构」代码块（含动态计数）。"""
    tpl_count = len(list((root() / "templates").glob("*.png")))

    def names(lst: list[Entry]) -> str:
        return ", ".join(e.name for e in lst)

    return "\n".join([
        "```",
        "main.py            入口：check / snap（每日任务都在 tools/ 下独立运行）",
        "config.toml        阈值、拟人点击参数、窗口裁边",
        "wb/cfg.py          配置加载（路径/阈值/点击参数的唯一来源）",
        "wb/bot.py          窗口定位、截屏、模板匹配、拟人点击",
        "wb/kit.py          用例运行时脚手架（Screen / 统一 CLI / 单实例锁 / 广告流 / 回首页 / 看门狗）",
        "wb/registry.py     用例注册表（清单单一事实源：smoke 校验与 README 清单都读它）",
        "wb/selftest_kit.py 离线回放脚手架（实测帧 + 点击驱动状态机，零消耗验证分支）",
        "wb/croplab.py      模板裁剪/校验共享库（先校验后落盘）",
        f"tools/cases/       {len(CASES)} 个每日用例: {names(CASES)}",
        f"tools/crop/        {len(CROPS)} 个模板裁剪工具: {names(CROPS)}",
        f"tools/selftest/    {len(SELFTESTS)} 个测试: {names(SELFTESTS)}",
        f"tools/maint/       {len(MAINT_TOOLS)} 个维护工具: {names(MAINT_TOOLS)}",
        f"templates/         按钮模板图（{tpl_count} 张，由 crop_* 用例与运行期裁剪产出）",
        "shots/             截图：snap_* 校准源、*_selftest 判层夹具、montage 预览、坐标 CSV",
        "```",
    ])
