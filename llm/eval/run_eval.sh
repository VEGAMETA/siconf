#!/usr/bin/env bash
# Прогон тестов lm-evaluation-harness на локальных моделях через llama.cpp (127.0.0.1:8080)
# С НАШИМИ настройками чата: системные промпты из D:\gen\prompts (ответ на время теста — английский),
# Gemma — с размышлениями и порядком «план → разбор → самопроверка». (gpt-oss удалена 2026-10-24, её результаты — results/gpt-oss-20b-high.)
# Тесты: GSM8K Platinum (50), IFEval (50), MMLU-Pro (по 4 вопроса на каждую из 14 областей).
# Результаты: D:\llm\eval\results\<модель>, полный журнал каждого запуска: logs\<модель>_<задачи>.log
set -u
cd /d/llm/eval
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost PYTHONIOENCODING=utf-8
unset ALL_PROXY all_proxy   # SOCKS-прокси ломает загрузку датасетов с Hugging Face
# IFEval нужен словарь NLTK punkt_tab; через прокси NLTK его не качает (защита от SSRF) —
# если пропал, скачать напрямую: без HTTP(S)_PROXY выполнить python -c "import nltk; nltk.download('punkt_tab')"
mkdir -p logs
python -I -X utf8 make_eval_prompts.py   # промпты всегда свежие, из боевых файлов

run() {  # $1 — модель в llama.cpp, $2 — файл системного промпта, $3 — параметры генерации, $4 — задачи, $5 — limit
  local log="logs/$1_${4// /+}.log"
  echo "=== $(date '+%H:%M:%S') $1: $4 (limit $5) ==="
  lm-eval run --model local-chat-completions \
    --model_args model="$1" base_url=http://127.0.0.1:8080/v1/chat/completions num_concurrent=4 max_retries=3 tokenized_requests=False timeout=3600 \
    --tasks $4 --apply_chat_template --fewshot_as_multiturn --system_instruction "$(cat "$2")" \
    --gen_kwargs max_gen_toks=16384 $3 \
    --limit "$5" --log_samples --output_path "results/$1" > "$log" 2>&1
  local rc=$?
  grep -E "^\|" "$log" | grep -v -E "^\|\s*\|"
  [ $rc -ne 0 ] && { echo "!!! код выхода $rc, конец журнала:"; tail -15 "$log"; }
}

GEMMA="do_sample=True temperature=1.0 top_p=0.95 top_k=64"

run gemma-4-26b-a4b sys_gemma_eval.txt "$GEMMA" "gsm8k_platinum_cot_llama ifeval" 50
run gemma-4-26b-a4b sys_gemma_eval.txt "$GEMMA" "mmlu_pro_llama" 4
echo "=== $(date '+%H:%M:%S') ГОТОВО ==="
