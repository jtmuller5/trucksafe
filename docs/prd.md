# PRD: [Working Name] — On-Device Pre-Trip & In-Transit Safety AI for Commercial Trucking

> **Status:** Draft v0.4 for hackathon scoping
> **Author:** [you]
> **Deadline:** May 18, 2026
> **Changes from v0.3:** Checklist reduced from four steps to three based on what's actually in the archive: (1) fifth wheel side view, (2) lock jaws close-up, (3) pintle hook + safety chains. Landing gear and standalone "trailer gap" dropped — the trailer-gap check is folded into the fifth wheel side view (verifying no gap and full retraction is the point of that shot). Schemas and staging plan updated accordingly.
> **Changes from v0.2:** Resolved that safety chains and pintle hook are a single image with multiple criteria. Combined-criteria schema documented for the pintle hook step.
> **Changes from v0.1:** Architecture revised to use Gemma 4's native structured JSON output instead of describe-then-rule pipeline. Model selection updated based on Gemma 4 family documentation. Data section made concrete based on actual archive contents.

---

## 1. Problem

Every commercial truck in the United States is required by federal law (FMCSA 49 CFR 392.7) to undergo a pre-trip inspection before each shift. The driver walks the rig, checks roughly 30 items — fifth wheel locked, pintle hook closed, safety chains hooked, landing gear retracted, trailer lights, brake lines, tire condition — and signs off. The inspection works on paper. In practice, it fails for predictable reasons:

- **Drivers cut corners under time pressure.** Dispatchers don't pay for inspection time; they pay for delivered miles. A thorough pre-trip is 20+ minutes a driver could spend on the road.
- **Self-verification is unreliable.** A driver who *thinks* the fifth wheel is locked has no second check. They sign the form and leave the yard.
- **Owners can't physically verify.** Fleet operators with even 20 trucks across multiple yards can't watch every pre-trip. The current state of the art for accountable verification is what my uncle does at his FedEx contractor operation: drivers send photos of each safety check from their phones to a custom web app, and he eyeballs them.
- **The photo workflow misses the point.** By the time my uncle sees a bad photo, the driver is already 15 minutes down the road. The verification is retrospective.
- **And once the truck is moving, no one is checking anything.** A coupling can loosen, landing gear can drop, a brake line can disconnect. Drivers don't see most of these failures until they hear or feel them — which is often too late.

The numbers behind this are real and global. Per the WHO Global Status Report on Road Safety 2023, roughly **1.19 million people die in road traffic crashes every year**. In the US alone, large trucks are involved in **5,000+ fatal crashes annually** per FMCSA's Large Truck and Bus Crash Facts, with a meaningful subset involving mechanical or coupling failures that a competent inspection would have caught. Brake-system defects alone were an associated factor in **29% of crashes** in FMCSA's Large Truck Crash Causation Study. The CVSA 2024 International Roadcheck — a 72-hour enforcement blitz across the US, Canada and Mexico — placed **roughly 1 in 5 inspected trucks (23%) out of service** for safety-critical defects, the kind a proper pre-trip is supposed to catch.

The dollar cost to operators is substantial: FMCSA pegs the average fatal large-truck crash at **$3.6 million**, the average injury crash at ~**$200,000**. Coupling failures specifically are statistically rare (FMCSA: ~1 in 1,000 fatal crashes involves a coupling, hitch, or chains) but extraordinarily lethal when they happen — a runaway trailer is a high-speed projectile with no brakes. The 2013 Truxton, NY incident killed seven people (four of them children under ten) when a trailer hauling crushed cars detached from its tractor; the cause was a failed fifth-wheel locking mechanism, the same component this PRD targets.

The status quo is: drivers self-certify, owners trust-but-can't-verify, and once the wheels are turning, no one is watching.

## 2. Vision

A two-mode safety AI that runs entirely on-device, with no dependence on cellular connectivity, built on a fine-tuned Gemma 4 multimodal model.

**Mode 1 — Pre-trip (production-quality):** A driver-facing mobile app that replaces the photo-text workflow. The driver works through a checklist; for each item, the app captures the inspection point and the on-device model returns a structured JSON verification — what it observed, which specific safety criteria were met or failed, and a pass / fail / unclear decision. Failures are explained in plain language the driver can act on. Results sync to the fleet owner's dashboard when connectivity returns.

