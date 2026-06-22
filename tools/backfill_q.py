# -*- coding: utf-8 -*-
import json, re, glob
# 我读正文判定的: 文件名 → 该概念话头列表里的序号
M = {
"2026-06-20T05-41-09Z":0,"2026-06-20T07-01-48Z":0,"2026-06-20T08-21-44Z":0,
"2026-06-20T16-03-06Z":0,"2026-06-20T17-11-42Z":1,"2026-06-20T18-43-11Z":2,
"2026-06-20T19-42-05Z":1,"2026-06-20T19-53-26Z":1,"2026-06-20T21-23-01Z":3,
"2026-06-20T22-03-21Z":4,"2026-06-20T23-11-52Z":5,"2026-06-20T23-21-55Z":0,
"2026-06-20T23-51-45Z":0,"2026-06-21T00-12-18Z":1,"2026-06-21T00-33-27Z":0,
"2026-06-21T06-12-12Z":1,"2026-06-21T07-14-00Z":0,"2026-06-21T07-24-59Z":1,
"2026-06-21T08-22-24Z":5,"2026-06-21T09-34-15Z":1,"2026-06-21T09-44-33Z":0,
"2026-06-21T19-52-48Z":1,"2026-06-22T00-06-25Z":0,"2026-06-22T05-13-19Z":1,
"2026-06-22T08-09-33Z":0,"2026-06-22T11-30-21Z":1,"2026-06-22T12-17-13Z":1,
}
d=json.load(open("data/state/koans.json"))
qs={}
for k in d["koans"]: qs.setdefault(k.get("concept"),[]).append(k["question"])
done=0
for stem,idx in M.items():
    f=f"outputs/blog/{stem}.md"
    md=open(f,encoding="utf-8").read()
    if "<!--Q:" in md: print("已有,跳过",stem); continue
    cm=re.search(r"参「([^」]+)」",md); c=cm.group(1) if cm else None
    if not c or idx>=len(qs.get(c,[])): print("✗ 无法定位",stem,c,idx); continue
    q=qs[c][idx].replace("\n"," ").strip()
    # 在副标题行后插入 <!--Q-->
    md2=re.sub(r"(\*参「[^」]+」之后[^\n]*\*\n)", r"\1<!--Q:"+q.replace("\\","\\\\")+"-->\n", md, count=1)
    if md2==md:  # 副标题没匹配到, 退而在首行后插
        md2=md.replace("\n","\n<!--Q:"+q+"-->\n",1)
    open(f,"w",encoding="utf-8").write(md2); done+=1
    print(f"✎ {stem} [{c}] ← {q[:34]}")
print("回填:",done,"/",len(M))
