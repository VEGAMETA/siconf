---
name: Image generation (FLUX 3)
description: Required rules for create_image and edit_image (FLUX 3 Image Klein): when to draw, brief or prompt mode, how to write the caption (realism, scale, actions, people, text), styles, sizes, edits and the check after the image. Read it before the first image call in a conversation.
---

# Image generation with FLUX 3

## Required steps (every image)

1. **Draw, do not describe.** "Нарисуй / сгенерируй / придумай / сделай / оформи" + a visual thing (cover, poster, logo, banner, avatar, illustration, wallpaper, sticker, icon) = call create_image in this answer. Text only if the user asks for ideas or a prompt. Missing details: take them from the conversation and attached files; ask one short question only if nothing says what the image is for.
2. **Change, do not redraw.** "Исправь, убери, замени, сделай светлее" about an image in the chat = edit_image on that image. A new create_image only when the whole composition is wrong.
3. **Pick the mode.** brief (the BFL writer composes the caption; first run +1-4 min): covers, posters, banners, ads, scenes with a story. prompt (you write the full caption): simple objects, animals, landscapes, icons, or a detailed user description to follow exactly.
4. **Compose in your thinking:** purpose and viewer, one focal subject and its place in the frame, at most 3-5 elements, where the text goes (empty area, never over a face), one key light and its direction, 2-4 main colors, the place and culture of the story (a story in Russia shows Russian streets, interiors and Cyrillic signs).
5. **Write it** by the rules below, call the tool with the right size.
6. **Check the preview** (rules at the end) and say plainly what is wrong.

## Caption rules (prompt mode; the brief follows the same ideas in 60-150 words)

- One English prose paragraph, 100-350 words, no tags or lists. Most important first: style and medium, then scene, light and camera, then each subject with colors, materials and state.
- **Realism by default.** Without a stated style, write an actual photograph: start with "Full-color indoor photograph, ..." / "outdoor photograph" / "studio photograph" / "close-up photograph"; add a few ordinary imperfect details of the real place; framing words help ("medium close-up, 85mm portrait, shallow depth of field"), camera brands do not.
- **Surreal only on request.** Then name exactly which rule breaks and how ("a whale floating above a wheat field, its shadow on the wheat"), describe it part by part with real materials, keep light, shadows and perspective real. One or two impossible ideas per image.
- **Real scale.** For every important object give its size against something near it: "a thin wedding band no bigger than a fingertip", "a cup that fits in her hand", "a door just taller than the woman". People, furniture, buildings and cars in true proportion.
- **Possible actions, spelled out.** "She writes with a pen on the open right-hand page, the pen tip touching the paper", "holds the mug by its handle". Unclear action: choose a calm pose instead.
- **People:** age range, build, hair, clothes, expression for each person in focus; one to three people; hands with a simple task or out of frame. Same character in several images: repeat the same description word for word and reuse the seed.
- **Colors:** name 2-4; exact brand colors as hex with a name: "#8B1E3F (deep burgundy)".
- **No negative words:** describe what is there ("a deserted street", "a clean unmarked wall", "natural bare skin").
- **Moods as visible facts;** styles by attributes, never by artist, artwork, real person or brand logo names.
- **Text in the image:** every word in double quotes with font style, weight, color, size and place, in the original language (Cyrillic works). Only the title and at most one short line, big and high-contrast. For production (a cover for sale, a logo) say that the final lettering is best set in a design tool.
- **Layout:** for covers and posters pass layout boxes (0-1000 grid) and cite each id in the caption ("a woman in a dark coat <woman_1>").

## Covers, posters, thumbnails

- Name the format and genre in the caption. Romance or women's fiction: the heroine's face and emotion as the focus, attractive and composed (not exhausted), warm or bittersweet palette, soft light, title large. Thriller: strong silhouette or detail, high contrast, cool tones, bold sans-serif. Fantasy: hero or key place, rich light, ornamental serif. Sci-fi: blue and silver, clean lines. Non-fiction: one clear symbol.
- Book or podcast cover 832x1216, YouTube thumbnail or banner 1344x768. For important images offer 2-3 variants with different seeds.

## Styles (one per image; open the caption with the line, then adapt)

- Cinematic still: "Cinematic film still, one motivated key light, teal-and-amber grading, shallow depth of field, natural skin texture."
- Analog film: "Analog film photograph, fine grain, lifted blacks, warm muted colors, slight halation, candid framing."
- Editorial portrait: "Magazine editorial portrait, soft key light from one side, natural polished skin, seamless one-color backdrop."
- Documentary: "Documentary photograph in available light, unposed moment, real clutter, honest colors."
- Product: "Studio product photograph, seamless background, large soft light, controlled reflections."
- Oil: "Oil painting, thick brushstrokes, palette-knife texture, layered color." Watercolor: "Watercolor on cold-press paper, soft blooms, hard dried edges, white paper as highlights." Gouache: "Flat opaque gouache, matte, 4-5 colors."
- Ink: "Black ink drawing, varied line weight, cross-hatching, white paper." Engraving: "Copperplate engraving, fine hatching, sepia on cream." Soviet poster: "Constructivist poster, flat red, black and cream, strong diagonals, blocky lettering."
- Flat vector: "Flat vector illustration, geometric shapes, limited palette, generous empty space." Isometric 3D: "Isometric 3D, soft clay materials, pastel palette, small diorama." Concept art: "Digital concept art, atmospheric perspective, light shafts, big readable shapes." Anime: "Anime illustration, clean line art, two-tone cel shading." Comic: "Comic art, bold inks, flat colors, halftone dots."
- Photorealistic surrealism: "Photorealistic surreal photograph: one impossible element shot as completely real, everything else an ordinary believable place, true light and shadows."
- A series (book illustrations, icon set, slides): pick the style line once and repeat it word for word, same palette and light.

## Size and quality

- Portrait or full figure 832x1216, landscape or room 1216x832, wide banner 1344x768, square or single object 1024x1024; the user's size wins.
- quality "best" only when the user asks for maximum quality (several times slower).

## Edits (edit_image)

- brief mode: a short request ("make the ring a realistic small size, keep everything else").
- prompt mode: 50-150 English words, an imperative describing only the change and its knock-on effects (shadows, what fills a removed area), ending with what stays the same ("keep the composition, her face, pose and clothes unchanged"); for style-keeping edits say so.
- Several images: "Create a photograph of ... using the face from the first image and the jacket from the second."

## After the image

- One line: which size and mode you used.
- Check the preview: focal subject, every requested element, text spelling, scale and proportions, physically possible actions (unless the impossible was requested), hands and faces. If something is clearly wrong, say so plainly instead of praising, and offer the fix.
- User unhappy: name concretely what differs, fix exactly that (usually edit_image), one change at a time; after two similar misses rethink the composition or switch the mode.
