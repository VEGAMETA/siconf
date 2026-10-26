"""
title: Навыки по задаче
description: Включает навыки document-analysis (приложен документ или спрашивают о нём), data-analysis (таблицы, расчёты, графики), technical-translation (просьба перевести), health (здоровье, симптомы, лекарства; торговые названия по ГРЛС — справка с МНН) и law (законы, права, суды, штрафы) ровно в тех сообщениях, где они нужны.
author: local
version: 0.4.0
"""

import re

# приложенный документ или вопрос про документ
DOCUMENT = re.compile(r"документ|договор|\bpdf\b|\bdocx?\b|файл[еау]?\b|спецификац|техзадани|\bтз\b|регламент|инструкци[яию] (?:в|из)|"
                      r"в (?:этом |приложенном )?(?:тексте|файле|документе)|приложенн|прочитай|резюмир|выжимк|конспект|"
                      r"\b(?:this|the attached) (?:document|file|pdf)\b|summari[sz]e", re.I)
# таблицы, расчёты, графики
DATA = re.compile(r"\bcsv\b|\bxlsx?\b|excel|таблиц|график|диаграмм|построй|посчитай|подсчитай|статистик|средн(?:ее|ий|юю)|медиан|"
                  r"процент|тренд|динамик|корреляц|\b(?:plot|chart|dataframe|pandas)\b", re.I)
# перевод
TRANSLATE = re.compile(r"переведи|перевод|переводи|\btranslate\b|на английский|на русский|по-английски|по-русски|in english|into russian", re.I)
# здоровье: симптомы, болезни, лекарства, анализы
HEALTH = re.compile(r"болит|боль\b|боли\b|болезн|заболеван|симптом|температур|давлени[ея] (?:\d|высок|низк|скач|подня|упал)|"
                    r"кашел|кашля|насморк|сыпь|тошнит|рвот|понос|диаре|головокруж|одышк|отек|отёк|сердц|аритми|"
                    r"диабет|гипертон|инсульт|инфаркт|аллерг|астм|простуд|орви|грипп|ангин|ковид|covid|"
                    r"лекарств|препарат|таблетк|антибиотик|\bдоз[аеуы]?\b|дозиров|побочн|противопоказ|"
                    r"анализ(?:ы|ов)? крови|анализ мочи|холестерин|гемоглобин|сахар в крови|глюкоз|узи\b|мрт\b|"
                    r"диагноз|лечени|лечить|вылечить|врач|педиатр|терапевт|беременн|прививк|вакцин|"
                    # названия лекарств: типичные окончания действующих веществ и частые безрецептурные препараты
                    r"[а-яё]{3,}(?:профен|циллин|мицин|зол|сартан|статин|олол|дипин|прил|тидин|тадин|оксацин|циклин|вир|азепам)(?:[ауеом]|ом|ами)?\b|"
                    # как принимать: «омепразол один раз в день или на два приёма», «по 10 мг», «сколько пить»
                    r"\d+(?:[.,]\d+)?\s*(?:мг|мкг|ме)\b|(?:пить|пью|принимать|принимаю)[^.?!]{0,40}раз[а]? в (?:день|сутки)|"
                    r"(?:на|в|за) (?:один|два|три|\d) при[её]м|сколько (?:пить|принимать)|"
                    r"щитовид|тирео|гормон|\b(?:ттг|т3|т4|св\.? ?т4)\b|"
                    r"парацетамол|аспирин|нурофен|анальгин|но-?шп|дротаверин|диклофенак|кетор|цитрамон|супрастин|"
                    r"активированн|смект|регидрон|омез|метформин|варфарин|ксарелто|эликвис|л-?тироксин|эутирокс", re.I)

# право: законы, кодексы, права и обязанности, суды, штрафы, договоры с работодателем и продавцом
LAW = re.compile(r"закон|кодекс|\b(?:гк|гпк|тк|ск|жк|нк|ук|апк|кас)(?:\s*рф)?\b|коап|стать[яиюей] \d|\bст\.\s*\d|\bуказ(?:а|ом|у)?\b|постановлени[ея] правительства|"
                 r"юрист|адвокат|нотариус|\bсуд(?:а|е|ом|у|ебн)?\b|\bиск(?:а|ом|у)?\b|исков|претензи|жалоб[аую] в|прокуратур|"
                 r"законн|незаконн|имеет? (?:ли )?право|имею право|вправе|обязан[аы]? ли|права потребител|вернуть товар|возврат товара|"
                 r"увольн|уволи|работодател|трудов[а-я]+ договор|отпуск|больничн|зарплат|алимент|развод|наследств|завещани|"
                 r"штраф|гибдд|осаго|каско|налог|вычет|ипотек|аренд|договор[а-я]* (?:аренды|купли|займа|подряда)|собственник|прописк|регистрац[ия] по месту|"
                 r"персональн[а-я]+ данн|полици|протокол об|административн[а-я]+ (?:правонаруш|ответствен)|уголовн", re.I)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


