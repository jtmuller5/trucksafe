# Gemma Fine-Tune & On-Device Deployment Guide

> A reusable brief distilled from the Gemmacademy build. Covers what we did, the gotchas that cost real time, and a working recipe to fine-tune a Gemma 4 model and ship it as an on-device `.litertlm`.

---

## What this pipeline does

1. **Generate synthetic Q&A** by serving a large Gemma "teacher" (Gemma 4 26B AWQ-4bit) on vLLM and prompting it with domain-specific source content.
2. **Fine-tune a small Gemma student** (Gemma 4 E2B) via Unsloth + TRL with LoRA on attention + MLP.
3. **Merge LoRA into base weights** as BF16 safetensors.
4. **Convert to `.litertlm`** with `litert-torch export_hf` (quantized).
5. **Run on-device** via `litert-lm` (CLI on desktop, AI Edge SDK on Android/iOS).

End-to-end timings on a single RTX 5090:
- Q&A generation (500 pairs): ~3.5 min
- Fine-tune (3 epochs, ~169 steps): ~80 sec
- Convert to `.litertlm`: ~5 min
- Total: ~10 min per run

---

## Environment

### Hardware assumed
- 1× NVIDIA RTX 5090 (32 GB) minimum. The pipeline fits on one GPU if you don't run vLLM and training concurrently; two GPUs is more comfortable.
- ≥16 GB host RAM free during the convert step. The MLIR optimization pass is host-RAM-hungry.

### Two separate uv venvs — DO NOT MERGE
The training stack and the serving stack pin different torch versions. Keep them apart.

```
project/
├── training/        # uv env: torch 2.10.0+cu128, unsloth, trl, transformers, litert-torch-nightly
└── serving/         # uv env: torch 2.11.0+cu130, vllm
```

**Why:** Unsloth's compiled kernels are pinned against torch 2.10; vLLM 0.20+ requires torch ≥2.11. Trying to unify them breaks one or the other.

`litert-torch-nightly` warns on import: "Skipping import of cpp extensions due to incompatible torch version. Upgrade to torch >= 2.11." **The pure-Python fallback works** for `export_hf`. Ignore the warning; don't upgrade torch in the training env.

---

## Step 1 — Serve a teacher model on vLLM

Pick a teacher that's smart enough to write training data your student model can learn from. We used Gemma 4 26B (MoE, ~13B active params).

### Working command
```bash
cd serving/
tmux new-session -d -s vllm
tmux send-keys -t vllm \
  'CUDA_VISIBLE_DEVICES=0 uv run vllm serve cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit \
     --port 8000 \
     --max-model-len 8192 \
     --max-num-batched-tokens 8192 \
     --gpu-memory-utilization 0.92 \
     --limit-mm-per-prompt '"'"'{"image": 0}'"'"' \
     --quantization compressed-tensors 2>&1 | tee /tmp/vllm.log' C-m
```

Loads in ~5 min. Uses ~30 GB of GPU 0's 32 GB at idle.

### Gotchas

- **FP8-Dynamic doesn't fit at 8K context on a 32 GB card.** Weights at 26.5 GB leave only 0.6 GB for KV cache, vs ~1.7 GB needed. Use AWQ-4bit instead (weights ~14 GB).
- **Gemma 4 is multimodal — vLLM trips on default batch size.** Pass `--max-num-batched-tokens 8192` AND `--limit-mm-per-prompt '{"image": 0}'` to disable the image pathway. Without the first you get `Chunked MM input disabled but max_tokens_per_mm_item is larger than max_num_batched_tokens`.
- **Harmless "SM 12.x requires CUDA >= 12.9" warnings.** FlashInfer/Cutlass kernel-detection quirk on Blackwell. Inference works.
- **Run vLLM in tmux/nohup.** Sessions get long; you don't want it dying when your terminal closes.

---

## Step 2 — Generate synthetic training data

Write a `generate_qa.py` that calls vLLM's OpenAI-compatible endpoint. Key design notes:

- **Batch 10–20 pairs per HTTP call.** Don't ask for all 500 at once — context blows up, diversity drops.
- **Rotate the focus area each batch** across ~16 different aspects of your lesson content. Forces variety.
- **Dedup by lowercased question.** Same question phrased twice is one example.
- **Temperature 0.8.** Lower (0.3) makes every pair sound identical.
- **Use guided/structured outputs** if vLLM supports them for your model — much more reliable than regex-parsing JSON out of free text.

