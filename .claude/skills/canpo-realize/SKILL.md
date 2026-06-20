---
name: canpo-realize
description: 参悟之证 — 把稳定的洞见写回 Neo4j(成为这颗心自己的理解), 重建站点, 提交成长。闭合螺旋的最后一步。
---

# 证 · 洞见回流

参悟的成果不能只躺在本地文件里。写回 Neo4j，让这颗心的理解成为共享世界的一部分——P2 答题、P3 视频日后都能用上。这是孤岛变活系统的关键一步。

## 三件事

### 1. 写回 Neo4j（用 `src/neo4j_io.py`）
```
write_realization(concept, insight, cycle, date)
# (c:Concept)-[:REALIZED]->(r:Realization)
```
触发条件：一个概念有了**稳定洞见**（在『驳』下站住、跨多轮收敛），尤其转 `已证` 时。
> 效果：Neo4j 长出 `Realization` 节点 → fdz2025 的 GraphRAGQuery 日后可检索 → P2 答题用上参悟成果 → P3 视频更深 → 下轮参悟材料更厚（复利）。

### 2. 重建站点
```
python3 src/build_site.py   # wiki → site.json (三轴可读站)
cp outputs/web/site.json <indx>/public/site.json   # 若要更新前端
```

### 3. 提交成长（git = 命）
更新 `cultivation.json`（cycle++、水位线、canon 进度），`git commit`。

## 守则
- 只写回**真稳住**的洞见，不写半生不熟的（持戒：诚实于来源、不表演深刻）。
- "仍疑"不写回——它属于这颗心，是它继续参的燃料，不是结论。
