"""
title: Поиск по текущей беседе
description: Ищет точные детали в полной (несжатой) истории текущего чата — чтобы после сжатия контекста модель могла найти и перепроверить то, что попало в краткий пересказ.
author: local
version: 0.1.0
"""

import json
import re

from open_webui.models.chats import Chats

EXCERPT_RADIUS = 400  # символов вокруг каждого совпадения
MAX_EXCERPTS_PER_MESSAGE = 3
FULL_MESSAGE_LIMIT = 20000  # символов при чтении сообщения целиком


async def _load_messages(chat_id, user):
    """Ветка текущего чата от первого сообщения до последнего, как видит её пользователь."""
    if not chat_id or not user:
        return None, "Нет контекста чата или пользователя"
    chat = await Chats.get_chat_by_id_and_user_id(chat_id, user.get("id"))
    if not chat:
        return None, "Чат не найден"
    history = (chat.chat or {}).get("history", {})
    messages_by_id = history.get("messages", {})
    chain, current, seen = [], history.get("currentId"), set()
    while current and current not in seen:
        seen.add(current)
        msg = messages_by_id.get(current)
        if not msg:
            break
        chain.append(msg)
        current = msg.get("parentId")
    chain.reverse()
    return chain, None


def _terms(query):
    words = [w.lower() for w in re.findall(r"[\w.\-]+", query) if len(w) >= 3]
    return list(dict.fromkeys(words))


def _excerpts(text, phrase, terms):
    low = text.lower()
    # приоритет: точная фраза, потом длинные (обычно более редкие) слова — короткое «рис» не должно
    # перебивать «carnaroli» только потому, что встретилось раньше внутри «ризотто»
    hits = []
    if phrase and phrase in low:
        hits.append(low.index(phrase))
    for term in sorted(terms, key=len, reverse=True):
        pos = low.find(term)
        if pos >= 0:
            hits.append(pos)
    windows = []
    for pos in hits:
        start, end = max(0, pos - EXCERPT_RADIUS), min(len(text), pos + EXCERPT_RADIUS)
        if any(s <= pos <= e for s, e in windows):
            continue
        windows.append((start, end))
        if len(windows) == MAX_EXCERPTS_PER_MESSAGE:
            break
    return [("…" if s > 0 else "") + text[s:e] + ("…" if e < len(text) else "") for s, e in sorted(windows)]


class Tools:
    def __init__(self):
        pass

    async def search_current_chat(self, query: str, max_results: int = 5, __user__: dict = None, __chat_id__: str = None) -> str:
        """
        Search the FULL, uncompressed history of the current conversation for exact details
        (numbers, names, versions, code, quotes, decisions) that may have been lost when older
        messages were summarized. Use it whenever you need a precise earlier detail instead of
        relying on a summary or guessing.
        :param query: Keywords or an exact phrase to look for, in the language the details were written in
        :param max_results: How many matching messages to return (default 5)
        :return: JSON with matching messages: position in the chat, role and text excerpts around the matches
        """
        chain, error = await _load_messages(__chat_id__, __user__)
        if error:
            return json.dumps({"error": error}, ensure_ascii=False)
        phrase, terms = query.strip().lower(), _terms(query)
        scored = []
        for position, msg in enumerate(chain, start=1):
            text = msg.get("content") or ""
            low = text.lower()
            score = sum(low.count(t) for t in terms) + (10 if phrase and phrase in low else 0)
            if score:
                scored.append((score, position, msg, text))
        scored.sort(key=lambda x: (-x[0], x[1]))
        results = [
            {"position": pos, "of": len(chain), "role": msg.get("role"), "excerpts": _excerpts(text, phrase, terms)}
            for _, pos, msg, text in scored[: max(1, min(max_results, 15))]
        ]
        return json.dumps(
            {"query": query, "total_messages": len(chain), "matches": results or "nothing found — try other keywords"},
            ensure_ascii=False,
        )

    async def read_current_chat_message(self, position: int, __user__: dict = None, __chat_id__: str = None) -> str:
        """
        Read one message of the current conversation in full, by its position from search_current_chat.
        Use it to verify an excerpt in its complete context.
        :param position: Message position (1 = first message of the chat)
        :return: JSON with the role and full text of the message
        """
        chain, error = await _load_messages(__chat_id__, __user__)
        if error:
            return json.dumps({"error": error}, ensure_ascii=False)
        if not 1 <= position <= len(chain):
            return json.dumps({"error": f"position must be between 1 and {len(chain)}"}, ensure_ascii=False)
        msg = chain[position - 1]
        text = msg.get("content") or ""
        return json.dumps(
            {"position": position, "of": len(chain), "role": msg.get("role"),
             "content": text[:FULL_MESSAGE_LIMIT], "truncated": len(text) > FULL_MESSAGE_LIMIT},
            ensure_ascii=False,
        )
