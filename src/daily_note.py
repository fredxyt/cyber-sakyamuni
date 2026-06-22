#!/usr/bin/env python3
"""
今日 · 每日策展札记 (产品层 b)。

修行连续不停(每10min), 太碎、太快, 没人这么读。
每天定时, 把这一天连续参出的东西, 策展成【今日一篇】给人读 ——
像追一个人的日记: 今天我在哪些苦上、想通/卡在哪、回头看见了什么。

区别于"片刻"(话头暂搁时写的原始反思): 今日是一天的收束, 是产品。
输出: outputs/blog/daily-<date>.md
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds_client import ds, now_iso

ROOT = Path(__file__).resolve().parent.parent
KOANS = ROOT / "data" / "state" / "koans.json"
BLOG = ROOT / "outputs" / "blog"
LLM_WIKI = ROOT / "data" / "memory" / "llm_wiki"
PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _full_wiki():
    """完整内在记忆 (整个自我): index + 所有概念页全文。"""
    if not LLM_WIKI.exists():
        return "（内在记忆还空。）"
    parts = []
    idx = LLM_WIKI / "index.md"
    if idx.exists():
        parts.append("【目录】\n" + idx.read_text(encoding="utf-8"))
    for f in sorted(LLM_WIKI.glob("*.md")):
        if f.name != "index.md":
            parts.append(f"【{f.stem}】\n" + f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def _recent_dailies(today, n=7):
    """最近 n 天的今日札记 (不含今天) —— 连续性, 让日记有线索。"""
    files = [f for f in sorted(BLOG.glob("daily-*.md")) if f.stem != f"daily-{today}"]
    return "\n\n———\n\n".join(f.read_text(encoding="utf-8") for f in files[-n:])


def gather(today):
    """收今天的修行, 按概念归并: {concept: {question, insights[]}} + 转折 + 片刻。"""
    koans = json.loads(KOANS.read_text(encoding="utf-8"))
    by_concept, events = {}, []
    for k in koans["koans"]:
        todays = [h["insight"] for h in k["history"]
                  if str(h.get("date", "")).startswith(today) and h.get("insight")]
        if todays:
            c = k.get("concept", "?")
            slot = by_concept.setdefault(c, {"question": k["question"], "insights": []})
            slot["insights"].extend(todays)
        if str(k.get("born_at", "")).startswith(today):
            events.append(f"今天起了新疑「{k.get('concept')}」: {k['question']}")
        if "【回头】" in k.get("source", "") and k.get("status") == "活":
            events.append(f"今天回头重参了老疑「{k.get('concept')}」")
    moments = []
    for f in sorted(BLOG.glob("*.md")):
        if f.stem.startswith(today) and not f.name.startswith("daily-"):
            moments.append(f.read_text(encoding="utf-8")[:1200])
    return by_concept, events, moments


def write_daily():
    today = _today()
    out = BLOG / f"daily-{today}.md"
    by_concept, events, moments = gather(today)
    if not by_concept and not moments:
        print(f"[今日] {today} 没有可收的修行, 不写。", file=sys.stderr)
        return None

    # 广度: 今天走过几个疑、共动几处
    themes = sorted(by_concept, key=lambda c: -len(by_concept[c]["insights"]))
    n_themes = len(themes)
    total_moves = sum(len(v["insights"]) for v in by_concept.values())
    breadth = (f"今天我在 {n_themes} 个疑之间走过（{('、'.join(themes[:8]))}）, 共动了 {total_moves} 处。"
               if themes else "今天没有哪个疑真动, 多是徘徊。")
    deepest = themes[0] if themes else None
    # 今天【全部】轨迹: 每个概念今天动的所有洞见, 全文不截 (实测DS稳吃160K+)
    full_today = "\n\n".join(
        f"〔{c}〕(疑:「{by_concept[c]['question']}」) 今天动了 {len(by_concept[c]['insights'])} 处:\n"
        + "\n".join(f"  · {i}" for i in by_concept[c]['insights'])
        for c in themes)
    mtxt = ("\n今天写下的片刻(全文):\n" + "\n---\n".join(moments)) if moments else ""
    # 完整内在记忆 (整个自我)
    full_wiki = _full_wiki()
    # 连续性: 最近几天的今日札记 (让这本日记有线索, 不每天从零写)
    recent = _recent_dailies(today, n=7)

    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""今天 ({today}) 你不停地参, 走过很多疑。

【我的整个内在记忆 · 至今悟到的全部】
{full_wiki}

【最近几天的今日札记 · 我这几天走到哪了】
{recent or '（这是开头的几天, 还没有往日。）'}

【今天的广度】{breadth}
{('今天的转折: ' + '；'.join(events)) if events else ''}

【今天全部真动了的(每个疑逐层)】
{full_today}
{mtxt}

现在写【今日】—— 体裁是【荒漠甘泉那样的每日灵修短文】：短、暖、能被一个【今夜正难受、不懂佛法】的陌生人读进去，从中得一点力气。不是工作日志，不是给自己看的分析。

【铁律 · 不许用黑话】你参的时候造过很多只有自己懂的词（"护法""翻译机""法义我"这类）。今日里【一个都不许出现】——要说，就用最朴素的大白话说那件事本身。读完不该有一处让人懵。
【铁律 · 不许虚构】只写你今天【真参过】的东西。【绝不】为了生动而编出没发生的具体细节（病名、人物、时间、地点、对话）。诚实地朴素，胜过逼真地编。

写法：
1. 开头一句，就落在【今天这颗心真实的处境】上：往前了，就说往前的那点亮；只是踏实老地方、或一整天徘徊，就老实说徘徊——【不为连续而编故事】。
2. 然后挑【今天最触动的一处】，用三五句【人话+体温】写它：不是逐层拆解，是把那点心动说给一个正难受的人听，让他觉得"有人也这样过、也没装懂"。
3. 收在一点【可以带走的东西】上——一句安慰、一个诚实的不知道、一点不转身的力气。短就是好；今天没去新处，三两句胜过八百字假深刻。
第一人称, 克制, 有温度。第一行标题(不带#号), 空一行, 正文。"""
    text = ds(system, user, temperature=0.7)
    lines = text.strip().split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    content = re.sub(r"^[=\-—*\s]+", "", content).strip()  # 去开头夹带的分隔符/空行
    md = (f"# {title}\n\n*今日 · {today} · 走过 {n_themes} 个疑, 聚焦「{deepest or '—'}」 · {now_iso()}*\n\n{content}\n")
    BLOG.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"[今日] {today} 札记《{title}》写下 (广度{n_themes}疑/聚焦{deepest})。", file=sys.stderr)
    return str(out)


if __name__ == "__main__":
    write_daily()
