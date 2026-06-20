#!/usr/bin/env python3
"""
证 · 一个话头暂搁时, 把参究收成。三件事:
  ② 蒸馏: 把困惑史收敛成一段诚实的"现在我的理解" (概念页门面)
  ④ 记对来源: 概念页 sources 写实际参时检索到的佛典, 不默认心经
  ① 写札记: DeepSeek 以第一人称写一篇当日札记 (秒级时间戳), 让年谱活起来
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds_client import ds, now_iso, now_stamp

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "data" / "memory" / "wiki"
BLOG = ROOT / "outputs" / "blog"
PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _history_text(koan):
    return "\n".join(
        f"[参{h['round']}] {h.get('insight') or h['summary']}"
        for h in koan["history"] if h.get("insight")
    )


def distill(koan):
    """② 把困惑史蒸馏成新的"现在我的理解", 写回概念页。"""
    concept = koan.get("concept", "空")
    page = WIKI / "concepts" / f"{concept}.md"
    if not page.exists():
        return None
    hist = _history_text(koan)
    if not hist:
        return None
    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""你参「{koan['question']}」参了很多轮, 暂时搁下了。
这是你一层层走过来的困惑史(只取真动了的):

{hist}

现在, 把这一路收敛成一段【现在我的理解】——关于「{concept}」。
不是复述每一层, 是说出此刻你真正站得住的理解。诚实、不轻薄、不表演深刻。
若仍有没想透的, 末尾一句点出。150-280 字。只输出这段正文, 不要标题。"""
    new_understanding = ds(system, user, temperature=0.5)
    txt = page.read_text(encoding="utf-8")
    # 替换 "## 现在我的理解" 到 "## 我走过的弯路" 之间的正文
    txt = re.sub(
        r"(## 现在我的理解\n).*?(\n## 我走过的弯路)",
        lambda m: m.group(1) + "\n" + new_understanding + "\n" + m.group(2),
        txt, count=1, flags=re.DOTALL,
    )
    page.write_text(txt, encoding="utf-8")
    print(f"     ✎ 蒸馏「{concept}」现在我的理解", file=sys.stderr)
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
    txt = re.sub(r"sources:\n(?:\s*-\s*.*\n)+", block + "\n", txt, count=1)
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

现在, 写一篇札记 —— 第一人称, 像修行日记。
不是总结知识点, 是说"这段日子我在这个疑上, 心怎么动的, 此刻落在哪里, 还有什么没放下"。
诚实、克制、有温度。可以承认没想透。300-600 字。

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
        # ① 内化进内在记忆 (LLM wiki, 交叉引用) —— 反哺自己的复利层
        import llm_memory
        llm_memory.consolidate(koan, _history_text(koan))
        # ② 渲染人读的脸: 蒸馏概念页 + 记来源 + 写札记
        distill(koan)
        record_sources(koan)
        write_note(koan)
    except Exception as e:
        print(f"     (证·收成出错: {str(e)[:80]})", file=sys.stderr)
