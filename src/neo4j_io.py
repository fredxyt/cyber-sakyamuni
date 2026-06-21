#!/usr/bin/env python3
"""
参悟 ↔ Neo4j 的桥。结束"孤岛"——让参悟有源头活水。

两个方向 (都是"闻"):
  read_new_suffering()  拉 watermark 之后 P2 新灌入的世界苦 (纯 cypher, 增量)
  retrieve_dharma()     给一个话头/疑, GraphRAG 检索相关佛法切片 (充分利用 154k chunk)

Neo4j 在服务器上, 本地经 ssh + docker exec cypher-shell 访问 (连接信息在 cultivation.json)。
同一套代码在服务器上直接跑也成立 (cypher-shell 直连)。
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
NEO = STATE.get("neo4j", {})
# 服务器 IP / ssh key 路径不入公开仓库 —— 从环境变量读 (本地开发用; 服务器走 ON_SERVER 本地bash, 不需要)
_HOST = os.environ.get("NEO4J_HOST") or NEO.get("host", "")
_SSH_KEY = os.environ.get("NEO4J_SSH_KEY") or NEO.get("ssh_key", "")
_CONTAINER = os.environ.get("NEO4J_CONTAINER") or NEO.get("container", "neo4j-bodhi")
_USER = os.environ.get("NEO4J_USER") or NEO.get("user", "neo4j")
KEY = (ROOT / _SSH_KEY).resolve() if _SSH_KEY else None

# 在服务器上跑 (cron): 直连 Neo4j, 不绕 ssh。本地开发: ssh 到服务器。
ON_SERVER = os.environ.get("CANPO_ON_SERVER") == "1"


def _sh(remote_cmd: str, timeout: int = 180, input_data: str = None):
    """服务器上直接 bash 跑; 本地经 ssh 跑。input_data 经 stdin 传 (避开 shell 引号)。"""
    if ON_SERVER:
        argv = ["bash", "-lc", remote_cmd]
    else:
        if not (KEY and _HOST):
            raise RuntimeError("本地 ssh 需设 NEO4J_HOST / NEO4J_SSH_KEY 环境变量")
        argv = ["ssh", "-i", str(KEY), f"ubuntu@{_HOST}", remote_cmd]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=input_data)


def embed(texts):
    """文本 → gemini-embedding (3072维, 服务器上算, 复用 dharma 同一向量空间)。
    返回 [[float,...], ...]。话头/洞见语义去重用 (孕育去重 + 新颖度闸)。"""
    remote = (   # 跑本仓库 vendored 的开源脚本(借 fdz2025 的 venv 拿库 + .env.gemini 拿key)
        "cd /home/ubuntu/cyber-sakyamuni && source /home/ubuntu/fdz2025/.venv/bin/activate && "
        "source /home/ubuntu/fdz2025/.env.gemini && python tools/embed_text.py"
    )
    out = _sh(remote, timeout=180, input_data=json.dumps(texts))
    if out.returncode != 0:
        raise RuntimeError(f"嵌入失败: {out.stderr[:200]}")
    for line in reversed(out.stdout.splitlines()):
        line = line.strip()
        if line.startswith("["):
            return json.loads(line)
    return []


def _neo4j_password() -> str:
    """密码从环境变量读 (不入库)。本地: export NEO4J_PASSWORD; 服务器: source .env.deepseek。"""
    pw = os.environ.get("NEO4J_PASSWORD") or NEO.get("password", "")
    if not pw:
        raise RuntimeError("NEO4J_PASSWORD 未设置 (source .env.deepseek 或 export)")
    return pw


def _cypher(query: str) -> str:
    """跑一句 cypher (docker exec cypher-shell), 返回 plain 文本。"""
    remote = (
        f'docker exec {_CONTAINER} cypher-shell '
        f'-u {_USER} -p {_neo4j_password()} "{query}" --format plain'
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


# ── 闻: 列出所有应世类型(覆盖的单元) + 按类型取苦 ──
def list_applications():
    """P2 给每个 Question 打的应世类型 + 各自数量。这是【覆盖单元】(有限、有意义)。"""
    q = ("MATCH (q:Question) WHERE q.application IS NOT NULL "
         "RETURN q.application AS app, count(*) AS n ORDER BY n DESC")
    out = []
    for line in _cypher(q).splitlines()[1:]:
        p = _split_plain(line)
        if len(p) >= 2 and p[0]:
            try:
                out.append({"app": p[0], "n": int(p[1])})
            except ValueError:
                pass
    return out


def read_suffering_by_app(app, limit=10):
    """取某一类苦的真实问题 (提炼话头用)。"""
    a = app.replace("'", "").replace('"', "")  # 用单引号包值(双引号会被外层 shell 吃掉), 去掉值内引号
    q = (f"MATCH (q:Question) WHERE q.application = '{a}' "
         f"RETURN toString(q.created_at) AS ts, q.application AS app, q.text AS text "
         f"ORDER BY q.created_at DESC LIMIT {limit}")
    rows = []
    for line in _cypher(q).splitlines()[1:]:
        p = _split_plain(line)
        if len(p) >= 3:
            rows.append({"ts": p[0], "app": p[1], "text": p[2]})
    return rows


# ── 闻: GraphRAG 检索佛法切片 (充分利用 P1 的 154k chunk) ──
def retrieve_dharma(query_text: str, k: int = 5):
    """给一个疑, GraphRAG 检索最相关的佛法 chunk (充分利用 P1 的 154k 切片)。
    在服务器上跑 (embedding + Neo4j 都在那), 复用 fdz2025 的向量索引。
    返回 [{text, summary, score}, ...]。
    """
    q = query_text.replace('"', "'").replace("\n", " ")[:300]
    remote = (   # 跑本仓库 vendored 的开源检索脚本(借 fdz2025 的 venv + key/neo4j env)
        "cd /home/ubuntu/cyber-sakyamuni && source /home/ubuntu/fdz2025/.venv/bin/activate && "
        "source /home/ubuntu/fdz2025/.env.gemini && source /home/ubuntu/fdz2025/.env.neo4j && "
        f'python tools/dharma_retrieve.py "{q}" {k}'
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
