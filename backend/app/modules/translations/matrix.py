"""Authoritative Language Capability Matrix and Script/Direction Detection for Phase 10."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.errors import AppError

SUPPORTED_UI_LOCALES: Tuple[str, ...] = ("en", "ml", "hi", "ta", "es")
SUPPORTED_TRANSLATION_TARGETS: Tuple[str, ...] = ("en", "ml", "hi", "ta", "es")
RTL_LANGUAGE_PREFIXES: Tuple[str, ...] = ("ar", "he", "fa", "ur")

LANGUAGE_DISPLAY_NAMES: Dict[str, Dict[str, str]] = {
    "en": {"native": "English", "english": "English"},
    "ml": {"native": "മലയാളം", "english": "Malayalam"},
    "hi": {"native": "हिन्दी", "english": "Hindi"},
    "ta": {"native": "தமிழ்", "english": "Tamil"},
    "es": {"native": "Español", "english": "Spanish"},
    "ar": {"native": "العربية", "english": "Arabic"},
    "zh": {"native": "中文", "english": "Chinese"},
    "ja": {"native": "日本語", "english": "Japanese"},
    "mul": {"native": "Mixed / Code-Switched", "english": "Mixed / Code-Switched"},
    "und": {"native": "Undetermined Language", "english": "Undetermined Language"},
}


@dataclass(frozen=True)
class LanguageCapabilityEntry:
    code: str
    native_name: str
    english_name: str
    direction: str  # "ltr" | "rtl"
    ui_locale_supported: bool
    content_posting_supported: bool
    on_demand_translation_target: bool
    meme_studio_font_shaping: str


LANGUAGE_CAPABILITY_MATRIX: List[LanguageCapabilityEntry] = [
    LanguageCapabilityEntry(
        code="en",
        native_name="English",
        english_name="English",
        direction="ltr",
        ui_locale_supported=True,
        content_posting_supported=True,
        on_demand_translation_target=True,
        meme_studio_font_shaping="NotoSans-Bold.ttf (HarfBuzz/Raqm)",
    ),
    LanguageCapabilityEntry(
        code="ml",
        native_name="മലയാളം",
        english_name="Malayalam",
        direction="ltr",
        ui_locale_supported=True,
        content_posting_supported=True,
        on_demand_translation_target=True,
        meme_studio_font_shaping="NotoSansMalayalam-Bold.ttf (HarfBuzz/Raqm)",
    ),
    LanguageCapabilityEntry(
        code="hi",
        native_name="हिन्दी",
        english_name="Hindi",
        direction="ltr",
        ui_locale_supported=True,
        content_posting_supported=True,
        on_demand_translation_target=True,
        meme_studio_font_shaping="NotoSansDevanagari-Bold.ttf (HarfBuzz/Raqm)",
    ),
    LanguageCapabilityEntry(
        code="ta",
        native_name="தமிழ்",
        english_name="Tamil",
        direction="ltr",
        ui_locale_supported=True,
        content_posting_supported=True,
        on_demand_translation_target=True,
        meme_studio_font_shaping="NotoSansTamil-Bold.ttf (HarfBuzz/Raqm)",
    ),
    LanguageCapabilityEntry(
        code="es",
        native_name="Español",
        english_name="Spanish",
        direction="ltr",
        ui_locale_supported=True,
        content_posting_supported=True,
        on_demand_translation_target=True,
        meme_studio_font_shaping="NotoSans-Bold.ttf (HarfBuzz/Raqm)",
    ),
    LanguageCapabilityEntry(
        code="ar",
        native_name="العربية",
        english_name="Arabic",
        direction="rtl",
        ui_locale_supported=False,
        content_posting_supported=True,
        on_demand_translation_target=False,
        meme_studio_font_shaping="Unicode RTL preserved in posts/comments",
    ),
    LanguageCapabilityEntry(
        code="mul",
        native_name="Mixed / Code-Switched",
        english_name="Mixed / Code-Switched",
        direction="ltr",
        ui_locale_supported=False,
        content_posting_supported=True,
        on_demand_translation_target=False,
        meme_studio_font_shaping="Script-detected Noto font fallback",
    ),
]


def validate_translation_target_locale(target_locale: str) -> str:
    cleaned = (target_locale or "").strip().lower().split("-")[0]
    if cleaned not in SUPPORTED_TRANSLATION_TARGETS:
        raise AppError(
            code="UNSUPPORTED_TRANSLATION_LANGUAGE",
            message=f"Target translation language '{target_locale}' is not supported. Supported target locales: {', '.join(SUPPORTED_TRANSLATION_TARGETS)}.",
            status_code=422,
        )
    return cleaned


def get_language_display_name(lang_tag: str) -> str:
    base = (lang_tag or "und").strip().lower().split("-")[0]
    entry = LANGUAGE_DISPLAY_NAMES.get(base)
    if entry:
        return entry["english"]
    return base.upper()


def detect_text_script_and_direction(
    text: str, declared_lang: Optional[str] = None
) -> Tuple[str, str, bool]:
    """Inspect Unicode code points to determine `(effective_source_lang, direction, is_uncertain)`.

    Honors honest uncertainty: if text mixes multiple scripts or is tagged `mul`/`und` without
    a single dominant script, marks `is_uncertain=True` rather than inventing false certainty.
    """
    counts: Dict[str, int] = {
        "ml": 0,
        "hi": 0,
        "ta": 0,
        "ar": 0,
        "zh": 0,
        "latin": 0,
    }
    for ch in text:
        cp = ord(ch)
        if 0x0D00 <= cp <= 0x0D7F:
            counts["ml"] += 1
        elif 0x0900 <= cp <= 0x097F:
            counts["hi"] += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            counts["ta"] += 1
        elif (0x0600 <= cp <= 0x06FF) or (0x0750 <= cp <= 0x077F) or (0x0590 <= cp <= 0x05FF):
            counts["ar"] += 1
        elif 0x4E00 <= cp <= 0x9FFF:
            counts["zh"] += 1
        elif (0x0041 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F):
            counts["latin"] += 1

    active_scripts = [k for k, v in counts.items() if v >= 2]
    decl = (declared_lang or "und").strip().lower().split("-")[0]

    direction = "rtl" if counts["ar"] > 0 or decl in RTL_LANGUAGE_PREFIXES else "ltr"

    if decl in {"mul", "und"}:
        if len(active_scripts) == 1 and active_scripts[0] in {"ml", "hi", "ta", "ar", "zh"}:
            return active_scripts[0], direction, True
        return decl, direction, True

    if len(active_scripts) > 1:
        # Mixed script detected
        return decl, direction, True

    return decl, direction, False
