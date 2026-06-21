#!/usr/bin/env python3
"""原子写 —— 写临时文件再 os.replace 改名。进程被杀/磁盘满时不会留下半写损坏的状态文件
(koans.json 一旦半写, 下一跳 json.loads 崩 → 永久停摆)。"""
import json
import os
from pathlib import Path


def write_json_atomic(path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)   # 同盘 rename 原子: 要么旧的完整, 要么新的完整, 永不半截
