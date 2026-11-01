# Multilingual & Localization Architecture

**Document ID:** ARCH-PO-008  
**Version:** 2.0.0  

## 1. Core Architectural Mandate

Workplace conversations naturally reflect local culture, regional idioms, and code-switching (for example, Indian professionals mixing English with Hindi, Malayalam, or Tamil, or LATAM workers mixing Spanish and English). Pressure Out accommodates multilingual expression from Day 1 in its database schema, API contracts, font rendering, and search indexing—even while launching with English (`en`) as the default UI locale.

## 2. Four Layers of Multilingual Support

### 2.1 Layer 1: End-to-End Unicode Integrity
* **Database:** PostgreSQL databases are initialized with `ENCODING = 'UTF8'` and `LC_COLLATE = 'C.UTF-8'`. Every text column (`posts.title`, `posts.body`, `comments.body`, `public_profiles.display_name`, `public_profiles.bio`, `meme_assets.captions_json`, `tags.display_name`) accepts full 4-byte UTF-8 Unicode (including Indic scripts, Arabic/Hebrew RTL scripts, CJK characters, and emojis).
* **API & Transport:** FastAPI serializes JSON with `ensure_ascii=False` and `Content-Type: application/json; charset=utf-8`. Pydantic validators normalize Unicode strings using **NFC (Canonical Decomposition, followed by Canonical Composition)** before storage and comparison so visually identical accented or Indic characters match consistently in search and tags.
* **Meme Studio Text Shaping:** Server-side template rendering (`TemplateRenderer`) uses Pillow compiled with `libraqm` / HarfBuzz and bundled **Google Noto Sans** font families (`Noto Sans`, `Noto Sans Devanagari`, `Noto Sans Malayalam`, `Noto Sans Tamil`, `Noto Sans Arabic`) so complex ligatures and conjunct consonants render accurately on meme images.

### 2.2 Layer 2: Interface Localization (UI i18n)
* **No Hardcoded Strings:** All user-visible UI labels, button texts, navigation items, validation messages, and moderation notices reside in structured JSON locale catalogs under `frontend/src/locales/{locale}/common.json`.
* **Locale Resolution Order:**
  1. Authenticated user's saved `preferred_ui_locale` (`users.preferred_ui_locale`).
  2. Browser `Accept-Language` header / cookie override for unauthenticated visitors.
  3. Default fallback: `en` (English).
* **Graceful Key Fallback:** If a specific string key is missing in a non-English locale catalog during progressive rollout, the i18n loader falls back cleanly to the `en` string rather than rendering raw key names.
* **RTL Layout Readiness:** Tailwind CSS layout components use logical properties (`ms-*`, `me-*`, `ps-*`, `pe-*`, `text-start`, `text-end`) rather than physical `left`/`right` properties so Right-to-Left (RTL) scripts render cleanly.

### 2.3 Layer 3: User-Generated Content Language & Mixed-Language Support
* **BCP 47 Language Tagging:** Every post and comment stores a `content_language` column validated against standard BCP 47 tags:
  * Specific primary languages: `en` (English), `hi` (Hindi), `ml` (Malayalam), `ta` (Tamil), `te` (Telugu), `kn` (Kannada), `es` (Spanish), `pt` (Portuguese), `fr` (French), etc.
  * **Code-Switching / Mixed Language:** `mul` (Multiple/Mixed languages—explicitly selectable in the composer as *"Mixed / Code-Switched, e.g., Hinglish, Manglish, Spanglish"*).
  * **Undetermined:** `und` (Fallback when user does not specify and heuristic detection is uncertain).
* **Authoritative Original Preservation:** User posts and comments are **never** automatically translated or rewritten on submission. The exact text submitted by the user is stored in `posts.body` and `comments.body`.
* **Language-Aware Discovery:** Users can configure `preferred_content_locales` (e.g., `["en", "hi", "mul"]`) in their settings to filter their `Popular`, `Latest`, and `Explore` feeds, or toggle *"All Languages"* at any time.

### 2.4 Layer 4: Optional Non-Destructive Translation
* **Derived Artifact Model:** When a reader clicks *"Translate to [Locale]"* on a post or comment written in another language, the backend queries `content_translations` keyed by `(source_type, source_id, target_locale, source_version_hash)`.
* **Cache & Invalidation:** Because `source_version_hash` is the SHA-256 hash of the original text, editing a post automatically invalidates stale translations without mutating the source row.
* **UI Presentation & Failure Handling:**
  * Translated content renders in a visually distinct container with a header badge: *"Translated from [Language] — Show Original"*.
  * If `TranslationProviderAdapter` is disabled, times out, or does not support the language pair, the UI keeps the original content visible and displays a non-intrusive toast: *"Translation is currently unavailable for this post."*

## 3. Supported-Language Capability Matrix

Because AI models and moderation classifiers do not perform equally across all human languages, Pressure Out maintains an explicit **Language Capability Matrix** in configuration (`app/modules/languages/matrix.py`) rather than promising uniform AI performance everywhere:

| Tier | Languages | Unicode Posts & Comments | UI Localization | On-Demand Translation | AI Meme Caption & Image Prompts | Automated Safety / PII Heuristics |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1 (Launch Default)** | English (`en`) | Supported (P0) | 100% Complete (P0) | Supported (P1) | Benchmark Verified (P0) | Full Regex + Keyword Coverage (P0) |
| **Tier 2 (Progressive Enablement)** | Hindi (`hi`), Malayalam (`ml`), Tamil (`ta`), Spanish (`es`), Mixed (`mul`) | Supported from Day 1 (P0) | Catalog Hooks Ready (P1 Rollout) | Supported via Adapter (P1) | Enabled with User Preview & Native Speaker Eval | Universal PII Regex + Escalation to Human Mod Queue |
| **Tier 3 (All Other Unicode Scripts)** | Any valid UTF-8 script (`und` / BCP 47) | Supported from Day 1 (P0) | Falls back to `en` UI | Best-effort or Disabled | Falls back to Manual Template Captioning if unsupported | Universal PII Regex + Human Escalation |