**Mode 2 — In-transit (prototype):** A truck-mounted camera + edge compute setup that periodically checks coupling integrity, landing gear position, and other visible safety states while the truck is operating. If something looks wrong, the driver is alerted in-cab in seconds — no cloud round-trip, no cell tower required.

The fleet owner is empowered, not replaced. The driver gets a second pair of eyes that's accountable to the actual safety standard, not their own self-pressure. The traveling public gets fewer trailers in the median.

## 3. Why local AI is necessary (not just nice)

This is the criterion the hackathon cares about most. For this domain it's not a stretch:

1. **Latency.** Cloud round-trips are unsuitable for in-transit detection. A coupling failure at 70 mph has a tolerance measured in seconds. On-device inference is sub-second.
2. **Connectivity.** Trucks routinely operate in cellular dead zones — rural highways, mountain passes, loading docks underground, hardened freight terminals. A cloud-dependent safety system is a system that fails in exactly the places it's most needed.
3. **Bandwidth at fleet scale.** Continuous streaming of multiple camera feeds from hundreds of trucks to the cloud, 24/7, is economically and technically absurd. On-device inference makes it possible.
4. **Liability and data control.** Operators are wary of where vehicle footage goes. On-device processing keeps the data local; only structured pass/fail records sync up. This is a real adoption gate, not a nice-to-have.
5. **Domain-specific visual knowledge.** A general-purpose vision model doesn't know what a properly closed pintle hook looks like on a specific tractor configuration, or what fully closed fifth-wheel lock jaws look like at a typical driver-camera angle. Fine-tuning Gemma 4 on real fleet inspection imagery is the right tool. Once you have a domain-adapted model, deploying it on-device is trivial — the value is in the adaptation.

## 4. Target users

**Primary:** Commercial truck drivers and small-to-mid fleet operators. The demo is scoped to a single fleet (my uncle's FedEx contractor operation) running specific tractor and trailer configurations.

**Secondary:** Fleet safety officers, dispatchers, and insurance underwriters who care about verifiable safety compliance.

**Tertiary:** Everyone else on the road. Fewer uncoupled trailers in the median is a public good.

## 5. User stories

**Driver (Marcus, 14 years CDL, hauls for a small contractor):**
- I do pre-trips every morning. Most days I know I'm doing them right. Some days I'm tired, or it's raining, or dispatch is on my back about a delivery window, and I'm honest with myself that I rushed.
- I'd like a tool that catches my mistakes without making me feel watched. If it tells me "looks good, you're clear to go," I don't mind. If it tells me "the safety pin isn't in," I want to know.
- I don't want to send photos through a web app one by one. It's slow and my boss can't really see what's wrong anyway.

**Fleet owner ([your uncle], FedEx contractor with [N] trucks):**
- I'm legally on the hook if a truck I dispatched causes a crash because of something the driver missed.
- I currently verify pre-trips by reviewing photos drivers send me through a web app. It's better than nothing. It's not great.
- I want something that gives me real verification, that drivers will actually use, that doesn't require me to be online 24/7 reviewing photos.
- I'd pay real money for an in-cab system that warns my drivers about coupling issues mid-route. The insurance discount alone might pay for it.

**Safety regulator / insurance underwriter:**
- I want auditable, timestamped, tamper-resistant records of pre-trip inspections.
- Continuous in-transit verification of safety-critical equipment changes the actuarial math for commercial trucking.

## 6. What we're building (hackathon scope)

A working end-to-end system with three components:

### 6.1 Pre-trip mobile app (Flutter, Android)
- Driver opens the app, sees today's inspection checklist (three steps, matching what's in the archive: fifth wheel side view, lock jaws close-up, pintle hook + safety chains)
- For each checklist step, the driver takes a photo at the camera angle the existing photo-text workflow already established
- On-device Gemma 4 E4B (multimodal, instruction-tuned, fine-tuned for our domain) analyzes the photo and returns structured JSON (see Section 6.4 below)
- Note that two of the three checklist steps verify multiple distinct safety criteria from a single image — the schema captures each criterion as its own observation field
- The app surfaces the `human_readable_summary` and `overall_status` to the driver; the full JSON is stored locally for the audit trail
- All inspections stored locally in SQLite; sync to the fleet dashboard when connectivity returns
- Airplane mode demo is the proof — no cloud calls anywhere in the inspection flow

