---
name: canpo-perceive
description: 参悟之闻 — 从 Neo4j 拉新世界苦, 检索相关佛法切片, 孕育/喂养话头。当参悟需要源头活水(新材料/新话头)时使用。
---

# 闻 · 源头活水

让参悟不再是孤岛：从共享的 Neo4j 世界里取材，孕育值得参的话头。

## 三件事（用 `src/neo4j_io.py`）

### 1. 拉新世界苦（增量）
```
read_new_suffering(watermark)  # 水位线之后 P2 新灌入的 Question
```
更新前先读 `cultivation.json.watermarks.question_created_at`；读完更新它。

### 2. 检索佛法切片（充分利用 P1 的 154k chunk）
```
retrieve_dharma(疑或苦, k=5)   # GraphRAG 向量检索相关佛法 chunk
```
> ⚠ 现状：`retrieve_dharma` 待接 fdz2025 的向量索引（embedding=gemini-embedding-001 → Neo4j vector index）。接通前，参的"经"角度退回读 canon 里的经文。

### 3. 孕育话头（话头库生长）
一个**好话头 = 一个真实的苦 × 一条佛法 的张力**。
- 从新世界苦里挑反复出现、最锥心的一类（如"独自面对衰老病死"）。
- 配一条相关佛法（检索到的切片 / 已读的经）。
- 张力点 = 话头。写入 `data/state/koans.json`（status=活）。
- 例：k001 = 心经「照见五蕴皆空」× 41 声真实的痛。

## 产出
- `koans.json` 多出新的活话头
- 更新水位线（记下读到哪）
- 待参的切片/经文，供 canpo-contemplate 喂给参循环