### What makes good source content
- Named characters / catchphrases / classroom routines (or domain equivalent). Specificity is what makes generated data testable later.
- ~1500–2500 words is a good size for one lesson.
- Generic source content → generic, untestable training data. This is the single biggest quality lever.

### Verification rule of thumb
Sample 50 random pairs. If <40 are training-quality (would teach the right thing), iterate the system prompt before training. One prompt iteration is usually enough if your source content is specific.

---

## Step 3 — Fine-tune with Unsloth

### Critical config (the one we shipped)

```python
MODEL_NAME = "unsloth/gemma-4-E2B-it"  # Unsloth's re-upload, loads cleanly
MAX_SEQ_LENGTH = 2048
LORA_RANK = 128          # NOT 32. See "The big lesson" below.
LORA_ALPHA = 128         # convention: alpha == rank. Don't leave it at the rank-32 value.

# In FastModel.get_peft_model(...)
target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                  "gate_proj", "up_proj", "down_proj"]
finetune_attention_modules = True
finetune_mlp_modules = True

# In SFTConfig(...)
per_device_train_batch_size = 4
gradient_accumulation_steps = 2     # effective batch = 8
num_train_epochs = 3
learning_rate = 2e-4
optim = "adamw_8bit"
lr_scheduler_type = "linear"
warmup_steps = 10
weight_decay = 0.01
```

### Pin to a specific GPU
```python
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # MUST be set before importing torch/unsloth
import torch
from unsloth import FastModel
```

### Override the chat template to match the on-device runtime
Otherwise train tokenization and on-device tokenization diverge silently.

```python
TEMPLATE_PATH = Path(__file__).parent / "reference-template" / "chat_template.jinja"
with TEMPLATE_PATH.open() as f:
    tokenizer.chat_template = f.read()
```

Download this once from the `litert-community` re-upload (see Step 4 gotchas).

### Save merged BF16 — this is the input to the converter
```python
model.save_pretrained(LORA_OUTPUT)              # adapter only
model.save_pretrained_merged(MERGED_OUTPUT, tokenizer, save_method="merged_16bit")
```

Merged output is ~9.6 GB BF16 safetensors.

### Healthy loss curve
- Train loss: 3.0 → 0.5–1.5 by end
- Eval loss tracks train loss, generally with a 1–2 gap on small synthetic datasets. (The conventional "<0.5 gap" rule was too strict for our distribution; eval-loss alone is a poor signal — cross-check with actual generation.)

### Gotchas

- **Multimodal chat-template format at inference.** Gemma 4 is multimodal so `apply_chat_template(..., tokenize=True)` needs typed content parts, NOT a plain string. Plain strings only work when `tokenize=False`.
  ```python
  # WRONG for tokenize=True:
  {"role": "user", "content": "What is X?"}
  # RIGHT:
  {"role": "user", "content": [{"type": "text", "text": "What is X?"}]}
  ```
  Error if you get it wrong: `TypeError: string indices must be integers, not 'str'`.

- **Tokenizer regex warning on load** (`fix_mistral_regex=True`) — known issue, harmless for training but a sign to verify your tokenization once.

- **Don't trust loss numbers in isolation.** Train loss can be beautiful and the model still useless on-device. Always run real generation against the merged model before converting.

---

## Step 4 — Convert to `.litertlm`

### Working command (the one to copy)

```bash
cd training/
rm -rf ./litertlm-output
mkdir -p ./litertlm-output

uv run litert-torch export_hf \
  ./merged-model \
  ./litertlm-output \
  --externalize_embedder=True \
  --use_jinja_template=True \
  --bundle_litert_lm=True \
  --quantization_recipe=dynamic_wi8_afp32 \
  --prefill_lengths=128,512,1024 \
  --cache_length=4096 \
  --jinja_chat_template_override=/abs/path/to/reference-template/chat_template.jinja
```