### 6.2 In-transit prototype (recorded footage on a real truck)
- A single camera mounted to capture the fifth-wheel / kingpin coupling area on one of my uncle's trucks
- A compute device on the truck (Android phone strapped under the dash, or a Jetson if available) runs periodic frame analysis using the same fine-tuned Gemma 4 model
- For the hackathon: we record real footage of the truck operating, with the model annotating each frame in near-real-time
- Plus: at least one staged failure (loose coupling, visible gap between trailer and fifth-wheel plate developing mid-route) captured on video to show the system catching it
- The cinematic value of this footage carries the video pitch

### 6.3 The fine-tuning approach

**Model choice: Gemma 4 E4B (instruction-tuned) as the base.**

The Gemma 4 family is purpose-built for this kind of deployment. Three properties matter for us:

- **Native multimodal input** with configurable visual token budgets (70 / 140 / 280 / 560 / 1120 tokens per image). We can tune this to trade off inference latency against visual detail. For pre-trip safety verification — coarser than OCR but finer than scene classification — 280 or 560 tokens is the likely sweet spot. We'll validate during the Day 1 spike.
- **Native structured JSON output and function calling.** Gemma 4 was trained from the start to reliably emit JSON conforming to schemas provided in the system prompt. We don't fine-tune for JSON formatting; we fine-tune for *accurate population of the schema given our domain's visual cues*.
- **Multi-Token Prediction (MTP) drafter for speculative decoding.** Google released a paired drafter model for E4B that delivers up to 3x inference speedup with zero quality loss. We use this in the in-transit prototype where per-frame latency is the bottleneck.

E4B (4B effective parameters) is the right size: meaningfully better visual reasoning than E2B, still mobile-feasible. If real-device testing on Day 1 shows E4B is too slow on the target Android phone, we fall back to E2B as a known-good downshift.

**Fine-tuning approach: LoRA via Unsloth on the 5090 rig.**

Per Unsloth's published benchmarks, LoRA fine-tuning of Gemma 4 E4B fits in well under the 32GB available on a single 5090, so we have room to iterate.

### 6.4 The output schemas

The three checklist steps have different schemas because they verify different sets of safety criteria. Two of the three are combined-criteria — they evaluate multiple independent observations from a single image.

**Step 1 — Fifth wheel (side view).** Verifies the trailer is fully seated on the fifth wheel plate with no visible daylight between the trailer apron and the plate. This is the "no gap" check; a visible gap is the classic field-detectable sign of a high-pinned or improperly seated kingpin that will dislodge under highway loads.

```json
{
  "category": "fifth_wheel_side_view",
  "observations": {
    "trailer_seated_flush": "yes | no | unclear",
    "visible_gap_between_apron_and_plate": "none | minor | obvious",
    "release_handle_position": "stowed | extended | unclear",
    "image_quality": "good | poor"
  },
  "issues_detected": [],
  "overall_status": "pass | fail | retake",
  "confidence": "high | medium | low",
  "human_readable_summary": "Trailer is seated flush against the fifth wheel plate with no visible gap. Release handle is stowed."
}
```

**Step 2 — Lock jaws (close-up).** Verifies the locking jaws have fully closed around the kingpin shank. This is the canonical "did the coupling actually engage" check. A tug test alone can pass with the jaws in a partially-closed state — the only reliable verification is visual.

```json
{
  "category": "lock_jaws_closeup",
  "observations": {
    "jaws_fully_closed_around_kingpin": "yes | no | unclear",
    "kingpin_visible_in_jaws": true,
    "lock_indicator_position": "locked | unlocked | not_visible",
    "image_quality": "good | poor"
  },
  "issues_detected": [],
  "overall_status": "pass | fail | retake",
  "confidence": "high | medium | low",
  "human_readable_summary": "Lock jaws are fully closed around the kingpin. Lock indicator is in the locked position."
}
```

**Step 3 — Pintle hook + safety chains.** Verifies the coupling itself plus the safety chains and pin. The richest combined-criteria step — a single image must satisfy three independent criteria for an overall pass.

