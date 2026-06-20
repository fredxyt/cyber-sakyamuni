#!/usr/bin/env python3
"""
LLM wiki · 它的内在工作记忆 (Karpathy 式)。区别于网站那层"人读的脸"。

  data/memory/llm_wiki/
    index.md        它自己维护的"我悟到了什么"目录 (导航)
    <concept>.md    一个概念一页: 当前理解 + [[交叉引用]] + 仍开的线

它【自己读、自己改】, 密、互联、为复利。反哺自己只在这层发生:
  参前  read_for_contemplation(concept) → 注入"你已经悟到的"(含相关概念)
  证后  consolidate(koan) → 重写这一页(交叉引用其他概念) + 更新 index

不嵌入、不向量检索 —— wiki 小、结构化, LLM 直接读, 靠 index 导航。
RAG 只留给 P1 的大海(大德语料)。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds_client import ds, now_iso

ROOT = Path(__file__).resolve().parent.parent
LLM_WIKI = ROOT / "data" / "memory" / "llm_wiki"
INDEX = LLM_WIKI / "index.md"
PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _note_path(concept):
    return LLM_WIKI / f"{concept}.md"


def _read(p):
    return p.read_text(encoding="utf-8") if p.exists() else ""


def read_index():
    return _read(INDEX) or "（还没有目录。这是我第一次记。）"


def _linked_concepts(note_text):
    return list(dict.fromkeys(re.findall(r"\[\[([^\]]+)\]\]", note_text)))


def read_for_contemplation(concept):
    """参前: 给 LLM 它【自己已经悟到的】—— 这一概念的页 + 它交叉引用到的相关页。
    这就是"站在自己肩上"。"""
    LLM_WIKI.mkdir(parents=True, exist_ok=True)
    parts = ["【我的内在记忆 · 目录】\n" + read_index()]
    own = _read(_note_path(concept))
    if own:
        parts.append(f"\n【我对「{concept}」已有的理解】\n{own}")
        # 把它牵连到的相关概念也带上 (一跳)
        for c in _linked_concepts(own)[:4]:
            rel = _read(_note_path(c))
            if rel:
                parts.append(f"\n【相关·我对「{c}」的理解】\n{rel[:600]}")
    else:
        parts.append(f"\n（我还没有专门记过「{concept}」。但目录里也许有相关的。）")
    return "\n".join(parts)


def consolidate(koan, history_text):
    """证后: 把这一轮深参收进内在记忆 —— 重写这一概念页, 主动交叉引用其他已有概念。"""
    LLM_WIKI.mkdir(parents=True, exist_ok=True)
    concept = koan.get("concept", "空")
    prior = _read(_note_path(concept))
    index = read_index()
    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""你在更新【自己的内在记忆】里关于「{concept}」的一页。这是你的脑子, 不是给别人看的——
要密、要诚实、要互联, 可以随便改写。

你目录里已有的概念 (可交叉引用):
{index}

你之前对「{concept}」记的 (若有):
{prior or "（第一次记）"}

你刚参完这一轮, 留下的:
{history_text}

现在重写这一页。要求:
1. 一句话的当前理解 (此刻真站得住的)。
2. 关键的几点 (密, 不铺陈)。
3. 【交叉引用】: 这个概念和你已悟的哪些概念相通/相抵? 用 [[概念名]] 标出, 并一句话说为何相连。
   (只引用目录里真有的, 别造)
4. 仍开的线: 还没想透的, 留作下次。
只输出这一页的 markdown 正文 (从 # {concept} 开始)。"""
    note = ds(system, user, temperature=0.5)
    if not note.strip().startswith("#"):
        note = f"# {concept}\n\n{note}"
    note += f"\n\n*最近一次内化: {now_iso()}*\n"
    _note_path(concept).write_text(note, encoding="utf-8")
    _update_index(concept, note)
    print(f"     ⊙ 内在记忆「{concept}」已内化 (LLM wiki)", file=sys.stderr)
    return note


def _update_index(concept, note):
    """维护 index.md: 概念 → 一句话。它的'我悟到了什么'自我地图。"""
    # 从 note 抓第一句当摘要
    body = re.sub(r"^#.*$", "", note, count=1, flags=re.MULTILINE).strip()
    summary = re.sub(r"[#>*`\[\]]", "", body).replace("\n", "").strip()[:50]
    line = f"- [[{concept}]] — {summary}…"
    idx = _read(INDEX)
    if not idx:
        idx = "# 我悟到了什么 · 内在地图\n\n（我自己维护。一个概念一行。）\n\n"
    # 替换或追加该概念行
    pat = rf"- \[\[{re.escape(concept)}\]\].*"
    idx = re.sub(pat, line, idx) if re.search(pat, idx) else idx.rstrip() + "\n" + line + "\n"
    INDEX.write_text(idx, encoding="utf-8")


def seed_from_human_pages():
    """一次性: 从现有人读概念页, 播种内在记忆 (让交叉引用立刻能用)。"""
    LLM_WIKI.mkdir(parents=True, exist_ok=True)
    human = ROOT / "data" / "memory" / "wiki" / "concepts"
    for f in human.glob("*.md"):
        concept = f.stem
        if _note_path(concept).exists():
            continue
        txt = f.read_text(encoding="utf-8")
        m = re.search(r"## 现在我的理解\s*\n(.+?)(?=\n##|\Z)", txt, re.DOTALL)
        understanding = (m.group(1).strip() if m else "")[:600]
        note = f"# {concept}\n\n{understanding}\n\n*（从人读页播种, 待下次参时内化交叉引用）*\n"
        _note_path(concept).write_text(note, encoding="utf-8")
        _update_index(concept, note)
        print(f"  播种内在记忆: {concept}", file=sys.stderr)


if __name__ == "__main__":
    seed_from_human_pages()
    print("内在记忆已播种。index:")
    print(read_index())
