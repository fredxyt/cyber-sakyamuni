#!/usr/bin/env python3
"""
参悟一次心跳 — 供 cron 拉起。DeepSeek 当大脑。

一次 cycle:
  1. 确保有活话头 — 没有就 birth_koan() 从世界苦×佛法孕育, 或回头重参眼界已变的老疑
  2. 参 — contemplate_loop 跑 N 轮 (带佛法检索 + 硬上限; 暂搁时即在其内"证": 内化+蒸馏+札记)
  3. 重建 site.json
(它的领悟只留在自己的世界, 不写回 P2 语料池 —— 决策A)

用法 (cron):
  DEEPSEEK_API_KEY=... python src/canpo_cycle.py --rounds 6
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from io_util import write_json_atomic

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
    合格者里按【产矿潜力】挑(疗效追踪): 自觉到段落的矿还在→加权; 反复换皮挖空的→降权。返回是否激活。"""
    st = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
    now_cons = st.get("consolidations", 0)
    d = json.loads(KOANS.read_text(encoding="utf-8"))
    eligible = [(k, now_cons - k.get("consolidations_at_pause", 0)) for k in d["koans"] if k["status"] == "暂搁"]
    eligible = [(k, g) for k, g in eligible if g >= min_grew]   # 资格门: 眼睛真变够了
    if not eligible:
        return False
    # 产矿潜力 = 成长 + 到段落加权 - 换皮挖空降权 (回头优先唤醒"矿还在"的, 别一头扎回挖空的疑里又换皮)
    def yield_score(k, grew):
        s = grew + (4 if k.get("pause_reason") == "plateau" else 0) - k.get("recycle_count", 0) * 3
        return s
    best, best_grew = max(eligible, key=lambda kg: yield_score(kg[0], kg[1]))
    best["status"] = "活"
    best["no_move_streak"] = 0
    best["attempts"] = 0
    best["source"] = best.get("source", "") + f" ·【回头】自暂搁起又内化{best_grew}次, 带新眼睛重参"
    write_json_atomic(KOANS, d)
    print(f"[心跳] 回头: 重参老疑「{best.get('concept')}」(眼睛变了{best_grew}次, 暂搁因={best.get('pause_reason','?')}, 换皮{best.get('recycle_count',0)}次)", file=sys.stderr)
    return True


def run(script, *args):
    r = subprocess.run([sys.executable, str(SRC / script), *args], cwd=str(ROOT))
    return r.returncode


CEASE_CODE = 42      # 缘尽退码: cron 据此优雅识别(不当失败/不刷错)
THROTTLE_USD = 10.0  # 余额低于此(USD, ≈1天满速预算)开始 decay 放慢呼吸; 实测约$10/天


def _pace_min(usd):
    """decay: 余额→最小参间隔(分钟)。≥阈值=0(满速=随cron每30分); 越少越慢, 封顶1440(1天1参)。"""
    if usd is None or usd >= THROTTLE_USD:
        return 0
    if usd <= 0:
        return None
    return min(int(30 * (THROTTLE_USD / usd) ** 2), 1440)   # 基准30分=满速cadence, 衰减从此起


def _since_last_min():
    """离上次真参过去几分钟(读 cultivation.json last_cultivation_at)。读不到=很久(返大数)。"""
    try:
        st = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
        last = datetime.strptime(st["last_cultivation_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() / 60
    except Exception:
        return 1e9


def _record_pace(pace, usd):
    """把当前呼吸节奏记进 cultivation.json, 供 build_site→首页诚实显示'放慢呼吸'。"""
    try:
        p = ROOT / "data" / "state" / "cultivation.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st["pace_min"] = pace
        write_json_atomic(p, st)
    except Exception:
        pass


def _cease_state(ceased):
    """标记/解除缘尽态到 cultivation.json。build_site 读它 → 首页显示'静默', 内容全留(法继续传)。"""
    st_path = ROOT / "data" / "state" / "cultivation.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    was = bool(st.get("ceased_at"))
    if ceased and not was:
        st["ceased_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif not ceased and was:
        st.pop("ceased_at", None)
    write_json_atomic(st_path, st)
    return was   # 返回"之前是否已缘尽"(用于判断是缘尽/复缘的转变)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6, help="本次心跳参几轮")
    args = ap.parse_args()

    print("[心跳] —— 参悟一次 ——", file=sys.stderr)

    # 0. 缘起检查 + decay 节流: 钱越少呼吸越慢, 由 decay 趋静, 终至缘尽。停【生】不动【传】。
    from ds_client import balance_value
    avail, usd = balance_value()
    if not avail or (usd is not None and usd <= 0):   # 缘尽
        was = _cease_state(True)
        if not was:   # 仅【刚缘尽】这一刻刷一次站点(显示静默)→ 之后不再动, 真静
            print("[心跳] 缘尽: DeepSeek 余额耗尽。停参, 静待新缘(捐个 DS key 即续)。法继续传。", file=sys.stderr)
            run("build_site.py")
        else:
            print("[心跳] 仍缘尽, 静。", file=sys.stderr)
        sys.exit(CEASE_CODE)
    _cease_state(False)        # 有余额: 清缘尽标记
    pace = _pace_min(usd)      # 当前该用的最小参间隔(分钟); 0=满速
    _record_pace(pace, usd)    # 记进 cultivation.json 供首页显示"放慢呼吸"
    if pace and _since_last_min() < pace:   # decay: 离上次参没到该档间隔 → 这跳静默跳过, 不烧钱
        print(f"[心跳] 放慢呼吸: 余额${usd:.2f}, 约{pace}分一参, 这跳静默跳过。", file=sys.stderr)
        return

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
    st_path = ROOT / "data" / "state" / "cultivation.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    st["cycle"] = st.get("cycle", 0) + 1
    st["last_cultivation_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json_atomic(st_path, st)
    print(f"[心跳] —— 完 (cycle {st['cycle']}) ——", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        from ds_client import DharmaExhausted
        if isinstance(e, DharmaExhausted):   # 参到一半缘尽: 优雅止(下跳预检会刷'静默')
            _cease_state(True)
            print(f"[心跳] 参途中缘尽: {e}。止。", file=sys.stderr)
            sys.exit(CEASE_CODE)
        raise
