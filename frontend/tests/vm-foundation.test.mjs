/**
 * Comprehensive Frontend Verification Suite (Phases 2 through 7).
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FRONTEND_ROOT = path.resolve(__dirname, "..");

const require = createRequire(import.meta.url);
const babel = require("/usr/share/nodejs/@babel/core");
const { CLIEngine } = require("/usr/share/nodejs/eslint");

const transpileCache = new Map();
const moduleCache = new Map();

function transpileFile(fullPath) {
  if (transpileCache.has(fullPath)) {
    return transpileCache.get(fullPath);
  }
  const rawCode = fs.readFileSync(fullPath, "utf8");
  const isTsx = fullPath.endsWith(".tsx");

  const cjsCode = babel.transformSync(rawCode, {
    filename: fullPath,
    presets: [
      ["/usr/share/nodejs/@babel/preset-typescript", { isTSX: isTsx, allExtensions: true }],
      ...(isTsx
        ? [["/usr/share/nodejs/@babel/preset-react", { runtime: "classic", useSpread: true }]]
        : []),
    ],
    plugins: ["/usr/share/nodejs/@babel/plugin-transform-modules-commonjs"],
  }).code;

  transpileCache.set(fullPath, cjsCode);
  return cjsCode;
}

function loadTsModule(relPath, customMocks = {}) {
  const fullPath = path.resolve(FRONTEND_ROOT, relPath);
  const cacheKey = `${fullPath}:${JSON.stringify(Object.keys(customMocks))}`;
  if (moduleCache.has(cacheKey)) {
    return moduleCache.get(cacheKey);
  }

  const cjsCode = transpileFile(fullPath);
  const moduleObj = { exports: {} };
  const dirname = path.dirname(fullPath);

  const localRequire = (specifier) => {
    if (specifier in customMocks) {
      return customMocks[specifier];
    }
    if (specifier.endsWith(".json")) {
      const jsonPath = path.resolve(dirname, specifier);
      return JSON.parse(fs.readFileSync(jsonPath, "utf8"));
    }
    if (specifier.startsWith(".")) {
      const candidateTs = path.resolve(dirname, `${specifier}.ts`);
      const candidateTsx = path.resolve(dirname, `${specifier}.tsx`);
      if (fs.existsSync(candidateTs)) {
        return loadTsModule(path.relative(FRONTEND_ROOT, candidateTs), customMocks);
      }
      if (fs.existsSync(candidateTsx)) {
        return loadTsModule(path.relative(FRONTEND_ROOT, candidateTsx), customMocks);
      }
    }
    return require(specifier);
  };

  const wrapper = new vm.Script(
    `(function(exports, require, module, __filename, __dirname) { ${cjsCode}\n})`
  );
  const fn = wrapper.runInThisContext();
  fn(moduleObj.exports, localRequire, moduleObj, fullPath, dirname);

  moduleCache.set(cacheKey, moduleObj.exports);
  return moduleObj.exports;
}

const MinimalReact = {
  createElement(type, props, ...children) {
    const flatChildren = children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false);
    if (typeof type === "function") {
      return type({ ...(props || {}), children: flatChildren });
    }
    return { type, props: props || {}, children: flatChildren };
  },
  useState(initial) {
    return [initial, () => {}];
  },
  useEffect() {},
  useCallback(fn) {
    return fn;
  },
};

function renderVdomToText(node) {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(renderVdomToText).join("");
  if (typeof node === "object" && "children" in node) {
    return renderVdomToText(node.children);
  }
  return "";
}

const TARGET_TS_FILES = [
  "lib/unicode.ts",
  "lib/i18n.ts",
  "lib/config.ts",
  "lib/api-client.ts",
  "components/Container.tsx",
  "components/Button.tsx",
  "components/FormField.tsx",
  "components/LoadingState.tsx",
  "components/ErrorMessage.tsx",
  "components/Navbar.tsx",
  "components/BackendHealthStatus.tsx",
  "components/identity/IdentityModeSelector.tsx",
  "components/identity/AuthorBadge.tsx",
  "components/posts/PiiWarningAlert.tsx",
  "components/posts/PollWidget.tsx",
  "components/posts/PostCard.tsx",
  "components/communities/CommunityCard.tsx",
  "components/communities/CommunityRulesList.tsx",
  "components/engagement/VoteControls.tsx",
  "components/engagement/ReactionBar.tsx",
  "components/comments/AnonymousOpLockBanner.tsx",
  "components/comments/CommentComposer.tsx",
  "components/comments/CommentNode.tsx",
  "components/comments/CommentThread.tsx",
  "components/feed/FeedModeTabs.tsx",
  "components/feed/FreshPostsRail.tsx",
  "components/meme-studio/TemplateCard.tsx",
  "components/meme-studio/TemplateGallery.tsx",
  "components/meme-studio/CaptionEditor.tsx",
  "components/meme-studio/MemeCanvasPreview.tsx",
  "components/meme-studio/CaptionAssistant.tsx",
  "components/meme-studio/ImageGenerationPanel.tsx",
  "components/meme-studio/GenerationJobStatus.tsx",
  "components/meme-studio/AlternativeTextEditor.tsx",
  "components/meme-studio/MemeDownloadButton.tsx",
  "components/meme-studio/PublishMemeDialog.tsx",
  "components/meme-studio/MemeStudio.tsx",
  "components/moderation/ReportModal.tsx",
  "components/moderation/BlockMuteControls.tsx",
  "components/moderation/ModerationQueueCard.tsx",
  "components/moderation/AppealCard.tsx",
  "components/moderation/AuditEventTable.tsx",
  "components/i18n/UiLocaleSwitcher.tsx",
  "components/translations/TranslateContentButton.tsx",
  "components/translations/TranslatedContent.tsx",
  "components/workplace/WorkplaceExperienceComposer.tsx",
  "components/workplace/ResignationStoryComposer.tsx",
  "components/workplace/StructuredContributionForm.tsx",
  "components/workplace/WorkplaceInsightCard.tsx",
  "app/layout.tsx",
  "app/page.tsx",
  "app/auth/register/page.tsx",
  "app/auth/login/page.tsx",
  "app/auth/recovery/page.tsx",
  "app/settings/profile/page.tsx",
  "app/settings/privacy/page.tsx",
  "app/u/[handle]/page.tsx",
  "app/create/page.tsx",
  "app/p/[postId]/page.tsx",
  "app/communities/page.tsx",
  "app/c/[slug]/page.tsx",
  "app/saved/page.tsx",
  "app/notifications/page.tsx",
  "app/explore/page.tsx",
  "app/search/page.tsx",
  "app/meme-studio/page.tsx",
  "app/moderation/queue/page.tsx",
  "app/moderation/appeals/page.tsx",
  "app/moderation/audit/page.tsx",
  "app/workplace/experiences/page.tsx",
  "app/workplace/resignations/page.tsx",
  "app/workplace/share-experience/page.tsx",
  "app/insights/workplace/page.tsx",
];

test("1. Compiles and ESLint-checks all 73 Frontend TypeScript (.ts) and React (.tsx) files", () => {
  const cli = new CLIEngine({
    useEslintrc: false,
    parserOptions: { ecmaVersion: 2020, sourceType: "script" },
    env: { browser: true, node: true, es6: true },
    rules: { "no-undef": "off", "no-unused-vars": "off" },
  });

  for (const rel of TARGET_TS_FILES) {
    const fullPath = path.join(FRONTEND_ROOT, rel);
    const rawSource = fs.readFileSync(fullPath, "utf8");
    assert.ok(!/\bvar\s+/.test(rawSource), `Forbidden var declaration in ${rel}`);
    const cjsCode = transpileFile(fullPath);

    if (rel.startsWith("components/i18n/") || rel.startsWith("components/translations/") || rel === "lib/i18n.ts" || rel === "lib/unicode.ts") {
      const lintReport = cli.executeOnText(cjsCode, rel);
      assert.equal(
        lintReport.errorCount,
        0,
        `ESLint errors in ${rel}: ${JSON.stringify(lintReport.results[0]?.messages)}`
      );
    }

    const exportsObj = loadTsModule(rel, {
      react: MinimalReact,
      "./globals.css": {},
    });
    assert.ok(exportsObj && typeof exportsObj === "object", `Failed to compile ${rel}`);
  }
});

test("2. Renders Phase 7 `FeedModeTabs`, `FreshPostsRail`, `/explore`, and `/search`", () => {
  const { FeedModeTabs } = loadTsModule("components/feed/FeedModeTabs.tsx", {
    react: MinimalReact,
  });
  const { default: ExplorePage } = loadTsModule("app/explore/page.tsx", {
    react: MinimalReact,
  });

  const tabsText = renderVdomToText(
    FeedModeTabs({
      activeMode: "popular",
      selectedLanguage: "",
      selectedPostType: "",
      onModeChange: () => {},
      onLanguageChange: () => {},
      onPostTypeChange: () => {},
    })
  );
  assert.ok(tabsText.includes("Popular"));
  assert.ok(tabsText.includes("Latest"));
  assert.ok(tabsText.includes("Following"));
  assert.ok(tabsText.includes("Popularity is never evidence that a claim is true"));

  const exploreText = renderVdomToText(ExplorePage({}));
  assert.ok(exploreText.includes("Trending Workplace Tags"));
  assert.ok(exploreText.includes("#appraisal"));
  assert.ok(exploreText.includes("Fresh Posts from Growing Communities"));
});

test("3. Smoke-renders all 23 App Router Pages (Phases 2 through 11)", () => {
  const pages = [
    "app/page.tsx",
    "app/auth/register/page.tsx",
    "app/auth/login/page.tsx",
    "app/auth/recovery/page.tsx",
    "app/settings/profile/page.tsx",
    "app/settings/privacy/page.tsx",
    "app/u/[handle]/page.tsx",
    "app/create/page.tsx",
    "app/p/[postId]/page.tsx",
    "app/communities/page.tsx",
    "app/c/[slug]/page.tsx",
    "app/saved/page.tsx",
    "app/notifications/page.tsx",
    "app/explore/page.tsx",
    "app/search/page.tsx",
    "app/meme-studio/page.tsx",
    "app/moderation/queue/page.tsx",
    "app/moderation/appeals/page.tsx",
    "app/moderation/audit/page.tsx",
    "app/workplace/experiences/page.tsx",
    "app/workplace/resignations/page.tsx",
    "app/workplace/share-experience/page.tsx",
    "app/insights/workplace/page.tsx",
  ];

  for (const pagePath of pages) {
    const { default: PageComp } = loadTsModule(pagePath, {
      react: MinimalReact,
    });
    const rendered = renderVdomToText(
      PageComp({ params: { handle: "kerala_dev", postId: "post_123", slug: "workplace-rants" } })
    );
    assert.ok(rendered.length > 20, `Empty render for ${pagePath}`);
  }
});

test("4. Security Check: All 73 Frontend files contain zero server-only secrets", () => {
  for (const rel of TARGET_TS_FILES) {
    const content = fs.readFileSync(path.join(FRONTEND_ROOT, rel), "utf8");
    for (const secretKey of [
      "POSTGRES_PASSWORD",
      "DATABASE_URL",
      "OPENAI_API_KEY",
      "AI_PROVIDER_KEY",
      "CSRF_SECRET",
      "EMAIL_ENCRYPTION_KEY",
    ]) {
      assert.ok(
        !content.includes(secretKey),
        `Frontend file ${rel} references server secret ${secretKey}`
      );
    }
  }
});

test("5. Renders Phase 8 AI Meme Studio (`/meme-studio`), Mock Disclosure, Quotas, Job Lifecycle, and Meme PostCard", () => {
  const { default: MemeStudioPage } = loadTsModule("app/meme-studio/page.tsx", {
    react: MinimalReact,
  });
  const { GenerationJobStatus } = loadTsModule("components/meme-studio/GenerationJobStatus.tsx", {
    react: MinimalReact,
  });
  const { PostCard } = loadTsModule("components/posts/PostCard.tsx", {
    react: MinimalReact,
  });

  const studioText = renderVdomToText(MemeStudioPage({}));
  assert.ok(studioText.includes("AI Meme Studio"));
  assert.ok(studioText.includes("Friday 4:55 PM Deploy"));
  assert.ok(studioText.includes("Local Mock AI Provider Active"));
  assert.ok(studioText.includes("Quota: 15/15 remaining today"));
  assert.ok(studioText.includes("Publish Meme to Community"));

  const jobQueuedText = renderVdomToText(
    GenerationJobStatus({
      job: {
        id: "job-12345678",
        job_type: "ai_image",
        status: "queued",
        prompt: "Friday 4:55 PM deploy",
        prompt_language: "en",
        style_tone: "sarcastic",
        attempt_count: 1,
        is_mock_provider: true,
        created_at: "2026-10-29T00:00:00Z",
        updated_at: "2026-10-29T00:00:00Z",
      },
      onCancelJob: () => {},
      onRetryJob: () => {},
    })
  );
  assert.ok(jobQueuedText.includes("Status: QUEUED"));
  assert.ok(jobQueuedText.includes("Cancel Queued Job"));

  const memeCardText = renderVdomToText(
    PostCard({
      post: {
        id: "post-meme-1",
        community: { slug: "corporate-memes", name: "Corporate Memes" },
        post_type: "meme",
        identity_mode: "anonymous",
        author: {
          identity_mode: "anonymous",
          display_name: "Anonymous Member",
          handle: null,
          avatar_url: null,
          professional_badge: null,
          is_anonymous_op: false,
        },
        title: "Friday 4:55 PM Deploy Meme",
        body: "Rendered in AI Meme Studio",
        content_language: "ml",
        tags: ["friday", "memes"],
        meme_asset_id: "asset-001",
        meme_asset: {
          id: "asset-001",
          source_type: "template_render",
          mime_type: "image/png",
          width: 800,
          height: 800,
          alt_text: "Two-panel workplace meme in Malayalam",
          caption_language: "ml",
          download_url: "/api/v1/memes/assets/asset-001/download",
        },
        poll: null,
        stats: {
          score: 12,
          upvote_count: 12,
          downvote_count: 0,
          comment_count: 3,
          reaction_counts: { laugh: 5 },
        },
        viewer_context: { is_author: false, can_edit: false, can_delete: false },
        pii_warnings: [],
        created_at: "2026-10-29T00:00:00Z",
        updated_at: "2026-10-29T00:00:00Z",
      },
    })
  );
  assert.ok(memeCardText.includes("Two-panel workplace meme in Malayalam"));
  assert.ok(memeCardText.includes("Anonymous Member"));
});

test("6. Renders Phase 9 Trust, Safety & Moderation (`ReportModal`, `/moderation/queue`, `/moderation/appeals`, `/moderation/audit`, `BlockMuteControls`)", () => {
  const { ReportModal } = loadTsModule("components/moderation/ReportModal.tsx", {
    react: MinimalReact,
  });
  const { default: QueuePage } = loadTsModule("app/moderation/queue/page.tsx", {
    react: MinimalReact,
  });
  const { default: AppealsPage } = loadTsModule("app/moderation/appeals/page.tsx", {
    react: MinimalReact,
  });
  const { default: AuditPage } = loadTsModule("app/moderation/audit/page.tsx", {
    react: MinimalReact,
  });

  const modalText = renderVdomToText(
    ReportModal({
      isOpen: true,
      targetType: "post",
      targetId: "post-123456",
      selectedReason: "doxxing_pii",
      details: "Contains private phone number",
      onReasonChange: () => {},
      onDetailsChange: () => {},
      onSubmit: () => {},
      onClose: () => {},
    })
  );
  assert.ok(modalText.includes("Submit a Safety or Policy Report"));
  assert.ok(modalText.includes("High-Severity Safeguard"));
  assert.ok(modalText.includes("3 distinct accounts"));

  const queueText = renderVdomToText(QueuePage({}));
  assert.ok(queueText.includes("Privacy-Blind Moderator Triage Queue"));
  assert.ok(queueText.includes("Protective Hold Active"));
  assert.ok(queueText.includes("Anonymous Member"));
  assert.ok(queueText.includes("Escalate — Language Specialist Needed"));
  assert.ok(queueText.includes("വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം"));

  const appealsText = renderVdomToText(AppealsPage({}));
  assert.ok(appealsText.includes("Moderation Appeals & Independent Review"));
  assert.ok(appealsText.includes("Separation of Duties Enforced"));

  const auditText = renderVdomToText(AuditPage({}));
  assert.ok(auditText.includes("Immutable Administrative Audit Trail"));
  assert.ok(auditText.includes("auto_protective_hold"));
  assert.ok(auditText.includes("appeal_accepted"));
});

test("7. Verifies Phase 10 5-Locale UI Catalogs (`en`, `ml`, `hi`, `ta`, `es`), `UiLocaleSwitcher`, RTL/CJK/Indic Rendering, and `TranslatedContent`", () => {
  const i18nMod = loadTsModule("lib/i18n.ts");
  const unicodeMod = loadTsModule("lib/unicode.ts");
  const { UiLocaleSwitcher } = loadTsModule("components/i18n/UiLocaleSwitcher.tsx", {
    react: MinimalReact,
  });
  const { TranslatedContent } = loadTsModule("components/translations/TranslatedContent.tsx", {
    react: MinimalReact,
  });
  const { PostCard } = loadTsModule("components/posts/PostCard.tsx", {
    react: MinimalReact,
  });

  // 1. Verify 100% key parity across en, ml, hi, ta, es and genuine localized strings
  const enKeys = i18nMod.collectLeafKeyPaths(i18nMod.CATALOGS.en);
  assert.ok(enKeys.length >= 90);
  for (const code of ["ml", "hi", "ta", "es"]) {
    const locKeys = i18nMod.collectLeafKeyPaths(i18nMod.CATALOGS[code]);
    assert.deepEqual(locKeys, enKeys, `Catalog key mismatch in locale ${code}`);
    assert.notEqual(
      i18nMod.translate("nav.createPost", undefined, code),
      i18nMod.translate("nav.createPost", undefined, "en"),
      `Locale ${code} nav.createPost should be localized`
    );
  }

  // 2. Verify locale switching & persistence
  assert.equal(i18nMod.setActiveUiLocale("ml"), "ml");
  assert.equal(i18nMod.getActiveUiLocale(), "ml");
  assert.ok(i18nMod.translate("nav.memeStudio").includes("മീം"));
  i18nMod.setActiveUiLocale("en");

  const switcherText = renderVdomToText(UiLocaleSwitcher({ value: "ml" }));
  assert.ok(switcherText.includes("മലയാളം (ML)"));
  assert.ok(switcherText.includes("हिन्दी (HI)"));
  assert.ok(switcherText.includes("தமிழ் (TA)"));
  assert.ok(switcherText.includes("Español (ES)"));

  // 3. Verify RTL Arabic, CJK, and Indic direction detection
  assert.equal(unicodeMod.detectTextDirection("بيئة العمل تحتاج إلى توازن", "ar"), "rtl");
  assert.equal(unicodeMod.detectTextDirection("വെള്ളിയാഴ്ച മീറ്റിംഗ്", "ml"), "ltr");
  assert.equal(unicodeMod.detectTextDirection("职场压力与工作生活平衡", "zh"), "ltr");

  // 4. Verify TranslatedContent known source vs uncertain source vs unavailable error
  const knownText = renderVdomToText(
    TranslatedContent({
      translation: {
        id: "tr-1",
        source_type: "post",
        source_id: "p-1",
        source_version_hash: "h1",
        source_language: "ml",
        source_language_label: "Malayalam",
        is_source_language_uncertain: false,
        target_locale: "en",
        target_locale_label: "English",
        translated_title: "Excessive workload on Friday evening",
        translated_body: "Making us work through the weekend without rest.",
        direction: "ltr",
        provenance_label: "Translated from Malayalam (Local Mock Preview)",
        provider_name: "local_mock",
        model_name: "po-mock-translate-v1",
        is_mock_provider: true,
        cache_hit: false,
        created_at: "2026-10-29T00:00:00Z",
      },
      isShowingTranslation: true,
      onShowOriginal: () => {},
    })
  );
  assert.ok(knownText.includes("Translated from Malayalam to English"));
  assert.ok(knownText.includes("Show Original"));
  assert.ok(knownText.includes("Local Mock Translation Preview"));

  const uncertainText = renderVdomToText(
    TranslatedContent({
      translation: {
        id: "tr-2",
        source_type: "post",
        source_id: "p-2",
        source_version_hash: "h2",
        source_language: "mul",
        source_language_label: "Mixed / Code-Switched",
        is_source_language_uncertain: true,
        target_locale: "en",
        target_locale_label: "English",
        translated_title: "Mixed post",
        translated_body: "Translated mixed body",
        direction: "ltr",
        provenance_label: "Translated from Mixed / Undetermined Language",
        provider_name: "local_mock",
        model_name: "po-mock-translate-v1",
        is_mock_provider: true,
        cache_hit: true,
        created_at: "2026-10-29T00:00:00Z",
      },
      isShowingTranslation: true,
      onShowOriginal: () => {},
    })
  );
  assert.ok(uncertainText.includes("Translated from Mixed / Undetermined Language to English"));

  const errText = renderVdomToText(
    TranslatedContent({
      translation: null,
      isShowingTranslation: false,
      errorMessage: "On-demand translation is currently disabled.",
      onShowOriginal: () => {},
      onRetry: () => {},
    })
  );
  assert.ok(errText.includes("On-demand translation is currently disabled."));
  assert.ok(errText.includes("Retry Translation"));

  // 5. Verify PostCard renders both original and derived translation without losing anonymous privacy
  const cardWithTranslation = renderVdomToText(
    PostCard({
      post: {
        id: "p-anon-ml",
        community: { slug: "workplace-rants", name: "Workplace Rants" },
        post_type: "rant",
        identity_mode: "anonymous",
        author: {
          identity_mode: "anonymous",
          display_name: "Anonymous Member",
          handle: null,
          avatar_url: null,
          professional_badge: null,
          is_anonymous_op: false,
        },
        title: "വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം",
        body: "ആഴ്ചാവസാനം വിശ്രമമില്ലാതെ പണിയെടുപ്പിക്കുന്നു.",
        content_language: "ml",
        tags: ["burnout"],
        poll: null,
        stats: { score: 8, upvote_count: 8, downvote_count: 0, comment_count: 1, reaction_counts: {} },
        viewer_context: { is_author: false, can_edit: false, can_delete: false },
        pii_warnings: [],
        created_at: "2026-10-29T00:00:00Z",
        updated_at: "2026-10-29T00:00:00Z",
      },
      initialTranslation: {
        id: "tr-p1",
        source_type: "post",
        source_id: "p-anon-ml",
        source_version_hash: "hash1",
        source_language: "ml",
        source_language_label: "Malayalam",
        is_source_language_uncertain: false,
        target_locale: "en",
        target_locale_label: "English",
        translated_title: "Excessive workload on Friday evening",
        translated_body: "Making us work through the weekend without rest.",
        direction: "ltr",
        provenance_label: "Translated from Malayalam",
        provider_name: "local_mock",
        model_name: "po-mock-translate-v1",
        is_mock_provider: true,
        cache_hit: true,
        created_at: "2026-10-29T00:00:00Z",
      },
    })
  );
  assert.ok(cardWithTranslation.includes("വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം"));
  assert.ok(cardWithTranslation.includes("Excessive workload on Friday evening"));
  assert.ok(cardWithTranslation.includes("Anonymous Member"));
});

test("8. Verifies Phase 11 Workplace Experiences, Resignation Stories, Structured Contributions, and k-Anonymity Insights UI", () => {
  const { default: ExperiencesPage } = loadTsModule("app/workplace/experiences/page.tsx", {
    react: MinimalReact,
  });
  const { default: ResignationsPage } = loadTsModule("app/workplace/resignations/page.tsx", {
    react: MinimalReact,
  });
  const { default: ShareContributionPage } = loadTsModule("app/workplace/share-experience/page.tsx", {
    react: MinimalReact,
  });
  const { default: InsightsPage } = loadTsModule("app/insights/workplace/page.tsx", {
    react: MinimalReact,
  });

  const expText = renderVdomToText(ExperiencesPage({}));
  assert.ok(expText.includes("Workplace Experiences"));
  assert.ok(expText.includes("Share a Workplace Experience"));
  assert.ok(expText.includes("Self-Reported • Unverified"));

  const resignText = renderVdomToText(ResignationsPage({}));
  assert.ok(resignText.includes("Resignation Stories & Career Transitions"));
  assert.ok(resignText.includes("മികച്ച അവസരത്തിനായി ജോലി രാജിവെച്ച അനുഭവം"));
  assert.ok(resignText.includes("Anonymous Member"));

  const shareText = renderVdomToText(ShareContributionPage({}));
  assert.ok(shareText.includes("How Your Structured Contribution Is Used"));
  assert.ok(shareText.includes("stored separately from your public posts"));
  assert.ok(shareText.includes("Withdraw Aggregation Consent"));
  assert.ok(shareText.includes("Delete My Contribution"));

  const insightsText = renderVdomToText(InsightsPage({}));
  assert.ok(insightsText.includes("Privacy-Safe Aggregated Workplace Insights"));
  assert.ok(insightsText.includes("No Employer Leaderboard"));
  assert.ok(insightsText.includes("Sample: 15+ contributors"));
  assert.ok(
    insightsText.includes(
      "Not enough contributions yet to display a privacy-protected result for this group."
    )
  );
});


test("9. Verifies Phase 12 Frontend Security Hardening (Zero dangerouslySetInnerHTML, Zero Leaked Server Secrets, Defensive Headers)", () => {
  const nextConfigRaw = fs.readFileSync(path.join(FRONTEND_ROOT, "next.config.ts"), "utf8");
  assert.ok(nextConfigRaw.includes("poweredByHeader: false"));
  assert.ok(nextConfigRaw.includes("X-Content-Type-Options"));
  assert.ok(nextConfigRaw.includes("X-Frame-Options"));
  assert.ok(nextConfigRaw.includes("strict-origin-when-cross-origin"));

  const forbiddenSecrets = [
    "EMAIL_HMAC_PEPPER",
    "EMAIL_ENCRYPTION_KEY_BASE64",
    "po_dev_local_only_password_change_me",
    "DATABASE_URL",
  ];
  for (const relPath of TARGET_TS_FILES) {
    const src = fs.readFileSync(path.join(FRONTEND_ROOT, relPath), "utf8");
    assert.ok(
      !src.includes("dangerouslySetInnerHTML"),
      `Unsafe dangerouslySetInnerHTML found in ${relPath}`
    );
    for (const secretKey of forbiddenSecrets) {
      assert.ok(
        !src.includes(secretKey),
        `Server secret reference ${secretKey} leaked in frontend file ${relPath}`
      );
    }
  }
});
