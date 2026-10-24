#!/usr/bin/env bash
# A/B/C шага 4 (самопроверка) на Gemma: MMLU-Pro по 10 вопросов на область (140), одинаковые вопросы,
# одинаковые параметры, отличается только шаг 4. Результаты: results/ab_old, ab_new, ab_noalt
set -u
cd /d/llm/eval
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost PYTHONIOENCODING=utf-8
unset ALL_PROXY all_proxy
mkdir -p logs
python -I -X utf8 make_ab_prompts.py || exit 1

ab() {  # $1 — вариант (old|new|noalt)
  local log="logs/ab_$1_mmlu_pro.log"
  echo "=== $(date '+%H:%M:%S') вариант $1 ==="
  lm-eval run --model local-chat-completions \
    --model_args model=gemma-4-26b-a4b base_url=http://127.0.0.1:8080/v1/chat/completions num_concurrent=4 max_retries=3 tokenized_requests=False timeout=3600 \
    --tasks mmlu_pro_llama --apply_chat_template --fewshot_as_multiturn --system_instruction "$(cat "sys_ab_$1.txt")" \
    --gen_kwargs max_gen_toks=16384 do_sample=True temperature=1.0 top_p=0.95 top_k=64 \
    --limit 10 --log_samples --output_path "results/ab_$1" > "$log" 2>&1
  local rc=$?
  grep -E "^\|" "$log" | grep -E "mmlu_pro_llama +\|" | head -1
  [ $rc -ne 0 ] && { echo "!!! код выхода $rc"; tail -15 "$log"; }
}

ab old
ab new
ab noalt
echo "=== $(date '+%H:%M:%S') A/B/C ГОТОВО ==="
