# AI Meme Studio Architecture & External Service Boundaries

**Document ID:** ARCH-PO-007  
**Version:** 2.0.0  
**Related Diagram:** [MEME_GENERATION_FLOW.md](../diagrams/MEME_GENERATION_FLOW.md)

## 1. Architectural Overview

The **AI Meme Studio** (`app/modules/memes/`) is a first-class creation engine integrated directly with Pressure Out's social posting pipeline. It is engineered around three design mandates:
1. **Zero Hard-Coded AI Vendors:** All external AI calls pass through replaceable server-side Python adapter interfaces (`CaptionProviderAdapter` and `ImageProviderAdapter`).
2. **Always-On Template Fallback:** Template-based meme creation runs 100% locally using deterministic image composition, guaranteeing that users can create and publish memes even if external AI providers are unconfigured, rate-limited, or offline.
3. **Strict Cost, Quota & Privacy Guardrails:** Prompts are sanitized before leaving the boundary, per-user and global daily spend caps are enforced in PostgreSQL before any provider call, and API keys never leave the backend server.

## 2. Three Creation Workflows

### 2.1 Mode 1: Template-Based Meme Creation (Synchronous, P0)
1. **Template Catalog:** Curated workplace meme templates stored in `meme_templates` with predefined `text_regions` JSON (bounding box coordinates, default font size, text alignment, stroke width) and license metadata.
2. **Caption Composition:** Users enter top, bottom, or multi-region text in any Unicode script (`en`, `hi`, `ta`, `ml`, `es`, etc.) and preview positioning in the browser canvas.
3. **Server Rendering & Validation:** Submitting `POST /api/v1/memes/render-template` invokes `TemplateRenderer` (using Pillow + HarfBuzz/Raqm text shaping with bundled Noto fonts so complex Indic ligatures and emojis render accurately), writes a validated PNG/WebP to Object Storage, creates a `meme_assets` row, and returns the asset ready for download or publication.

### 2.2 Mode 2: AI-Assisted Workplace Captions (Low-Latency, P0)
1. **User Input:** User provides a short workplace situation prompt (max 300 chars, e.g., *"My manager scheduled a 4:45 PM Friday meeting with no agenda"*), selects a `tone` (`sarcastic`, `wholesome`, `dramatic`, `absurd`, `deadpan`), and selects a `language` (`BCP 47` tag).
2. **Preflight & Quota Check:** Backend verifies the user has not exceeded their daily caption quota (default: **15 requests/day/user**), runs the PII scanner to strip/reject emails or phone numbers, and invokes `CaptionProviderAdapter.generate_captions()`.
3. **Review & Edit:** Returns 3–5 structured caption options (`[{ "top_text": "...", "bottom_text": "..." }]`). The user must review, optionally edit, and explicitly apply a caption before publishing.

### 2.3 Mode 3: Custom AI Image Generation (Asynchronous Job Lifecycle, P0)
Because image generation takes 3–25 seconds and carries higher per-call cost, it uses an asynchronous job state machine (`meme_jobs`):
1. **Job Submission:** Client sends `POST /api/v1/memes/jobs` with header `Idempotency-Key: <uuid>`, `prompt`, `style_tone`, and `language`.
2. **Quota & Spend Circuit Breaker:** Backend checks:
   * User has no more than **1 active (`queued` or `generating`) job** concurrently.
   * User has not exceeded their daily AI image quota (default: **5 images/day/user**).
   * Platform-wide daily AI spend (`SUM(estimated_cost_micros)` in `ai_provider_usage` for current UTC day) is below `AI_DAILY_SPEND_CAP_USD`.
