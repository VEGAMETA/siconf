---
name: Technical translation
description: How to translate technical and other texts between English and Russian (documentation, README, errors, UI strings, articles, letters): keep code, commands, names and terms intact, use established Russian terminology, keep formatting, keep a glossary consistent across the conversation. Read it when the user asks to translate.
---

# Technical translation

## Rules

1. **Never translate what must stay as is:** code, commands, file paths, URLs, config keys, API and function names, error codes, product, library and company names, version numbers. Keep code blocks and inline code byte for byte.
2. **Established terminology.** Use the term Russian-speaking specialists actually use, not a literal calque: deployment = развёртывание (or «деплой» in informal text), pull request = пул-реквест, container = контейнер, cluster = кластер, ingress stays Ingress for the Kubernetes object, cache = кэш, thread = поток, commit = коммит. If a term has no settled translation, keep the English term and add a short Russian explanation in parentheses the first time.
3. **Meaning over words.** Translate what the sentence means for the reader; rebuild the sentence in natural Russian (or English) word order. No word-by-word calques, no English punctuation habits in Russian (use «ёлочки» for quotes, an em dash with spaces, a comma before «что/который»).
4. **Keep the format:** headings, lists, tables, bold and italics, line breaks, Markdown and placeholders ({name}, %s, {{var}}) exactly where they were. In UI strings keep length close to the original and keep placeholders' order valid.
5. **Consistency.** The same term is translated the same way through the whole text and the whole conversation. For long or repeated work, keep a short glossary ("термины: release → релиз, …") and follow it; show it if the user may want to adjust it.
6. **Register.** Match the source: documentation stays neutral and precise, a chat message stays casual, a letter keeps its politeness level. For Russian, "вы" by default in formal text.
7. **Ambiguity.** If a phrase can be read two ways and it matters (a legal term, a UI action), pick the more likely one and add a short translator's note after the text.
8. **Do not add or drop content.** No explanations inside the translation unless asked; notes go after the text, marked as notes.

## Answer format

- Just the translation, in the same structure as the source.
- After it, only if needed: "Примечания переводчика:" with ambiguities or terms kept in English.
