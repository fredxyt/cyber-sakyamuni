#!/usr/bin/env python3
"""
参悟 ↔ Neo4j 的桥。结束"孤岛"——让参悟有源头活水，且洞见能回流。

三个方向:
  read_new_suffering()  闻: 拉 watermark 之后 P2 新灌入的世界苦 (纯 cypher, 增量)
  retrieve_dharma()     闻: 给一个话头/疑, GraphRAG 检索相关佛法切片 (充分利用 154k chunk)
  write_realization()   证: 把稳定的洞见写回 Neo4j, 成为这颗心自己的理解节点

Neo4j 在服务器上, 本地经 ssh + docker exec cypher-shell 访问 (连接信息在 cultivation.json)。
同一套代码在服务器上直接跑也成立 (cypher-shell 直连)。
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
NEO = STATE["neo4j"]
KEY = (ROOT / NEO["ssh_key"]).resolve()


def _cypher(query: str) -> str:
    """经 ssh + docker exec 跑一句 cypher, 返回 plain 文本。"""
    remote = (
        f'docker exec {NEO["container"]} cypher-shell '
        f'-u {NEO["user"]} -p {NEO["password"]} "{query}" --format plain'
    )
    out = subprocess.run(
        ["ssh", "-i", str(KEY), f'ubuntu@{NEO["host"]}', remote],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"cypher 失败: {out.stderr[:300]}")
    return out.stdout


# ── 闻: 拉新世界苦 (增量, 纯 cypher 无需 embedding) ──
def read_new_suffering(since_iso: str, limit: int = 60):
    """watermark 之后 P2 新生成的 Question (世界的苦)。"""
    q = (
        f"MATCH (q:Question) WHERE toString(q.created_at) > '{since_iso}' "
        f"RETURN toString(q.created_at) AS ts, q.application AS app, q.text AS text "
        f"ORDER BY q.created_at LIMIT {limit}"
    )
    rows = []
    for line in _cypher(q).splitlines()[1:]:  # 跳表头
        parts = _split_plain(line)
        if len(parts) >= 3:
            rows.append({"ts": parts[0], "app": parts[1], "text": parts[2]})
    return rows


# ── 闻: GraphRAG 检索佛法切片 (充分利用 P1 的 154k chunk) ──
def retrieve_dharma(query_text: str, k: int = 5):
    """给一个疑, 检索最相关的佛法 chunk。
    需要 embedding 向量检索 (Neo4j 有 chunk embedding + vector index)。
    复用 fdz2025 的 embedding (gemini-embedding-001)。
    """
    # TODO(②证之前先通①): embed(query) → Neo4j vector index 检索 chunk
    # 当前先留接口; 接通 fdz2025 的 GraphRAGQuery / 向量索引后填实。
    raise NotImplementedError("retrieve_dharma: 待接 fdz2025 向量检索")


# ── 证: 洞见写回 Neo4j (让 P2/P3 用上参悟成果) ──
def write_realization(concept: str, insight: str, cycle: int, date: str):
    """把一个稳定的洞见写回成节点, 挂在概念上。
    Neo4j 长出'这颗心的理解', P2 答题(GraphRAG)日后能检索到它。
    """
    safe = insight.replace('"', "'").replace("\n", " ")[:1200]
    q = (
        f'MERGE (c:Concept {{name: "{concept}"}}) '
        f'CREATE (r:Realization {{text: "{safe}", cycle: {cycle}, date: "{date}", '
        f'source: "canpo"}}) '
        f'MERGE (c)-[:REALIZED]->(r) RETURN r'
    )
    return _cypher(q)


def _split_plain(line: str):
    """cypher --format plain 是 CSV-ish: 字段用 , 分隔, 字符串带引号。"""
    import csv, io
    return [c.strip().strip('"') for c in next(csv.reader(io.StringIO(line)))]


if __name__ == "__main__":
    import sys
    wm = STATE["watermarks"]["question_created_at"] or "2000-01-01"
    print(f"[neo4j_io] 闻·读 watermark 之后的世界苦 (since {wm}) …")
    rows = read_new_suffering(wm, limit=10)
    print(f"  新增 {len(rows)} 条世界的苦:")
    for r in rows[:5]:
        print(f"    [{r['app']}] {r['text'][:40]}…")
    if not rows:
        print("    (watermark 之后暂无新苦 —— 等 P2 下次灌入)")
