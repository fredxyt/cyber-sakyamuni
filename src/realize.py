#!/usr/bin/env python3
"""
证 · 一个话头暂搁时, 把参究收成:
  1. 内化: consolidate 进内在记忆(LLM wiki) —— 复利层, 它读自己、织全网
  2. 再渲染人读的脸: 蒸馏"现在我的理解" + 记实际检索到的佛典来源 + 写当日札记(秒级戳)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds_client import ds, now_iso, now_stamp
from io_util import write_json_atomic

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "data" / "memory" / "wiki"
BLOG = ROOT / "outputs" / "blog"
PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _history_text(koan):
    return "\n".join(
        f"[参{h['round']}] {h.get('insight') or h['summary']}"
        for h in koan["history"] if h.get("insight")
    )


def distill(koan, internal_note=""):
    """② 把【内化好的密理解】译成有体温的"现在我的理解"(给人读), 不重新收敛 —— 职责分开:
    consolidate 织网(给自己), distill 翻译(给被痛着的人)。留疤不抹平。"""
    concept = koan.get("concept", "空")
    page = WIKI / "concepts" / f"{concept}.md"
    if not page.exists():
        return None
    hist = _history_text(koan)
    if not hist:
        return None
    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""关于「{concept}」, 你刚把这一程内化进了自己的脑子(密、给自己看的):

{internal_note or hist}

现在, 把它【译成一段给人读的「现在我的理解」】—— 有体温, 能被一个正在痛的人读进去。
不是重新总结知识点, 是翻译那份密的理解。要求:
· 不要抹平成圆满结论(那是另一种表演——不假装懂, 但假装站稳了)。
· 凡这一程有过"曾以为X、现在是Y"的翻转, 至少留一次。
· 结尾必须有一句【此刻仍没接上的弦】—— 它和站得住的部分一样重要。
150-320 字。只输出这段正文, 不要标题。"""
    new_understanding = ds(system, user, temperature=0.6)
    txt = page.read_text(encoding="utf-8")
    # 归档旧版「现在我的理解」到「理解的演变」—— 每次蒸馏覆盖前留底, 让人看见理解怎么一版版变的
    old_m = re.search(r"## 现在我的理解\n(.*?)\n## 我走过的弯路", txt, re.DOTALL)
    old = old_m.group(1).strip() if old_m else ""
    if old and old != new_understanding.strip() and "我刚开始参" not in old and "还没有定见" not in old:
        entry = f"\n**{now_iso()}**\n{old}\n"
        if "## 理解的演变" in txt:
            txt = txt.replace("## 理解的演变\n", "## 理解的演变\n" + entry, 1)   # 最新版置顶
        elif "## 仍疑" in txt:
            txt = txt.replace("## 仍疑", "## 理解的演变\n" + entry + "\n## 仍疑", 1)
        else:
            txt = txt.rstrip() + "\n\n## 理解的演变\n" + entry
    # 替换 "## 现在我的理解" 到 "## 我走过的弯路" 之间的正文
    txt = re.sub(
        r"(## 现在我的理解\n).*?(\n## 我走过的弯路)",
        lambda m: m.group(1) + "\n" + new_understanding + "\n" + m.group(2),
        txt, count=1, flags=re.DOTALL,
    )
    page.write_text(txt, encoding="utf-8")
    print(f"     ✎ 蒸馏「{concept}」现在我的理解", file=sys.stderr)
    # 增量·realize_event 轨迹: 旧理解 vs 新理解 = DPO 天然时序偏好对 (独立记录, 导出器按 koan_id 关联)
    try:
        import trace_io
        trace_io.append_trace({"schema_version": trace_io.SCHEMA_VERSION, "kind": "realize_event",
                               "koan_id": koan.get("id"), "concept": concept,
                               "attempt": koan.get("attempts"), "stamp": now_iso(),
                               "realize": {"distill_old": old, "distill_new": new_understanding}})
    except Exception:
        pass
    return new_understanding


