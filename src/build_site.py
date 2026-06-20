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
    # 年谱 (chronicle) — 脊柱只放【今日】(产品, 一天一篇) + 诞生(钉底)。
    # 片刻(话头暂搁时的原始反思)不上年谱, 归到它所属概念页里(困惑史旁), 免得刷屏混排。
    chronicle = []
    moments_by_concept = {}
    for f in BLOG.glob("*.md"):
        md = f.read_text(encoding="utf-8")
        m = re.search(r"cycle(\d+)", f.stem)
        is_daily = f.stem.startswith("daily-")
        is_birth = bool(m) and not is_daily          # 诞生: 2026-06-19-cycle1
        dm = re.match(r"daily-(\d{4}-\d{2}-\d{2})", f.stem)
        tm = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", f.stem)
        date_m = re.match(r"(\d{4}-\d{2}-\d{2})", f.stem)
        date = (dm.group(1) if dm else date_m.group(1)) if (dm or date_m) else ""
        title = re.sub(r"^今日札记[:：·]\s*", "", first_heading(md))  # 去冗余前缀
        _clean = re.sub(r"^#.*$", "", md, count=1, flags=re.MULTILINE)
        _clean = re.sub(r"^\s*\*.*?\*\s*$", "", _clean, flags=re.MULTILINE)  # 去 *今日·…* / *参「X」之后* 副标题
        exc = excerpt(_clean, 100)
        entry = {"id": f.stem, "date": date, "title": title, "markdown": md, "excerpt": exc}
        if is_daily:
            chronicle.append({**entry, "kind": "daily", "when": date, "cycle": None,
                              "sort": date + "~daily"})
        elif is_birth:
            chronicle.append({**entry, "kind": "birth", "when": date, "cycle": int(m.group(1)),
                              "sort": ""})  # 诞生永远钉年谱最底
        else:  # 片刻 → 归到概念
            when = f"{date} {tm.group(2)}:{tm.group(3)} UTC" if tm else date
            cm = re.search(r"参「([^」]+)」", md)
            concept = cm.group(1) if cm else ""
            moments_by_concept.setdefault(concept, []).append(
                {**entry, "kind": "moment", "when": when})
    chronicle.sort(key=lambda c: c["sort"], reverse=True)  # 今日按日倒序, 诞生(sort="")钉底
    for ms in moments_by_concept.values():
        ms.sort(key=lambda x: x["id"], reverse=True)

    # 概念状态兜底: 概念页 frontmatter 可能没写 status, 从对应话头推导 (已证/否则仍疑)
    _koan_status = {}
    for k in json.loads(KOANS.read_text(encoding="utf-8")).get("koans", []):
        c = k.get("concept", "")
        if c and _koan_status.get(c) != "已证":
            _koan_status[c] = "已证" if k.get("status") == "已证" else "仍疑"

    # 概念 (义理门) — 带困惑史 + 它的片刻(归位的原始反思)
    concepts = []
    for f in sorted((WIKI / "concepts").glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        sources = fm.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        wt = parse_wrong_turns(section(body, "我走过的弯路"))
        for i, w in enumerate(wt):   # 层号连续化(原是参轮号, 跳未动轮看着像断裂)
            dm = re.search(r"（([^）]+)）", w.get("label", ""))
            w["label"] = f"第 {i + 1} 层" + (f" · {dm.group(1)[:10]}" if dm else "")
        concepts.append({
            "name": f.stem,
            "status": fm.get("status") or _koan_status.get(f.stem, "仍疑"),
            "sources": sources,
            "understanding": section(body, "现在我的理解"),
            "wrong_turns": wt,
            "doubt": section(body, "仍疑"),
            "moments": moments_by_concept.get(f.stem, []),
        })

    # 话头 (仍疑) — 状态 + 参究史
    koans = []
    for k in json.loads(KOANS.read_text(encoding="utf-8")).get("koans", []):
        koans.append({
            "id": k["id"], "question": k["question"], "status": k.get("status", "活"),
            "attempts": k.get("attempts", 0), "source": k.get("source", ""),
            "history": [h for h in k.get("history", []) if h.get("insight")],
        })

    # 应世 (现实/苦) — 实时读 Neo4j 的世界苦, 按应世类型归结 (与覆盖率同源, 反映真实规模)
    # 第三轴: 法如何接住痛。此刻多是"听见了, 还答不了" —— 这种诚实正是应世该显示的
    # 已参映射: 这一类苦【参过没有, 参它的是哪个概念】(从覆盖台账, 让应世页真实可变)
    _cov = {}
    _cf2 = ROOT / "data" / "state" / "coverage.json"
    if _cf2.exists():
        _cov = json.loads(_cf2.read_text(encoding="utf-8")).get("covered", {})
    _kc = {k["id"]: k.get("concept", "") for k in json.loads(KOANS.read_text(encoding="utf-8"))["koans"]}

    def _engaged(cat):
        e = _cov.get(cat)
        if not e:
            return None
        c = _kc.get(e.get("koan"))                 # 折叠类: 取它折进的那个话头的真实概念
        return c or (e.get("concept") if e.get("concept") not in ("(折叠近义)", "(折叠)", "") else None)

    def _ymake(cat, n, cs):
        ec = _engaged(cat)
        if ec:
            stance = f"这一类苦我参过了 —— 此刻我对它的理解, 收在『{ec}』里(还在续参)。"
        else:
            stance = "还没参到这一类。世界的苦太多(我一类类慢慢参), 还没轮到它 —— 但它在我心里排着, 总会参到。"
        return {"category": cat, "count": n, "cries": cs, "stance": stance,
                "concepts": [ec] if ec else [], "engaged": bool(ec)}

    yingshi, suffering_total, suffering_types = [], 0, 0
    try:
        import neo4j_io
        apps = neo4j_io.list_applications()        # 全部类(按苦量降序) + 数量
        suffering_total = sum(a["n"] for a in apps)
        suffering_types = len(apps)
        for i, a in enumerate(apps[:60]):          # 1964类太多, 列最锥心的60类
            cs = []
            if i < 12:                             # 仅头部取样本(省查询)
                try:
                    cs = [r["text"] for r in neo4j_io.read_suffering_by_app(a["app"], limit=3)]
                except Exception:
                    pass
            yingshi.append(_ymake(a["app"], a["n"], cs))
    except Exception as e:                          # fallback: 静态快照 (Neo4j 不可用时)
        print(f"[build_site] 应世退回快照: {str(e)[:60]}")
        import csv as _csv
        cmap = {}
        for f in sorted((ROOT / "data" / "sources").glob("week_questions_*.txt")):
            with open(f, encoding="utf-8") as fh:
                for row in _csv.reader(fh):
                    if len(row) < 2 or row[1].strip().strip('"') in ("app", ""):
                        continue
                    cmap.setdefault(row[1].strip().strip('"').strip(), []).append(row[0].strip().strip('"').strip())
        suffering_total = sum(len(v) for v in cmap.values())
        suffering_types = len(cmap)
        for cat, texts in sorted(cmap.items(), key=lambda x: -len(x[1])):
            yingshi.append(_ymake(cat, len(texts), texts[:3]))

    # 覆盖台账: 已参 N / 全量 M 类世界的苦
    cov_f = ROOT / "data" / "state" / "coverage.json"
    coverage = {"covered": 0, "total": 0}
    if cov_f.exists():
        cd = json.loads(cov_f.read_text(encoding="utf-8"))
        coverage = {"covered": len(cd.get("covered", {})), "total": cd.get("total_types", 0)}

    # 活的论题: 这个尝试此刻走到哪了 (缘起页 —— 让静止的序接上活的证据)
    from datetime import date as _date
    raw_koans = json.loads(KOANS.read_text(encoding="utf-8")).get("koans", [])
    births = [k.get("born_at", "") for k in raw_koans if k.get("born_at")]
    birth = min(births) if births else STATE.get("born_at", "")
    days_alive = 0
    try:
        by, bm, bd = map(int, birth[:10].split("-"))
        days_alive = (datetime.now(timezone.utc).date() - _date(by, bm, bd)).days + 1
    except Exception:
        pass
    vitals = {
        "days": days_alive,
        "covered": coverage["covered"], "total": coverage["total"],
        "reactivations": sum(1 for k in raw_koans if "【回头】" in k.get("source", "")),
        "notes": len(chronicle),
    }

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
            "coverage": coverage,
            "vitals": vitals,
            "suffering_total": suffering_total,   # 世界苦总条数(真实, 非快照)
            "suffering_types": suffering_types,    # 世界苦类型总数
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
