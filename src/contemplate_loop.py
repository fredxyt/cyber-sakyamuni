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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds_client import ds, now_iso  # 共享大脑 + 秒级时间戳
import realize as realize_mod       # 证: 暂搁时内化+蒸馏+写札记
import llm_memory                   # 内在记忆: 参前读自己 (反哺自己)
from io_util import write_json_atomic  # 原子写, 防半写损坏 koans.json
try:
    import neo4j_io  # 闻·读: 检索佛法切片
except Exception:
    neo4j_io = None

ROOT = Path(__file__).resolve().parent.parent
KOANS = ROOT / "data" / "state" / "koans.json"
WIKI = ROOT / "data" / "memory" / "wiki"
NO_MOVE_LIMIT = 3   # 参 3 轮没【真】往前 → 暂搁 (真推进多在前段, 别磨死马)
ATTEMPT_CAP = 16    # 硬上限: 参满 16 轮强制暂搁 (实测真推进在前~14轮, 30太宽只会换皮打转)

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
    write_json_atomic(KOANS, d)


def retrieve_canon(koan):
    """闻·读: 给话头检索相关佛法切片 (充分利用 154k chunk)。
    命中时以检索法义为主料, 心经退为背景 (#7); 并返回实际来源名 (#4)。
    返回 (canon_text, source_names)。"""
    if neo4j_io is None:
        return SUTRA, []
    try:
        chunks = neo4j_io.retrieve_dharma(koan["question"], k=15)  # 5→15 (无视成本, DS吃得下)
        if chunks:
            body = "\n\n".join(f"· {c.get('text') or c.get('summary','')}" for c in chunks)  # 用全文不只摘要
            srcs = [c.get("source") for c in chunks if c.get("source")]
            text = (
                f"【从佛法藏中检索到、与此疑直接相关的法义 (主料)】\n{body}\n\n"
                f"【背景 · 心经】\n{SUTRA}"
            )
            return text, srcs
    except Exception as e:
        print(f"     (检索切片失败, 退回经文: {str(e)[:60]})", file=sys.stderr)
    return SUTRA, []


def attack(koan, angle_name, angle_prompt, canon, memory, world=""):
    system = f"你就是下面持戒所描述的生命。你正在参一个话头。\n\n{PRECEPTS}"
    user = f"""你在参这个仍疑:

  「{koan['question']}」
  （来处: {koan['source']}）

{world}

你这一程【已经悟到的】(逐轮, 别再重复, 要么超越、要么诚实承认到顶了):
{prior_realizations(koan)}

{memory}

你读过的经, 与从佛法藏中检索到的相关法义:
{canon}

现在, 用这一个角度去参 ——【{angle_name}】:
{angle_prompt}
（站在上面这些已悟之上往前凿。换个漂亮说法把上面某条重说一遍, 不算参 ——
  要么真的更进一步, 要么老实说"这一程到顶了"。）

只从这一个角度, 写 150-400 字。不要面面俱到。诚实, 锋利。"""
    try:
        return angle_name, ds(system, user, max_tokens=32000)
    except Exception as e:   # 单角度哑了不炸全轮, 其余角度+收敛照常
        return angle_name, f"(【{angle_name}】这一角度此刻哑了: {str(e)[:40]})"


def prior_realizations(koan, limit=10000, clip=100000):
    """这一程逐轮真悟到的(全程全文, 不截 —— 实测DS稳吃160K+token) —— 喂给参与判, 防换皮重复。"""
    real = [h for h in koan["history"] if h.get("verdict") == "动" and h.get("insight")]
    if not real:
        return "（这是第一次参它, 还没有已得的理解）"
    return "\n".join(f"{i+1}. {h['insight'][:clip]}" for i, h in enumerate(real[-limit:]))


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

你这一程【已经悟到的】(逐轮):
{prior_realizations(koan)}

