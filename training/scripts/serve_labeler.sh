#!/usr/bin/env bash
# Serve Gemma 4 31B (NVFP4-turbo) for image labeling via vLLM's OpenAI-compatible endpoint.
# Tensor-parallel across both 5090s. Multimodal pathway is left enabled (no --language-model-only).
#
# Prereqs: both 5090s must be free. Kill any other vLLM / ASR / inference processes first.
# Run this inside a tmux/nohup session — vLLM is long-running and you don't want a dropped
# SSH connection to take it down.
#
# tmux quickstart:
#   tmux new-session -d -s labeler 'bash training/scripts/serve_labeler.sh 2>&1 | tee /tmp/vllm-labeler.log'
#   tmux attach -t labeler          # to watch startup
#   tmux send-keys -t labeler C-c   # to stop

set -euo pipefail

# cyankiwi's AWQ-4bit is the only locally-downloaded multimodal Gemma 4 31B
# variant. Architecture is Gemma4ForConditionalGeneration (with vision tower
# kept at FP16; only LM layers are 4-bit compressed-tensors). LilaRest's
# NVFP4-turbo, despite being well-served by ai-server, is text-only —
# its architecture is Gemma4ForCausalLM with the vision tower stripped.
MODEL_PATH="${MODEL_PATH:-cyankiwi/gemma-4-31B-it-AWQ-4bit}"
PORT="${PORT:-8000}"

# Use the ai-server venv directly — vllm 0.20.2rc1.dev138+g52458b60a is the
# known-good build for Gemma 4 on Blackwell. Plain pypi 0.20.2 doesn't ship
# sm_120 NVFP4 kernels (irrelevant here but still cleaner to use the dev venv).
VLLM_PY="${VLLM_PY:-$HOME/ai-server/.venv/bin/python}"

# CUDA 12.9 + ninja on PATH — only matters if flashinfer JIT-compiles a kernel.
# Cheap to set even when not strictly needed.
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.9}"
export PATH="$CUDA_HOME/bin:$HOME/ai-server/.venv/bin:$PATH"

"$VLLM_PY" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" \
  --served-model-name gemma-4-31b-labeler \
  --host 0.0.0.0 \
  --port "$PORT" \
  --tensor-parallel-size 2 \
  --max-model-len 8192 \
  --max-num-batched-tokens 8192 \
  --max-num-seqs 4 \
  --gpu-memory-utilization 0.90 \
  --quantization compressed-tensors \
  --attention-backend triton_attn \
  --enforce-eager \
  --trust-remote-code \
  --async-scheduling
