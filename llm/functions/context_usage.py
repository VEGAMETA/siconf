"""
title: Расход контекста
description: Под каждым ответом — строка: сколько контекста занято (из 256K), сколько токенов в ответе, скорость генерации и чтения промпта по данным llama.cpp, сколько взято из кэша. Перед следующим запросом строка вырезается из истории, модель её не видит.
author: local
version: 0.2.1
"""

import re

from pydantic import BaseModel, Field

# строка статистики — Markdown-курсив (HTML вроде <sub> Open WebUI не отрисовывает); старый формат <sub> тоже вырезаем
STATS_RE = re.compile(r"\n*(?:<sub>контекст [^<]*</sub>|\*контекст [^*\n]*\*)\s*$")


def _k(n):
    """12345 -> «12,3K» (русская запятая)."""
    return f"{n / 1000:.1f}K".replace(".", ",") if n >= 1000 else str(int(n))


class Filter:
    class Valves(BaseModel):
        context_size: int = Field(default=262144, description="Размер контекста модели в токенах (пресет llama.cpp)")
        warn_percent: int = Field(default=75, description="С какого заполнения предупреждать о скором сжатии беседы")

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict) -> dict:
        # строка статистики — для человека; модели она не нужна и сбивала бы кэш llama.cpp
        for m in body.get("messages") or []:
            if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                m["content"] = STATS_RE.sub("", m["content"])
        return body

    def outlet(self, body: dict) -> dict:
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "assistant"), None)
        if not last or not isinstance(last.get("content"), str):
            return body
        usage = last.get("usage") or (last.get("info") or {}).get("usage") or {}
        # поля последнего вызова модели (Open WebUI в input/output_tokens складывает все вызовы ответа)
        prompt = usage.get("prompt_tokens") or 0
        completion = usage.get("completion_tokens") or 0
        if not (prompt or completion):
            return body
        used = prompt + completion
        percent = 100 * used / self.valves.context_size
        parts = [f"контекст {_k(used)} / {_k(self.valves.context_size)} ({percent:.1f} %)".replace(".", ","),
                 f"ответ {_k(completion)} ток."]
        if usage.get("predicted_per_second"):
            parts.append(f"генерация {usage['predicted_per_second']:.0f} ток/с")
        if usage.get("prompt_n") is not None and usage.get("prompt_per_second"):
            read = f"прочитано {_k(usage['prompt_n'])} ток. ({usage['prompt_per_second']:.0f} ток/с)"
            if usage.get("cache_n"):
                read += f", из кэша {_k(usage['cache_n'])}"
            parts.append(read)
        total_in = usage.get("input_tokens")
        if total_in and total_in > prompt:
            parts.append(f"всего за ответ с инструментами {_k(total_in + (usage.get('output_tokens') or 0))}")
        if percent >= self.valves.warn_percent:
            parts.append("скоро сжатие беседы")
        last["content"] = STATS_RE.sub("", last["content"]) + "\n\n*" + " · ".join(parts) + "*"
        return body
