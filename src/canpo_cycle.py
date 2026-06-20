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


def try_reactivate(min_grew=8):
    """回头: 只在【眼睛真变了】时才回参老疑 —— 自它暂搁以来, 整颗心又内化了足够多次。
    min_grew: 自暂搁以来全局内化次数至少长这么多才回 (默认8≈走了一小段路)。
    离上次参太近、wiki 没怎么变 → 一律不回参 (回了也只是重复旧结论)。
    在合格者中挑【变化最大】的(暂搁最久、看过最多新东西的)。返回是否激活。"""
    st = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
    now_cons = st.get("consolidations", 0)
    d = json.loads(KOANS.read_text(encoding="utf-8"))
    best, best_grew = None, -1
    for k in d["koans"]:
        if k["status"] != "暂搁":
            continue
        grew = now_cons - k.get("consolidations_at_pause", 0)  # 暂搁后眼睛变了多少
        if grew >= min_grew and grew > best_grew:
            best, best_grew = k, grew
    if best is None:
        return False
    best["status"] = "活"
    best["no_move_streak"] = 0
    best["attempts"] = 0
    best["source"] = best.get("source", "") + f" ·【回头】自暂搁起又内化{best_grew}次, 带新眼睛重参"
    KOANS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[心跳] 回头: 重参老疑「{best.get('concept')}」(暂搁后眼睛变了 {best_grew} 次)", file=sys.stderr)
    return True


def run(script, *args):
    r = subprocess.run([sys.executable, str(SRC / script), *args], cwd=str(ROOT))
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6, help="本次心跳参几轮")
    args = ap.parse_args()

    print("[心跳] —— 参悟一次 ——", file=sys.stderr)

    # 1. 确保有活话头: 扫盲吃满整圈(覆盖1964类世界苦), 跑完一圈才回头
    if not has_alive():
        print("[心跳] 扫盲: 孕育未参过的一类苦…", file=sys.stderr)
        run("birth_koan.py")                 # 主线: 先把世界的苦一类类走遍
        if not has_alive():                  # 找不到新类 = 跑完一圈了 → 才回头
            print("[心跳] 一圈已尽, 回头看眼睛变够了的老疑…", file=sys.stderr)
            try_reactivate(min_grew=8)        # 只回那些"暂搁后又长了很多"的 (眼睛真变了)
        if not has_alive():
            print("[心跳] 无可参 (都太近/没变够), 静待。", file=sys.stderr)
            return

    # 2. 参 N 轮 (带检索 + 硬上限; 参尽自动停)
    print(f"[心跳] 参 {args.rounds} 轮…", file=sys.stderr)
    run("contemplate_loop.py", "--max-rounds", str(args.rounds), "--sleep", "2")

    # 3. 重建站点 (前端读 site.json)
    run("build_site.py")

    # 4. 推进 cycle 计数 + last
    from datetime import datetime, timezone
    st_path = ROOT / "data" / "state" / "cultivation.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    st["cycle"] = st.get("cycle", 0) + 1
    st["last_cultivation_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    st_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[心跳] —— 完 (cycle {st['cycle']}) ——", file=sys.stderr)


if __name__ == "__main__":
    main()
