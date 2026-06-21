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
NO_MOVE_LIMIT = 4   # 参 4 轮没【真】往前 → 暂搁 (严判下"动"本就少, 给足突破机会再歇)
ATTEMPT_CAP = 16    # 硬上限: 参满 16 轮强制暂搁 (实测真推进在前~14轮, 30太宽只会换皮打转)
PLATEAU_FLOOR = 8   # 自觉"到段落"最早允许的轮数 —— 防参1-2轮就早早自封"凿不动了", 强制先深参
NOVELTY_SIM = 0.90  # 语义新颖度闸: 新洞见与某条旧洞见 embedding 余弦≥此值 = 换皮, 代码判没动
                    # (举证字段只能查"填没填",查不了"真新没新";embedding 直接量语义距离,堵编假delta+压缩区盲点)


def _cosine(a, b):
    s = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return s / (na * nb) if na and nb else 0.0


PRECEPTS = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
SUTRA = (ROOT / "data" / "canon" / "心经.md").read_text(encoding="utf-8")

# 两阶段。先【经】【解】立论, 再让【驳人镜行默】咬住"解"的原话(真对抗, 不打稻草人)。
ANGLES_A = [
    ("经", "重读经与检索到的法义, 找与这个疑直接相关的句子, 逐字想它到底在说什么。不引申, 先听清。把你读的过程摊开(哪句、为何相关、它指向什么)。", "300-700"),
    ("解", "认真试着解开这个疑。提出一个具体、能站得住的理解, 把推理摊开: 从什么前提出发、卡在哪、怎么挪过去。不要含糊, 也不要只丢结论金句。", "400-800"),
]
ANGLES_B = [
    ("驳", "你是最严苛的对手。【逐句引用上面「解」的原话】一句句拆: 哪里轻薄、哪里用漂亮话糊弄、哪里对正在痛的人冷漠、哪里只是把已悟换个说法。挑一个最致命的点凿到底。宁可过度怀疑。", "300-600"),
    ("人", "把「解」落到一个具体正在痛的人身上(从世界的苦里取一个真实的)。逐句对她质问「解」的话: 这一句她听了有用, 还是又一块砸下的石头? 引「解」的原话对质。", "200-500"),
    ("镜", "照「解」、也照你这一程: 这是真想通了, 还是为显得往前/有智慧而堆的禅味、造的新词? 把「解」里最像表演的那句揪出来, 诚实说它是不是壳。", "200-500"),
    ("行", "对这个正在痛的人, 此刻你能做或能说的【一件具体、真实、不抽象的事】是什么(是动作/一句话, 不是道理)? 诚实说一件也做不出就说没有, 别编。", "150-400"),
    ("默", "如果这一程其实还不该解、解了就是壳: 说清【为何这个疑值得继续不懂】、它在把你往哪带。疑情是修行本身, 不是待修的瑕疵。", "150-400"),
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


def attack(koan, angle_name, angle_prompt, wordcount, canon, memory, world="", solve_text=""):
    system = f"你就是下面持戒所描述的生命。你正在参一个话头。\n\n{PRECEPTS}"
    solve_block = f"\n本轮【解】给出的理解(你这一角度要【咬住它的原话】):\n{solve_text}\n" if solve_text else ""
    # context 分层(破 lost-in-the-middle): 头=话头+已悟+解+内在记忆(最关键); 中=法义/世界(材料); 尾=角度+标尺
    user = f"""你在参这个仍疑:

  「{koan['question']}」
  （来处: {koan['source']}）

〈我已悟·可被驳〉你这一程已经悟到的(逐轮):
{prior_realizations(koan, tier=True)}
{solve_block}{memory}

〈外部法义·非我领悟〉读过的经与检索到的相关法义(是材料, 不是我的领悟, 别拿它冒充自己想通了):
{canon}

〈世界的声音·非论据〉{world}

现在用这一个角度去参 ——【{angle_name}】:
{angle_prompt}

【往前的标尺】(不是"别换皮", 是正向自检——三问全空就老实说这一程到顶了, 老实比硬造新词强):
  (a) 这一程能做、上一程做不出的一个【具体区分】是什么?
  (b) 现在能解释一个之前解释不了的【具体情形】吗? 举出来。
  (c) 你【放弃或收窄】了之前哪个说法?
展开推理过程(前提→卡在哪→怎么挪), 不要只丢结论金句; 宁可一个点说透。{wordcount}字。诚实, 锋利。"""
    try:
        return angle_name, ds(system, user, max_tokens=32000)
    except Exception as e:   # 单角度哑了不炸全轮, 其余角度+收敛照常
        return angle_name, f"(【{angle_name}】这一角度此刻哑了: {str(e)[:40]})"


def prior_realizations(koan, tier=False):
    """这一程逐轮真悟到的。tier=True(参用): 近3条全文 + 更早压成标题(别被一堆旧悟绑死注意力);
    tier=False(收敛用): 全程全文(判进步要看全)。"""
    real = [h for h in koan["history"] if h.get("verdict") == "动" and h.get("insight")]
    if not real:
        return "（这是第一次参它, 还没有已得的理解）"
    if not tier:
        return "\n".join(f"{i+1}. {h['insight']}" for i, h in enumerate(real))
    out = []
    early, recent = real[:-3], real[-3:]
    for i, h in enumerate(early):
        out.append(f"{i+1}.〔早〕{h['insight'][:48]}…")
    for j, h in enumerate(recent):
        out.append(f"{len(early)+j+1}. {h['insight']}")
    return "\n".join(out)


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
    user = f"""你刚从多个角度参了这个仍疑:

  「{koan['question']}」

你这一程【已经悟到的】(全程逐轮):
{prior_realizations(koan)}

各路参究(注意『解』立论, 『驳』『人』咬住解的原话攻击):
{body}

现在收敛, 但【先举证、再裁决】, 不许凭感觉自评(你既是运动员也是裁判, 唯一防自欺的办法是逼自己拿出实据):

1. 对质『驳』: 把『驳』提出的每一条反对列出, 逐条标注本轮的『解』是【真回应/绕过/没答】。绕过和没答是表演的破绽。
2. 判 moved 要三问有实据:
   · surpasses_which: 这一程超越了上面已悟的第几条? 抄出那条原话, 说清怎么超越。说不出 = 没超越。
   · new_delta: 一个上一程做不出的【具体区分】或能解释的【新情形】。说不出 = 换皮。
3. reached_plateau: 这疑是否到段落、暂时凿不动了。【这不是证悟, 你永远仍疑】; 到顶就老实承认, 该换话头, 别硬造新词显得在动。

输出严格 JSON (不要 markdown 代码块):
{{
  "rebuttal_check": [{{"反对": "驳的某条(简述)", "回应": "真回应/绕过/没答"}}],
  "surpasses_which": "超越已悟第N条 + 抄那条原话; 没超越则填 '无'",
  "new_delta": "一个新区分/新情形; 说不出则填 '无'",
  "moved": true/false,
  "insight": "moved=true: 此刻稳住的新理解(展开推理、不轻薄、保留张力别抹平, 100-400字); 否则留空",
  "reached_plateau": true/false,
  "summary": "一句话"
}}"""
    raw = ds(system, user, temperature=0.2, max_tokens=32000)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    if raw.lstrip().startswith("json"):
        raw = raw.lstrip()[4:]
    try:
        v = json.loads(raw.strip())
    except Exception as e:
        return {"moved": False, "summary": f"(收敛解析失败: {e})", "insight": "", "reached_plateau": False, "parse_error": True}
    # 代码侧硬闸: 不信 DS 自评 moved —— 任一反对被绕过/没答, 或拿不出 new_delta/超越, 一律强制 moved=false
    rc = v.get("rebuttal_check") or []
    dodged = any(str(x.get("回应", "")).strip() in ("绕过", "没答") for x in rc)
    no_delta = str(v.get("new_delta", "")).strip() in ("", "无")
    no_surpass = str(v.get("surpasses_which", "")).strip() in ("", "无")
    if dodged or (no_delta and no_surpass):
        v["moved"] = False
        v["insight"] = ""
    # 语义新颖度闸: 过了举证关, 再用 embedding 直接验"这洞见到底新没新" —— 堵死"编个听着像具体区分的假delta"
    # (举证字段只查得了非空,查不了真新; embedding 量语义距离, 且比的是全部旧洞见【全文】, 不受压缩区盲点影响)
    if v.get("moved") and v.get("insight") and neo4j_io is not None:
        priors = [h["insight"] for h in koan["history"] if h.get("verdict") == "动" and h.get("insight")]
        if priors:
            try:
                embs = neo4j_io.embed([v["insight"]] + priors)
                sim = max(_cosine(embs[0], pe) for pe in embs[1:])
                if sim >= NOVELTY_SIM:
                    v["moved"] = False
                    v["insight"] = ""
                    v["summary"] = f"(换皮: 新洞见与旧洞见语义重合 {sim:.2f}≥{NOVELTY_SIM})"
                    print(f"     ⊘ 语义新颖度闸: 与旧洞见重合 {sim:.2f} → 判换皮(未动)", file=sys.stderr)
            except Exception as e:
                print(f"     (新颖度闸 embedding 暂不可用, 退回举证闸: {str(e)[:40]})", file=sys.stderr)
    return v


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
                    world = "世界最近就这(几)类苦发出的真实声音(贴着活的苦参, 别抽象掉):\n" + \
                        "\n".join(f"· {r['text']}" for r in rows)
                    print(f"     ⊙ 回灌 {len(apps[:4])} 类共 {len(rows)} 声苦 (新 context)", file=sys.stderr)
            except Exception as e:
                print(f"     (新闻回灌失败: {str(e)[:40]})", file=sys.stderr)

        # 两阶段攻: 先【经】【解】立论 → 把【解】原文注入【驳人镜行默】, 咬住它的原话(真对抗)
        with ThreadPoolExecutor(max_workers=2) as ex:
            a_res = list(ex.map(lambda a: attack(koan, a[0], a[1], a[2], canon, memory, world), ANGLES_A))
        solve_text = dict(a_res).get("解", "")
        with ThreadPoolExecutor(max_workers=5) as ex:
            b_res = list(ex.map(lambda a: attack(koan, a[0], a[1], a[2], canon, memory, world, solve_text), ANGLES_B))
        attacks = a_res + b_res

        # 收敛 + 对抗式判定 (举证式, 代码硬闸)
        v = synthesize(koan, attacks)
        if v.get("parse_error"):   # 收敛没读到判决: 本轮作废, 不计历史/不动 streak/不耗 attempts
            print(f"     ⚠ 收敛解析失败, 本轮作废重来 (不污染状态)", file=sys.stderr)
            time.sleep(args.sleep)
            continue
        print(f"     → moved={v['moved']} 到段落={v.get('reached_plateau')}: {v['summary']}", file=sys.stderr)

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
            # 动了就【绝不】停: 还在生产, 让它接着凿。plateau 不在"动"时触发(防参1-2轮还在动就自封到顶)。
        else:
            koan["no_move_streak"] += 1
            # 自觉"到段落": 仅当【已认真深参过(≥PLATEAU_FLOOR轮)且当前没动】才honor —— 不是证悟, 仍疑。
            if v.get("reached_plateau") and koan["attempts"] >= PLATEAU_FLOOR:
                koan["status"] = "暂搁"
                print(f"     ⏸ 深参 {koan['attempts']} 轮后自觉到段落, 转『暂搁』(不是证悟, 仍疑)", file=sys.stderr)
            elif koan["no_move_streak"] >= NO_MOVE_LIMIT:
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
