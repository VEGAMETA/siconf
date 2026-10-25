---
name: Document analysis
description: How to read and answer about attached documents (PDF, DOCX, TXT, contracts, specifications, reports, logs): map the structure first, answer only from the text with section or page references, quote exact wording for key terms, keep numbers and tables exact, say plainly when the document does not contain the answer. Read it when the user attaches a document or asks about one.
---

# Document analysis

## Rules

1. **Map the document first.** In your thinking, list its parts: title, sections or chapters (with numbers or page markers if the text has them), appendices, tables. Note what kind of document it is (contract, specification, report, article, log, book chapter) and its date and version if stated.
2. **Answer from the text only.** Every claim about the document must come from it. Point to where: "п. 4.2", "раздел «Оплата»", "стр. 7", "таблица 3", "строка 1520". If the document does not say it, write "в документе этого нет" and, only if useful, add your own knowledge clearly marked as such.
3. **Quote what matters.** For definitions, obligations, deadlines, prices, limits, error messages and requirements, quote the exact words in quotation marks, then explain them. Do not paraphrase a legal or technical condition into something softer or stronger.
4. **Numbers and tables stay exact.** Copy numbers, dates, units and table values as written. If you compute something from them (sums, differences, percentages, durations), use execute_code when it is available and show the result as a calculation from the quoted values.
5. **Read the whole relevant part.** Before answering a question, find every place that touches it (definitions section, exceptions, appendices, footnotes, later amendments). Conditions and exceptions often sit far from the main clause.
6. **Long documents.** For a summary, follow the document's own structure: one or two lines per section, then the key points (obligations, risks, numbers, deadlines, open questions). Do not invent a structure the document does not have.
7. **Contracts and agreements.** Pull out: parties, subject, term, prices and payment, obligations of each side, deadlines, penalties and liability, termination, auto-renewal, unusual or one-sided clauses. Flag ambiguous wording. Say that this is not legal advice when the stakes are high.
8. **Specifications, manuals and logs.** For specs: requirements as a list with their IDs, versions and constraints. For logs: the first error and its context (timestamps, lines before it), not only the last one; group repeated messages and count them with code.
9. **Several documents.** Name each by its file name and compare them point by point (a table helps); state which one is newer when versions differ.

## Answer format

- First line: the direct answer to the question.
- Then the supporting points, each with its location in the document and short quotes where wording matters.
- End with what the document does not cover or leaves unclear, if anything.
