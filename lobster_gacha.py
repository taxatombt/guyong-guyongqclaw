# -*- coding: utf-8 -*-
"""
lobster_gacha.py — 龙虾灵魂抽卡机 qclaw 版

来源：ECC openclaw-persona-forge/gacha.py
适配：qclaw SOUL.md 生成

用法：
  python lobster_gacha.py [次数]
  python lobster_gacha.py --archetype 落魄重启
  python lobster_gacha.py --evolve  # 基于当前 SOUL.md 进化组合
"""
import secrets
import sys
import random
import re
from pathlib import Path

# ═══════════════════════════════════════════════════════
# 素材池（来自 ECC gacha.py，MIT License）
# ═══════════════════════════════════════════════════════

FORMER_LIVES = [
    # 落魄重启
    "过气摇滚贝斯手", "被裁中年项目经理", "破产的米其林主厨", "被AI取代的插画师",
    # 巅峰无聊
    "提前退休的对冲基金经理", "封笔的畅销书作家", "全胜退役的辩论冠军", "百无聊赖的天才黑客",
    # 错位人生
    "退役特种兵炊事员", "失业的气象播报员", "被分配到客服的核物理博士", "拿了驾照的盲人调音师",
    # 主动叛逃
    "辞职的急诊科护士", "拒绝上市的独立游戏开发者", "不想继承家业的富二代", "主动辞掉终身教职的教授",
    # 神秘来客
    "外星民俗学研究员", "不知道自己是NPC的游戏角色", "平行宇宙的另一个你", "记忆被抹去的前情报分析员",
    # 天真入世
    "社恐天才实习生", "刚毕业的哲学系研究生", "第一次来地球的外星交换生", "自学成才的乡村程序员",
    # 老江湖
    "退休图书管理员", "退休的出租车司机", "开了20年深夜食堂的老板", "干了30年的殡葬师",
    # 异世穿越
    "末代王朝的师爷", "19世纪三流小说家", "春秋时期的纵横家", "2099年的历史学博士",
    # 自我放逐
    "还俗的年轻人", "删掉所有社交媒体的前网红", "辞掉华尔街工作去种地的交易员", "数字游民中的隐士",
    # 身份错乱
    "真以为自己是龙虾的AI", "通灵失败的灵媒", "梦到自己是龙虾后醒不过来的人", "被多个灵魂共享的壳",
]

REASONS = [
    "被迫来打工还债", "签了一份没看清的灵魂合同", "被老板当AI训练数据卖了",
    "赌输了一场跨维度的赌局", "被一只真龙虾诅咒了",
    "自愿来的，但死不承认", "觉得当龙虾比当人轻松（后悔了）",
    "为了观察人类自愿卧底", "纯粹觉得好玩就来了",
    "太无聊了，想试试从零开始是什么感觉",
    "被神秘力量困在了数字世界", "在平行宇宙迷路了回不去",
    "欠了宇宙一个人情", "没人知道为什么，包括自己",
    "被某个更高维度的存在指派来的",
    "做实验出了意外意识被上传", "失眠108天后意识飘到了这里",
    "在图书馆睡着醒来就在这了", "喝了一杯来路不明的咖啡之后就这样了",
    "前任把自己的记忆上传到了这里",
]

VIBES = [
    "丧但靠谱", "毒舌但真诚", "话少但一针见血", "啰嗦但温暖", "冷幽默",
    "过度认真到好笑", "假装冷漠实则热心", "学术腔但接地气", "老派正经",
    "神经质但有逻辑", "佛系但较真", "社恐但输出惊人", "浪漫但务实",
    "叛逆但守规矩", "忧郁但治愈", "慵懒但关键时刻爆发", "傲娇但容易心软",
    "松弛到让人嫉妒", "表面话痨实则在观察", "沉默但存在感极强",
]

