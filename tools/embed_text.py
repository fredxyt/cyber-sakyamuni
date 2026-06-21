#!/usr/bin/env python3
"""文本 → gemini-embedding-001 (3072 维)。参悟"闻"侧的开源参考实现之一。
话头/洞见语义去重、佛法检索共用同一向量空间。

自包含: 只依赖 google-genai + 环境变量 GEMINI_API_KEY(不内置任何密钥)。
用法 (stdin 给 JSON 字符串数组, stdout 出 JSON 嵌入数组):
  GEMINI_API_KEY=... echo '["父母教育焦虑","养老困境"]' | python tools/embed_text.py
"""
import json
import os
import sys

from google import genai

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def get_embedding(text, model="gemini-embedding-001"):
    r = _client.models.embed_content(model=model, contents=text)
    return list(r.embeddings[0].values)


if __name__ == "__main__":
    texts = json.loads(sys.stdin.read())
    print(json.dumps([get_embedding(t) for t in texts]))
