# Как писать запросы для генерации видео и картинок

Шпаргалка для страницы `http://192.168.0.109:8188/simple` и моделей **LTX 2.3** (видео со звуком) и **Wan 2.2 Mega NSFW** (без звука).

Запросы пишите **по-английски**: обе модели понимают его лучше всего.

---

## Главные правила

1. **Описывайте то, что видно, а не абстракции.** У слов вроде «miracles», «formless», «strange surreal forms», «magic» нет картинки, и модель выдаёт кашу. Пишите предметы, материалы, цвета, движения.
2. **Не выдумывайте слова.** «aboba», «pseudorytm» модель либо пропустит, либо LTX их **произнесёт вслух**.
3. **Не давайте модели команд.** Не надо «use this image», «make a scene», «generate». LTX воспринимает такой текст как реплику и озвучивает его. Пишите описание, как будто сцена уже происходит.
4. **Расписывайте движение по шагам.** Нужно не «перестраивается во что-то», а «поднимается в столб → раскалывается на ветви → тает в лужу → снова встаёт спиралью».
5. **Всегда называйте камеру и свет**, например: `slow orbit`, `camera pushes in`, `handheld close-up`, `wide shot`, `cold blue backlight`, `warm lamp light`, `golden hour`.
6. **Не противоречьте себе.** «Течёт как жидкость» и «сохраняет точную форму» одновременно не получатся, модели придётся выбирать.
7. **Меняйте одну вещь за раз** и делайте 2–3 попытки с разным seed («Ещё раз с другим seed» на странице). Результат сильно зависит от случая.

---

## LTX 2.3 (со звуком)

Официальные правила Lightricks:

- **Один связный абзац**, не больше 200 слов, события **по порядку**.
- **Первым предложением главное действие.**
- Дальше по очереди:
  1. детали движений и жестов;
  2. внешность персонажей и предметов, точно;
  3. фон и окружение;
  4. ракурс и движение камеры;
  5. свет и цвета;
  6. внезапные изменения и события.
- Пишите **буквально и точно**, как оператор описывает план съёмки.
- **Звук описывайте отдельной фразой**: `Sound: soft breathing, rain on the window, distant thunder.`

### Стиль на странице
| Стиль | CFG | Когда выбирать |
|---|---|---|
| **Плавно** | 1.0 | медленно, чувственно, интимно, **без речи**; движения мало |
| **Кино** | 3.5 | экшен, превращения, много движения и звука |

Для сюрреализма и превращений берите **«Кино»**: при CFG 1 сцена почти стоит на месте. Речь отсекает стандартный негативный запрос (`speaking, talking, singing...`).

### Если загружено фото
- Описывайте, **что происходит дальше**: движение, действие, камеру. Внешность модель возьмёт с фото.
- Ползунок **«Насколько держаться фото»** в «Дополнительно»:
  - меньше, 0.7–0.8: больше движения и свободы;
  - больше, 0.9–1.0: ближе к фото, лицо не «уплывает».

---

## Wan 2.2 Mega NSFW (без звука)

Формула: **объект → сцена → движение → камера → свет → стиль**.

- Короче, чем для LTX: 1–3 предложения.
- Глаголы движения в начале: `walking`, `turning`, `stretching`, `melting`, `rising`.
- В конце можно добавить стиль и качество: `cinematic, highly detailed, sharp focus`.
- **С фото описывайте только движение.** Внешность Wan берёт с картинки.
- Негативный запрос у Wan почти не работает (CFG 1), рассчитывайте на основной запрос.

### LoRA на странице
| LoRA | Что делает | Сила по умолчанию |
|---|---|---|
| DR34ML4Y | общий NSFW | 0.7 |
| Detailz | детализация | 0.4 |
| Genitals helper | анатомия | выкл. (0.6) |
| UltraReal | фотореализм | выкл. (0.6) |

Если картинка «пережарена» или ломается, снизьте силу LoRA до 0.4–0.5 или выключите лишние.

---

## Сюрреализм и превращения

- **Привязывайте странное к физическому предмету**: жидкость, фарфор, воск, кость, металл, стекло, комната. Опишите, как **именно этот предмет** меняется.
- **Называйте фактуры**: `glossy porcelain`, `molten wax`, `wet concrete`, `brushed steel`, `translucent jelly`.
- **Разбивайте превращение на этапы** и связывайте их словами `then`, `suddenly`, `as`, `again`.
- **Слова «trippy», «psychedelic», «surreal» сами по себе ничего не дают.** Используйте их только в дополнение к конкретному описанию.

### Пример: как было и как стало

**Было** (каша, почти без движения, голос читает текст):
```
instant ivory welding, missing pseudorytm aboba watching miracles surreal, substance is rebuilding to something formless or very strange surreal forms
```

**Стало, LTX** (стиль «Кино»):
```
A pool of molten ivory-white liquid bubbles in the middle of a dark empty concrete room, glowing faintly like hot porcelain. Bright welding sparks burst from its surface as it suddenly pulls itself upward into a tall twisting column, then splits into three smooth bone-like branches that curl and knot around each other. The surface keeps shifting between liquid and glossy porcelain, rippling with slow waves. In the foreground a small round creature with one large blinking eye sits motionless, watching, as the shape collapses back into a puddle and instantly rises again as a spiral. The camera slowly orbits the form at eye level. Cold blue light from above, orange sparks reflecting on the wet floor. Sound: crackling welding sparks, a low resonant hum, wet liquid sloshing.
```

