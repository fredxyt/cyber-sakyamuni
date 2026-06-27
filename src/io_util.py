#!/usr/bin/env python3
"""原子写 —— 写临时文件再 os.replace 改名。进程被杀/磁盘满时不会留下半写损坏的状态文件
(koans.json 一旦半写, 下一跳 json.loads 崩 → 永久停摆)。"""
import json
import os
from pathlib import Path

BAD_TITLE_PUNCT = "。！？!?；;"


def write_json_atomic(path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)   # 同盘 rename 原子: 要么旧的完整, 要么新的完整, 永不半截


def _clean_title_prefix(title):
    title = title.strip().lstrip("#").strip()
    return title.removeprefix("今日札记").lstrip(":：· ").strip()


def title_looks_bad(title, max_chars=24, bad_punctuation=True):
    title = _clean_title_prefix(title)
    return (not title) or len(title) > max_chars or (bad_punctuation and any(p in title for p in BAD_TITLE_PUNCT))


def split_generated_note(text, fallback_title, max_title_chars=24):
    """Split LLM note output and keep paragraph-like first lines out of H1."""
    raw = text.strip()
    lines = raw.split("\n", 1)
    raw_title = _clean_title_prefix(lines[0]) if lines else ""
    if title_looks_bad(raw_title, max_title_chars):
        return fallback_title, raw
    return raw_title, (lines[1].strip() if len(lines) > 1 else "")


def safe_display_title(title, fallback_title, max_title_chars=24, bad_punctuation=False):
    title = _clean_title_prefix(title)
    if title_looks_bad(title, max_title_chars, bad_punctuation=bad_punctuation):
        return fallback_title
    return title