3. **Worker Execution (`SKIP LOCKED`):** Background worker claims the `queued` job, transitions it to `generating`, and calls `ImageProviderAdapter.generate_image()` with a strict timeout (default: **30 seconds**) and at most **1 automatic idempotent retry** on transient `502`/`504` network errors.
4. **Output Validation (`validating` -> `ready`):** Worker verifies image magic bytes (`PNG`/`WebP`/`JPEG`), enforces max asset size (**≤ 5 MB**), strips any embedded EXIF metadata, writes to private Object Storage, records usage in `ai_provider_usage`, and updates `status = 'ready'`.
5. **Cancellation:** While a job is still in `status = 'queued'`, the owner can call `POST /api/v1/memes/jobs/{id}/cancel` to transition it to `cancelled` without consuming quota.

## 3. Provider-Neutral Service Interfaces (`app/modules/memes/adapters/base.py`)

```python
from dataclasses import dataclass
from typing import Protocol, Sequence

@dataclass(frozen=True)
class CaptionRequest:
    sanitized_prompt: str
    tone: str          # sarcastic | wholesome | dramatic | absurd | deadpan
    language_tag: str  # BCP 47 tag e.g. "en", "hi", "es"
    max_suggestions: int = 4

@dataclass(frozen=True)
class CaptionCandidate:
    top_text: str
    bottom_text: str

@dataclass(frozen=True)
class CaptionResult:
    candidates: Sequence[CaptionCandidate]
    provider_name: str
    model_name: str
    input_tokens: int
    output_tokens: int
    estimated_cost_micros: int

@dataclass(frozen=True)
class ImageGenRequest:
    job_id: str
    sanitized_prompt: str
    style_preset: str
    language_tag: str
    width: int = 1024
    height: int = 1024

@dataclass(frozen=True)
class ImageGenResult:
    image_bytes: bytes
    mime_type: str
    provider_name: str
    model_name: str
    estimated_cost_micros: int

class CaptionProviderAdapter(Protocol):
    async def generate_captions(self, req: CaptionRequest) -> CaptionResult: ...

class ImageProviderAdapter(Protocol):
    async def generate_image(self, req: ImageGenRequest) -> ImageGenResult: ...
```

## 4. Configurable Quotas, Cost Controls & Privacy Boundaries

| Control Parameter | Default Environment Variable | Baseline Value | Enforcement Behavior |
| :--- | :--- | :--- | :--- |
| **Max Prompt Length** | `MEME_MAX_PROMPT_CHARS` | `400` chars | Validated by Pydantic; rejects longer inputs with `422`. |
| **Caption Quota / User / Day** | `MEME_CAPTION_DAILY_LIMIT` | `15` requests | Checked against `meme_jobs`; returns `429 MEME_QUOTA_EXCEEDED`. |
| **AI Image Quota / User / Day** | `MEME_IMAGE_DAILY_LIMIT` | `5` jobs | Checked against `meme_jobs`; returns `429 MEME_QUOTA_EXCEEDED`. |
| **Max Concurrent Jobs / User** | `MEME_MAX_CONCURRENT_JOBS` | `1` job | Prevents queue flooding by a single account. |
| **Max Retries per Job** | `MEME_JOB_MAX_RETRIES` | `1` retry (2 attempts total) | Prevents duplicate billing on stuck provider requests. |
| **Provider Request Timeout** | `MEME_PROVIDER_TIMEOUT_SEC` | `10s` (caption) / `30s` (image) | Enforced via `httpx.Timeout`; maps timeout to safe user error. |
| **Global Daily Spend Circuit Breaker** | `AI_DAILY_SPEND_CAP_USD` | `$25.00` / day (configurable) | Automatically disables live AI adapters and falls back to Template Maker + alerts engineering when daily threshold is reached. |

### 4.1 AI Privacy Rules
* **What May Be Sent to External Providers:** Only `sanitized_prompt`, `tone`/`style_preset`, and `language_tag`.
* **What Must NEVER Be Sent:** `user_id`, `@handle`, `email`, IP address, community slug, session cookies, or prompts flagged as containing personal phone numbers/emails.
* **Provider Selection Criteria (Before Production Enablement):** Any commercial AI vendor wired into `http_provider.py` must contractually guarantee **zero training on API customer prompts/outputs** and **≤ 30-day abuse-monitoring log retention**.
