"""Тестовые системные промпты из боевых (D:\\gen\\prompts): всё как в чате, но ответ на английском.

Gemma получает промпт с <|think|> и порядком размышлений (как «Gemma 4 26B» в чате),
gpt-oss — промпт без <|think|> (как «gpt-oss 20B (думает дольше)»).
"""
import datetime
import pathlib

SRC = pathlib.Path(r"D:\gen\prompts")
OUT = pathlib.Path(__file__).parent
base = (SRC / "system_prompt_en.txt").read_text(encoding="utf-8").strip()
plan = (SRC / "thinking_plan_en.txt").read_text(encoding="utf-8").strip()

REPLACE = [
    # язык ответа: на время теста — английский, иначе автопроверка не сработает
    ("- Write the final answer in Russian only, unless the user explicitly asks for another language.",
     "- Write the final answer in English (evaluation mode)."),
    (" Do not draft or quote the Russian answer inside your thinking: plan it in English and write Russian only in the final answer.", ""),
    ("say plainly in Russian that web search is off", "say plainly that web search is off"),
    ("(e.g. \"по моим данным, не проверено\")", "(e.g. \"not verified\")"),
    ("5. Only then write the final answer in Russian, following the plan.", "5. Only then write the final answer, following the plan."),
    # в Open WebUI дату подставляет сам интерфейс, здесь — скрипт
    ("{{CURRENT_DATE}}", datetime.date.today().isoformat()),
]


def adapt(text):
    for old, new in REPLACE:
        text = text.replace(old, new)
    return text


gemma = adapt(base + "\n\n" + plan)
oss = adapt(base.replace("<|think|>", "").strip())
for name, text in (("sys_gemma_eval.txt", gemma), ("sys_oss_eval.txt", oss)):
    (OUT / name).write_text(text, encoding="utf-8")
    left = [w for w in ("Russian", "Russian", "CURRENT_DATE") if w in text]
    print(f"{name}: {len(text)} симв., осталось упоминаний: {sorted(set(left)) or 'нет'}")