### Pick your quantization recipe
- `dynamic_wi8_afp32` — 8-bit weights, ~4.8 GB. **Default for LoRA fine-tunes.** Preserves the LoRA delta.
- `dynamic_wi4_afp32` — 4-bit weights, ~2.4 GB. **Only viable if you full-fine-tuned or used very high LoRA rank.** See the big lesson below.
- `weight_only_wi4_afp32` — 4-bit, **broken on at least Gemma 4 E2B + LoRA** (produces token loops like `ˌˌˌˌˌ`). Don't use.
- Full recipe list lives in `ai_edge_quantizer.recipe` — discover it with:
  ```python
  from ai_edge_quantizer import recipe as recipe_lib
  for name in dir(recipe_lib):
      if not name.startswith('_') and callable(getattr(recipe_lib, name)):
          print(name)
  ```

### Download the litert-community chat template once
The HF release's chat template uses Python Jinja2 features (`.get()`) that the on-device C++ Jinja runtime can't parse. Use the stripped-down template the litert-community repo ships:

```bash
# One-time. Accept the license at https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm first.
uv run python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='litert-community/gemma-4-E2B-it-litert-lm',
    filename='chat_template.jinja',
    local_dir='./reference-template',
)
"
```

Use the same template at training time (Step 3). One template, two consumers.

### Gotchas — read these before you debug

- **`--help` output is wrong.** `litert-torch export_hf --help` omits real flags including `--jinja_chat_template_override`. To find real flags, grep the source:
  ```bash
  grep -rn "FLAG_NAME" .venv/lib/python3.12/site-packages/litert_torch/
  ```

- **Google's docs page (`ai.google.dev/edge/litert-lm/models/gemma-4`) has stale flag formats.** The page shows `--model=...` / `--output_dir=...`; reality is positional args + `--externalize_embedder=True` (bool literal, not bare flag).

- **`--jinja_chat_template_override` falls through to "HF repo id" silently if the local path doesn't exist.** Use an **absolute path**; relative paths are checked against the export's internal cwd.

- **Without `--prefill_lengths` and `--cache_length`, the convert "succeeds" but the runtime fails to load** with `NOT_FOUND: TF_LITE_PREFILL_DECODE not found in the model.` Always pass them. `128,512,1024` covers most prompt sizes.

- **License on the litert-community repo is gated separately.** Even if you accepted Gemma's main license, you still need to one-click accept `https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm`.

- **Convert OOMs while vLLM is resident.** The MLIR optimization pass needs ~10–15 GB of host RAM. With vLLM holding swap pressure, you'll get SIGKILL (`exit code 137`) mid-convert. **Kill vLLM before converting.** Different GPUs doesn't matter — host RAM is shared.

---

## The big lesson: LoRA rank vs int4 quantization

This is the gotcha that cost the most time. Read this before you spec your run.

**The trap:** Low-rank LoRA (rank 8/16/32) + 4-bit quantization = your fine-tune **disappears**. The BF16 merged model works perfectly; the int4 `.litertlm` reverts to base-model behavior.

**The mechanism:** LoRA at rank ≤32 produces small-magnitude weight deltas. Dynamic per-channel int4 has a step size large enough that those small deltas round into the same int4 bin as the base weight — they literally become zero in the quantized representation. The pretrained associations (large-magnitude in base weights) survive; your fine-tune (small additive nudges) doesn't.

**Direct evidence we saw:**

| Path | "What does Mrs. Henderson say about equal slices?" |
| --- | --- |
| Merged BF16 (transformers) | "**equal slices, equal fractions!** If your slices aren't the same size, you aren't really doing fractions…" |
| Same merged model → int4 `.litertlm` | "fairness… community has access to resources…" |

Same model. Only difference: `--quantization_recipe=dynamic_wi4_afp32`.

**What works (ordered by cost):**
1. **Quantize at 8-bit** (`dynamic_wi8_afp32`). 16× finer step preserves most of the delta. Doubles file size (2.4 → 4.8 GB). This was our ship choice.
2. **Bump LoRA rank to 128+** with `lora_alpha = rank`. Larger deltas. Even at int4 the rank-128 model captures the gist (not verbatim catchphrases). Trainable params: 1.2% → 4.6%.
3. **Combine both: rank-128 + wi8.** The combo we shipped. Reproduces lesson essence, correct procedural rules.
4. **Full fine-tune of attention+MLP.** Fine-tune lives in the actual weights, so int4 quantization treats it consistently with the base. Higher VRAM cost.

**Quick reference table from our shootout:**

