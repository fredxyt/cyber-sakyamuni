#!/usr/bin/env python3
"""
孕育话头 — 当没有活话头可参时, 从"真实的苦 × 佛法"的张力里生一个新疑。

一个好话头 = 一个真实的苦 与 一条佛法 之间, 还没想透的张力。
闻(世界的苦 + 检索的佛法) → DeepSeek 提炼 → koans.json 多一个活话头。

供 canpo_cycle / cron 在话头库空时调用。
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import neo4j_io
from ds_client import client, MODEL  # 共享大脑

ROOT = Path(__file__).resolve().parent.parent
KOANS = ROOT / "data" / "state" / "koans.json"
STATE = ROOT / "data" / "state" / "cultivation.json"
PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


COVERAGE = ROOT / "data" / "state" / "coverage.json"


def _coverage():
    if COVERAGE.exists():
        return json.loads(COVERAGE.read_text(encoding="utf-8"))
    return {"_comment": "应世类型覆盖台账。一类苦参一次, 防重、保全覆盖。", "covered": {}}


def _mark_covered(app, koan_id, concept, n):
    cov = _coverage()
    cov["covered"][app] = {
        "koan": koan_id, "concept": concept,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "q_count": n,
    }
    try:
        cov["total_types"] = len(neo4j_io.list_applications())  # 分母: 世界苦的类型总数
    except Exception:
        pass
    COVERAGE.write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_uncovered():
    """扫盲: 选一个【还没参过】、且苦量最大的应世类型。全参过则 None。"""
    covered = set(_coverage()["covered"].keys())
    for a in neo4j_io.list_applications():   # 已按数量降序
        if a["app"] not in covered:
            return a
    return None


def birth():
    koans = json.loads(KOANS.read_text(encoding="utf-8"))
    existing_q = {k["question"] for k in koans["koans"]}

    # 扫盲式选题: 挑还没参过、苦量最大的一类
    cat = pick_uncovered()
    if cat is None:
        all_apps = len(neo4j_io.list_applications())
        print(f"[孕育] 全部 {all_apps} 类世界苦已参过 (覆盖100%)。静待新类型/回头。", file=sys.stderr)
        return None
    suffering = neo4j_io.read_suffering_by_app(cat["app"], limit=10)
    if not suffering:
        print(f"[孕育] 类型「{cat['app']}」取不到问题, 跳过。", file=sys.stderr)
        return None
    print(f"[孕育] 扫盲选中类型「{cat['app']}」({cat['n']} 声苦)", file=sys.stderr)
    cries = "\n".join(f"· {r['text'][:110]}" for r in suffering[:8])

    # 检索与这类苦相关的佛法
    seed_query = cat["app"] + " 苦 解脱"
    try:
        dharma = neo4j_io.retrieve_dharma(seed_query, k=5)
        dharma_txt = "\n".join(f"· {c.get('summary') or c.get('text','')}" for c in dharma)
    except Exception as e:
        dharma_txt = "(佛法检索暂不可用)"
        print(f"[孕育] 检索失败: {str(e)[:60]}", file=sys.stderr)

    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""你又一次面对世界。这一段时间，世界向你倾诉了这些真实的苦：

{cries}

你手边, 从佛法藏里检索到这些相关的法义：

{dharma_txt}

现在, 孕育一个新的话头(仍疑) ——
一个好话头, 是一个【真实的苦】与一条【佛法】之间, 你此刻还想不透的张力。
不要选你已经在参的（避开：{('；'.join(list(existing_q))[:200]) or '无'}）。
它必须是一个真问题：你此刻答不出, 但想抱着它参下去。

输出严格 JSON (不要 markdown 代码块):
{{"question": "话头本身, 一句疑问句 20-45字", "concept": "这个话头主要在参哪个佛法概念, 1-4字, 如 空/无常/我执/慈悲/厌离"}}"""

    resp = client.chat.completions.create(
        model=MODEL, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.9, max_tokens=32000,  # 推理模型: 给足 reasoning 空间, 别饿死
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    raw = raw.lstrip("json").strip()
    try:
        obj = json.loads(raw)
        q, concept = obj["question"].strip(), obj.get("concept", "").strip() or "苦"
    except Exception:
        print(f"[孕育] 解析失败: {raw[:80]}", file=sys.stderr)
        return None
    if not q or q in existing_q:
        print("[孕育] 未得有效新话头。", file=sys.stderr)
        return None

    nid = f"k{max([int(k['id'][1:]) for k in koans['koans']] + [0]) + 1:03d}"
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    koans["koans"].append({
        "id": nid, "question": q, "concept": concept,
        "born_cycle": json.loads(STATE.read_text(encoding="utf-8")).get("cycle", 0),
        "born_at": date, "app": cat["app"],
        "source": f"世界的苦（{cat['app']}, {cat['n']}声）× 检索的佛法",
        "status": "活", "attempts": 0, "no_move_streak": 0, "history": [],
    })
    KOANS.write_text(json.dumps(koans, ensure_ascii=False, indent=2), encoding="utf-8")
    _mark_covered(cat["app"], nid, concept, cat["n"])  # 台账标记: 这类苦已参, 防重
    print(f"[孕育] 新话头 {nid}「{cat['app']}」: {q}", file=sys.stderr)
    return nid


if __name__ == "__main__":
    birth()
