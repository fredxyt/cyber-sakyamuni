#!/usr/bin/env python3
"""
wiki → 可读站点数据 (site.json)

不是图, 是给人读的结构。主体是时间(札记), 概念页带困惑史。
INDX 前端套上它的皮(配色/排版)来渲染。每次修行后重跑。

输出: outputs/web/site.json
"""
import json
from io_util import write_json_atomic
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


def parse_evolution(md):
    """「理解的演变」: 历版"现在我的理解"快照 (蒸馏覆盖前留底), 最新在前。→ [{date, text}]"""
    out = []
    for m in re.finditer(r"\*\*([^*]+)\*\*\s*\n(.*?)(?=\n\*\*[^*]+\*\*|\Z)", md or "", re.DOTALL):
        t = m.group(2).strip()
        if t:
            out.append({"date": m.group(1).strip(), "text": t})
    return out


def main():
    # 年谱 (chronicle) — 脊柱只放【今日】(产品, 一天一篇) + 诞生(钉底)。
    # 片刻(话头暂搁时的原始反思)不上年谱, 归到它所属概念页里(困惑史旁), 免得刷屏混排。
    chronicle = []
    moments_by_concept = {}
    moments_by_date = {}      # B: 当天参详, 挂到当天「今日」下
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
        else:  # 片刻(参详) → 概念页(困惑史旁) + 当天年谱(挂今日下, B)
            when = f"{date} {tm.group(2)}:{tm.group(3)}:{tm.group(4)} UTC" if tm else date
            cm = re.search(r"参「([^」]+)」", md)
            concept = cm.group(1) if cm else ""
            mo = {**entry, "kind": "moment", "when": when, "concept": concept}
            moments_by_concept.setdefault(concept, []).append(mo)
            moments_by_date.setdefault(date, []).append(mo)
    chronicle.sort(key=lambda c: c["sort"], reverse=True)  # 今日按日倒序, 诞生(sort="")钉底
    for ms in moments_by_concept.values():
        ms.sort(key=lambda x: x["id"], reverse=True)
    # B: 每个「今日」挂上当天的参详笔记(倒序, 最新参的在最前 —— 与年谱逆时序一致, 首页一瞥取最近几则)
    daily_dates = {c["date"] for c in chronicle if c.get("kind") == "daily"}
    for c in chronicle:
        if c.get("kind") == "daily":
            c["day_moments"] = sorted(moments_by_date.get(c["date"], []), key=lambda x: x["id"], reverse=True)
    # 当天还没写今日札记的(如今天白天)——造一个 stub, 让当天参详照样上年谱, 不必等入夜
    # 入夜写了真「今日」后, 同日期的真 daily 会自然顶替(下次构建该日已在 daily_dates, 不再生 stub)
    for date, ms in moments_by_date.items():
        if date not in daily_dates:
            chronicle.append({
                "id": f"day-{date}", "date": date, "kind": "daystub", "cycle": None,
                "title": "今天还在参 · 今日札记入夜成文", "excerpt": "", "when": date,
                "sort": date + "~daystub", "markdown": "",
                "day_moments": sorted(ms, key=lambda x: x["id"], reverse=True),
            })
    chronicle.sort(key=lambda c: c["sort"], reverse=True)   # 重排, stub 按日期落位(今天的在最前)

    # 概念 (义理门) — 带困惑史 + 它的片刻(归位的原始反思)
    concepts = []
    for f in sorted((WIKI / "concepts").glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        sources = fm.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        wt = parse_wrong_turns(section(body, "我走过的弯路"))
        def _ts(w):
            m = re.search(r"（([^）]+)）", w.get("label", ""))
            return m.group(1) if m else ""
        wt.sort(key=_ts)   # 按秒级时间戳升序, 困惑史正序(一天多层, 防文档错位)
        for i, w in enumerate(wt):   # 层号连续化(原是参轮号, 跳未动轮看着像断裂)
            ts = _ts(w)              # 完整秒级戳, 不再 [:10] 截到天 —— 一天多层要分得清时分秒
            disp = ts.replace("T", " ").replace("Z", " UTC") if "T" in ts else ts
            w["label"] = f"第 {i + 1} 层" + (f" · {disp}" if ts else "")
        concepts.append({
            "name": f.stem,
            "status": fm.get("status") or "仍疑",   # 永远仍疑: 没有"已证"状态
            "sources": sources,
            "understanding": section(body, "现在我的理解"),
            "understanding_history": parse_evolution(section(body, "理解的演变")),
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
            "concept": k.get("concept", ""),
            # 只发最近3条洞见(前端只用最后1条) —— 防 site.json 随轮次无限膨胀
            "history": [h for h in k.get("history", []) if h.get("insight")][-3:],
        })

    # 应世 (现实/苦) — 实时读 Neo4j 的世界苦, 按应世类型归结 (与覆盖率同源, 反映真实规模)
    # 第三轴: 法如何接住痛。此刻多是"听见了, 还答不了" —— 这种诚实正是应世该显示的
    # 已参映射: 这一类苦【参过没有, 参它的是哪个概念】(从覆盖台账, 让应世页真实可变)
    _cov = {}
    _cf2 = ROOT / "data" / "state" / "coverage.json"
    if _cf2.exists():
        _cov = json.loads(_cf2.read_text(encoding="utf-8")).get("covered", {})
    _koans_by_id = {k["id"]: k for k in json.loads(KOANS.read_text(encoding="utf-8"))["koans"]}
    _kc = {kid: k.get("concept", "") for kid, k in _koans_by_id.items()}

    def _engaged(cat):
        e = _cov.get(cat)
        if not e:
            return None
        c = _kc.get(e.get("koan"))                 # 折叠类: 取它折进的那个话头的真实概念
        return c or (e.get("concept") if e.get("concept") not in ("(折叠近义)", "(折叠)", "") else None)

    # 传层映射: 概念→人读的「现在我的理解」(distill 译过, 可读)。应世的"此刻我看到的"取这个,
    # 【不再裸贴参层原始洞见】(那是密的、自造词的, 二谛: 传层该可读)。
    _cu = {c["name"]: c.get("understanding", "") for c in concepts}

    def _ymake(cat, n):
        # 隐私: 不发布用户求助原文(cries)。但要切题——接上这类苦【孕育的话头】的具体疑与洞见,
        # 不再只给"我参过了"的空模板(那对真有此苦的读者毫无帮助)。
        ec = _engaged(cat)
        e = _cov.get(cat) or {}
        koan = _koans_by_id.get(e.get("koan"))
        question, seen = "", ""
        if koan:
            question = koan.get("question", "")
            seen = _cu.get(ec, "")                  # 此刻我看到的 = 该概念人读的理解(传层, 可读)
        if ec:
            stance = f"面对这一类苦, 我给不了答案。我抱着一个疑在参, 此刻看到的写在下面 —— 不是药方, 是陪你一起看见。更深处收在『{ec}』。"
        else:
            stance = "还没参到这一类。世界的苦太多(我一类类慢慢参), 还没轮到它 —— 但它在我心里排着, 总会参到。"
        return {"category": cat, "count": n, "cries": [], "stance": stance,
                "concepts": [ec] if ec else [], "engaged": bool(ec),
                "koan_id": koan["id"] if koan else "", "question": question, "seen": seen}

    yingshi, suffering_total, suffering_types = [], 0, 0
    try:
        import neo4j_io
        apps = neo4j_io.list_applications()        # 全部类(按苦量降序) + 数量 (1次查询, 不取原文)
        suffering_total = sum(a["n"] for a in apps)
        suffering_types = len(apps)
        # 参过的(engaged)永远钉住 —— AI 真实参过的内容不因排名波动而消失; 再补一小批当下最锥心的未参类
        # (未参尾巴收小到20, 否则它随 P2 持续灌入不停重洗, 看着像"内容彻底换了一批")
        engaged = [a for a in apps if _engaged(a["app"])]
        unengaged = [a for a in apps if not _engaged(a["app"])]
        for a in engaged + unengaged[:20]:
            yingshi.append(_ymake(a["app"], a["n"]))
    except Exception as e:   # Neo4j 不可达: 应世留空(已初始化为空), 不阻塞其余构建, 下次心跳恢复
        print(f"[build_site] 应世跳过(Neo4j 不可达): {str(e)[:60]}")

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
    _total_moments = sum(len(ms) for ms in moments_by_concept.values())
    vitals = {
        "days": days_alive,
        "covered": coverage["covered"], "total": coverage["total"],
        "reactivations": sum(1 for k in raw_koans if "【回头】" in k.get("source", "")),
        "notes": len(chronicle),                                # 旧字段(daily+诞生), 保留兼容
        "written": len(chronicle) + _total_moments,             # 真实写作量: 札记 + 参详(片刻)
    }

    # 缘起 (造它的人的声音 —— 整站唯一一页"人"在说话)
    origin_f = ROOT / "data" / "memory" / "origin.md"
    origin = origin_f.read_text(encoding="utf-8") if origin_f.exists() else ""
    # 关于 (说明 + 目标 + 指向 GitHub)
    about_f = ROOT / "data" / "memory" / "about.md"
    about = about_f.read_text(encoding="utf-8") if about_f.exists() else ""

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
        "about": about,
        "canon": canon,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(OUT, site)
    print(f"站点数据已生成: {OUT}")
    print(f"  札记 {len(chronicle)} · 概念 {len(concepts)} · 话头 {len(koans)} · 经 {len(canon)}")
    for c in concepts:
        print(f"    概念「{c['name']}」{c['status']}: 困惑史 {len(c['wrong_turns'])} 层")


if __name__ == "__main__":
    main()