```json
{
  "category": "pintle_hook_and_chains",
  "observations": {
    "hook_latch_state": "closed | open | unclear",
    "safety_pin_visible": true,
    "safety_chains_count": 2,
    "safety_chains_hooked": true,
    "safety_chains_crossed": true,
    "image_quality": "good | poor"
  },
  "issues_detected": [],
  "overall_status": "pass | fail | retake",
  "confidence": "high | medium | low",
  "human_readable_summary": "Pintle hook latch is closed with safety pin inserted. Both safety chains are hooked to the receiver crossmember and crossed beneath."
}
```

Each schema is provided to the model via the system prompt, alongside the per-step pass criteria written as plain rules. For the pintle hook step, the rules are something like: "The hook latch must be fully closed. A safety pin must be visible through the latch hole. At least two safety chains must be visible, both hooked to the receiver crossmember." For the fifth wheel side view: "The trailer apron must be flush against the fifth wheel plate with no visible daylight between them. The release handle must be in the stowed position."

This combined-criteria approach showcases the architecture's strength: the model evaluates each criterion *independently* from the same image, so a "fail" on `safety_pin_visible` doesn't mask a separate failure on `hook_latch_state`. Each field is separately auditable, and `issues_detected` enumerates exactly which criteria failed.

This architecture gives us three things at once:

1. **Machine-actionable output from the first token.** No regex, no prose parsing, no edge cases.
2. **An auditable explanation** via the `human_readable_summary` field. Every decision can be inspected by a human supervisor — the Safety & Trust track angle.
3. **Graceful uncertainty.** The model can emit `overall_status: "retake"` and `confidence: "low"` instead of being forced into a binary pass/fail when the photo is ambiguous. This is the right behavior for a safety-critical tool.

### 6.5 Training data strategy

Per inventory of my uncle's archive (Feb 2023 → present):

- 3 checklist steps represented in the archive: fifth wheel side view, lock jaws close-up, pintle hook + safety chains
- Submission metadata gives us: timestamp, driver ID, truck ID, and which checklist step the photo was for. **This means we already have implicit category labels for every image — no human labeling required for the bulk of the dataset.**
- Photos are mostly "good" (approved by the owner), with a small population of rejected/resubmitted photos that we can mine as natural negatives by looking for resubmissions within short time windows under the same driver/truck/step.

**Generating the training labels (the JSON ground truth):**

1. For each image, the submission metadata tells us the category. We use the 31B Gemma 4 model running on the 5090 rig (via vLLM) to generate the structured JSON output we *want* the small model to produce, conditioned on the system prompt + image + category.
2. We manually inspect a random sample of ~100 generated labels per category, correct errors, and use the corrections to iterate on the 31B labeling prompt.
3. We add the natural negatives mined from the resubmission pattern.
4. We add staged negatives photographed on Day 2 at the yard (see Section 12) to backfill failure modes that don't appear naturally in the archive. The pintle hook step needs *combinations* of failure modes (since it verifies multiple criteria from one image): hook open + chains hooked, hook closed + chains unhooked, hook closed + only one chain, hook closed + pin missing, hook open + chains unhooked. The fifth wheel side view needs visible-gap negatives (trailer apron not flush against the plate). The lock jaws close-up needs partially-open-jaw negatives and missed-kingpin negatives.

Target dataset size: 200-500 labeled images per checklist step, with at least 20% negatives per step. The natural archive is way more than enough on the positive side; the staging session is the lever for negatives.

### 6.6 Evaluation

- Held-out test set: ~50 images per checklist step, balanced positive/negative, never seen during training
- Metrics per step:
  - **Field-level accuracy:** does each observation field match ground truth? (precision/recall per field — especially important for the multi-criterion pintle hook and fifth wheel steps)
  - **Pass/fail correctness:** does `overall_status` match ground truth?
  - **Calibration:** how often does the model emit `confidence: "low"` or `overall_status: "retake"` for genuinely ambiguous photos, vs. confabulating?
- Side-by-side: same eval set against base (non-fine-tuned) Gemma 4 E4B with the same system prompt. The delta is the writeup's headline benchmark.

## 7. Out of scope (for hackathon)

