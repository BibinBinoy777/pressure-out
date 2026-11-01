# Frontend Product & Technical Architecture

**Document ID:** ARCH-PO-002  
**Version:** 2.0.0  

## 1. Frontend Technology Stack & Principles

* **Framework:** Next.js (App Router) with React 19 and TypeScript (strict mode).
* **Styling:** Tailwind CSS with semantic CSS design tokens (supporting high-contrast light and dark modes).
* **UI Primitives:** Accessible headless primitives (Radix UI / shadcn-style pattern) ensuring WAI-ARIA compliance, keyboard navigation, and focus trapping.
* **Data Fetching & State:**
  * **Server Components (RSC):** Used for initial rendering of public feeds, community directories, and public post detail pages to ensure fast First Contentful Paint (FCP) and SEO discoverability.
  * **Client Query Layer (TanStack Query / SWR pattern):** Manages cursor-paginated feeds, optimistic vote/reaction toggles, and polling for asynchronous AI Meme Studio jobs.
  * **Local Component State:** Scoped strictly to transient UI forms (Composer draft text, Meme Canvas layer coordinates, Identity Mode selector).
* **Core Security Rule:** The frontend hides unauthorized buttons for usability, but **never** acts as the security boundary. It never receives private account fields for other users and never stores AI provider keys.

## 2. Information Architecture & Route Map

All user-facing routes are organized under locale-aware or locale-negotiated App Router segments:

| Route Path | Access | Rendering Strategy | Primary Page Responsibilities | MVP Status |
| :--- | :--- | :--- | :--- | :--- |
| `/` | Public | SSR + Client Hydration | Landing hero for new visitors; unified Home Feed (`Popular` / `Latest` / `Following` tabs), community sidebar, quick post CTA. | **MVP (P0)** |
| `/explore` | Public | SSR | Trending topics, curated starter communities, "Fresh Posts" discovery rail, language filter bar. | **MVP (P0)** |
| `/communities` | Public | SSR | Searchable, categorized directory of all active workplace communities with member counts and descriptions. | **MVP (P0)** |
| `/c/[slug]` | Public | SSR + Client Feed | Individual community header, community rules drawer, join/leave button, and cursor-paginated community feed. | **MVP (P0)** |
| `/p/[postId]` | Public | SSR + Client Comments | Full post view (text, meme image, poll widget, or exit story card), reaction bar, translation toggle, and paginated nested comment tree. | **MVP (P0)** |
| `/search` | Public | CSR / SSR | Search results filtered by query string, community (`c/[slug]`), post type (`meme`, `rant`, etc.), and content language (`BCP 47`). | **MVP (P0)** |
| `/auth/register` | Guest Only | Client Form | Pseudonymous registration (`handle`, `password`, optional `recovery_email`, preferred language selector). | **MVP (P0)** |
| `/auth/login` | Guest Only | Client Form | Handle + password login with brute-force feedback and recovery link. | **MVP (P0)** |
| `/auth/recovery` | Guest Only | Client Form | Request and complete password reset via recovery email token or backup recovery code. | **MVP (P0)** |
| `/create` | Authenticated | Client Interactive | Multi-tab post composer (`Discussion`, `Rant`, `Question`, `Poll`, `Story`, `Advice`, `Exit Story`) with prominent **Identity Mode Selector**, **Language Tag Selector**, and **Pre-Publish PII Warning Banner**. | **MVP (P0)** |
| `/meme-studio` | Authenticated | Client Interactive | Signature **AI Meme Studio**: Template gallery, interactive HTML5 Canvas / SVG text overlay editor, AI Caption Assistant panel, AI Image Generator job tracker, `alt_text` editor, download & publish actions. | **MVP (P0)** |
| `/u/[handle]` | Public | SSR | Public pseudonymous profile displaying bio, voluntary professional badge (if enabled), and public `pseudonymous`/`professional` posts (**never** `anonymous` posts). | **MVP (P0)** |
| `/saved` | Authenticated | Client Private | Private list of bookmarked posts and saved draft memes. | **MVP (P0)** |
| `/notifications` | Authenticated | Client Private | In-app alerts for post replies, comment replies, meme job completion, and moderation notices. | **MVP (P1)** |
| `/settings/profile` | Authenticated | Client Private | Edit display name, bio, and optional **Professional Profile** (`role_title`, `industry`, `experience_band`, `region_label`). | **MVP (P0)** |
| `/settings/privacy` | Authenticated | Client Private | Default posting identity preference, blocked/muted users list, active device sessions (with "Revoke All"), and Account Deletion workflow. | **MVP (P0)** |
| `/moderation/queue` | Mod / Admin | Client Protected | Filterable queue of reported posts/comments (`doxxing_pii`, `harassment`, `spam`), context viewer, action drawer with mandatory reason codes. | **MVP (P0)** |
| `/moderation/appeals` | Mod / Admin | Client Protected | Review user-submitted appeals against content removals or account restrictions. | **MVP (P0)** |
| `/moderation/audit` | Admin Only | Client Protected | Read-only searchable view of security-relevant administrative and moderation `audit_events`. | **MVP (P0)** |

