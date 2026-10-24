---
name: local-image-gen
description: Generate or edit images on the user's local GPU with FLUX 3 (via the local-ai MCP server) and save them straight into the project. Use whenever the user asks for an image, illustration, icon, favicon, logo draft, hero or banner image, placeholder, texture, sprite, mockup picture or cover while working in code, or asks to edit, restyle or fix an existing image file. Prefer it over describing an image in words or leaving TODO placeholders.
---

# Local image generation (FLUX 3 on the user's PC)

The user's PC (RTX 4060 Ti 16 GB) runs FLUX 3 Image Klein in ComfyUI. The `local-ai` MCP server exposes it:

- `generate_image(prompt | brief, size, quality, seed, layout, out_path, out_size)`
- `edit_image(images, prompt | brief, quality, seed, out_path, out_size)`

If these tools are not loaded yet, find them with ToolSearch (query "local-ai generate_image"). They are free and private: use them rather than an external image service.

## 1. Make sure the generator is running

- ComfyUI must answer on http://127.0.0.1:8188 (`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8188/` → 200).
- If not, start the whole stack with `D:\llm\start_all.bat` (shortcut "Local AI"), or only ComfyUI with `D:\gen\start_comfyui_lan.bat` in the background, and wait until the port answers (first start takes about 30 s). Images need only ComfyUI, not the LLM.
- Generating unloads the local LLM (Gemma) from VRAM; it reloads by itself on its next request.

## 2. Decide the asset

- Where it goes: follow the project's conventions (`public/`, `static/`, `assets/`, `src/assets/`, `docs/img/`). Pass an absolute `out_path`; the folder is created.
- Format by extension of `out_path`: `.webp` for photos and illustrations on the web, `.png` for UI pieces and screenshots-like art, `.jpg` when the project already uses it, `.ico` for favicons and Windows icons (multi-size, use `out_size: "256x256"`).
- `size` is the generation canvas (~1 megapixel), choose the asset's aspect ratio: `1024x1024` square (icons, avatars), `1344x768` wide (hero, banner, OG image), `1216x832` landscape, `832x1216` portrait (cover, poster, phone wallpaper). `out_size` then fits the saved copy into the target size (it never enlarges).
- FLUX makes opaque images. For an icon or sprite that needs transparency, generate it on a flat solid background color and tell the user transparency needs a separate background-removal step.
- Keep words out of UI assets: headings, labels and buttons belong in HTML/CSS. Generated text is often misspelled, so ask for "empty space reserved for a headline" instead.

## 3. Choose the mode

- **prompt** (you write the caption): icons, logos drafts, objects, textures, patterns, simple illustrations, anything where you know exactly what you want. Fast (about 10 s).
- **brief** (the official BFL prompt writer writes the caption from your short brief): hero images, banners, posters, covers, scenes with people or a story. Better composition; the first run takes 1-4 minutes longer while the writer loads, then about 20 s. The returned text includes the caption it wrote.

## 4. Writing the prompt (prompt mode)

- One English prose paragraph, 100-350 words for scenes; 50-120 words is enough for an icon or a texture. No tags.
- Medium and style first ("Flat vector app icon ...", "Isometric 3D illustration ...", "Full-color indoor photograph ...", "Seamless tileable texture ..."), then the subject, then setting, light (one key light with direction), palette.
- Main thing first: earlier words weigh more.
- Name 2-4 colors; for brand colors give hex with a name: "#2B2D6E (deep indigo)". Reuse the project's palette if it has one (CSS variables, Tailwind config, brand docs).
- Real sizes and proportions for objects that matter ("a cup that fits in one hand"); the model enlarges what seems important.
- No negative prompts: describe what is there instead ("a clean solid off-white background", "a deserted street").
- For layout-sensitive images (banners with a headline area, covers) say where the empty space is, or pass `layout` boxes on a 0-1000 grid and cite each id in the caption.
- No camera brand names, no real people, no third-party logos.

## 5. Writing the brief (brief mode)

60-150 words in any language: purpose and audience, what the image shows in one sentence, the focal subject and 3-5 elements, composition and where text or empty space goes, exact text in quotes if any (keep it short), palette, light, style, real sizes of key objects, the setting's place and culture.

## 6. Check and iterate

- Look at the returned preview: subject, every requested element, proportions, hands and faces, text spelling, empty space where a headline will go.
- To fix one thing, use `edit_image` on the generated file (the path is in the result) with a short `brief` ("make the loaf smaller, keep everything else") or an instruction ending with what stays unchanged.
- For a variation of the same image reuse the seed; for alternatives use new seeds. Change one thing at a time; after two similar misses, rethink the composition or switch mode.
- For important images (a hero, a cover) offer two or three variants; each takes seconds.

## 7. Report

Tell the user where the file was saved, its size and format, which mode and seed were used, and anything that still needs a human (exact lettering, transparency).

The full rule set used by the chat assistant, with more on composition, people, genres and covers, is in `D:\gen\prompts\skills\image-generation.md`; read it for complex or story-driven images.
