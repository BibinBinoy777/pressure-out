"""Unicode normalization and text-preservation utilities.

Implements NFC (Canonical Decomposition, followed by Canonical Composition)
normalization as specified in Phase 1 `MULTILINGUAL_SUPPORT.md` and Phase 2 Section 9.
Preserves native scripts (Malayalam, Hindi, Tamil, English, Emoji, and mixed-language
text) without transliteration or lossy ASCII stripping.
"""
from __future__ import annotations

import unicodedata
from typing import Optional


def normalize_unicode_nfc(text: str) -> str:
    """Normalize a Unicode string to NFC form while preserving all native characters.

    Args:
        text: Input string in any script (English, Malayalam, Hindi, Tamil, Emoji, etc.).

    Returns:
        NFC-normalized Unicode string with null bytes stripped for PostgreSQL UTF-8 safety.

    Raises:
        TypeError: If `text` is not a `str`.
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str for Unicode normalization, got {type(text).__name__}")
    # Strip NUL (chr(0)) characters which PostgreSQL UTF-8 text columns reject,
    # while preserving all printable Unicode code points, combining marks, ZWJ/ZWNJ, and emojis.
    cleaned = text.replace(chr(0), "")
    return unicodedata.normalize("NFC", cleaned)


def normalize_optional_unicode_nfc(text: Optional[str]) -> Optional[str]:
    """Normalize an optional string to NFC if present."""
    if text is None:
        return None
    return normalize_unicode_nfc(text)
