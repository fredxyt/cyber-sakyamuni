#!/usr/bin/env python3
"""
参悟一次心跳 — 供 cron 拉起。DeepSeek 当大脑。

一次 cycle:
  1. 确保有活话头 — 没有就 birth_koan() 从世界苦×佛法孕育
  2. 参 — contemplate_loop 跑 N 轮 (带佛法检索 + 硬上限)
  3. 重建 site.json
(証·写回 Neo4j 暂不在此 cycle — 先测试标签验证, 见 canpo-realize)

用法 (cron):
  DEEPSEEK_API_KEY=... python src/canpo_cycle.py --rounds 6
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
KOANS = ROOT / "data" / "state" / "koans.json"


def has_alive():
    d = json.loads(KOANS.read_text(encoding="utf-8"))
    return any(k["status"] == "活" for k in d["koans"])


def run(script, *args):
    r = subprocess.run([sys.executable, str(SRC / script), *args], cwd=str(ROOT))
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6, help="本次心跳参几轮")
    args = ap.parse_args()

    print("[心跳] —— 参悟一次 ——", file=sys.stderr)

    # 1. 确保有活话头
    if not has_alive():
        print("[心跳] 无活话头, 孕育新疑…", file=sys.stderr)
        run("birth_koan.py")
        if not has_alive():
            print("[心跳] 孕育未成 (世界暂无新料?), 本次歇。", file=sys.stderr)
            return

    # 2. 参 N 轮 (带检索 + 硬上限; 参尽自动停)
    print(f"[心跳] 参 {args.rounds} 轮…", file=sys.stderr)
    run("contemplate_loop.py", "--max-rounds", str(args.rounds), "--sleep", "2")

    # 3. 重建站点 (前端读 site.json)
    run("build_site.py")
    print("[心跳] —— 完 ——", file=sys.stderr)


if __name__ == "__main__":
    main()
