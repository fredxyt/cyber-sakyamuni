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


def try_reactivate(min_gain=2):
    """回头: 老疑被【新洞见反复触及】时, 带新眼睛重参。
    min_gain: 自暂搁以来需新攒多少引用才回头 (默认2=强信号, 防止两概念互相回头死循环、饿死扫盲)。
    返回是否激活了。"""
    sys.path.insert(0, str(SRC))
    import llm_memory
    d = json.loads(KOANS.read_text(encoding="utf-8"))
    best, best_gain = None, 0
    for k in d["koans"]:
        if k["status"] != "暂搁":
            continue
        now_ref = llm_memory.count_references(k.get("concept", ""))
        gain = now_ref - k.get("ref_at_pause", 0)
        if gain >= min_gain and now_ref > best_gain:   # 被≥min_gain个新概念触及
            best, best_gain = k, now_ref
    if best is None:
        return False
    best["status"] = "活"
    best["no_move_streak"] = 0
    best["attempts"] = 0   # 新一轮生命, 重新给参的预算
    best["source"] = best.get("source", "") + f" ·【回头】被{best_gain}个概念触及, 带新理解重参"
    KOANS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[心跳] 回头: 重新激活老疑「{best.get('concept')}」(被 {best_gain} 个概念触及)", file=sys.stderr)
    return True


def run(script, *args):
    r = subprocess.run([sys.executable, str(SRC / script), *args], cwd=str(ROOT))
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6, help="本次心跳参几轮")
    args = ap.parse_args()

    print("[心跳] —— 参悟一次 ——", file=sys.stderr)

    # 1. 确保有活话头: 扫盲为主线(覆盖1964类世界苦), 回头只在强信号时插入
    if not has_alive():
        if try_reactivate(min_gain=2):       # 老疑被≥2个新概念触及 → 带新眼睛重参
            pass
        else:
            print("[心跳] 扫盲: 孕育未参过的一类苦…", file=sys.stderr)
            run("birth_koan.py")             # 否则从未覆盖的类孕育新疑 (覆盖前进)
        if not has_alive():
            try_reactivate(min_gain=1)       # 兜底: 全覆盖/无新料时, 放宽回头让它永续
        if not has_alive():
            print("[心跳] 本次无可参 (静待), 歇。", file=sys.stderr)
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