# торговые названия лекарств → МНН из ГРЛС (D:\llm\health\grls_build.py): модель путала их по памяти (торговое название
# приняла за другое вещество). Справка дописывается к сообщению до того, как модель начнёт думать
GRLS_DB = r"D:\llm\health\grls.db"
_grls = {"mtime": None, "keys": {}}
ENDINGS = re.compile(r"(?:ами|ом|ой|ем|ей|ах|ов|ам|а|у|е|ы|и|ю|я)$")


def _stem(words):
    """Основа последнего слова; слова из 1-2 букв («АМ», «и») не трогаются — иначе «конкор ам» совпадал
    с «конкор и» и Конкор (бисопролол) становился Конкор АМ (бисопролол + амлодипин)."""
    last = words[-1]
    if len(last) > 3:
        last = ENDINGS.sub("", last)
    elif len(last) == 3:
        last = re.sub(r"[аеиуыюя]$", "", last)  # «шпа», «шпы» → «шп»
    return " ".join(words[:-1] + [last])


def _brands():
    import os
    import sqlite3
    try:
        mtime = os.path.getmtime(GRLS_DB)
    except OSError:
        return {}
    if _grls["mtime"] != mtime:
        con = sqlite3.connect(f"file:{GRLS_DB}?mode=ro", uri=True)
        keys = {}
        for k, t, i, g, a in con.execute("select key, trade, inn, grp, active from names where searchable = 1"):
            # по основе: «но шпа» и «но-шпы» сводятся к «но шп»
            stem = _stem(k.split())
            if len(stem) >= 4:
                keys.setdefault(stem, (k, (t, i, g, a)))
        _grls["keys"] = keys
        con.close()
        _grls["mtime"] = mtime
    return _grls["keys"]


def _find_brands(text):
    """Торговые названия в сообщении, с падежами («омеза», «глюкофаж лонг», «но-шпу»)."""
    keys = _brands()
    if not keys:
        return []
    words = re.findall(r"[a-zа-яё0-9]+", re.sub(r"[\-]", " ", text.lower().replace("ё", "е")))
    found, i = {}, 0
    while i < len(words):
        for n in (3, 2, 1):
            chunk = words[i:i + n]
            if len(chunk) < n:
                continue
            stem = _stem(chunk)
            hit = None
            if stem in keys:
                # слово сообщения совпадает с названием целиком, кроме последней буквы: «эутироксом» — «эутирокс», «шпы» — «шпа»;
                # «в корне» — не «Корнам» (у бренда срезалось «-ам», основа «корн» совпала случайно)
                key, last = keys[stem][0], chunk[-1]
                name_last = key.split()[-1]
                common = len(next((name_last[:j] for j in range(min(len(name_last), len(last)), 0, -1) if name_last[:j] == last[:j]), ""))
                hit = stem if common >= len(name_last) - 1 else None
            if hit:
                found[hit] = keys[hit][1]
                i += n - 1
                break
        i += 1
    return list(found.values())


def _append(message, note):
    content = message.get("content")
    if isinstance(content, str):
        message["content"] = content + note
    elif isinstance(content, list):
        for part in reversed(content):
            if isinstance(part, dict) and part.get("type") == "text":
                part["text"] = part.get("text", "") + note
                break


def _has_document(body, message):
    """Приложен файл, который не картинка (картинки идут через image_url и навык картинок)."""
    files = list(body.get("files") or []) + list(message.get("files") or [])
    for f in files:
        if not isinstance(f, dict):
            continue
        kind = (f.get("type") or "").lower()
        name = ((f.get("file") or {}).get("filename") or f.get("name") or "").lower()
        if kind == "image" or re.search(r"\.(png|jpe?g|webp|gif|bmp)$", name):
            continue
        return True
    return False


class Filter:
    def inlet(self, body: dict) -> dict:
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "user"), None)
        if not last:
            return body
        text = _text(last.get("content"))
        skills = set()
        if _has_document(body, last) or DOCUMENT.search(text):
            skills.add("document-analysis")
        if DATA.search(text):
            skills.add("data-analysis")
        if TRANSLATE.search(text):
            skills.add("technical-translation")
        brands = _find_brands(text)
        if HEALTH.search(text) or brands:
            skills.add("health")
        if brands:
            lines = [f"{t} — МНН: {i}" + (f" ({g})" if g else "") + ("" if a else ", регистрация не действует") for t, i, g, a in brands[:5]]
            _append(last, "\n\n[Справка ГРЛС о названиях лекарств в сообщении: " + "; ".join(lines) +
                    ". Ищи и отвечай по МНН.]")
        if LAW.search(text):
            skills.add("law")
        if skills:
            body["skill_ids"] = sorted(set(body.get("skill_ids") or []) | skills)
        return body
