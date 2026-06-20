#!/bin/bash
# 永动参悟 daemon — 串行不停, 回头, 永远做不完。DeepSeek 当大脑。
# 一批: 确保活话头(回头or新疑) → 参 N 轮 → 内化 → 渲染 → push。然后歇 PACE 秒, 再来。
# 守护 cron 保证它挂了自动重启。
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
mkdir -p logs
LOG="logs/daemon_$(date +%Y%m%d).log"
ROUNDS="${1:-4}"          # 每批参几轮
PACE="${PACE:-45}"        # 批间歇秒 (节律/成本旋钮; 越小越连续越烧)

source "$DIR/.env.deepseek" 2>/dev/null
export CANPO_ON_SERVER="${CANPO_ON_SERVER:-1}"
PY="/home/ubuntu/fdz2025/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo "[$(date -u +%FT%TZ)] 永动参悟 daemon 启动 (rounds=$ROUNDS pace=${PACE}s)" >> "$LOG"

while true; do
  {
    echo "—— 一批 $(date -u +%FT%TZ) ——"
    "$PY" src/canpo_cycle.py --rounds "$ROUNDS"
    if [ -n "$(git status --porcelain)" ]; then
      git add -A
      git -c user.name="cyber-sakyamuni" -c user.email="noreply@anthropic.com" \
        commit -q -m "参悟 $(date -u +%FT%TZ)"
      git pull --rebase -X theirs -q origin master 2>&1 | tail -1
      git push -q origin master 2>&1 | tail -1 && echo "pushed."
    fi
  } >> "$LOG" 2>&1
  sleep "$PACE"
done