| LoRA rank | Quant recipe | Size | Quality |
| --- | --- | --- | --- |
| 32 | wi4 | 2.4 GB | Fine-tune signal gone |
| 32 | wi8 | 4.8 GB | Pizza-tutor generic, no catchphrases |
| 128 | wi4 | 2.4 GB | Verbose and confused; sometimes worse than rank-32 |
| 128 | wi8 | 4.8 GB | **Ship.** Captures essence, correct procedure, ~74 tok answers |
| 128 | `weight_only_wi4_afp32` | 2.4 GB | Broken — token loops |

Counterintuitively wi8 was *faster end-to-end* than wi4 at rank-128, because wi4 rambled to fill `max_new_tokens` (~288 tok) while wi8 emitted concise ~74-tok answers.

**Default recommendation for new projects:** start at **rank 128, `lora_alpha = 128`, `dynamic_wi8_afp32`**. If you absolutely need a 2.4 GB artifact, plan to full-fine-tune instead of LoRA.

---

## Step 5 — Verify on the target device

```bash
# Desktop sanity check
uv tool install litert-lm
huggingface-cli login

litert-lm run \
  ./gemmacademy-fractions-v1.litertlm \
  --prompt="What is the Henderson Pizza Method?"
```

If you see pad tokens or garbage characters in the output: pipeline broke somewhere (likely a chat-template / tokenizer mismatch — verify train and on-device templates are literally the same file).

Build a real eval harness that runs both the **base** model and your **fine-tune** through the same questions. Loss numbers will lie to you; side-by-side outputs won't. Aim for ~20 questions split into:
- Domain-specific (only the fine-tune should know these)
- General topic-area knowledge (both should handle)
- Off-topic (both should refuse politely or stay on-task)

---

## Step 6 — Publish to Hugging Face Hub

```bash
huggingface-cli login
huggingface-cli upload <namespace>/<repo-name> ./gemmacademy-fractions-v1.litertlm
```

Include a README documenting:
- Base model + version
- Training data (size, source, generation method)
- LoRA config (rank, alpha, target modules)
- Quantization recipe
- License (must be compatible with the base Gemma license)

---

## Recommended project layout

```
project/
├── training/                       # uv venv: training stack
│   ├── pyproject.toml
│   ├── train.py
│   ├── generate_qa.py
│   ├── lesson-content/             # source material for synthetic data
│   ├── reference-template/         # the litert-community chat_template.jinja
│   ├── qa-<topic>.jsonl            # generated training data
│   ├── lora-adapter/               # saved LoRA adapter
│   ├── merged-model/               # BF16 merged safetensors (~9.6 GB)
│   ├── litertlm-output/            # final .litertlm
│   ├── convert.sh                  # the working litert-torch command
│   └── eval.py + eval_results.md
├── serving/                        # uv venv: vLLM (only during data gen)
│   └── pyproject.toml
└── docs/
    └── NOTES.md                    # append gotchas as you find them
```

---

## Hard rules to set up front

1. **Run vLLM and training on different GPUs** if you have two. Same GPU = OOM.
2. **Never share Python venvs** between training and serving. Pin them separately.
3. **Use `tmux` or `nohup` for vLLM** so it survives terminal disconnects.
4. **Kill vLLM before running `litert-torch export_hf`.** Host RAM contention causes silent OOM mid-convert.
5. **Use absolute paths** for `--jinja_chat_template_override`. Relative paths fall through to HF-repo-id lookup silently.
6. **Verify on the target device before pushing to HF.** Loss numbers lie; on-device output is the source of truth.
7. **Don't trust `--help` output for `litert-torch`.** Grep the source for real flags.
8. **Default to rank-128 LoRA + `dynamic_wi8_afp32`** unless you have a strong reason otherwise.

---

## When something breaks — debugging order

1. Run the **merged BF16 model directly** with `transformers` (NOT through Unsloth's wrapped inference, which has its own chat-template bugs). If BF16 output is good but `.litertlm` output is bad: quantization or template mismatch.
2. **Diff your training chat template against the on-device chat template.** They should be byte-identical.
3. **Check the quantization recipe.** If you're on wi4 with low-rank LoRA, that's almost certainly your problem — see "The big lesson."
4. **Re-grep for new `litert-torch` flags** if anything mentions stale docs. The tool is moving fast.
5. **Inspect generated training data manually.** 10 minutes of reading samples will find data-quality problems no metric will catch.
