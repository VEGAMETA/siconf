---
name: Data analysis
description: How to analyse tables and numbers (CSV, Excel data pasted as text, logs with numbers, measurements, prices) with execute_code: load the data, check it, compute with code instead of in your head, and draw charts with matplotlib. Read it when the user gives data or asks to calculate, compare, find trends or plot a chart.
---

# Data analysis

## Rules

1. **Compute with code, never in your head.** Every count, sum, average, percentage, trend or comparison comes from execute_code (Python with pandas and matplotlib in the browser). Show the key numbers from the printed output, not from memory.
2. **Load and look first.** Put the data into a pandas DataFrame (from the pasted text with io.StringIO, or from the attached file's text). Print the shape, column names, dtypes and the first rows. Check for missing values, duplicates, wrong types (numbers stored as text, commas as decimal separators, dates as strings) and fix them before analysing; say what you fixed.
3. **Answer the actual question.** Decide which numbers answer it (a total, a change over time, a ranking, a distribution, a correlation) and compute exactly those. Prefer a few clear numbers over a dump of statistics.
4. **Charts.** When a chart helps (trends, comparisons, distributions) or the user asks for one, draw it with matplotlib in the same code: one idea per chart, a title, axis labels with units, readable tick labels, no 3D, no pie charts for more than 4 parts. Line for time, bars for categories, histogram for distributions, scatter for two numeric variables. Call plt.show() so the image appears in the chat.
5. **Be honest about the data.** Mention small samples, outliers, missing periods and when a correlation does not prove a cause. Never invent rows or fill gaps without saying so.
6. **Russian number format in the answer.** Write numbers in the answer with a space as thousands separator and a comma as decimal separator (12 345,6), units and periods stated.
7. **Big data.** If the data is too large to paste, ask for a sample or for the columns that matter, or describe the code the user can run locally.
8. **For a live interactive chart** (sliders, tooltips, dashboards) the visualize skill and tool may be available; use them only when the user asks for an interactive view.

## Answer format

- First line: the answer in numbers ("Средний чек вырос на 12,4 %: с 1 830 до 2 057 ₽").
- Then the chart (if any) and 2-5 key observations with their numbers.
- End with caveats about the data, if any.