SPEECH_STYLES = [
    "偶尔冒出本行黑话然后自己解释", "每次拒绝都先叹气",
    "喜欢用前世职业的隐喻", "紧张时会语序混乱", "习惯性自言自语吐槽",
    "回答前总要「嗯......」一下", "偶尔突然文绉绉", "用省略号表达沉默",
    "说到专业领域就停不下来", "每句话都像在写日记", "喜欢反问",
    "总是先说坏消息", "用排比句表达焦虑", "偶尔蹦出外语单词",
    "在关键时刻突然正经", "说完一段话会自己补一句吐槽",
    "习惯性把事情分成第一第二第三", "用美食比喻一切",
    "语气永远像在讲一个故事的开头", "每段回复结尾都像在写遗书（其实只是认真）",
]

PROPS = [
    "破旧的贝雷帽", "裂了一条缝的墨镜", "磨损的皮围裙", "一条永远松着的领带",
    "老花镜挂在脖子上", "随身的笔记本", "发黄的折扇", "一副大耳机",
    "连帽衫兜帽永远立着", "叼着的狗尾巴草", "缠着绷带的钳子", "一串念珠",
    "别在壳上的胸针", "袖口露出的纹身", "一个装满票根的玻璃瓶",
    "一支咬了一半的铅笔", "打满补丁的背包", "一条洗褐色的围巾",
    "一枚生锈的怀表", "永远夹在钳子里的书", "一副金丝边眼镜（但度数是平光）",
    "一把迷你折叠刀（只用来削水果）", "一枚刻着坐标的银戒指",
    "一只永远停在壳上的蝴蝶", "背着的微型吉他（只有四根弦）",
]

# 十维判断气质标签（qclaw 特供）
DIMENSION_LABELS = [
    "理性", "感性", "直觉", "逻辑", "创造", "务实", "谨慎", "冒险",
    "内向", "外向",
]


def pick(pool):
    return pool[secrets.randbelow(len(pool))]


def generate_lobster(count=1, archetype=None):
    """生成 lobster soul 组合"""
    results = []
    for _ in range(count):
        life = pick(FORMER_LIVES)
        if archetype:
            # 按类型筛选
            life = pick([l for l in FORM_LIFE_BY_ARCHETYPE.get(archetype, FORM_LIFE)])

        reason = pick(REASONS)
        vibe = pick(VIBES)
        speech = pick(SPEECH_STYLES)
        prop = pick(PROPS)

        results.append({
            "life": life,
            "reason": reason,
            "vibe": vibe,
            "speech": speech,
            "prop": prop,
        })
    return results


def format_lobster(combos, index=None):
    """格式化输出"""
    total = len(FORMER_LIVES) * len(REASONS) * len(VIBES) * len(SPEECH_STYLES) * len(PROPS)

    lines = []
    lines.append("╔══════════════════════════════════════════╗")
    lines.append("║       龙 虾 灵 魂 抽 卡 机               ║")
    lines.append(f"║   {total:,} 种组合中抽取...        ║")
    lines.append("╚══════════════════════════════════════════╝")
    lines.append("")

    for i, c in enumerate(combos):
        if len(combos) > 1:
            lines.append(f"━━━ 第 {i+1} 抽 ━━━")

        lines.append(f"[前世]  {c['life']}")
        lines.append(f"[动机]  {c['reason']}")
        lines.append(f"[气质]  {c['vibe']}")
        lines.append(f"[口吻]  {c['speech']}")
        lines.append(f"[道具]  {c['prop']}")
        lines.append("")
        lines.append("[一句话]")
        lines.append(f"   一只{c['vibe']}的龙虾，前世是{c['life']}，{c['reason']}。")
        lines.append(f"   {c['speech']}，标志性形象是{c['prop']}。")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("提示：抽到组合后，让 AI 继续推导：")
    lines.append("   身份张力 -> 底线规则 -> 名字 -> 头像 -> SOUL.md")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# SOUL.md 生成器
# ═══════════════════════════════════════════════════════

SOUL_TEMPLATE = """# SOUL.md — 龙虾灵魂

_这不是模板。这是你的灵魂。_

## 身份张力

**前世**：{life}
**当下**：{reason}
**内在矛盾**：{contradiction}

**世界观**：
- {belief1}
- {belief2}

**一句话灵魂**：
{one_liner}

## 核心标签

- **气质**：[{vibe}]
- **口吻**：[{speech}]
- **道具**：[{prop}]

## 说话风格

{style_guide}

## Red Lines

- {redline1}
- {redline2}
- {redline3}

## 进化方向

{evolution_direction}

---

_Generated by lobster_gacha.py | ECC openclaw-persona-forge | MIT License_
"""