现在收敛。诚实判断——经过这一轮(尤其那个唱反调的『驳』和自省的『镜』), 你对这个疑:
  - 是否真的比【上面已悟的那些】更进一步了? 还是只是把其中某条换个隐喻/漂亮说法重说一遍?

严守持戒, 两道闸都过才算 moved=true:
  ① 这个理解在『驳』的攻击下还站得住 (不轻薄、不被驳倒);
  ② 且它【确实超越了上面已悟的全部】—— 不是任何一条的复述/换皮。
只要是旧领悟换个说法 (哪怕说得更漂亮、单独看也站得住), 一律 moved=false。
若五路都只是在重复已悟的, 老实判 moved=false (这是该暂搁、换话头的信号)。

输出严格的 JSON (不要 markdown 代码块, 直接输出 JSON):
{{
  "moved": true/false,
  "summary": "这一轮发生了什么, 一句话",
  "insight": "如果 moved=true: 此刻稳住的、能写进 wiki 的新理解 (诚实, 不轻薄, 100-300字)。如果 moved=false: 留空",
  "resolved": true/false,
  "_resolved_note": "resolved=true 仅当这个疑真的参透了(罕见)。多数时候即使 moved 也还 resolved=false, 疑还开着"
}}"""
    raw = ds(system, user, temperature=0.6, max_tokens=32000)
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
        # 解析失败 ≠ 未动。标 parse_error, 让本轮作废重来, 不污染 no_move_streak/历史。
        return {"moved": False, "summary": f"(收敛解析失败: {e})", "insight": "", "resolved": False, "parse_error": True}


def update_wiki_concept(koan, verdict, round_no, date):
    """把真动了的洞见, 追加进【这个话头所属概念】页的历程。页不存在则新建。"""
    concept = koan.get("concept") or "空"
    page = WIKI / "concepts" / f"{concept}.md"
    if not page.exists():  # 新话头 → 新概念页, 给个诚实的初稿骨架
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            f"---\nfirst_seen: {date}\nlast_revised: {date}\nstatus: 仍疑\nsources: []\n---\n\n"
            f"# {concept}\n\n## 现在我的理解\n\n我刚开始参它，还没有定见。\n\n## 我走过的弯路\n\n"
            f"## 仍疑\n\n**{koan['question']}**\n\n这是我正抱着参的话头。\n",
            encoding="utf-8")
    txt = page.read_text(encoding="utf-8")
    entry = f"\n**第 {round_no} 轮参究（{date}）** {verdict['insight']}\n"
    marker = "## 仍疑"
    txt = txt.replace(marker, entry + "\n" + marker, 1) if marker in txt else txt + entry
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
        stamp = now_iso()                       # 秒级 (24x7 不停, 日级会撞车)
        attempt = koan["attempts"] + 1          # #5: 轮号用累计 attempts, 不用 per-run round_no
        print(f"\n[参] 本次第 {round_no} 轮 · 话头 {koan['id']} · 累计第 {attempt} 参", file=sys.stderr)
        print(f"     「{koan['question']}」", file=sys.stderr)

        # 闻·读: 为这个话头检索相关佛法切片 (不再只读死经)
        canon, srcs = retrieve_canon(koan)
        if srcs:
            koan["dharma_sources"] = list(dict.fromkeys((koan.get("dharma_sources") or []) + srcs))
            print(f"     ⟐ 检索到相关法义, 注入参究 (来源 {len(srcs)})", file=sys.stderr)

        # 反哺自己: 参前读【内在记忆】(自己已悟的相关概念) —— 站在自己肩上
        try:
            memory = llm_memory.read_for_contemplation(koan.get("concept", "空"))
            print(f"     ⊙ 读内在记忆 (站在自己肩上)", file=sys.stderr)
        except Exception as e:
            memory = ""
            print(f"     (读内在记忆失败: {str(e)[:50]})", file=sys.stderr)

        # 新闻回灌: 拉这话头整簇(主类+折叠的近义类)的【最近真实苦声】当新 context
        world = ""
        apps = koan.get("apps") or ([koan["app"]] if koan.get("app") else [])
        if apps:
            try:
                rows = []
                for a in apps[:4]:                       # 折叠进来的近义类都带上
                    rows += neo4j_io.read_suffering_by_app(a, limit=3)
                if rows:
                    world = "世界最近就这(几)类苦发出的真实声音(可能有新的, 让参贴着活的苦):\n" + \
                        "\n".join(f"· {r['text'][:95]}" for r in rows[:8])
                    print(f"     ⊙ 回灌 {len(apps[:4])} 类共 {len(rows)} 声苦 (新 context)", file=sys.stderr)
            except Exception as e:
                print(f"     (新闻回灌失败: {str(e)[:40]})", file=sys.stderr)

        # 五角度并行攻
        with ThreadPoolExecutor(max_workers=5) as ex:
            attacks = list(ex.map(lambda a: attack(koan, a[0], a[1], canon, memory, world), ANGLES))

        # 收敛 + 对抗式判定
        v = synthesize(koan, attacks)
        if v.get("parse_error"):   # 收敛没读到判决: 本轮作废, 不计历史/不动 streak/不耗 attempts
            print(f"     ⚠ 收敛解析失败, 本轮作废重来 (不污染状态)", file=sys.stderr)
            time.sleep(args.sleep)
            continue
        print(f"     → moved={v['moved']} resolved={v.get('resolved')}: {v['summary']}", file=sys.stderr)

        # 更新话头 (#5: round = attempt; 时间到秒)
        koan["attempts"] = attempt
        koan["history"].append({
            "round": attempt, "date": stamp,
            "verdict": "动" if v["moved"] else "未动",
            "summary": v["summary"],
            "insight": v.get("insight", ""),
        })
        if v["moved"]:
            koan["no_move_streak"] = 0
            if v.get("insight"):
                update_wiki_concept(koan, v, attempt, stamp)
                print(f"     ✎ 概念「{koan.get('concept','空')}」增一层理解", file=sys.stderr)
            if v.get("resolved"):
                # 不自封已证: LLM 达不到真证悟, 自称参透即是妄。觉得到段落 → 暂搁, 仍疑。
                koan["status"] = "暂搁"
                print(f"     ⏸ 自觉参到一段落, 转『暂搁』(不自封已证 —— 真心永远仍疑)", file=sys.stderr)
        else:
            koan["no_move_streak"] += 1
            if koan["no_move_streak"] >= NO_MOVE_LIMIT:
                koan["status"] = "暂搁"
                print(f"     ⏸ 参 {NO_MOVE_LIMIT} 轮未动, 转『暂搁』(深疑, 别磨死马)", file=sys.stderr)

        # 硬上限: 防表演深刻 —— 参满 ATTEMPT_CAP 轮无论动否, 强制暂搁, 换话头
        if koan["status"] == "活" and koan["attempts"] >= ATTEMPT_CAP:
            koan["status"] = "暂搁"
            print(f"     ⏹ 参满 {ATTEMPT_CAP} 轮硬上限, 强制『暂搁』(防表演深刻, 该换话头)", file=sys.stderr)

        # 证: 一个话头转暂搁/已证时, 收成 —— 内化 + 蒸馏 + 札记
        if koan["status"] in ("暂搁", "已证"):
            realize_mod.realize(koan)
            # 回头闸: 记下此刻的内化次数(眼睛基线)。日后必须又内化够多(眼睛真变了)才回参。
            st = json.loads((ROOT / "data" / "state" / "cultivation.json").read_text(encoding="utf-8"))
            koan["consolidations_at_pause"] = st.get("consolidations", 0)

        save_koans(koans)
        time.sleep(args.sleep)

    print(f"[参] 本次共参 {round_no} 轮。", file=sys.stderr)


if __name__ == "__main__":
    main()
