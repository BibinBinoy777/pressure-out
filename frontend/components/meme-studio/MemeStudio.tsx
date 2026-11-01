"use client";

import React, { useState } from "react";
import type {
  CaptionSuggestionItem,
  IdentityMode,
  MemeAssetResponse,
  MemeJobResponse,
  MemeTemplateResponse,
} from "../../lib/api-client";
import { TemplateGallery } from "./TemplateGallery";
import { CaptionEditor } from "./CaptionEditor";
import { MemeCanvasPreview } from "./MemeCanvasPreview";
import { CaptionAssistant } from "./CaptionAssistant";
import { ImageGenerationPanel } from "./ImageGenerationPanel";
import { GenerationJobStatus } from "./GenerationJobStatus";
import { AlternativeTextEditor } from "./AlternativeTextEditor";
import { MemeDownloadButton } from "./MemeDownloadButton";
import { PublishMemeDialog } from "./PublishMemeDialog";
import { ErrorMessage } from "../ErrorMessage";

const INITIAL_TEMPLATES: MemeTemplateResponse[] = [
  {
    id: "tmpl-01-friday-deploy",
    slug: "friday-455pm-deploy",
    name: "Friday 4:55 PM Deploy",
    description:
      "Two-panel split contrasting calm weekend plans with a sudden production incident or last-minute manager request.",
    category: "engineering",
    width: 800,
    height: 800,
    aspect_ratio: "1:1",
    text_regions: [
      {
        id: "top",
        label: "Top Caption (Expectation / Calm)",
        x: 40,
        y: 36,
        width: 720,
        height: 180,
        align: "center",
        max_chars: 160,
        default_font_size: 36,
        min_font_size: 18,
      },
      {
        id: "bottom",
        label: "Bottom Caption (Reality / Chaos)",
        x: 40,
        y: 584,
        width: 720,
        height: 180,
        align: "center",
        max_chars: 160,
        default_font_size: 36,
        min_font_size: 18,
      },
    ],
    default_typography: { text_color: "#FFFFFF", stroke_color: "#0F172A", stroke_width: 4 },
    default_alt_text:
      "Two-panel workplace meme contrasting peaceful weekend plans with a Friday 4:55 PM surprise task.",
    category_tags: ["engineering", "on-call", "friday", "deadlines"],
    license_info: "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    preview_url: "/api/v1/memes/templates/friday-455pm-deploy/preview",
  },
  {
    id: "tmpl-02-could-have-been-email",
    slug: "could-have-been-an-email",
    name: "This Meeting Could Have Been an Email",
    description:
      "Classic top-and-bottom banner meme illustrating an exhausting 60-minute calendar invite for a 2-sentence status update.",
    category: "meetings",
    width: 800,
    height: 800,
    aspect_ratio: "1:1",
    text_regions: [
      {
        id: "top",
        label: "Top Setup",
        x: 40,
        y: 32,
        width: 720,
        height: 160,
        align: "center",
        max_chars: 150,
        default_font_size: 36,
        min_font_size: 18,
      },
      {
        id: "bottom",
        label: "Bottom Punchline",
        x: 40,
        y: 608,
        width: 720,
        height: 160,
        align: "center",
        max_chars: 150,
        default_font_size: 36,
        min_font_size: 18,
      },
    ],
    default_typography: { text_color: "#FFFFFF", stroke_color: "#0F172A", stroke_width: 4 },
    default_alt_text: "Workplace meeting meme showing a calendar block that could have been a short email.",
    category_tags: ["meetings", "calendar", "corporate-life"],
    license_info: "CC0-1.0 / Pressure Out Original Programmatic Artwork",
    preview_url: "/api/v1/memes/templates/could-have-been-an-email/preview",
  },
];

