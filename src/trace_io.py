"""参悟轨迹无损落盘 —— 纯观察: 接收已算好的数据, 不重算/不改判, 从不写回 v/koan。
fail-open: 任何异常吞掉, 绝不抛回心跳。
隐私: 写 data/traces/raw/ (gitignored, 含 P2 真人苦原文, 绝不入库/分发)。
schema 与设计见 docs/trace-recording-design.md。为日后微调/训练(DPO/SFT/trace/CPT)准备。
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "traces" / "raw"            # 红区: 含真人原文, gitignored
CULT = ROOT / "data" / "state" / "cultivation.json"
SCHEMA_VERSION = 1
_A_ANGLES = {"经", "解"}


def _cycle():
    try:
        return json.loads(CULT.read_text(encoding="utf-8")).get("cycle")
    except Exception:
        return None   # contemplate_loop 内无 cycle 变量, 从 cultivation.json 读; 失败=null


def _prior_full(koan):
    """全量逐轮已悟(非喂进 attack 的 tier 截断版)。"""
    rows = [h["insight"] for h in koan.get("history", [])
            if h.get("verdict") == "动" and h.get("insight")]
    return "\n".join(f"{i + 1}. {t}" for i, t in enumerate(rows))


def no_move_reason(v, gate):
    """纯读: 从已有字段重建'为何没往前', 把'未动'的会困惑变成可训练标签。"""
    if v.get("parse_error"):
        return {"category": "parse_error", "detail": "收敛 JSON 解析失败"}
    nov = gate.get("novelty", {})
    if nov.get("recycled"):
        return {"category": "recycled", "detail": f"换皮: 与旧洞见语义重合 sim={nov.get('sim')}"}
    ev = gate.get("evidence", {})
    if ev.get("dodged"):
        return {"category": "dodged", "detail": "对质中有'驳'被绕过/没答"}
    if ev.get("no_delta") and ev.get("no_surpass"):
        return {"category": "no_evidence", "detail": "new_delta 与 surpasses 皆空"}
    if v.get("reached_plateau"):
        return {"category": "plateau", "detail": "自觉到段落, 诚实喊停"}
    return None   # 动了


def build_trace(koan, attempt, stamp, *, canon, srcs, chunks, memory, apps,
                world_rows, attacks, v, raw_snapshot, gate):
    """组装一条轨迹记录。所有入参都是参究已算好的局部变量, 纯读。"""
    a_list = []
    for name, text in (attacks or []):
        text = text or ""
        a_list.append({
            "phase": "A" if name in _A_ANGLES else "B",
            "angle": name, "text": text, "char_len": len(text),
            "errored": text.startswith(f"(【{name}】"),
        })
    insight = v.get("insight", "") or ""
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": f"{koan['id']}-{attempt}-{stamp}",
        "koan_id": koan["id"], "concept": koan.get("concept", "空"),
        "question": koan.get("question", ""), "source": koan.get("source", ""),
        "cycle": _cycle(), "attempt": attempt,
        "no_move_streak_before": koan.get("no_move_streak", 0),
        "recycle_count": koan.get("recycle_count", 0), "stamp": stamp,
        "verdict": "动" if v.get("moved") else "未动",
        "context": {
            "prior_realizations": _prior_full(koan),
            "memory": memory or "",
            "canon_hit": bool(chunks),
            "canon_chunks": chunks or [],            # 命中时存全文; 退回时 []
            "canon_fallback": None if chunks else "SUTRA",
            "dharma_sources": srcs or [],
            "world": {"privacy": "P0_REAL_PERSON",   # 硬标记: 真人苦原文, 脱敏/拒导依据
                      "apps": (apps or [])[:4],
                      "rows": world_rows or []},
        },
        "attacks": a_list,
        "verdict_full": {
            "rebuttal_check": v.get("rebuttal_check"),
            "surpasses_which": v.get("surpasses_which"),
            "new_delta": v.get("new_delta"),
            "summary": v.get("summary"),
            "summary_raw": raw_snapshot.get("summary"),
            "moved_raw": raw_snapshot.get("moved"),   # DS 原始自评(闸介入前)
            "moved_final": v.get("moved"),            # 三道闸后
            "insight": insight,
            "insight_raw": raw_snapshot.get("insight", ""),
            "insight_char_len": len(insight),
            "reached_plateau": v.get("reached_plateau"),
            "parse_error": bool(v.get("parse_error")),
        },
        "gate": gate,
        "outcome": {
            "no_move_reason": no_move_reason(v, gate),
            "status_after": koan.get("status"),
            "wiki_updated": bool(v.get("moved") and insight),
        },
        "realize": {"distill_old": None, "distill_new": None, "note_title": None},
    }


def append_trace(rec, parse_error=False):
    """append-only JSONL + fsync(进程被杀前也落盘)。心跳单进程(flock), 无并发写。fail-open。"""
    try:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sub = "_parse_errors" if parse_error else rec.get("koan_id", "unknown")
        p = RAW_DIR / sub / f"{day}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"     (轨迹落盘失败, 不阻断: {str(e)[:50]})", file=sys.stderr)
