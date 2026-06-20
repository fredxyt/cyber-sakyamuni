#!/usr/bin/env python3
"""共享的 DeepSeek 大脑客户端 + 秒级时间戳。三处参悟代码共用, 不重复实例化。"""
import os
from datetime import datetime, timezone

from openai import OpenAI

client = OpenAI(
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.environ["DEEPSEEK_API_KEY"], timeout=600,
)
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-pro")


def ds(system, user, temperature=0.85, max_tokens=32000):
    """推理模型: max_tokens 给足, 别让 reasoning 饿死答案。"""
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature, max_tokens=max_tokens,
    )
    return r.choices[0].message.content.strip()


def now_iso() -> str:
    """秒级 UTC 时间戳。24x7 不停参, 日级不够分辨, 必须到秒。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_stamp() -> str:
    """文件名安全的秒级戳 (冒号换横线): 2026-06-20T01-12-30Z"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
