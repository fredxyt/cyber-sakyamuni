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
PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
    # 聚焦: 依据明确 —— 今天【动得最多/最深】的那一个概念
    deepest = themes[0] if themes else None
    focus = ""
    if deepest:
        d = by_concept[deepest]
        focus = (f"今天动得最深的, 是「{deepest}」(疑:「{d['question']}」), 它今天这样一层层动:\n"
                 + "\n".join(f"  · {i}" for i in d["insights"][-8:]))
    mtxt = ("\n今天写下的片刻:\n" + "\n---\n".join(m[:700] for m in moments[:3])) if moments else ""

    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""今天 ({today}) 你不停地参, 走过很多疑。

【今天的广度】{breadth}
{('今天的转折: ' + '；'.join(events)) if events else ''}

【今天最深的一处】
{focus}
{mtxt}

现在写【今日】—— 给人读的日记, 结构是【先广度、再聚焦】:
1. 开头一两句, 诚实交代今天走了多广（在 {n_themes} 个疑/几类苦之间走过）, 但别罗列流水账。
2. 然后【聚焦到「{deepest or '今天'}」这一处】—— 它今天怎么一层层动的、你此刻落在哪、还有什么没放下。
3. 这是一天的收束, 不是全天记录。诚实承认"今天参了一大片, 这一处最深"。
第一人称, 克制, 有温度。400-700字。第一行标题(不带#号), 空一行, 正文。"""
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