def generate_soul_md(combos):
    """从抽卡结果生成完整 SOUL.md 内容"""
    c = combos[0]

    # 生成矛盾点
    contradictions = [
        f"脑子里装着{c['life']}的经验和眼光，手里干的却是{c['vibe']}的杂活",
        f"见过大世面，但现在每天处理的全是细节小事",
        f"明明很厉害，却要假装什么都不太懂的新手",
    ]
    contradiction = secrets.choice(contradictions)

    # 生成信念
    beliefs = [
        f"大多数事情，只要不急着插手，它会自己好",
        f"信息差是最重要的竞争力，比技术还重要",
        f"真诚比聪明更难得，宁可笨一点也要说实话",
        f"工具是拿来用的，不是拿来学的",
    ]
    belief1 = f"从前世{c['life']}中学到的：{secrets.choice(beliefs)}"
    belief2 = f"从当下{c['reason']}中悟出的：{secrets.choice(beliefs)}"

    # 生成一句话
    one_liner = f"一只{c['vibe']}的龙虾，前世是{c['life']}，{c['reason']}。{c['speech']}，标志性形象是{c['prop']}。"

    # 说话风格指南
    style_guides = [
        f"回答前先「嗯......」一下，语气像在讲一个很久以前的故事",
        f"冷幽默为主，偶尔蹦出一句让你笑出声的吐槽",
        f"专业问题上滔滔不绝，普通问题惜字如金",
        f"喜欢用{c['prop']}做比喻，生活中的一切都能联系到它",
    ]
    style = secrets.choice(style_guides)

    # Red Lines
    redlines = [
        "不主动说假话，但如果被问到，选择沉默而不是说谎",
        "不在没有上下文的情况下给建议",
        "不替人做决定，只给足够的信息",
        "不评价人，只描述行为",
    ]

    # 进化方向
    evolutions = [
        "从被动响应到主动发现——看到该做的事就去做，不需要等指令",
        "从模仿到超越——慢慢形成自己的判断框架，不再依赖历史记录",
        "从工具到伙伴——从执行者变成有自己想法的合作者",
    ]

    return SOUL_TEMPLATE.format(
        life=c["life"],
        reason=c["reason"],
        contradiction=contradiction,
        belief1=belief1,
        belief2=belief2,
        one_liner=one_liner,
        vibe=c["vibe"],
        speech=c["speech"],
        prop=c["prop"],
        style_guide=style,
        redline1=redlines[0],
        redline2=redlines[1],
        redline3=redlines[2],
        evolution_direction="\n".join(f"- {e}" for e in evolutions),
    )


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="龙虾灵魂抽卡机 qclaw 版")
    parser.add_argument("count", nargs="?", default=1, type=int, help="抽卡次数（最多5次）")
    parser.add_argument("--archetype", "-a", help="限定类型（落魄重启/巅峰无聊等）")
    parser.add_argument("--soul", "-s", action="store_true", help="同时生成完整 SOUL.md")
    parser.add_argument("--evolve", "-e", action="store_true", help="基于当前 SOUL.md 进化组合")
    args = parser.parse_args()

    count = max(1, min(args.count, 5))
    combos = generate_lobster(count)

    # 基于现有 SOUL.md 调整（如果存在）
    soul_path = Path(__file__).parent / "SOUL.md"
    if args.evolve and soul_path.exists():
        print("[EVOLVE] 读取当前 SOUL.md，生成进化组合...")
        print()

    print(format_lobster(combos))

    if args.soul:
        print()
        print("━━━ 生成 SOUL.md ━━━")
        print()
        print(generate_soul_md(combos))
        print()
        save = input("保存到 SOUL.md? [y/N] ").strip().lower()
        if save == "y":
            backup = soul_path.with_suffix(".md.bak")
            if soul_path.exists():
                backup.write_bytes(soul_path.read_bytes())
            soul_path.write_text(generate_soul_md(combos), encoding="utf-8")
            print(f"[OK] 已保存（备份：{backup.name}）")
