"""A/B/C: шаг 4 плана размышлений.

old — старая самопроверка; new — «попробуй опровергнуть» с разбором самой сильной альтернативы;
noalt — то же без альтернативы (проверяет, не сбивает ли альтернатива с верного ответа).
Основа — sys_gemma_eval.txt (боевой промпт, ответ на английском), отличается только шаг 4.
"""
import pathlib

OUT = pathlib.Path(__file__).parent
OLD_STEP = ("4. Check: look for contradictions, points from the user's request you have not covered, "
            "wrong numbers, units or names, and fix them.")
TAIL = ("Also look for contradictions, points from the user's request you have not covered, wrong units or names. "
        "Change your answer only when you find a concrete error in it, not because an alternative merely sounds plausible. "
        "If a doubt that matters remains, state it in one line in the answer; do not hedge on what you have verified.")
NEW_STEP = ("4. Check: try to prove your draft answer wrong. Re-derive key numbers independently, "
            "consider the strongest alternative answer or reading of the question and say why it loses, "
            "and re-read the question for a false premise or a detail you skipped. " + TAIL)
NOALT_STEP = ("4. Check: try to prove your draft answer wrong. Re-derive key numbers independently "
              "and re-read the question for a false premise or a detail you skipped. " + TAIL)

base = (OUT / "sys_gemma_eval.txt").read_text(encoding="utf-8")
assert base.count(OLD_STEP) == 1, "шаг 4 в промпте не найден"
(OUT / "sys_ab_old.txt").write_text(base, encoding="utf-8")
(OUT / "sys_ab_new.txt").write_text(base.replace(OLD_STEP, NEW_STEP), encoding="utf-8")
(OUT / "sys_ab_noalt.txt").write_text(base.replace(OLD_STEP, NOALT_STEP), encoding="utf-8")
print("sys_ab_old.txt / sys_ab_new.txt / sys_ab_noalt.txt готовы")