export function MemeStudio() {
  const [templates] = useState<MemeTemplateResponse[]>(INITIAL_TEMPLATES);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [selectedTemplate, setSelectedTemplate] = useState<MemeTemplateResponse>(
    INITIAL_TEMPLATES[0]
  );
  const [captionValues, setCaptionValues] = useState<Record<string, string>>({
    top: "Expectation: Quiet Friday afternoon focus block",
    bottom: "Reality: 'Quick 5-minute sync' invite at 4:55 PM",
  });
  const [language, setLanguage] = useState<string>("en");
  const [outputFormat, setOutputFormat] = useState<"PNG" | "WEBP">("PNG");
  const [altText, setAltText] = useState<string>("");

  const [scenarioPrompt, setScenarioPrompt] = useState<string>(
    "My manager scheduled a 4:55 PM Friday sync with no agenda"
  );
  const [tone, setTone] = useState<string>("sarcastic");
  const [suggestions, setSuggestions] = useState<CaptionSuggestionItem[]>([]);
  const [captionQuotaRemaining] = useState<number | null>(15);
  const [imageQuotaRemaining] = useState<number | null>(5);

  const [renderedAsset, setRenderedAsset] = useState<MemeAssetResponse | null>(null);
  const [activeJob, setActiveJob] = useState<MemeJobResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [communitySlug, setCommunitySlug] = useState<string>("corporate-memes");
  const [identityMode, setIdentityMode] = useState<IdentityMode>("pseudonymous");
  const [postTitle, setPostTitle] = useState<string>(
    "When the Friday 4:55 PM calendar invite drops with zero context"
  );
  const [postBody, setPostBody] = useState<string>(
    "Created in the Pressure Out AI Meme Studio."
  );
  const [tagsInput, setTagsInput] = useState<string>("friday-deploy, meetings");
  const [publishedPostId] = useState<string | null>(null);

  const handleApplySuggestion = (item: CaptionSuggestionItem) => {
    setCaptionValues({
      top: item.top_text,
      bottom: item.bottom_text,
    });
  };

  return (
    <div className="space-y-8">
      {errorMsg ? (
        <ErrorMessage
          title="AI Meme Studio Notice"
          message={errorMsg}
          onRetry={() => setErrorMsg(null)}
        />
      ) : null}

      <TemplateGallery
        templates={templates}
        selectedTemplateSlug={selectedTemplate.slug}
        selectedCategory={selectedCategory}
        onCategoryChange={setSelectedCategory}
        onSelectTemplate={(t) => setSelectedTemplate(t)}
      />

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-7">
          <CaptionAssistant
            prompt={scenarioPrompt}
            tone={tone}
            suggestions={suggestions}
            quotaRemaining={captionQuotaRemaining}
            dailyLimit={15}
            isMockProvider={true}
            aiEnabled={true}
            onPromptChange={setScenarioPrompt}
            onToneChange={setTone}
            onGenerateSuggestions={() => {
              setSuggestions([
                {
                  top_text: `When ${scenarioPrompt.slice(0, 60)}`,
                  bottom_text: "Directly into the weekend backlog abyss",
                  tone,
                  language,
                },
              ]);
            }}
            onApplySuggestion={handleApplySuggestion}
          />

          <CaptionEditor
            regions={selectedTemplate.text_regions}
            captionValues={captionValues}
            language={language}
            outputFormat={outputFormat}
            onCaptionChange={(regionId, txt) =>
              setCaptionValues((prev) => ({ ...prev, [regionId]: txt }))
            }
            onLanguageChange={setLanguage}
            onOutputFormatChange={setOutputFormat}
            onRenderMeme={() => {
              setRenderedAsset({
                id: "asset-preview-local-01",
                source_type: "template_render",
                template_id: selectedTemplate.id,
                mime_type: outputFormat === "WEBP" ? "image/webp" : "image/png",
                file_size_bytes: 28400,
                sha256_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                width: selectedTemplate.width,
                height: selectedTemplate.height,
                captions: [
                  { region_id: "top", text: captionValues["top"] || "" },
                  { region_id: "bottom", text: captionValues["bottom"] || "" },
                ],
                caption_language: language,
                alt_text:
                  altText ||
                  `${selectedTemplate.name}: ${captionValues["top"] || ""} / ${captionValues["bottom"] || ""}`,
                safety_status: "approved",
                is_published: false,
                download_url: `/api/v1/memes/templates/${selectedTemplate.slug}/preview`,
                created_at: new Date().toISOString(),
              });
            }}
          />

          <ImageGenerationPanel
            prompt={scenarioPrompt}
            styleTone={tone}
            aiImageEnabled={true}
            hasActiveJob={
              activeJob !== null &&
              (activeJob.status === "queued" ||
                activeJob.status === "generating" ||
                activeJob.status === "validating")
            }
            quotaRemaining={imageQuotaRemaining}
            dailyLimit={5}
            onStartJob={() => {
              setActiveJob({
                id: "job-preview-0001",
                job_type: "ai_image",
                status: "queued",
                prompt: scenarioPrompt,
                prompt_language: language,
                style_tone: tone,
                attempt_count: 0,
                is_mock_provider: true,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              });
            }}
          />

          <GenerationJobStatus
            job={activeJob}
            onCancelJob={() =>
              setActiveJob((prev) =>
                prev ? { ...prev, status: "cancelled" } : null
              )
            }
            onRetryJob={() =>
              setActiveJob((prev) =>
                prev ? { ...prev, status: "queued", attempt_count: prev.attempt_count + 1 } : null
              )
            }
          />
        </div>

        <div className="space-y-6 lg:col-span-5">
          <MemeCanvasPreview
            template={selectedTemplate}
            captionValues={captionValues}
            renderedAsset={renderedAsset}
          />

          <AlternativeTextEditor altText={altText} onChange={setAltText} />

          <div className="flex flex-wrap items-center gap-3">
            <MemeDownloadButton asset={renderedAsset} />
          </div>
        </div>
      </div>

      <PublishMemeDialog
        asset={renderedAsset}
        communitySlug={communitySlug}
        identityMode={identityMode}
        title={postTitle}
        body={postBody}
        tagsInput={tagsInput}
        publishedPostId={publishedPostId}
        onCommunityChange={setCommunitySlug}
        onIdentityModeChange={setIdentityMode}
        onTitleChange={setPostTitle}
        onBodyChange={setPostBody}
        onTagsChange={setTagsInput}
        onPublish={() => {}}
      />
    </div>
  );
}
