"""
title: Навык картинок по запросу
description: Включает навык image-generation для сообщения, в котором просят картинку (нарисовать, придумать обложку, логотип, постер, исправить картинку): правила FLUX 3 попадают к модели ровно тогда, когда нужны.
author: local
version: 0.1.0
"""

import re

SKILL = "image-generation"

# «нарисуй кота» — достаточно глагола рисования
DRAW = re.compile(r"нарису|изобрази|сгенериру|перерису|отрису|\bdraw\b|\bpaint\b|generate an? (image|picture)", re.I)
# «придумай обложку», «сделай логотип» — действие + визуальная вещь
ACTION = re.compile(r"придума|сделай|сделать|создай|создать|оформи|покажи|исправ|поправ|измени|убери|добавь|замени|"
                    r"\b(make|create|design|show|fix|edit|change|remove|add|replace)\b", re.I)
VISUAL = re.compile(r"обложк|постер|плакат|логотип|\bлого\b|аватар|баннер|превью|иллюстрац|картинк|изображени|"
                    r"\bфото|рисун|открытк|стикер|\bобои|иконк|\bарт\b|"
                    r"\b(cover|poster|logo|avatar|banner|thumbnail|illustration|image|picture|photo|drawing|icon|wallpaper)\b", re.I)
IMAGE_TOOLS = {"create_image", "edit_image"}


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _has_image(content):
    return isinstance(content, list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in content)


def _image_conversation(messages):
    """Картинки уже рисовали в этой беседе (вызовы create_image / edit_image в истории)."""
    for msg in messages[-12:]:
        for call in msg.get("tool_calls") or []:
            if (call.get("function") or {}).get("name") in IMAGE_TOOLS:
                return True
    return False


class Filter:
    def inlet(self, body: dict) -> dict:
        messages = body.get("messages") or []
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if not last:
            return body
        text = _text(last.get("content"))
        wants_image = (
            DRAW.search(text)
            or (ACTION.search(text) and VISUAL.search(text))
            # приложил картинку и просит что-то поменять
            or (_has_image(last.get("content")) and ACTION.search(text))
            # правка уже нарисованного: «сделай вечер», «убери кольцо»
            or (_image_conversation(messages) and ACTION.search(text))
        )
        if wants_image:
            body["skill_ids"] = sorted(set(body.get("skill_ids") or []) | {SKILL})
        return body
