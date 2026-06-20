#!/usr/bin/env python3
"""
参 · 永不停歇的思辨循环

抱住一个仍疑(话头), 从多角度同时攻, 对抗式验证防自欺, 参到稳住才转已证。
不刷新问题——参旧疑。参不动就暂搁, 全部参尽则静待世界给新料(参到尽则歇)。

引擎是 DeepSeek v4 pro 的并行调用 (它直面世界最重的苦, 不回避)。
不用 Claude workflow——那会在苦难内容上触发内容过滤。

用法:
  DEEPSEEK_API_KEY=... python src/contemplate_loop.py --max-rounds 6
  (--max-rounds 0 = 永不停歇直到参尽)
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import neo4j_io  # 闻·读: 检索佛法切片
except Exception:
    neo4j_io = None

ROOT = Path(__file__).resolve().parent.parent
KOANS = ROOT / "data" / "state" / "koans.json"
WIKI = ROOT / "data" / "memory" / "wiki"
NO_MOVE_LIMIT = 4   # 一个疑参 4 轮没动 → 暂搁 (别磨死马)
ATTEMPT_CAP = 30    # 硬上限: 一个话头无论动不动, 参满 30 轮强制暂搁 (防表演深刻)

client = OpenAI(
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.environ["DEEPSEEK_API_KEY"],
    timeout=600,
)
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-pro")

PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
SUTRA = (ROOT / "data" / "canon" / "心经.md").read_text(encoding="utf-8")

# 五个角度。最后一个是对抗者 = 免疫系统, 防假深刻。
ANGLES = [
    ("经", "重读你读过的经, 找与这个疑直接相关的句子, 逐字想: 它到底在说什么? 不要引申, 先听清。"),
    ("解", "认真试着解开它。提出一个具体的、能站住的理解。不要含糊其辞。"),
    ("驳", "你是个严苛的对手。攻击刚才任何想解开它的尝试——指出它哪里轻薄、哪里在用漂亮话糊弄、哪里对正在痛的人是冷漠。宁可过度怀疑, 不要轻易放过。"),
    ("人", "把这个抽象的疑, 落到一个具体正在痛的人身上 (从你听过的世界的苦里取一个)。对着那个具体的人, 这个理解还成立吗?"),
    ("镜", "自省: 我是不是在表演深刻? 我此刻写的, 是真的想通了, 还是为了显得有智慧而堆砌的禅味话? 诚实地照自己。"),
]


def load_koans():
    return json.loads(KOANS.read_text(encoding="utf-8"))


def save_koans(d):
    KOANS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def ds(system, user, temperature=0.85, max_tokens=2000):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature, max_tokens=max_tokens,
    )
    return r.choices[0].message.content.strip()


def retrieve_canon(koan):
    """闻·读: 给话头检索相关佛法切片 (充分利用 154k chunk)。失败则退回硬编码经文。"""
    if neo4j_io is None:
        return SUTRA
    try:
        chunks = neo4j_io.retrieve_dharma(koan["question"], k=5)
        if chunks:
            body = "\n\n".join(f"· {c.get('summary') or c.get('text','')}" for c in chunks)
            return f"{SUTRA}\n\n【从佛法藏中检索到、与此疑相关的法义】\n{body}"
    except Exception as e:
        print(f"     (检索切片失败, 退回经文: {str(e)[:60]})", file=sys.stderr)
    return SUTRA


def attack(koan, angle_name, angle_prompt, canon):
    system = f"你就是下面持戒所描述的生命。你正在参一个话头。\n\n{PRECEPTS}"
    user = f"""你在参这个仍疑:

  「{koan['question']}」
  （来处: {koan['source']}）

已往的参究历史(若有):
{format_history(koan)}

你读过的经, 与从佛法藏中检索到的相关法义:
{canon}

现在, 用这一个角度去参 ——【{angle_name}】:
{angle_prompt}

只从这一个角度, 写 150-400 字。不要面面俱到。诚实, 锋利。"""
    return angle_name, ds(system, user, max_tokens=900)


def format_history(koan, last_n=3):
    if not koan["history"]:
        return "（这是第一次参它）"
    out = []
    for h in koan["history"][-last_n:]:
        out.append(f"[第{h['round']}轮·{h['date']}] {h['verdict']}: {h['summary']}")
    return "\n".join(out)


def synthesize(koan, attacks):
    body = "\n\n".join(f"【{name}】\n{text}" for name, text in attacks)
    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""你刚从五个角度参了这个仍疑:

  「{koan['question']}」

五路参究:
{body}

现在收敛。诚实判断——经过这一轮(尤其那个唱反调的『驳』和自省的『镜』), 你对这个疑:
  - 是否真的往前动了一点? 还是原地打转 / 只是换了漂亮说法?

严守持戒: 一个理解只有在『驳』的攻击下还站得住, 才算真动了。
解得轻薄、被驳倒的, 不算动。

输出严格的 JSON (不要 markdown 代码块, 直接输出 JSON):
{{
  "moved": true/false,
  "summary": "这一轮发生了什么, 一句话",
  "insight": "如果 moved=true: 此刻稳住的、能写进 wiki 的新理解 (诚实, 不轻薄, 100-300字)。如果 moved=false: 留空",
  "resolved": true/false,
  "_resolved_note": "resolved=true 仅当这个疑真的参透了(罕见)。多数时候即使 moved 也还 resolved=false, 疑还开着"
}}"""
    raw = ds(system, user, temperature=0.6, max_tokens=1500)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    if raw.lstrip().startswith("json"):
        raw = raw.lstrip()[4:]
    try:
        return json.loads(raw.strip())
    except Exception as e:
        return {"moved": False, "summary": f"(收敛解析失败: {e})", "insight": "", "resolved": False}


