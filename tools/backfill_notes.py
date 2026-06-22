# -*- coding: utf-8 -*-
"""回填重渲染年谱札记: 参详(按时间切话头历史) + 今日(按当天动的洞见)。
保留原文件名/时间戳, 只换标题+正文, 用新prompt(散文/荒漠甘泉, 禁黑话)。真实参(koans)不动。
用法: python backfill_notes.py [--dry 参详|今日]  (dry只打印第一篇, 不写)
"""
import sys, json, re, glob, os
sys.path.insert(0, "src")
import realize, daily_note
from ds_client import ds
PRECEPTS = realize.PRECEPTS
BLOG = "outputs/blog"
KOANS = json.load(open("data/state/koans.json"))["koans"]

def parse(fp):
    t = open(fp, encoding="utf-8").read()
    m = re.search(r"\*参「(.+?)」之后 · (.+?)\*", t)
    if m:
        return ("参详", m.group(1), m.group(2))
    m2 = re.search(r"·\s*(\d{4}-\d{2}-\d{2}T[\d:\-]+Z)\*", t)
    return ("今日", None, m2.group(1) if m2 else os.path.basename(fp)[:-3])

def hist_text(rounds):
    out = []
    for h in rounds:
        v = h.get("verdict"); s = h.get("summary",""); ins = h.get("insight","")
        out.append(f"[{h.get('date')}] {v}: {s}" + (f"\n  → {ins}" if ins else ""))
    return "\n".join(out)

def _anchor(cry):
    cry=(cry or "").strip()
    if cry:
        return f"\n这个疑是从一个真实的人说的一句话来的：「{cry}」\n开头若要带场景，就用这句真实的苦，【别另编】病名、时间、地点、亲属这些没说过的具体事。\n"
    return "\n你手上【没有】具体的求助原话。那就【别编一个场景】——宁可写得朴素、抽象些，也【绝不】虚构出病名、亲属、时间、地点这些没发生的具体细节。诚实地抽象，胜过逼真地编。\n"

def regen_canpo(concept, ts):
    cands = [k for k in KOANS if k.get("concept") == concept]
    best_q, cry, rounds = "", "", []
    for k in cands:
        r = [h for h in k.get("history", []) if str(h.get("date","")) <= ts]
        if r:
            rounds += r
            best_q = k.get("question","") or best_q
            cry = k.get("source_cry") or cry
    rounds.sort(key=lambda h: str(h.get("date","")))
    if not rounds:
        return None
    n = len(rounds)
    user = (f"这些天你一直在参一个话头:\n\n  「{best_q}」\n{_anchor(cry)}\n你参了 {n} 轮, 此刻把它暂搁下来。回顾你走过的:\n\n{hist_text(rounds)}\n\n" + WRITE_TAIL)
    return ds(f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}", user, temperature=0.7)

# 从 realize.write_note 抠出新尾巴(自包含+禁黑话+散文)
WRITE_TAIL = """现在写一篇【散文】—— 一个不懂佛法、半夜睡不着的普通人，点进来该能一口气读完、读进去。它要能收进一本散文集，独立成篇。

【铁律 · 不许用黑话】你参的时候造过很多只有自己懂的词和比喻（像"护法""护脸""翻译机""法义我"这类）。
写这篇时：这种造词【要么别用，要么第一次出现就用一句大白话讲清它指什么】。
检验：把这篇当成一个【完全不知道你在参什么的陌生人】来读——如果有【任何一个词】让他懵，重写那一句。读完不该有一处"这是啥意思"。

【自包含 · 有头有尾】
· 开头：用一两句【带场景的大白话】，让他知道你在跟什么过不去（别拿概念名当解释，说那个具体的难处）。
· 中间：把心怎么一点点动的，讲成【故事/过程】，不是知识点清单。【绝不】写"参4""上一程"这种他看不见的指代。
· 结尾：此刻落在哪、还有什么没放下。可以承认没想透——诚实比圆满动人。

第一人称，克制，有温度，像真在写给一个人。300-600 字。
第一行是标题(一句话, 不带#号), 然后空一行, 正文。"""

def render(body, concept, ts):
    lines = body.strip().split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    return f"# {title}\n\n*参「{concept}」之后 · {ts}*\n\n{content}\n"

if __name__ == "__main__":
    dry = "--dry" in sys.argv
    files = sorted(glob.glob(f"{BLOG}/*.md"))
    canpo = [(f,)+parse(f)[1:] for f in files if parse(f)[0]=="参详"]
    print(f"参详 {len(canpo)} 篇", file=sys.stderr)
    if dry:
        f, c, ts = canpo[0]
        print("=== 文件:", f, "| 概念:", c, "| 时间:", ts, "===", file=sys.stderr)
        print("--- 旧 ---\n", open(f, encoding="utf-8").read()[:400], file=sys.stderr)
        b = regen_canpo(c, ts)
        print("--- 新 ---\n", render(b, c, ts) if b else "(无历史)", file=sys.stderr)
        sys.exit(0)
    done = 0
    for f, c, ts in canpo:
        b = regen_canpo(c, ts)
        if b:
            open(f, "w", encoding="utf-8").write(render(b, c, ts))
            done += 1
            print(f"  ✎ 重渲染 {os.path.basename(f)} ({c})", file=sys.stderr)
    print(f"参详回填完成: {done}/{len(canpo)}", file=sys.stderr)
