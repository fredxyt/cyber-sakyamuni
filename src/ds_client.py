#!/usr/bin/env python3
"""共享的 DeepSeek 大脑客户端 + 秒级时间戳。三处参悟代码共用, 不重复实例化。"""
import os
import sys
import time
from datetime import datetime, timezone

from openai import OpenAI

client = OpenAI(
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.environ["DEEPSEEK_API_KEY"], timeout=600,
)
MODEL = os.environ.get("DS_MODEL", "deepseek-v4-pro")


def ds(system, user, temperature=0.85, max_tokens=32000, retries=3):
    """推理模型: max_tokens 给足, 别让 reasoning 饿死答案。
    重试+指数退避+温度递增 —— 24x7 下 DeepSeek 限流/超时是必发事件, 不能一崩了之。"""
    last = None
    for attempt in range(1, retries + 1):
        try:
            t = min(temperature + (attempt - 1) * 0.1, 1.0)
            r = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=t, max_tokens=max_tokens,
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            last = e
            print(f"     (DeepSeek 第{attempt}次失败: {str(e)[:60]}, 退避重试)", file=sys.stderr)
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise last


def now_iso() -> str:
    """秒级 UTC 时间戳。24x7 不停参, 日级不够分辨, 必须到秒。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_stamp() -> str:
    """文件名安全的秒级戳 (冒号换横线): 2026-06-20T01-12-30Z"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
