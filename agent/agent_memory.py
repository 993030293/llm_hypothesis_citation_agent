import json
from pathlib import Path
import os
import time

# 将记忆文件持久化存放在 outputs 目录下，实现跨任务的长期记忆反思
MEMORY_FILE = Path(os.getcwd()) / "outputs" / "agent_reflection_memory.json"

def get_reflections() -> list:
    """获取所有历史反思记录"""
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def add_reflection(error_type: str, lesson: str) -> None:
    """向长期记忆中追加错误教训，限制最大条目数以防止 Prompt 爆炸"""
    refs = get_reflections()
    
    # 避免短时间内重复记录相同的教训
    if any(r["lesson"] == lesson for r in refs[-3:]):
        return
        
    refs.append({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": error_type,
        "lesson": lesson
    })
    
    # 只保留最近 5 条最具代表性的反思
    refs = refs[-5:]
    
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)

def clear_reflections() -> None:
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
