"""Короткий тест-ловушка для вариантов самопроверки (шаг 4): 20 задач с неочевидным ответом.

Запуск: python traps.py old new noalt   (промпты sys_ab_<вариант>.txt делает make_ab_prompts.py)
Каждая задача — SAMPLES раз на вариант, параллельно 4 запроса, напрямую в llama.cpp.
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.request
from fractions import Fraction

SAMPLES = 2
SUFFIX = "\n\nEnd your reply with a final line in the form 'Answer: <value>'."
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
traps = json.load(open("traps.json", encoding="utf-8"))


def match(ans, expected):
    """Числовой ответ: первое число или дробь в ответе (10 cents, 22.5°, 1/2 = 0.5); иначе — слово целиком."""
    ans = ans.lower().replace(",", "")
    try:
        exp = Fraction(expected)
    except ValueError:
        return re.sub(r"[^a-z]", "", ans) == expected
    m = re.search(r"-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?", ans)
    return bool(m) and Fraction(m.group().replace(" ", "")) == exp


def ask(system, q):
    body = {"model": "gemma-4-26b-a4b", "messages": [{"role": "system", "content": system}, {"role": "user", "content": q + SUFFIX}],
            "temperature": 1.0, "top_p": 0.95, "top_k": 64, "max_tokens": 16384}
    t0 = time.time()
    r = json.load(op.open(urllib.request.Request(os.environ.get("TRAPS_URL", "http://127.0.0.1:8080") + "/v1/chat/completions", json.dumps(body).encode(),
                                                  {"Content-Type": "application/json"}), timeout=3600))
    content = r["choices"][0]["message"].get("content") or ""
    m = re.findall(r"answer\s*[:：]\s*\**\s*([^\n*]+)", content, re.I)
    return (m[-1] if m else ""), r["usage"]["completion_tokens"], time.time() - t0


results = {}
for variant in sys.argv[1:]:
    system = open(f"sys_ab_{variant}.txt", encoding="utf-8").read()
    jobs = [(t, s) for t in traps for s in range(SAMPLES)]
    with cf.ThreadPoolExecutor(4) as ex:
        outs = list(ex.map(lambda j: ask(system, j[0]["q"]), jobs))
    rows = []
    for (t, _), (ans, toks, sec) in zip(jobs, outs):
        rows.append({"id": t["id"], "ok": match(ans, t["a"]), "ans": ans, "tokens": toks, "sec": round(sec)})
    results[variant] = rows
    ok = sum(r["ok"] for r in rows)
    print(f"{variant}: {ok}/{len(rows)} верно, средне {sum(r['tokens'] for r in rows) / len(rows):.0f} токенов на ответ", flush=True)
    json.dump(results, open(os.environ.get("TRAPS_OUT", "traps_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("\nпо задачам (верных из %d):" % SAMPLES)
for t in traps:
    line = "  ".join(f"{v}={sum(r['ok'] for r in results[v] if r['id'] == t['id'])}" for v in results)
    wrong = {v: [r["ans"] for r in results[v] if r["id"] == t["id"] and not r["ok"]] for v in results}
    print(f"{t['id']:18} {line}   ошибки: {({k: v for k, v in wrong.items() if v})}")
