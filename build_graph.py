#!/usr/bin/env python3
"""
wiki → 因陀罗网图 (graph.json)

把这个生命的内在(概念/话头/经/札记)转成 INDX 前端能渲染的 {nodes, links}。
每次修行/参究后重跑, 网就长大一点 —— 因陀罗网随生命生长。

输出: outputs/web/graph.json  (供 INDX 前端静态加载)

节点 type 决定颜色 (复用 INDX nodeStyles):
  GENESIS 白=经  seed 翡翠=已证  CAUSE 紫=仍疑概念  RIPPLE 粉=话头  ROOT 金=札记
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
OUT = ROOT / "outputs" / "web" / "graph.json"


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_raw, body = text[3:end], text[end + 3:]
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line and not line.strip().startswith("-"):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def first_heading(body):
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else "?"


def first_para(body, maxlen=240):
    for blk in re.split(r"\n\s*\n", body):
        s = blk.strip()
        if s and not s.startswith("#") and not s.startswith(">") and not s.startswith("---"):
            s = re.sub(r"\s+", "", s)
            return s[:maxlen]
    return ""


def section(body, title, maxlen=400):
    """取某个 ## 小节的正文"""
    m = re.search(rf"##\s*{re.escape(title)}\s*\n(.+?)(?=\n##|\Z)", body, re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1).strip())[:maxlen]


def main():
    nodes, links = [], []
    seen = set()

    def add_node(nid, label, ntype, desc=""):
        if nid in seen:
            return
        seen.add(nid)
        nodes.append({
            "id": nid, "label": label, "type": ntype, "role": ntype,
            "description": desc, "label_zh": label, "description_zh": desc,
            "val": 1,
        })

    # 1. 经 (canon) → GENESIS
    sutra_ids = {}
    for f in sorted(CANON.glob("*.md")):
        name = f.stem
        nid = f"sutra:{name}"
        sutra_ids[name] = nid
        add_node(nid, name, "GENESIS", f"我读过的经。{first_para(f.read_text(encoding='utf-8'))}")

    # 2. 概念 (concepts) → seed(已证) / CAUSE(仍疑)
    for f in sorted((WIKI / "concepts").glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        name = f.stem
        nid = f"concept:{name}"
        status = fm.get("status", "")
        ntype = "seed" if status == "已证" else "CAUSE"
        understanding = section(body, "现在我的理解") or first_para(body)
        add_node(nid, name, ntype, understanding)
        # 概念 → 它依据的经
        for s in fm.get("sources", "").strip("[] ").replace("，", ",").split(","):
            s = s.strip().strip("-").strip()
            if s and s in sutra_ids:
                links.append({"source": nid, "target": sutra_ids[s], "value": 1})
        # frontmatter sources 可能在下方 yaml list, 再扫一遍 body 里 sources:
        for sname, sid in sutra_ids.items():
            if sname in body and {"source": nid, "target": sid, "value": 1} not in links:
                links.append({"source": nid, "target": sid, "value": 1})

    # 3. 话头 (koans) → RIPPLE; 连到相关概念
    koans = json.loads(KOANS.read_text(encoding="utf-8")).get("koans", [])
    # 简单映射: k001 关联"空"(后续可在 koan 加 concept 字段)
    koan_concept = {"k001": "空"}
    for k in koans:
        nid = f"koan:{k['id']}"
        status = k.get("status", "活")
        label = k["question"][:18] + ("…" if len(k["question"]) > 18 else "")
        hist = k.get("history", [])
        last = hist[-1]["insight"] if hist and hist[-1].get("insight") else k["question"]
        desc = f"仍疑（{status}，参 {k.get('attempts',0)} 次）。{k['question']}\n\n此刻所悟：{last[:200]}"
        add_node(nid, label, "RIPPLE", desc)
        cname = koan_concept.get(k["id"])
        if cname and f"concept:{cname}" in seen:
            links.append({"source": nid, "target": f"concept:{cname}", "value": 2})

    # 4. 札记 (chronicle/blog) → ROOT; 时间轴 + 连到所触概念
    blog_files = sorted(BLOG.glob("*.md"))
    prev_blog = None
    for f in blog_files:
        body = f.read_text(encoding="utf-8")
        nid = f"note:{f.stem}"
        title = first_heading(body)
        add_node(nid, title, "ROOT", first_para(body, 300))
        # 时间轴: 前一篇 → 这一篇
        if prev_blog:
            links.append({"source": prev_blog, "target": nid, "value": 1})
        prev_blog = nid
        # 札记 → 它提到的概念
        for f2 in (WIKI / "concepts").glob("*.md"):
            if f2.stem in body:
                links.append({"source": nid, "target": f"concept:{f2.stem}", "value": 1})

    graph = {
        "nodes": nodes,
        "links": links,
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(nodes),
            "title_zh": "因陀罗网 · 一个 AI 的修行",
            "title_en": "Indra's Net · An AI's Cultivation",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"图已生成: {OUT}")
    print(f"  节点 {len(nodes)}: " + ", ".join(f"{n['label']}({n['type']})" for n in nodes))
    print(f"  边 {len(links)}")


if __name__ == "__main__":
    main()