**Стало, Wan**:
```
Molten ivory liquid rising from the floor of a dark concrete room and constantly reshaping itself: it stretches into a twisting column, splits into curling bone-like branches, melts back into a puddle and rises again as a spiral. Bright welding sparks spray from its surface. A small one-eyed creature watches from the foreground. Slow orbiting camera, cold blue backlight, orange sparks, surreal, cinematic, highly detailed.
```

---

## FLUX 3 Image Klein (картинки)

В чате запрос для FLUX 3 пишет Gemma, поэтому достаточно сказать по-русски, что нужно. Правила ниже для тех, кто пишет запрос сам. Взяты из карточки модели и официального улучшателя запросов BFL (`D:\gen\prompts\official\flux3_upsampler_*.txt`).

- **Короткий запрос даёт шаблонную картинку.** Модель ждёт полное описание сцены: один абзац прозы на 100–350 слов, без тегов и списков.
- **Порядок:** тип кадра и стиль → сцена → свет и камера → каждый объект с цветом, материалом и состоянием.
- **Без указанного стиля** начинайте как с фотографии: `Full-color outdoor photograph, ...`, `Studio photograph, ...`, `Close-up photograph, ...`. Добавьте пару обычных, неидеальных деталей из самой сцены: так фото не выглядит стоковым.
- **Расстановка словами:** `on the left`, `in the foreground`, `in the background`.
- **Настроение — через видимое:** не «тревожно», а «серый свет, пустая улица, мокрый асфальт».
- **Чего не должно быть, пишите как то, что есть:** не «без людей», а «пустая площадь».
- **Стиль описывайте признаками** (палитра, мазок, фактура), а не названием картины.
- **Текст на картинке** — в двойных кавычках, с шрифтом, цветом и местом.
- **Необычные предметы — по частям:** «рыба из прозрачного стекла: обтекаемое тело, спинной плавник, жабры, веерный хвост».

### Правка картинки
Gemma правит последнюю картинку беседы, приложенную вами или нарисованную ею: «сделай куртку зелёной», «убери машину», «сделай из наброска фото». Неизменённые части остаются как были. Инструкция для модели пишется так: что изменить, что от этого поменяется ещё (тени, отражения, чем заполнить убранное) и в конце — что остаётся без изменений. Можно объединить несколько картинок: «возьми человека с первой и поставь в интерьер со второй».

### Режимы
| Режим | Модель | Шаги | Время на 4060 Ti |
|---|---|---|---|
| обычный | дистиллированная int8 | 16, без CFG | ~15 с (оценка) |
| «максимальное качество» | базовая int8 | 50, CFG 3.5 | в ~6 раз дольше |

LoRA для FLUX 3 пока почти нет, старые от Z-Image не подходят.

---

## Словарик для камеры и света

**Камера:** `static shot`, `slow push in`, `pull back`, `slow orbit around`, `tracking shot following`, `handheld`, `close-up`, `extreme close-up`, `wide shot`, `low angle`, `high angle`, `top-down view`, `POV`.

**Свет:** `soft window light`, `warm lamp light`, `golden hour`, `cold blue backlight`, `rim light`, `neon reflections`, `candlelight`, `harsh flash`, `volumetric fog with light rays`.

**Движение:** `slowly`, `suddenly`, `rhythmically`, `in slow motion`, `swaying`, `rippling`, `pulsing`, `twisting`, `collapsing`, `unfolding`.

---

## Если что-то не так

| Проблема | Что сделать |
|---|---|
| Голос читает текст запроса | Уберите команды и выдуманные слова; LTX в стиле «Плавно» или проверьте, что `speaking, talking` есть в негативе |
| Почти нет движения | LTX: стиль «Кино»; с фото снизьте «держаться фото» до 0.75; добавьте глаголы движения и камеру |
| Каша, шум, бесформенность | Больше конкретики: предмет, материал, этапы; меньше абстрактных слов |
| Лицо или персонаж «уплывает» | С фото поднимите «держаться фото»; уберите лишние LoRA; короче опишите движение |
| Лишние люди и предметы | Явно напишите, кто в кадре: `only one woman in the room`, `empty background` |
| Слишком долго | «Обычное» качество и 3 секунды; не переключайтесь между моделями без нужды |

---

## Источники

- [Lightricks LTX-2 — Prompting for LTX-2](https://github.com/Lightricks/LTX-2)
- [Lightricks LTX-Video — Prompt Engineering](https://github.com/Lightricks/LTX-Video)
- [ChrisColeTech/LTX-2.3-uncensored-v1.4 — настройки и CFG](https://huggingface.co/ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8)
- [Phr00t/WAN2.2-14B-Rapid-AllInOne — Mega, сэмплеры и LoRA](https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne)
- [Wan 2.2 Prompt Guide — Dreamina](https://dreamina.capcut.com/ai-video/wan-2-2-prompt)
- [Wan 2.2 Prompting Guide — VEED](https://www.veed.io/learn/wan-2-2-prompting-guide)
- [How to get the most out of prompts for WAN Models — Hugging Face Forum](https://discuss.huggingface.co/t/how-to-get-the-most-out-of-prompts-for-wan-models/170354)
- [Prompting AI video for psychedelic visuals — InVideo](https://invideo.io/faq/how-do-you-prompt-ai-video-generators-for-psychedelic-or/)
- [12 Tips for Writing AI Video Prompts — Blend](https://www.blendnow.com/blog/ai-video-prompt-writing-tips)
