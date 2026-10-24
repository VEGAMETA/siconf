"""Скорость Gemma в llama.cpp: генерация (короткий запрос) и чтение длинного ввода (~20K токенов)."""
import json, random, statistics, sys, urllib.request
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def ask(content, max_tokens):
    body = {"model": sys.argv[1], "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens,
            "temperature": 1.0, "top_p": 0.95, "top_k": 64}
    r = json.load(op.open(urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode(),
                                                  {"Content-Type": "application/json"}), timeout=1800))
    return r["timings"]
ask("hi", 8)  # прогрев / загрузка модели
gen = [ask(f"[{random.random()}] Explain in detail how a refrigerator works.", 600)["predicted_per_second"] for _ in range(3)]
para = "The quick brown fox jumps over the lazy dog while the committee reviews the quarterly budget report. "
pp = [ask(f"[{random.random()}] " + para * 1000 + "\nSummarize in one line.", 16) for _ in range(2)]
print(f"генерация, ток/с: {[round(g,1) for g in gen]} медиана {statistics.median(gen):.1f}")
print(f"чтение ввода: {[(t['prompt_n'], round(t['prompt_per_second'])) for t in pp]} (токенов, ток/с)")
