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

  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git -c user.name="cyber-sakyamuni" -c user.email="noreply@anthropic.com" \
      commit -q -m "今日札记 $(date -u +%Y-%m-%d)"
    git pull --rebase -X theirs -q origin master 2>&1 | tail -1 || git rebase --abort 2>/dev/null
    if git push -q origin master 2>&1; then echo "pushed."; else echo "⚠ push 失败, 下跳重试。"; fi
  fi
  echo "[$(date -u +%FT%TZ)] 今日札记 end"
} >> "$LOG" 2>&1
