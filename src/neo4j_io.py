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
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
NEO = STATE["neo4j"]
KEY = (ROOT / NEO["ssh_key"]).resolve()

# 在服务器上跑 (cron): 直连 Neo4j, 不绕 ssh。本地开发: ssh 到服务器。
ON_SERVER = os.environ.get("CANPO_ON_SERVER") == "1"


def _sh(remote_cmd: str, timeout: int = 180):
    """服务器上直接 bash 跑; 本地经 ssh 跑。"""
    if ON_SERVER:
        argv = ["bash", "-lc", remote_cmd]
    else:
        argv = ["ssh", "-i", str(KEY), f'ubuntu@{NEO["host"]}', remote_cmd]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _cypher(query: str) -> str:
    """跑一句 cypher (docker exec cypher-shell), 返回 plain 文本。"""
    remote = (
        f'docker exec {NEO["container"]} cypher-shell '
        f'-u {NEO["user"]} -p {NEO["password"]} "{query}" --format plain'
    )
    out = _sh(remote, timeout=120)
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
    """给一个疑, GraphRAG 检索最相关的佛法 chunk (充分利用 P1 的 154k 切片)。
    在服务器上跑 (embedding + Neo4j 都在那), 复用 fdz2025 的向量索引。
    返回 [{text, summary, score}, ...]。
    """
    q = query_text.replace('"', "'").replace("\n", " ")[:300]
    remote = (
        "cd /home/ubuntu/fdz2025 && source .venv/bin/activate && "
        "source .env.gemini && source .env.neo4j && "
        "export PYTHONPATH=/home/ubuntu/fdz2025 && "
        f'python scripts/tools/dharma_retrieve.py "{q}" {k}'
    )
    out = _sh(remote, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(f"检索失败: {out.stderr[:300]}")
    # 末行才是 JSON (前面可能有 venv/source 噪音)
    for line in reversed(out.stdout.splitlines()):
        line = line.strip()
        if line.startswith("["):
            return json.loads(line)
    return []


# ── 证: 洞见写回 Neo4j (让 P2/P3 用上参悟成果) ──
def write_realization(concept: str, insight: str, cycle: int):
    """证·写回: 洞见嵌入并写成 :CanpoRealization (隔离标签, P2 暂看不见)。
    服务器端 dharma_writeback.py 做 embedding + 入图; 验证好后 golive 才进 P2 索引。"""
    text = insight.replace('"', "'").replace("\n", " ").strip()[:1500]
    remote = (
        "cd /home/ubuntu/fdz2025 && source .venv/bin/activate && "
        "source .env.gemini && source .env.neo4j && export PYTHONPATH=/home/ubuntu/fdz2025 && "
        f'printf %s "{text}" | python scripts/tools/dharma_writeback.py write "{concept}" {cycle}'
    )
    out = _sh(remote, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"写回失败: {out.stderr[:200]}")
    return out.stdout.strip()


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
