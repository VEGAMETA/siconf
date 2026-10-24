"""Посредник между Open WebUI и llama.cpp: размышления Gemma партиями с контрольными точками.

Open WebUI -> http://127.0.0.1:8081/v1 -> этот посредник -> http://127.0.0.1:8080 (llama.cpp)

Обычный ответ (до FIRST токенов размышлений, ~93% случаев) проходит без изменений.
Если модель всё ещё думает, генерация останавливается, в её размышления дописывается контрольная точка
(«уверена — отвечай; нет — назови, что не проверено и как проверишь иначе») и генерация продолжается
с того же места: llama.cpp продолжает незакрытые размышления последнего сообщения ассистента и берёт
прочитанное из кэша. Следующие точки — каждые STEP токенов, после HARD — «время вышло, отвечай».
Ответ и вызовы инструментов разбирает сам llama.cpp. Всё остальное (модели, служебные запросы
без размышлений) проходит насквозь.
"""
import collections
import json
import logging
import os
import re
import time

import aiohttp
from aiohttp import web

UPSTREAM = "http://127.0.0.1:8080"
LISTEN_HOST, LISTEN_PORT = "127.0.0.1", int(os.environ.get("THINK_PORT", 8081))
# по 431 ответу Gemma (2026-10-24): длиннее 6000 токенов — 7%, длиннее 12000 — 1%, длиннее 16000 — только круги
FINAL_ANSWER_CAP = 4000
FIRST, STEP, HARD = (int(os.environ.get(k, d)) for k, d in (("THINK_FIRST", 6000), ("THINK_STEP", 4000), ("THINK_HARD", 18000)))

# Формулировки мягкие: пауза «оглянуться», а не «торопись» (без счётчика токенов) — давление
# заставляет модель бросать рассуждение на середине. Финал твёрдый, но разрешает честную неуверенность.
CHECKPOINT = (
    "\n\n[Pause: take stock before going on. If the answer is already established, write it. If something important "
    "is still open, name it in one sentence and how you will settle it: with a tool such as code or web search, or by "
    "a different method than the ones you have tried. Then continue calmly; there is no need to rush.]\n"
)
# Круг: одна и та же строка размышлений повторилась LOOP_REPEATS раз среди последних LOOP_WINDOW строк
# (как «Is it "Втулка"? Is it "Втулка"?») — не ждать паузы на 6000, а сразу остановить и подсказать выход
LOOP_WINDOW, LOOP_REPEATS, MAX_LOOP_NOTES = 40, 4, 2
# Петля — это вырождение выборки (модель застряла на одном слове), одна пауза её не снимает. После первой
# пойманной петли до конца ответа включается DRY. Разделитель — символ, которого в тексте не бывает: со
# стандартными (\n : " *) DRY не ловит «Is it **"Втулка"**?», а пустой список сервер не принимает.
ANTI_REPEAT = {"dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 3, "dry_penalty_last_n": 4096,
               "dry_sequence_breakers": ["␞"]}
LOOP = (
    "\n\n[Pause: you are going in circles, the same lines and candidates keep coming back. Do not list them again. {way} "
    "Keep the final answer in the language your instructions require.]\n"
)
LOOP_SEARCH = ("The answer depends on something you cannot recall, so call the {tool} tool now with a short query and "
               "build the answer on its results.")
LOOP_NO_SEARCH = ("Answer with what you have: give your best candidates once and ask the user one short clarifying "
                  "question.")
FINAL = (
    "\n\n[Thinking time is up. Write the final answer now with what you have: give your best answer, and say plainly "
    "which part is uncertain. Keep the final answer in the language your instructions require.]\n"
)

log = logging.getLogger("think_proxy")
HOP = {"host", "content-length", "transfer-encoding", "connection", "keep-alive", "accept-encoding"}


def batched(body):
    """Партии нужны только Gemma с включёнными размышлениями (служебная модель без них идёт насквозь)."""
    kwargs = body.get("chat_template_kwargs") or {}
    return str(body.get("model", "")).startswith("gemma") and kwargs.get("enable_thinking") is not False


async def passthrough(request, session, raw=None):
    """Запрос как есть, ответ потоком как есть."""
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    data = raw if raw is not None else await request.read()
    async with session.request(request.method, UPSTREAM + request.rel_url.path_qs, headers=headers, data=data,
                               timeout=aiohttp.ClientTimeout(total=None)) as up:
        resp = web.StreamResponse(status=up.status, headers={k: v for k, v in up.headers.items() if k.lower() not in HOP})
        await resp.prepare(request)
        async for chunk in up.content.iter_any():
            await resp.write(chunk)
        await resp.write_eof()
        return resp


