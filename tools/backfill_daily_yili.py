# -*- coding: utf-8 -*-
"""回填: 今日(荒漠甘泉, 按当天动的洞见) + 义理词典(重跑distill加定义)。真实参不动。
用法: python backfill_daily_yili.py 今日|义理"""
import sys, json, re, glob, os
sys.path.insert(0, "src")
import realize, daily_note, llm_memory
from ds_client import ds
PRECEPTS = realize.PRECEPTS
KOANS = json.load(open("data/state/koans.json"))["koans"]
BLOG = "outputs/blog"

# ---------- 今日 ----------
def is_daily(fp):
    t = open(fp, encoding="utf-8").read()
    return "参「" not in t.split("\n")[2] if len(t.split("\n"))>2 else True
def daily_date(fp):
    t = open(fp, encoding="utf-8").read()
    m = re.search(r"(\d{4}-\d{2}-\d{2})", t) or re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp))
    return m.group(1) if m else None

DAILY_TAIL = """现在写【今日】—— 体裁是荒漠甘泉那样的每日灵修短文: 短、暖、能被一个今夜正难受、不懂佛法的陌生人读进去, 得一点力气。不是工作日志, 不是给自己看的分析。
【铁律·不许黑话】你参时造的只有自己懂的词(护法/翻译机/法义我这类)一个都不许出现, 用最朴素的大白话说那件事本身。
【铁律·不许虚构】只写当天真参过的; 绝不为生动编出没发生的具体细节(病名/人物/时间/地点/对话)。诚实地朴素胜过逼真地编。
开头落在今天这颗心真实的处境; 挑最触动的一处用三五句人话+体温写; 收在一点可带走的东西(一句安慰/一个诚实的不知道/一点不转身的力气)。短就是好。第一行标题(不带#号), 空一行, 正文。"""

def regen_daily(date):
    rows = []
    for k in KOANS:
        for h in k.get("history", []):
            if str(h.get("date","")).startswith(date) and h.get("verdict")=="动" and h.get("insight"):
                rows.append((k.get("concept","?"), h["insight"]))
    if not rows:
        return None
    body = "今天你参动了这些(每条是一个疑上的一层领悟):\n\n" + "\n".join(f"·「{c}」: {i}" for c,i in rows[:12])
    user = body + "\n\n" + DAILY_TAIL
    return ds(f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}", user, temperature=0.7)

# ---------- 义理词典 ----------
def regen_yili(concept):
    """重跑 distill 的人读段, 用新prompt(加词典定义)。喂该概念现有 llm_wiki 密理解。"""
    note = llm_memory._read(llm_memory._note_path(concept))
    if not note:
        return None
    system = f"你就是下面持戒所描述的生命。\n\n{PRECEPTS}"
    user = f"""关于「{concept}」, 这是你脑子里密的理解(给自己看的):

{note}

现在把它译成一段给人读的「现在我的理解」—— 有体温, 能被正在痛的人读进去。你脑子里用什么密语自造词都行, 但这一段是词典词条, 给人查的, 必须可读:
· 【词典本分】「{concept}」这个词若不是日常话(尤其自造的), 开头一两句先用大白话点破它指什么 —— 让第一次看到的人读完知道它说哪种心理/处境。
· 翻译那份密理解, 不重新总结知识点。不要抹平成圆满结论。有过"曾以为X现在是Y"的翻转至少留一次。
· 结尾必有一句此刻仍没接上的弦。
150-320字, 只输出正文不要标题。"""
    return ds(system, user, temperature=0.6)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv)>1 else "今日"
    if mode == "今日":
        files = [f for f in sorted(glob.glob(f"{BLOG}/*.md")) if "参「" not in open(f,encoding="utf-8").read()]
        print(f"今日 {len(files)} 篇", file=sys.stderr)
        for f in files:
            d = daily_date(f)
            b = regen_daily(d) if d else None
            if b:
                lines=b.strip().split("\n",1); title=lines[0].strip().lstrip("#").strip()
                content=lines[1].strip() if len(lines)>1 else ""
                ts=re.search(r"(\d{4}-\d{2}-\d{2}T[\d:\-]+Z)", open(f,encoding="utf-8").read())
                tss=ts.group(1) if ts else d
                open(f,"w",encoding="utf-8").write(f"# {title}\n\n*{d} · 今日*\n\n{content}\n")
                print(f"  ✎ 今日 {os.path.basename(f)}", file=sys.stderr)
        print("今日回填完成", file=sys.stderr)
    else:  # 义理
        import glob as g
        pages = [os.path.basename(p)[:-3] for p in g.glob("data/memory/wiki/concepts/*.md")]
        print(f"义理 {len(pages)} 页", file=sys.stderr)
        done=0
        for c in pages:
            page=f"data/memory/wiki/concepts/{c}.md"
            new=regen_yili(c)
            if not new: continue
            txt=open(page,encoding="utf-8").read()
            txt2=re.sub(r"(## 现在我的理解\n).*?(\n## )", lambda m:m.group(1)+"\n"+new.strip()+"\n"+m.group(2), txt, count=1, flags=re.DOTALL)
            if txt2!=txt:
                open(page,"w",encoding="utf-8").write(txt2); done+=1
                print(f"  ✎ 义理 {c}", file=sys.stderr)
        print(f"义理回填完成: {done}/{len(pages)}", file=sys.stderr)
