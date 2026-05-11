# System architecture

Placeholder. Cover at least:

- Labeler pipeline (image archive → Gemma 4 31B via vLLM → JSON labels validated against `shared/schemas/`)
- Fine-tune pipeline (Unsloth LoRA on Gemma 4 E4B → export to `.litertlm`)
- Mobile inference (Flutter + LiteRT-LM, 3-step inspection flow)
- Dashboard data flow (Next.js / TypeScript, fleet-owner review)