## 3. Directory & Module Structure (`frontend/`)

```text
frontend/
├── public/
│   └── fonts/                      # Self-hosted Noto Sans / Inter variable fonts for Unicode coverage
├── src/
│   ├── app/
│   │   ├── (public)/               # /, /explore, /communities, /c/[slug], /p/[postId], /search, /u/[handle]
│   │   ├── (auth)/                 # /auth/login, /auth/register, /auth/recovery
│   │   ├── (authenticated)/        # /create, /meme-studio, /saved, /notifications, /settings/*
│   │   └── (moderation)/           # /moderation/queue, /moderation/appeals, /moderation/audit
│   ├── components/
│   │   ├── ui/                     # Button, Dialog, Dropdown, Tabs, Toast, Badge, Tooltip (WCAG AA)
│   │   ├── identity/               # IdentityModeSelector, AuthorBadge, AnonymousOpLockBanner, PiiWarningAlert
│   │   ├── feed/                   # PostCard, PollWidget, ExitStoryCard, ReactionBar, VoteControls
│   │   ├── comments/               # CommentTree, CommentNode, CommentComposer, LoadMoreSubtreeButton
│   │   ├── meme-studio/            # TemplatePicker, MemeCanvasEditor, AiCaptionDrawer, AiImageJobStatus
│   │   ├── i18n/                   # LanguageTagSelect, ContentTranslationToggle, UiLocaleSwitcher
│   │   └── moderation/             # ReportModal, ModQueueItem, ModActionForm, AppealModal
│   ├── lib/
│   │   ├── api-client.ts           # Central fetch wrapper with CSRF header, credentials: 'include', error parsing
│   │   ├── schemas/                # Zod validation schemas mirroring FastAPI Pydantic models
│   │   ├── pii-scanner.ts          # Client-side pre-flight regex hint for emails/phones before server validation
│   │   └── i18n.ts                 # Dictionary loader & fallback resolver
│   ├── locales/
│   │   ├── en/common.json          # Authoritative English catalog
│   │   └── hi/common.json          # Starter additional locale catalog structure
│   └── types/
│       └── api.d.ts                # Generated from FastAPI OpenAPI /api/v1/openapi.json
└── tests/
    ├── unit/                       # Vitest + React Testing Library component tests
    └── e2e/                        # Playwright browser flow & accessibility (axe) tests
```

## 4. Critical Frontend UX Safeguards

1. **Prominent Identity Selector:** Inside both `PostComposer` and `CommentComposer`, the active identity mode is rendered as a high-contrast pill directly adjacent to the "Publish" button:
   * **Pseudonymous:** Blue badge — `Posting as @handle`
   * **Anonymous:** Amber/Slate shield badge — `Posting as Anonymous Member (Your handle will not be shown)`
   * **Professional:** Emerald badge — `Posting with Professional Context (@handle • Role / Industry)`
2. **Sticky Anonymous OP Reply Lock:** When `post.is_viewer_author === true` and `post.identity_mode === 'anonymous'`, the `CommentComposer` initializes in locked `Anonymous OP` mode. Switching away requires clicking *"Unlock & reveal my handle"* inside a confirmation dialog.
3. **Accessibility & Multilingual Typography:** CSS font stacks explicitly include `'Inter', 'Noto Sans', 'Noto Sans Devanagari', 'Noto Sans Tamil', 'Noto Sans Malayalam', system-ui, sans-serif` with `line-height: 1.6` so Indic and non-Latin diacritics never clip vertically.
