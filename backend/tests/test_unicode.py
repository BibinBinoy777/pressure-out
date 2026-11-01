"""Unicode NFC normalization and multilingual text-integrity tests.

Verifies lossless preservation of:
1. English text
2. Malayalam
3. Hindi
4. Tamil
5. Emoji
6. Mixed-language / code-switched text
"""
from __future__ import annotations

import json
import unittest

from app.core.unicode import normalize_optional_unicode_nfc, normalize_unicode_nfc


class UnicodePreservationTests(unittest.TestCase):
    """Validates NFC normalization and end-to-end UTF-8 text integrity."""

    def test_preserves_english_malayalam_hindi_tamil_emoji_and_mixed_text(self) -> None:
        samples = {
            "english": "Work is serious. Talking about it doesn't have to be.",
            "malayalam": "ജോലിസ്ഥലത്തെ സമ്മർദ്ദവും തമാശകളും പങ്കുവെക്കാം — വെള്ളിയാഴ്ച മീറ്റിംഗ്!",
            "hindi": "ऑफिस की राजनीति और शुक्रवार शाम 4:55 की मीटिंग का दर्द",
            "tamil": "அலுவலக நகைச்சுவைகள் மற்றும் பணி அனுபவங்களை பகிர்ந்து கொள்ளுங்கள்",
            "emoji": "Deploy on Friday at 5 PM?! 😭🔥💻🫠🚀",
            "mixed_language": (
                "Bro ఈ appraisal cycle और നമ്മുടെ team lead — "
                "அதிக pressure! Need coffee ☕😅 #CorporateChaos"
            ),
        }

        for label, original in samples.items():
            with self.subTest(language=label):
                normalized = normalize_unicode_nfc(original)
                self.assertEqual(normalized, original)
                dumped = json.dumps({"text": normalized}, ensure_ascii=False)
                restored = json.loads(dumped)["text"]
                self.assertEqual(restored, original)

    def test_normalizes_decomposed_nfd_to_canonical_nfc(self) -> None:
        decomposed = "Cafe\u0301 resume\u0301"
        composed = "Caf\u00e9 resum\u00e9"
        self.assertNotEqual(decomposed, composed)
        self.assertEqual(normalize_unicode_nfc(decomposed), composed)

    def test_strips_null_bytes_while_keeping_zero_width_joiners(self) -> None:
        text_with_zwj_and_null = "യ\u200d" + chr(0) + "👨‍💻"
        cleaned = normalize_unicode_nfc(text_with_zwj_and_null)
        self.assertNotIn(chr(0), cleaned)
        self.assertIn("\u200d", cleaned)
        self.assertIn("👨‍💻", cleaned)

    def test_optional_helper_handles_none_and_rejects_non_string(self) -> None:
        self.assertIsNone(normalize_optional_unicode_nfc(None))
        with self.assertRaises(TypeError):
            normalize_unicode_nfc(12345)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