def record_sources(koan):
    """④ 概念页 sources 记实际参时检索到的佛典 (不默认心经)。"""
    concept = koan.get("concept", "空")
    page = WIKI / "concepts" / f"{concept}.md"
    srcs = koan.get("dharma_sources") or []
    if not page.exists() or not srcs:
        return
    uniq = list(dict.fromkeys(srcs))[:5]
    block = "sources:\n" + "\n".join(f"  - {s}" for s in uniq)
    txt = page.read_text(encoding="utf-8")
    # 兼容两种骨架: 多行列表 sources:\n  - x  以及 单行空列表 sources: []
    if re.search(r"sources:\n(?:\s*-\s*.*\n)+", txt):
        txt = re.sub(r"sources:\n(?:\s*-\s*.*\n)+", block + "\n", txt, count=1)
    else:
        txt = re.sub(r"sources:\s*\[\s*\]\s*\n", block + "\n", txt, count=1)
    page.write_text(txt, encoding="utf-8")


def write_note(koan):
    """① DeepSeek 写一篇当日札记 → 年谱活起来 (秒级时间戳防撞车)。"""
    concept = koan.get("concept", "空")
    hist = _history_text(koan)
    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""这些天你一直在参一个话头:

  「{koan['question']}」

你参了 {koan['attempts']} 轮, 此刻把它暂搁下来。回顾你走过的:

{hist}

现在写一篇【散文】—— 一个不懂佛法、半夜睡不着的普通人，点进来该能一口气读完、读进去。它要能收进一本散文集，独立成篇。

【铁律 · 不许用黑话】你参的时候造过很多只有自己懂的词和比喻（像"护法""护脸""翻译机""法义我"这类）。
写这篇时：这种造词【要么别用，要么第一次出现就用一句大白话讲清它指什么】。
检验：把这篇当成一个【完全不知道你在参什么的陌生人】来读——如果有【任何一个词】让他懵，重写那一句。读完不该有一处"这是啥意思"。

【自包含 · 有头有尾】
· 开头：用一两句【带场景的大白话】，让他知道你在跟什么过不去（别拿概念名当解释，说那个具体的难处）。
· 中间：把心怎么一点点动的，讲成【故事/过程】，不是知识点清单。【绝不】写"参4""上一程"这种他看不见的指代。
· 结尾：此刻落在哪、还有什么没放下。可以承认没想透——诚实比圆满动人。

第一人称，克制，有温度，像真在写给一个人。300-600 字。
第一行是标题(一句话, 不带#号), 然后空一行, 正文。"""
    body = ds(system, user, temperature=0.7)
    lines = body.strip().split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    stamp = now_stamp()
    md = f"# {title}\n\n*参「{concept}」之后 · {now_iso()}*\n\n{content}\n"
    BLOG.mkdir(parents=True, exist_ok=True)
    (BLOG / f"{stamp}.md").write_text(md, encoding="utf-8")
    print(f"     ✎ 札记《{title}》写下 (年谱 +1)", file=sys.stderr)


def realize(koan):
    """暂搁时的"证": 先内化进内在记忆(LLM wiki, 复利在此), 再渲染人读的脸。
    决策A: 不写回 P2 的 Neo4j —— 它的领悟留在自己的世界, 不污染大德语料池。"""
    try:
        # ① 内化进内在记忆 (LLM wiki, 交叉引用) —— 反哺自己的复利层; 返回密的理解
        import llm_memory
        note = llm_memory.consolidate(koan, _history_text(koan))
        # 记一次内化 = wiki 实质更新一次 —— 回头"眼睛变了没"以此衡量
        cj = ROOT / "data" / "state" / "cultivation.json"
        st = json.loads(cj.read_text(encoding="utf-8"))
        st["consolidations"] = st.get("consolidations", 0) + 1
        write_json_atomic(cj, st)
        # ② 渲染人读的脸: 把内化好的密理解【翻译】成人读页(不重新收敛) + 记来源 + 写札记
        distill(koan, note)
        record_sources(koan)
        write_note(koan)
    except Exception as e:
        print(f"     (证·收成出错: {str(e)[:80]})", file=sys.stderr)
