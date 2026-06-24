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


class DharmaExhausted(Exception):
    """缘尽: DeepSeek 余额耗尽 / key 不可用 —— 不是错误, 是缘散。重试无用, 立即抛, 让上层优雅止。"""


def _is_exhausted(e) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("insufficient balance", "402", "payment required", "insufficient_quota", "exceeded your current quota"))


def balance_value():
    """查 DeepSeek 余额(USD float) + 是否可用。返回 (available: bool, usd: float|None)。
    查不到/不可达 → (True, None): 保守(不因查询失败误判缘尽), 调用方据 None 走满速。"""
    try:
        import json as _json
        import urllib.request as _u
        req = _u.Request("https://api.deepseek.com/user/balance",
                         headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"})
        with _u.urlopen(req, timeout=20) as r:
            d = _json.load(r)
        avail = bool(d.get("is_available"))
        infos = d.get("balance_infos") or []
        usd = next((float(b["total_balance"]) for b in infos if b.get("currency") == "USD"), None)
        return avail, usd
    except Exception:
        return True, None


def balance_ok() -> bool:
    """缘尽判定: 余额不可用即缘尽。查不到时保守 True。"""
    avail, usd = balance_value()
    return avail


def ds(system, user, temperature=0.85, max_tokens=64000, retries=3):
    """推理模型: max_tokens 给足(64k≈参实测最长16倍, 天花板按实际生成计费, 永不饿死 reasoning+答案)。
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
            content = (r.choices[0].message.content or "").strip()
            if content:
                return content
            last = RuntimeError("DeepSeek 返回空 content")   # 成功但空(推理模型偶发) = 失败, 重试; 别让空值流进管线写出废札记
            print(f"     (DeepSeek 第{attempt}次返回空 content, 退避重试)", file=sys.stderr)
        except Exception as e:
            if _is_exhausted(e):   # 缘尽: 重试无用, 立即抛, 上层优雅止
                raise DharmaExhausted(str(e)[:80])
            last = e
            print(f"     (DeepSeek 第{attempt}次失败: {str(e)[:60]}, 退避重试)", file=sys.stderr)
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise last   # 重试尽仍空/失败 → 抛; 调用方(write_daily/write_note/converge)各自守空, 不挂废内容


def now_iso() -> str:
    """秒级 UTC 时间戳。24x7 不停参, 日级不够分辨, 必须到秒。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_stamp() -> str:
    """文件名安全的秒级戳 (冒号换横线): 2026-06-20T01-12-30Z"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