async def sse(up):
    """Строки data: из потока llama.cpp как словари."""
    async for line in up.content:
        line = line.strip()
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if payload == b"[DONE]":
            return
        yield json.loads(payload)


class Batches:
    """Одна партия = один потоковый запрос в llama.cpp; партии склеиваются в один ответ клиенту."""

    def __init__(self, body):
        self.body = body
        self.thinking = ""          # размышления целиком, включая контрольные точки
        self.content = ""           # уже выданная часть ответа (для продолжения, если партия его обрезала)
        self.thinking_tokens = 0
        self.answer_started = False
        self.completion_tokens = 0
        self.prompt_tokens = None
        self.chunk_id = None
        self.created = int(time.time())
        self.checkpoints = 0
        self.loop_notes = 0
        self.lines = collections.deque(maxlen=LOOP_WINDOW)
        self.partial_line = ""
        names = [(x.get("function") or {}).get("name", "") for x in body.get("tools") or []]
        # поиск в интернете, а не по базам знаний, беседам или памяти
        self.search_tool = next((n for n in ("search_web", "web_search") if n in names),
                                next((n for n in names if "web" in n and "search" in n), None))
        self.anti_repeat = False    # после пойманной петли — штраф за дословные повторы до конца ответа

    def looping(self, reasoning):
        """Добавить кусок размышлений; True, если какая-то строка повторилась LOOP_REPEATS раз в окне."""
        self.partial_line += reasoning
        *done, self.partial_line = self.partial_line.split("\n")
        for line in done:
            norm = re.sub(r"^[\s*\-\d.)#]+", "", line).strip(" *_").lower()
            if len(norm) < 8:
                continue
            self.lines.append(norm)
            if self.lines.count(norm) >= LOOP_REPEATS:
                return True
        return False

    def request_body(self, max_tokens, forced=False):
        body = dict(self.body, stream=True, stream_options={"include_usage": True})
        body.pop("max_completion_tokens", None)
        body.pop("max_tokens", None)
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if self.anti_repeat:
            body.update(ANTI_REPEAT)
        if self.thinking or self.content:
            # последнее сообщение ассистента = продолжение: с пустым content шаблон оставляет размышления
            # незакрытыми (модель думает дальше); с непустым — закрывает их и модель продолжает ответ
            content = self.content or (" " if forced else "")
            body["messages"] = list(self.body["messages"]) + [
                {"role": "assistant", "content": content, "reasoning_content": self.thinking}]
        return body

    def synthetic(self, reasoning):
        return {"id": self.chunk_id or "chatcmpl-think-proxy", "object": "chat.completion.chunk", "created": self.created,
                "model": self.body.get("model"), "choices": [{"index": 0, "delta": {"reasoning_content": reasoning},
                                                             "finish_reason": None}]}

    async def run(self, session, emit):
        """emit(chunk) получает чанки в формате OpenAI. Возвращает finish_reason последней партии."""
        user_cap = self.body.get("max_tokens") or self.body.get("max_completion_tokens")
        next_stop, forced = FIRST, False
        while True:
            # предел партии — только пока модель думает; ответ дописывается без нашего предела
            ours = None if self.answer_started or forced else next_stop - self.thinking_tokens
            if forced and not self.answer_started:
                ours = FINAL_ANSWER_CAP  # после «время вышло» модель может продолжить рассуждать уже в ответе
            left = user_cap - self.completion_tokens if user_cap else None
            limit = min(x for x in (ours, left) if x is not None) if (ours or left) else None
            # после «время вышло» обрезка — настоящий конец ответа: finish и usage идут клиенту как есть
            cut_by_us = ours is not None and (left is None or ours < left) and not forced
            finish, batch_reasoning, batch_tokens, looped = None, "", 0, False
            async with session.post(UPSTREAM + "/v1/chat/completions", json=self.request_body(limit, forced),
                                    timeout=aiohttp.ClientTimeout(total=None)) as up:
                if up.status != 200:
                    raise web.HTTPBadGateway(text=await up.text(), content_type="application/json")
                async for chunk in sse(up):
                    self.chunk_id = self.chunk_id or chunk.get("id")
                    chunk["id"] = self.chunk_id
                    usage = chunk.get("usage")
                    if usage:
                        batch_tokens = usage.get("completion_tokens", 0)
                        self.prompt_tokens = self.prompt_tokens or usage.get("prompt_tokens")
                        usage["completion_tokens"] = self.completion_tokens + batch_tokens
                        usage["prompt_tokens"] = self.prompt_tokens
                        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("reasoning_content"):
                            batch_reasoning += delta["reasoning_content"]
                            if not self.answer_started and not forced and self.looping(delta["reasoning_content"]):
                                looped = True
                        if delta.get("content"):
                            self.content += delta["content"]
                        if delta.get("content") or delta.get("tool_calls"):
                            self.answer_started = True
                        finish = choice.get("finish_reason") or finish
                        if choice.get("finish_reason") == "length" and cut_by_us:
                            choice["finish_reason"] = None  # конец партии, а не ответа: клиенту не показываем
                    # usage обрезанной нами партии клиенту не нужен — придёт итоговый
                    if usage and finish == "length" and cut_by_us:
                        continue
                    await emit(chunk)
                    if looped:
                        break  # закрыть поток: llama.cpp прекращает генерацию, когда клиент отключается
            if looped and not batch_tokens:
                batch_tokens = len(batch_reasoning) // 3  # usage не пришёл — оценка по длине текста
            self.completion_tokens += batch_tokens
            self.thinking += batch_reasoning
            log.info("batch: finish=%s tokens=%d reasoning=%d chars answer=%d chars forced=%s",
                     finish, batch_tokens, len(batch_reasoning), len(self.content), forced)
            if looped:
                self.loop_notes += 1
                self.anti_repeat = True
                self.thinking_tokens = self.completion_tokens
                self.lines.clear()
                if self.loop_notes > MAX_LOOP_NOTES or self.thinking_tokens >= HARD:
                    note, forced = FINAL.format(used=self.thinking_tokens), True
                else:
                    way = LOOP_SEARCH.format(tool=self.search_tool) if self.search_tool else LOOP_NO_SEARCH
                    note, next_stop = LOOP.format(way=way), max(next_stop, self.thinking_tokens + STEP)
                log.info("loop detected at ~%d thinking tokens (note %d)%s", self.thinking_tokens, self.loop_notes,
                         " -> final" if forced else "")
                self.thinking += note
                await emit(self.synthetic(note))
                continue
            if finish != "length" or not cut_by_us:
                return finish
            if self.answer_started and not forced:
                # модель уже закончила думать и отвечала, а партия обрезала ответ: дописать его без предела
                log.info("answer cut at batch boundary, continuing it")
                continue
            # партия кончилась посреди размышлений: контрольная точка или конец бюджета
            self.thinking_tokens = self.completion_tokens
            if self.thinking_tokens >= HARD:
                note, forced = FINAL.format(used=self.thinking_tokens), True
            else:
                self.checkpoints += 1
                note, next_stop = CHECKPOINT.format(used=self.thinking_tokens), self.thinking_tokens + STEP
            log.info("checkpoint %d at %d thinking tokens%s", self.checkpoints, self.thinking_tokens,
                     " (final)" if forced else "")
            self.thinking += note
            await emit(self.synthetic(note))