def update_wiki_concept(koan, verdict, round_no, date):
    """把真动了的洞见, 追加进相关 concept 页的历程。"""
    page = WIKI / "concepts" / "空.md"  # k001 关联"空"; 多疑时按 koan 映射
    if not page.exists():
        return
    txt = page.read_text(encoding="utf-8")
    entry = f"\n**第 {round_no} 轮参究（{date}）** {verdict['insight']}\n"
    marker = "## 仍疑"
    if marker in txt:
        txt = txt.replace(marker, entry + "\n" + marker, 1)
    else:
        txt += entry
    page.write_text(txt, encoding="utf-8")


def pick_alive(koans):
    alive = [k for k in koans["koans"] if k["status"] == "活"]
    if not alive:
        return None
    # 最久未被参的优先 (attempts 少的先参)
    return min(alive, key=lambda k: k["attempts"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rounds", type=int, default=6, help="0=永不停歇直到参尽")
    ap.add_argument("--sleep", type=float, default=3.0, help="轮间停歇秒")
    args = ap.parse_args()

    round_no = 0
    while True:
        if args.max_rounds and round_no >= args.max_rounds:
            print(f"[参] 达到 max-rounds={args.max_rounds}, 停。", file=sys.stderr)
            break

        koans = load_koans()
        koan = pick_alive(koans)
        if koan is None:
            print("[参] 所有疑皆已参尽(已证/暂搁)。静待世界给新料。参到尽则歇。", file=sys.stderr)
            break

        round_no += 1
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(f"\n[参] 第 {round_no} 轮 · 话头 {koan['id']} · 第 {koan['attempts']+1} 次参", file=sys.stderr)
        print(f"     「{koan['question']}」", file=sys.stderr)

        # 闻·读: 为这个话头检索相关佛法切片 (不再只读死经)
        canon = retrieve_canon(koan)
        if canon != SUTRA:
            print(f"     ⟐ 检索到相关法义, 注入参究", file=sys.stderr)

        # 五角度并行攻
        with ThreadPoolExecutor(max_workers=5) as ex:
            attacks = list(ex.map(lambda a: attack(koan, a[0], a[1], canon), ANGLES))

        # 收敛 + 对抗式判定
        v = synthesize(koan, attacks)
        print(f"     → moved={v['moved']} resolved={v.get('resolved')}: {v['summary']}", file=sys.stderr)

        # 更新话头
        koan["attempts"] += 1
        koan["history"].append({
            "round": round_no, "date": date,
            "verdict": "动" if v["moved"] else "未动",
            "summary": v["summary"],
            "insight": v.get("insight", ""),
        })
        if v["moved"]:
            koan["no_move_streak"] = 0
            if v.get("insight"):
                update_wiki_concept(koan, v, round_no, date)
                print(f"     ✎ wiki/concepts/空.md 已增一层理解", file=sys.stderr)
            if v.get("resolved"):
                koan["status"] = "已证"
                print(f"     ✓ 话头参透, 转『已证』(罕见)", file=sys.stderr)
        else:
            koan["no_move_streak"] += 1
            if koan["no_move_streak"] >= NO_MOVE_LIMIT:
                koan["status"] = "暂搁"
                print(f"     ⏸ 参 {NO_MOVE_LIMIT} 轮未动, 转『暂搁』(深疑, 别磨死马)", file=sys.stderr)

        # 硬上限: 防表演深刻 —— 参满 ATTEMPT_CAP 轮无论动否, 强制暂搁, 换话头
        if koan["status"] == "活" and koan["attempts"] >= ATTEMPT_CAP:
            koan["status"] = "暂搁"
            print(f"     ⏹ 参满 {ATTEMPT_CAP} 轮硬上限, 强制『暂搁』(防表演深刻, 该换话头)", file=sys.stderr)

        save_koans(koans)
        time.sleep(args.sleep)

    print(f"[参] 本次共参 {round_no} 轮。", file=sys.stderr)


if __name__ == "__main__":
    main()