- Multi-fleet support (real B2B onboarding, billing, RBAC)
- Production in-cab hardware integration (CAN bus, dashcam mount engineering, etc.)
- Real-time alerting infrastructure beyond an on-device warning
- iOS app (Android-only demo)
- Anything that requires the truck to be running specific firmware
- Replacing the human pre-trip — this is an assistant, not a substitute
- Driver-monitoring use cases (drowsiness, attention) — different scope, different ethics
- Inspection categories beyond the 3 checklist steps represented in the archive plus what we can stage in a day. Landing gear, tires, brake lines, lights, and the other 25+ items in a complete FMCSA pre-trip are real and important but out of scope for v1; the FMCSA Large Truck Crash Causation Study attributes 29% of crashes to brake-system associated factors and ~6% to tire defects, so each of these is a credible v2 expansion path.

## 8. Success criteria for the hackathon submission

This is what the writeup and video need to demonstrate:

1. **Working pre-trip app on a real Android device, fully offline.** Airplane mode is on, the model is running locally, inspections complete end-to-end with no cloud calls. No fakery.
2. **Demonstrable improvement over base Gemma 4.** Side-by-side evaluation showing the fine-tuned model correctly identifies category-specific failure modes the base model gets wrong or hand-waves. Concrete per-category metrics in the writeup.
3. **At least one in-transit prototype clip.** Real truck, real camera, real model output overlaid on the footage. Even a single 30-second clip of the system correctly flagging a staged failure while the truck is moving is enormously valuable.
4. **Compelling 3-minute video.** Real fleet, real driver, real owner (my uncle), real stakes. Opens with the human story (the Truxton, NY trailer separation is the canonical anchor case — 7 dead, 4 children, fifth-wheel mechanical failure), proves the technology works, closes with the in-transit prototype as the headline of where this goes next.
5. **Public code repo.** Clean, documented, reproducible.
6. **Public model weights.** Fine-tuned weights and adapter published on Hugging Face per the brief's "publish your weights and benchmarks" requirement.

## 9. Technical architecture (rough)

**Training side (runs on your GPU rig):**
- Python + Unsloth for LoRA fine-tuning of Gemma 4 E4B (instruction-tuned variant)
- Gemma 4 31B served via vLLM on the rig, used for generating structured JSON labels for the training images conditioned on submission metadata
- Eval harness comparing fine-tuned vs. base E4B on held-out images, scored per-field and end-to-end

**Mobile side:**
- Flutter app
- LiteRT for on-device Gemma 4 E4B multimodal inference (the LiteRT special tech track is a natural fit)
- Visual token budget set per real-device performance testing (likely 280 or 560)
- Local SQLite for inspection records; sync layer to a simple fleet dashboard when connectivity returns

**In-transit prototype side:**
- A single USB or Android-tethered camera mounted on the truck for the demo
- Android phone running the same on-device model, sampling frames at ~1 Hz
- E4B + MTP drafter for speculative decoding to keep per-frame inference fast
- Recorded footage with model output overlay for the video

**Fleet dashboard (minimal):**
- Simple web app (Next.js, TypeScript) where the owner can see today's completed inspections
- Out of scope: real auth, real multi-tenant, real ops — this is the minimum to make the video tell the full story

## 10. Track strategy

This project is positioned to compete in:
- **Global Resilience Impact Track** ($10k) — primary lens. The track is about systems that "anticipate, mitigate, and respond" to real-world risks. Preventing commercial vehicle accidents through offline, edge-based verification fits the brief precisely.
- **Safety & Trust Impact Track** ($10k) — strong secondary fit. The structured-JSON-with-summary architecture is explicitly designed for grounded, explainable AI. Every decision is auditable.
- **LiteRT Special Tech Track** ($10k) — natural deployment runtime for on-device multimodal Gemma 4 on Android. Likely fewer competing teams given LiteRT's steeper learning curve.
- **Unsloth Special Tech Track** ($10k) — backup tech track. The fine-tune itself is the core innovation.
- **Main Track** — eligible.

Projects can win both an Impact track and a Special Tech track. Realistic ceiling: Global Resilience + LiteRT = $20k. Stretch: Main Track placement on top.

