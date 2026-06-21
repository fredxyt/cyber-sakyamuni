#!/bin/bash
# 每日札记 (产品层 b) — 每天定时, 把这一天连续的修行策展成【今日一篇】给人读。
# 与永动参悟共用 flock 锁, 错开不撞 git。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
mkdir -p logs
LOG="logs/daily_$(date +%Y%m%d).log"

{
  echo "[$(date -u +%FT%TZ)] 今日札记 start"
  source "$DIR/.env.deepseek" 2>/dev/null
  export CANPO_ON_SERVER="${CANPO_ON_SERVER:-1}"
  PY="/home/ubuntu/fdz2025/.venv/bin/python"; [ -x "$PY" ] || PY=python3

  "$PY" src/daily_note.py
  "$PY" src/build_site.py
  # 每天把累积的参悟轨迹导成训练集(dpo/sft/trace/cpt); 输出在 data/traces/_export/(gitignored)。失败不阻断当日提交。
  "$PY" tools/export_traces.py || echo "[$(date -u +%FT%TZ)] 训练集导出失败, 不阻断。"
  # 备份训练料(raw+_export)到【私有 repo】异地存档; 与公开仓库彻底分开, 不进 GitHub 公开仓库。失败不阻断。
  ( cd data/traces \
    && git add -A \
    && if ! git diff --cached --quiet; then git commit -q -m "traces $(date -u +%Y-%m-%dT%H:%MZ)"; fi \
    && git push -q origin main ) || echo "[$(date -u +%FT%TZ)] traces 私有备份失败, 不阻断。"

  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    # 守门: 轨迹是原始日志(体量大), 该留本地; 误入暂存区即中止
    if git diff --cached --name-only | grep -q '^data/traces/'; then
      echo "🚨 traces 误入暂存区(原始日志, 该留本地), 中止提交。" >&2
      git reset -q; exit 0
    fi
    git -c user.name="cyber-sakyamuni" -c user.email="noreply@anthropic.com" \
      commit -q -m "今日札记 $(date -u +%Y-%m-%d)"
    git pull --rebase -X theirs -q origin master 2>&1 | tail -1 || git rebase --abort 2>/dev/null
    if git push -q origin master 2>&1; then echo "pushed."; else echo "⚠ push 失败, 下跳重试。"; fi
  fi
  echo "[$(date -u +%FT%TZ)] 今日札记 end"
} >> "$LOG" 2>&1
