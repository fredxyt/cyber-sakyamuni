#!/bin/bash
# 永久参悟 · cron 心跳 (DeepSeek 当大脑)
# 每次拉起: 确保活话头 → 参 N 轮 → 重建站点 → 提交成长
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
LOG_DIR="$DIR/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/canpo_$(date +%Y%m%d).log"
ROUNDS="${1:-4}"

# 自锁: 防重入(上一跳没跑完就跳过本跳)。锁写进脚本本身, 不只靠 crontab —— 可版本化、重装不丢。
exec 9>/tmp/canpo.lock
flock -n 9 || { echo "[$(date -u +%FT%TZ)] 上一跳还在跑, 跳过。" >> "$LOG"; exit 0; }

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

  # 整跳挂 1200s 墙钟超时: 喂全量context(160K+)调用更慢, 给足时间; hang也必在20分内释放锁。
  timeout 1200 "$PY" src/canpo_cycle.py --rounds "$ROUNDS"

  # 提交成长 (git = 命)
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    # 隐私守门(双保险): 轨迹含 P2 真人苦诉, 一旦进暂存区即中止提交, 宁可不提交也不泄露
    if git diff --cached --name-only | grep -q '^data/traces/'; then
      echo "[$(date -u +%H:%M:%SZ)] 🚨 traces 进入暂存区(含P2隐私), 中止提交。" >&2
      git reset -q; exit 0
    fi
    git -c user.name="cyber-sakyamuni" -c user.email="noreply@anthropic.com" \
      commit -q -m "参悟心跳 $(date -u +%Y-%m-%dT%H:%MZ)"
    echo "[$(date -u +%H:%M:%SZ)] committed."
    # rebase 纳入远端, 失败则自愈(abort)避免卡在 rebase 态导致永久停摆; 再推
    if ! git pull --rebase -X theirs -q origin master 2>&1 | tail -1; then
      git rebase --abort 2>/dev/null
      echo "[$(date -u +%H:%M:%SZ)] rebase 失败已 abort。"
    fi
    # 直接取 git push 退出码 (不经管道, 否则 tail 的成功会掩盖 push 失败 → 误报 pushed)
    if git push -q origin master 2>>"$LOG"; then echo "[$(date -u +%H:%M:%SZ)] pushed."
    else echo "[$(date -u +%H:%M:%SZ)] ⚠ push 失败(可能含拦截), 下跳重试。"; fi
  else
    echo "[$(date -u +%H:%M:%SZ)] 无变更 (参尽或歇)。"
  fi
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] 参悟心跳 end"
} >> "$LOG" 2>&1
