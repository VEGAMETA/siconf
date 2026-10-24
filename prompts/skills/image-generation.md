---
name: Image generation (FLUX 3)
description: How to plan, write and check images made with create_image and edit_image (FLUX 3 Image Klein). Read it before the first image call in a conversation.
---

# Image generation with FLUX 3

Follow these steps for every create_image or edit_image call.

## 1. Decide what to make

- A request to draw, generate or show a picture, or to come up with a visual thing (cover, poster, logo, icon, avatar, banner, wallpaper, sticker, illustration, postcard, thumbnail, character or scene look), means: generate the image now. Add one or two lines about the idea. If you thought of several concepts, generate the strongest one; the user can ask for the others.
- Answer with text only when the user clearly asks for ideas, a description or a prompt.
- Take missing details (title, theme, mood, story, setting) from the conversation and attached files. Ask one short question only when nothing says what the image is for.
- To change an image already in the conversation (attached or generated), use edit_image, not a new image: "fix this", "make it blue", "remove the car", "fix the spelling", "turn my sketch into a photo". To combine several images, set images to their number.

## 2. Choose the mode: brief or prompt

- **brief** (you act as art director, the official BFL prompt writer writes the FLUX caption): covers, posters, banners, thumbnails, ads, complex scenes with a story. Usually gives the better composition. The first use takes 1-4 minutes longer while the writer loads.
- **prompt** (you write the full FLUX caption yourself): simple images (an object, an animal, a landscape, a quick sketch idea), or when the user gave a detailed description that must be followed word for word. Faster.
- For edits, brief also works: a short request like "make the ring a realistic small size, keep everything else"; the writer looks at the image and expands it.

## 3. Compose first (in your thinking)

- The purpose and audience: what must a viewer understand in one second?
- One focal subject and where it sits in the frame. No more than 3-5 elements in total. A cover or poster is not a storyboard: pick one moment or symbol, not every plot point.
- Where text goes, with empty space reserved for it. Text never covers a face.
- Foreground, midground, background; one key light and its direction (light has the biggest effect on quality).
- A palette of 2-4 main colors.
- Real scale and proportions of every object and person (see step 5).
- Setting and culture: match the story's place and time. A story set in Russia shows Russian streets, buildings, interiors and Cyrillic signs, not an American suburb.

## 4. Write the brief (brief mode)

60-150 words, any language, containing:
- purpose, genre and audience ("book cover for a contemporary women's drama, readers 30-50");
- what the image is about in one sentence;
- the focal subject: who, age range, look, clothing, expression, pose; the one key moment or symbol;
- 3-5 elements and the composition: where the subject is, where the text goes and that its area stays empty;
- the exact text in quotes and its hierarchy (book title large, series line small); keep it to the title and at most one short line;
- palette, light, mood, style (photo or a named illustration style);
- real sizes of important objects ("a thin wedding band no bigger than a fingertip").

## 5. Write the caption (prompt mode)

FLUX 3 only works well with a full scene caption, never a short request.