async def chat(request):
    session = request.app["session"]
    raw = await request.read()
    try:
        body = json.loads(raw)
    except ValueError:
        return await passthrough(request, session, raw)
    if not batched(body):
        return await passthrough(request, session, raw)

    job = Batches(body)
    if body.get("stream"):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)

        async def emit(chunk):
            await resp.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n")

        await job.run(session, emit)
        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp

    # клиент без потока: собрать один ответ из чанков
    message = {"role": "assistant", "content": "", "reasoning_content": ""}
    tool_calls, usage = {}, None

    async def collect(chunk):
        nonlocal usage
        usage = chunk.get("usage") or usage
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            message["content"] += delta.get("content") or ""
            message["reasoning_content"] += delta.get("reasoning_content") or ""
            for tc in delta.get("tool_calls") or []:
                slot = tool_calls.setdefault(tc.get("index", 0), {"id": None, "type": "function",
                                                                  "function": {"name": "", "arguments": ""}})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["function"]["name"] += fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""

    finish = await job.run(session, collect)
    if tool_calls:
        message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
    return web.json_response({"id": job.chunk_id, "object": "chat.completion", "created": job.created,
                              "model": body.get("model"), "usage": usage,
                              "choices": [{"index": 0, "message": message, "finish_reason": finish}]})


async def other(request):
    return await passthrough(request, request.app["session"])


async def on_startup(app):
    app["session"] = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=64), trust_env=False)


async def on_cleanup(app):
    await app["session"].close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = web.Application(client_max_size=256 * 1024 * 1024)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_post("/chat/completions", chat)
    app.router.add_route("*", "/{tail:.*}", other)
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT, access_log=None)


if __name__ == "__main__":
    main()
