"""
title: Навыки в сообщение, а не в системный промпт
description: Срабатывает последним из фильтров: забирает выбранные навыки (skill_ids, в том числе от фильтров автовключения) и дописывает их текст в конец сообщения пользователя. Open WebUI сам вставляет навыки в системный промпт, и тогда каждая смена набора навыков меняет начало контекста — llama.cpp пересчитывает всю беседу заново (на 12K токенов это 12 с, на 100K+ — минуты). В конце сообщения навык меняет только хвост.
author: local
version: 0.1.0
"""

from open_webui.models.skills import Skills
from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        # больше, чем у фильтров автовключения (у них 0): этот должен идти после них
        priority: int = Field(default=100, description="Порядок среди фильтров: выполняется после остальных")

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(self, body: dict) -> dict:
        skill_ids = body.pop("skill_ids", None) or []
        if not skill_ids:
            return body
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "user"), None)
        if not last:
            body["skill_ids"] = skill_ids  # некуда дописать — пусть Open WebUI вставит сам
            return body
        blocks = []
        for sid in sorted(set(skill_ids)):
            skill = await Skills.get_skill_by_id(sid)
            if skill and skill.is_active and skill.content:
                blocks.append(f'<skill id="{skill.id}" name="{skill.name}">\n{skill.content.strip()}\n</skill>')
        if not blocks:
            return body
        note = "\n\n[Skill instructions for this message; follow them:]\n" + "\n\n".join(blocks)
        content = last.get("content")
        if isinstance(content, str):
            last["content"] = content + note
        elif isinstance(content, list):
            content.append({"type": "text", "text": note})
        return body
