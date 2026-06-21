#!/usr/bin/env python3
"""佛法切片检索 — 给一句疑, 在 Neo4j 里向量检索最相关的经文 Chunk。参悟"闻·读"侧的开源参考实现。

这是【读 P1 佛法语料的逻辑】。语料本身(15.4 万 chunk 的向量索引)在 Neo4j 里, 不开源; 这里是怎么读它。
自包含: 依赖 neo4j + google-genai + 环境变量 GEMINI_API_KEY / NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
        (绝不内置密码; 密钥全走环境)。
用法: python tools/dharma_retrieve.py "照见五蕴皆空 痛苦" 5
      → stdout JSON: [{text, summary, source, score(cosine)}, ...]
"""
import json
import os
import sys

from neo4j import GraphDatabase
from google import genai

CYPHER = """
CALL db.index.vector.queryNodes('chunk_embedding_idx', $k, $embedding)
YIELD node, score
OPTIONAL MATCH (a:Article)-[:HAS_CHUNK]->(node)
RETURN node.text AS text, node.summary AS summary, a.title AS source, score
ORDER BY score DESC
"""


def _embed(text):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = client.models.embed_content(model="gemini-embedding-001", contents=text)
    return list(r.embeddings[0].values)


def retrieve(query_text, k=5):
    emb = _embed(query_text)  # 3072 维, 与语料同一嵌入空间
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD")   # 必须由环境提供, 不内置默认密码
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    out = []
    try:
        with driver.session() as session:
            for r in session.run(CYPHER, embedding=emb, k=k):
                out.append({
                    "text": (r["text"] or "")[:600],
                    "summary": (r["summary"] or "")[:200],
                    "source": r["source"] or "",
                    "score": round(2.0 * r["score"] - 1.0, 4),  # Neo4j 余弦索引 [0,1] → 真余弦 [-1,1]
                })
    finally:
        driver.close()
    return out


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else ""
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(json.dumps(retrieve(q, k) if q else [], ensure_ascii=False))