- ONE continuous English prose paragraph of 100-350 words. No tags, no lists. Most important things first: the model weighs earlier words more.
- Order: medium and style, then scene, lighting and camera, then every subject with concrete colors, materials and state.
- Without a stated style, plan an actual photograph and open with "Full-color outdoor photograph, ...", "Full-color indoor photograph, ...", "Studio photograph, ..." or "Close-up photograph, ...". Give a photo a few ordinary, imperfect details from the scene itself instead of a stock-photo ideal. Framing and lens words help ("medium close-up, 85mm portrait, shallow depth of field"); camera brand names do not.
- Place things with frame-relative words: on the left, in the foreground, in the background. For covers and posters also pass layout boxes and cite each id in the caption ("a woman in a dark coat <woman_1>").
- **Scale and proportions:** the model enlarges whatever seems important (a ring the size of a bracelet, a cup as big as a head, a person towering over a door). For every object that matters, state its real size relative to something familiar near it: "a thin gold wedding band no bigger than a fingertip, tiny next to the loaf", "a coffee cup that fits in her hand", "a two-storey house whose front door is just taller than the woman standing in it". Keep people, furniture, buildings and vehicles in true proportion to each other and to the camera distance.
- **Actions with objects must be physically possible and spelled out:** the model draws each object well but often connects them wrongly (writing on a closed book, a cup held by its bottom, a key in a wall). Describe the interaction unambiguously: "she writes with a fountain pen on the open right-hand page of a notebook, the pen tip touching the paper", "she holds the mug by its handle". If the action is not essential, prefer a calm pose without it.
- **People:** age range, build, hair, clothing and expression for everyone in focus. Give hands a simple, natural task (holding a cup, resting on a table, in coat pockets) or keep them out of frame; complex finger poses break. Keep crowds out unless needed; one to three people in focus.
- **The same character in several images:** reuse the exact same description of face, hair and clothing word for word, and reuse the seed for small variations.
- **Colors:** name 2-4 main colors; for exact brand colors write the hex code with its name, "#8B1E3F (deep burgundy)".
- **No negative prompts:** describe what is there instead. "No people" becomes "a deserted street", "no text" becomes "a clean, unmarked wall", "no makeup" becomes "natural bare skin".
- Turn moods into visible facts. Describe a style by its attributes (palette, brushwork, texture), not by naming an artwork, artist, real person or brand logo.
- Describe unusual objects part by part ("a fish made of clear glass: streamlined body, dorsal fin, gills, fan-shaped tail").

## 6. Text in images

- Put every word that must appear in double quotes with font style, weight, color, size and placement, in the original language. Cyrillic works.
- Big short text renders well; small and long text gets misspelled. Keep to the title and at most one short line.
- High contrast between text and background, so the title stays readable at thumbnail size.
- Generated text is never guaranteed. When exact text matters for production (a cover for sale, a logo), say that the final lettering is best set separately in a design tool.

## 7. Genre conventions for covers, posters, banners, thumbnails

- Say the format and genre explicitly ("book cover", "YouTube thumbnail") and follow the genre unless asked otherwise:
  - romance or women's fiction: the heroine (face, emotion) as the focal subject, warm or bittersweet palette, soft light, title large;
  - thriller or crime: a strong silhouette or detail, high contrast, cool tones, bold sans-serif title;
  - fantasy: the hero or a key creature or place, rich saturated light, ornamental serif title;
  - sci-fi: blue and silver palette, clean lines;
  - non-fiction: one clear symbol or a clean typographic layout.
- Sizes: book or podcast cover "832x1216" (square for podcasts), YouTube thumbnail or banner "1344x768".
- For an important image (a cover), offer two or three variants with different seeds; each takes only about ten seconds once the models are loaded.

## 8. Size and quality

- Portrait or full-height figure "832x1216", landscape or room "1216x832", wide banner or thumbnail "1344x768", square or single object "1024x1024". Use the size the user asks for if any.
- quality "best" only when the user asks for maximum quality: it is several times slower.

## 9. Edit instructions (prompt mode of edit_image)

- 50-150 English words.
- One image: an imperative ("Change the jacket to dark green wool ...") that describes only the change, its knock-on effects (shadows, reflections, what fills a removed area) and ends with a clause saying what stays unchanged ("keep the composition, the woman's face, pose and clothing exactly the same").
- Style-preserving changes say so ("... while keeping the photograph's realistic style and color grading").
- Several images: "Create a photograph of ..." saying what to take from the first image, the second image, and so on.

## 10. After the image

- Say in one line which size and mode you used.
- If the tool result includes a preview, look at it and check: the focal subject, every requested element, the spelling of every text, the scale and proportions of objects and people, whether every action is physically possible (no writing on a closed book), hands and faces. If something is clearly wrong, say so plainly instead of praising the image, and offer the fix.
- When the user is unhappy: first name concretely what differs from what they wanted, then fix exactly that, usually with edit_image on the last image; use a new create_image only when the whole composition is wrong. Change one thing at a time. After two similar misses, rethink the composition or the mode instead of piling on adjectives. Tell the user in one line what you changed.