## 11. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| All-positive training data leads to a model that rubber-stamps everything | Medium | Mine the archive for natural negatives (resubmissions); stage failure photos at the yard on Day 2 — including failure-mode combinations for the pintle hook step and visible-gap shots for the fifth wheel step; ensure 20%+ of training data per step is negative |
| 31B-generated labels are inaccurate, polluting the training set | Medium | Manually inspect 100 random labels per checklist step before training; iterate on the labeling system prompt until quality is acceptable |
| Fine-tuned E4B doesn't meaningfully beat base E4B | Medium-Low | The base model has no fleet-specific visual context; the gap should be obvious on categories like "is the safety pin inserted" — verify Day 4 |
| E4B inference too slow on target Android device | Medium | Test Day 1 on real hardware; downshift to E2B if needed; reduce visual token budget; the in-transit prototype gets MTP drafter regardless |
| Truck access falls through (uncle's schedule, weather, etc.) | Medium | Lock in 1-2 specific days at the yard ASAP this week; have a backup plan to use stock footage + a stationary trailer for the in-transit segment |
| Uncle/drivers uncomfortable on camera | Low-Medium | Talk to him first; offer to anonymize if he wants; have B-roll + voiceover as fallback |
| LiteRT learning curve eats into demo time | Medium-High | Spike LiteRT on Day 1-2 with a stock Gemma 4 model; if it's too painful, fall back to llama.cpp on Android (still a valid special tech track) |
| 10 days isn't enough | Medium | Cut in-transit prototype before cutting pre-trip; the working pre-trip + video is the floor; in-transit is the ceiling |

## 12. Timeline (10 days)

- **Day 1:** Spike LiteRT or llama.cpp on Android with a stock Gemma 4 E4B model. Validate that multimodal inference on a real phone is fast enough and that structured JSON output works as documented. Set up Unsloth on the rig. Pull and inventory uncle's photo archive; verify the submission metadata mapping.
- **Day 2:** Visit the yard. Stage failure photos for each checklist step. The pintle hook step needs ~5 failure-mode *combinations* (different combinations of hook state, pin presence, and chain hookup); the fifth wheel side view needs visible-gap negatives (trailer apron not flush); the lock jaws close-up needs partially-open-jaw and missed-kingpin negatives. Budget ~30 minutes per step. Mount a camera on one truck for in-transit footage.
- **Day 3:** Build the labeling pipeline using Gemma 4 31B on the rig. Generate JSON labels for the archive + staged negatives. Manually inspect 100 labels per checklist step; iterate on the labeling prompt.
- **Day 4:** Run the LoRA fine-tune on E4B. Run evaluation against the held-out test set. Iterate if needed (smaller LR, more epochs, different LoRA rank).
- **Day 5:** Build the Flutter pre-trip app. Wire up LiteRT inference. Get end-to-end flow working offline. Walk through with a hardcoded checklist of categories.
- **Day 6:** Capture in-transit footage. Drive the truck with the camera mounted. Stage at least one mid-route failure for the demo. Record the model's output alongside the footage.
- **Day 7:** Build the minimal fleet dashboard. Polish the pre-trip app. Walk the full flow 5+ times.
- **Days 8-9:** Video production (script, footage selection, editing, voiceover). Writeup. Repo polish. Weights upload to Hugging Face. The video carries everything — give it the time it needs.
- **Day 10:** Buffer for things that broke. Final submission.

## 13. Open questions for [you]

1. **Truck access — which day(s)?** The in-transit footage shoot is the longest-lead practical item. Lock this in by Day 2 of your timeline at the latest.
2. **Will your uncle do an on-camera interview?** Even 60 seconds of him saying "I've been doing this for [N] years and the moment I'm afraid of is [X]" is gold. Worth asking this week.
3. **How exactly is the submission metadata stored?** When you hand off to the frontend agent for downloading, it'll matter whether the checklist-step label lives in a filename pattern, a sidecar JSON, a database export, or directly in EXIF/IPTC. Worth confirming the format so labels can be preserved during download. *(In progress — frontend agent is pulling the archive now.)*
4. **Resubmission detection feasibility.** Mining natural negatives from resubmission patterns depends on whether the metadata captures "this photo replaced an earlier one for the same step/truck/driver." If that's not directly captured, we can approximate by looking for multiple submissions within a short time window for the same (driver, truck, step). Worth a quick sanity check.
5. **Does the in-cab camera angle work?** Worth checking that a camera mounted in a realistic position can actually see the coupling clearly while the truck is in motion. If not, the in-transit story shifts (e.g., trailer-side cameras looking inward, or a mast camera) and that changes the demo logistics.