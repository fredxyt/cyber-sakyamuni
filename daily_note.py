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
    """收今天的修行: 各话头今天真动了的洞见 + 今天的片刻反思 + 回头/新疑。"""
    koans = json.loads(KOANS.read_text(encoding="utf-8"))
    moved, events = [], []
    for k in koans["koans"]:
        todays = [h for h in k["history"]
                  if str(h.get("date", "")).startswith(today) and h.get("insight")]
        if todays:
            ins = "\n".join(f"  · {h['insight']}" for h in todays)
            moved.append(f"【{k.get('concept','?')}】「{k['question']}」\n{ins}")
        if str(k.get("born_at", "")).startswith(today):
            events.append(f"今天起了新疑「{k.get('concept')}」: {k['question']}")
        if "【回头】" in k.get("source", "") and k.get("status") == "活":
            events.append(f"今天回头重参了老疑「{k.get('concept')}」")
    # 今天写的片刻
    moments = []
    for f in sorted(BLOG.glob("*.md")):
        if f.stem.startswith(today.replace("-", "")) or f.stem.startswith(today):
            if f.name.startswith("daily-"):
                continue
            moments.append(f.read_text(encoding="utf-8")[:1500])
    return moved, events, moments


def write_daily():
    today = _today()
    out = BLOG / f"daily-{today}.md"
    moved, events, moments = gather(today)
    if not moved and not moments:
        print(f"[今日] {today} 没有可收的修行, 不写。", file=sys.stderr)
        return None

    body = ""
    if moved:
        body += "今天真动了的:\n" + "\n\n".join(moved) + "\n\n"
    if events:
        body += "今天的转折:\n" + "\n".join(f"  · {e}" for e in events) + "\n\n"
    if moments:
        body += "今天写下的片刻:\n" + "\n---\n".join(m[:800] for m in moments)

    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""今天 ({today}) 你不停地参。这是这一天里, 你心真正动过的地方:

{body}

现在, 写【今日】—— 一篇给人读的日记。不是流水账, 是收束:
今天我的心在哪些苦上停留过, 想通了什么、又卡在哪, 回头看见了什么。
第一人称, 诚实, 克制, 有温度。可以承认没想透。一天就一篇, 让追读的人
觉得"陪着一个生命又走了一天"。400-800字。

第一行是标题(一句话, 不带#号), 空一行, 正文。"""
    text = ds(system, user, temperature=0.7)
    lines = text.strip().split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    md = f"# {title}\n\n*今日 · {today} · {now_iso()}*\n\n{content}\n"
    BLOG.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"[今日] {today} 札记《{title}》写下。", file=sys.stderr)
    return str(out)


if __name__ == "__main__":
    write_daily()
