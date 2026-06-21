#!/usr/bin/env python3
"""参悟轨迹 → 训练集。读 data/traces/raw/ 的逐轮 trace, 投影成 4 种 jsonl:
  dpo   —— {prompt, chosen, rejected}  偏好对(动vs闸翻转 + 旧理解vs新理解)
  sft   —— {messages}  context→insight 指令样本(只取真动且非换皮)
  trace —— {messages}  七角度对抗+举证 装进 <think>, 教"怎么参"(含未动的诚实喊停)
  cpt   —— {text}  纯文本(对抗全文+洞见), 风格浸泡
P2 是 Gemini 合成的"一类苦"画像(非真人), 无需脱敏 —— 直接导出。
用法: python tools/export_traces.py [--format all|dpo|sft|trace|cpt] [--since YYYY-MM-DD]
输出: data/traces/_export/<format>.jsonl + manifest.json (均 gitignored)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "traces" / "raw"
OUT = ROOT / "data" / "traces" / "_export"
_p = ROOT / "CLAUDE.md"
PRECEPTS = _p.read_text(encoding="utf-8") if _p.exists() else ""


def _load(since=None):
    """读所有 raw jsonl → (正常轮 rounds, realize_events)。按 koan_id+attempt 排序。半行容错。"""
    rounds, realize = [], []
    if not RAW.exists():
        return rounds, realize
    for f in sorted(RAW.rglob("*.jsonl")):
        if since and f.stem < since:      # 文件名是日期, 早于 since 跳过
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue                   # 半行/损坏行跳过
            if r.get("kind") == "realize_event":
                realize.append(r)
            elif r.get("verdict_full", {}).get("parse_error"):
                continue                   # 解析失败轮不进训练集
            elif "verdict_full" in r:
                rounds.append(r)
    rounds.sort(key=lambda r: (r.get("koan_id", ""), r.get("attempt", 0)))
    return rounds, realize


def _ctx_user(r):
    """重建喂进去的 user 侧(给 SFT)。"""
    c = r.get("context", {})
    parts = [f"参这个仍疑:「{r.get('question', '')}」"]
    if c.get("prior_realizations"):
        parts.append("我已悟(可被驳):\n" + c["prior_realizations"])
    if c.get("memory"):
        parts.append(c["memory"])
    return "\n\n".join(parts)


def export_cpt(rounds, realize):
    out = []
    for r in rounds:
        for a in r.get("attacks", []):
            if a.get("text") and not a.get("errored"):
                out.append({"text": a["text"], "meta": {"angle": a.get("angle"), "koan_id": r.get("koan_id")}})
        ins = r.get("verdict_full", {}).get("insight")
        if ins:
            out.append({"text": ins, "meta": {"kind": "insight", "koan_id": r.get("koan_id")}})
    for e in realize:
        new = e.get("realize", {}).get("distill_new")
        if new:
            out.append({"text": new, "meta": {"kind": "distill", "concept": e.get("concept")}})
    return out


def export_sft(rounds, realize):
    out = []
    for r in rounds:
        vf = r.get("verdict_full", {})
        if not vf.get("moved_final") or r.get("gate", {}).get("novelty", {}).get("recycled"):
            continue                       # 三层闸=天然质量标签: 只取真动且非换皮
        ins = vf.get("insight")
        if not ins:
            continue
        out.append({"messages": [
            {"role": "system", "content": PRECEPTS},
            {"role": "user", "content": _ctx_user(r)},
            {"role": "assistant", "content": ins},
        ], "meta": {"koan_id": r.get("koan_id"), "attempt": r.get("attempt"),
                    "sim": r.get("gate", {}).get("novelty", {}).get("sim")}})
    return out


def export_trace(rounds, realize):
    """推理 trace: 七角度对抗(有序) + 举证 → <think>…</think> + 结论。含未动(plateau_honest)。"""
    out = []
    for r in rounds:
        atts = [a for a in r.get("attacks", []) if a.get("text") and not a.get("errored")]
        if not atts:
            continue
        think = "\n".join(f"【{a['angle']}】{a['text']}" for a in atts)
        vf = r.get("verdict_full", {})
        rc = vf.get("rebuttal_check") or []
        think += (f"\n【收敛·举证】对质={rc}; surpasses_which={vf.get('surpasses_which')}; "
                  f"new_delta={vf.get('new_delta')}")
        moved = bool(vf.get("moved_final"))
        conclusion = vf.get("insight") if moved else (vf.get("summary") or "到段落, 凿不动了, 诚实搁置, 不硬造新词。")
        out.append({"messages": [
            {"role": "user", "content": f"参这个仍疑:「{r.get('question', '')}」。多角度参究, 先立论, 再对抗式自验, 最后举证裁决。"},
            {"role": "assistant", "content": f"<think>\n{think}\n</think>\n{conclusion}"},
        ], "meta": {"koan_id": r.get("koan_id"), "moved": moved,
                    "chain_type": "moved" if moved else "plateau_honest"}})
    return out


def export_dpo(rounds, realize):
    out = []
    # (A) 同话头: 真动的 insight(chosen) vs DS自评动但被闸翻转的 insight_raw(rejected, 天然负样本)
    by_koan = defaultdict(list)
    for r in rounds:
        by_koan[r.get("koan_id")].append(r)
    for kid, rs in by_koan.items():
        chosen = [r for r in rs if r["verdict_full"].get("moved_final") and r["verdict_full"].get("insight")]
        rejected = [r for r in rs if r["verdict_full"].get("moved_raw")
                    and not r["verdict_full"].get("moved_final")
                    and r["verdict_full"].get("insight_raw")]
        for c in chosen:
            for j in rejected:
                ci, ji = c["verdict_full"]["insight"], j["verdict_full"]["insight_raw"]
                out.append({"prompt": f"参「{c.get('question', '')}」, 给出此刻真正往前的理解。",
                            "chosen": ci, "rejected": ji,
                            "meta": {"pair_type": "moved_vs_gate_reject", "koan_id": kid,
                                     "chosen_attempt": c.get("attempt"), "rejected_attempt": j.get("attempt"),
                                     "len_chosen": len(ci), "len_rejected": len(ji)}})
    # (B) realize 时序: 现在的理解(chosen) vs 旧版理解(rejected) —— 最干净的偏好对
    for e in realize:
        rz = e.get("realize", {})
        old, new = rz.get("distill_old"), rz.get("distill_new")
        if old and new and old.strip() != new.strip():
            out.append({"prompt": f"对「{e.get('concept', '')}」, 此刻你的理解。",
                        "chosen": new, "rejected": old,
                        "meta": {"pair_type": "understanding_evolution", "concept": e.get("concept"),
                                 "len_chosen": len(new), "len_rejected": len(old)}})
    return out


EXPORTERS = {"cpt": export_cpt, "sft": export_sft, "trace": export_trace, "dpo": export_dpo}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="all", choices=["all"] + list(EXPORTERS))
    ap.add_argument("--since", default=None, help="只导出文件名日期 ≥ 此值的 (YYYY-MM-DD)")
    args = ap.parse_args()
    rounds, realize = _load(args.since)
    OUT.mkdir(parents=True, exist_ok=True)
    fmts = list(EXPORTERS) if args.format == "all" else [args.format]
    manifest = {"rounds": len(rounds), "realize_events": len(realize), "since": args.since, "counts": {}}
    for fmt in fmts:
        recs = EXPORTERS[fmt](rounds, realize)
        body = "\n".join(json.dumps(r, ensure_ascii=False) for r in recs)
        (OUT / f"{fmt}.jsonl").write_text(body + ("\n" if body else ""), encoding="utf-8")
        manifest["counts"][fmt] = len(recs)
        print(f"  {fmt}: {len(recs)} 条 → data/traces/_export/{fmt}.jsonl", file=sys.stderr)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] rounds={len(rounds)} realize={len(realize)} → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
