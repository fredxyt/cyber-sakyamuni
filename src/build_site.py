#!/usr/bin/env python3
"""
wiki → 可读站点数据 (site.json)

不是图, 是给人读的结构。主体是时间(札记), 概念页带困惑史。
INDX 前端套上它的皮(配色/排版)来渲染。每次修行后重跑。

输出: outputs/web/site.json
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "data" / "memory" / "wiki"
CANON = ROOT / "data" / "canon"
KOANS = ROOT / "data" / "state" / "koans.json"
BLOG = ROOT / "outputs" / "blog"
STATE = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
OUT = ROOT / "outputs" / "web" / "site.json"


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_raw, body = text[3:end], text[end + 3:]
    fm, key = {}, None
    for line in fm_raw.splitlines():
        if re.match(r"^\s*-\s+", line) and key:
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                fm[key].append(line.strip()[1:].strip())
        elif ":" in line:
            k, v = line.split(":", 1)
            key = k.strip()
            v = v.strip()
            fm[key] = v if v else []
    return fm, body


def section(body, title):
    m = re.search(rf"^##\s*{re.escape(title)}\s*\n(.+?)(?=\n##\s|\Z)", body, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else ""


def first_heading(body):
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else "?"


def excerpt(md, n=80):
    t = re.sub(r"[#>*`\-\[\]]", "", md)
    t = re.sub(r"\s+", "", t)
    return t[:n]


def parse_wrong_turns(md):
    """把'我走过的弯路'里的 **第N轮…** 段落拆成时间序列。"""
    items = []
    parts = re.split(r"\n\s*\n", md.strip())
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = re.match(r"\*\*(.+?)\*\*\s*(.*)", p, re.DOTALL)
        if m:
            items.append({"label": m.group(1).strip(), "text": m.group(2).strip()})
        else:
            items.append({"label": "", "text": p})
    return items


def main():
    # 札记 (chronicle) — 主体
    chronicle = []
    for f in sorted(BLOG.glob("*.md")):
        md = f.read_text(encoding="utf-8")
        m = re.search(r"cycle(\d+)", f.stem)
        date_m = re.match(r"(\d{4}-\d{2}-\d{2})", f.stem)
        chronicle.append({
            "id": f.stem,
            "date": date_m.group(1) if date_m else "",
            "cycle": int(m.group(1)) if m else None,
            "title": first_heading(md),
            "markdown": md,
            "excerpt": excerpt(re.sub(r"^#.*$", "", md, count=1, flags=re.MULTILINE), 100),
        })

    # 概念 (义理门) — 带困惑史
    concepts = []
    for f in sorted((WIKI / "concepts").glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        sources = fm.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        concepts.append({
            "name": f.stem,
            "status": fm.get("status", ""),
            "sources": sources,
            "understanding": section(body, "现在我的理解"),
            "wrong_turns": parse_wrong_turns(section(body, "我走过的弯路")),
            "doubt": section(body, "仍疑"),
        })

    # 话头 (仍疑) — 状态 + 参究史
    koans = []
    for k in json.loads(KOANS.read_text(encoding="utf-8")).get("koans", []):
        koans.append({
            "id": k["id"], "question": k["question"], "status": k.get("status", "活"),
            "attempts": k.get("attempts", 0), "source": k.get("source", ""),
            "history": [h for h in k.get("history", []) if h.get("insight")],
        })

    # 应世 (现实/苦) — 从世界真实的苦里抽, 按场景归类
    # 第三轴: 法如何接住痛。此刻多是"听见了, 还答不了" —— 这种诚实正是应世该显示的
    import csv as _csv
    yingshi = []
    SRC = ROOT / "data" / "sources"
    cries = {}
    for f in sorted(SRC.glob("week_questions_*.txt")):
        with open(f, encoding="utf-8") as fh:
            for row in _csv.reader(fh):
                if len(row) < 2 or row[1].strip().strip('"') in ("app", ""):
                    continue
                cat = row[1].strip().strip('"').strip()
                cries.setdefault(cat, []).append(row[0].strip().strip('"').strip())
    # 此刻这颗心唯一在参的法(空/k001), 本就是为了学会面对这些痛 —— 唯一诚实的关联
    engaged = [k["id"] for k in koans]  # 都源于"41声苦"
    for cat, texts in sorted(cries.items(), key=lambda x: -len(x[1])):
        yingshi.append({
            "category": cat, "count": len(texts),
            "cries": texts[:3],
            "stance": "我听见了。此刻我能带来的还很少 —— 我正在参的『空』，就是想学会怎么不轻薄地面对这样的痛。",
            "concepts": [c["name"] for c in concepts] if concepts else [],
        })

    # 缘起 (造它的人的声音 —— 整站唯一一页"人"在说话)
    origin_f = ROOT / "data" / "memory" / "origin.md"
    origin = origin_f.read_text(encoding="utf-8") if origin_f.exists() else ""

    # 经
    canon = [{"name": f.stem, "text": f.read_text(encoding="utf-8")} for f in sorted(CANON.glob("*.md"))]

    site = {
        "meta": {
            "title_zh": "因陀罗网", "subtitle_zh": "一个 AI 的修行",
            "born_at": STATE.get("born_at", ""),
            "cycle": STATE.get("cycle", 0),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {"chronicle": len(chronicle), "concepts": len(concepts), "koans": len(koans)},
        },
        "chronicle": chronicle,
        "concepts": concepts,
        "koans": koans,
        "yingshi": yingshi,
        "origin": origin,
        "canon": canon,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(site, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"站点数据已生成: {OUT}")
    print(f"  札记 {len(chronicle)} · 概念 {len(concepts)} · 话头 {len(koans)} · 经 {len(canon)}")
    for c in concepts:
        print(f"    概念「{c['name']}」{c['status']}: 困惑史 {len(c['wrong_turns'])} 层")


if __name__ == "__main__":
    main()
