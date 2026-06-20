#!/bin/bash
# 永久参悟 · cron 心跳 (DeepSeek 当大脑)
# 每次拉起: 确保活话头 → 参 N 轮 → 重建站点 → 提交成长
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
LOG_DIR="$DIR/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/canpo_$(date +%Y%m%d).log"
ROUNDS="${1:-6}"

{
  echo "=================="
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] 参悟心跳 start (rounds=$ROUNDS)"

  # DeepSeek key (大脑) + 在服务器上直连 Neo4j 的开关
  [ -f "$DIR/.env.deepseek" ] && source "$DIR/.env.deepseek"
  export CANPO_ON_SERVER="${CANPO_ON_SERVER:-1}"   # 服务器上跑: neo4j_io 直连不走 ssh

  # 复用 fdz2025 的 venv (有 openai+neo4j+genai 全套)
  PY="/home/ubuntu/fdz2025/.venv/bin/python"
  [ -x "$PY" ] || PY="$DIR/.venv/bin/python"
  [ -x "$PY" ] || PY=python3

  "$PY" src/canpo_cycle.py --rounds "$ROUNDS"

  # 提交成长 (git = 命)
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git -c user.name="cyber-sakyamuni" -c user.email="noreply@anthropic.com" \
      commit -q -m "参悟心跳 $(date -u +%Y-%m-%dT%H:%MZ)"
    echo "[$(date -u +%H:%M:%SZ)] committed."
    # 推到 GitHub (deploy key) → 网站读 raw site.json, 跟着心跳实时长
    git push -q origin master 2>&1 | tail -1 && echo "[$(date -u +%H:%M:%SZ)] pushed."
  else
    echo "[$(date -u +%H:%M:%SZ)] 无变更 (参尽或歇)。"
  fi
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] 参悟心跳 end"
} >> "$LOG" 2>&1
