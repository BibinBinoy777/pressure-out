"""Deterministic server-side TemplateRenderer for Phase 8 AI Meme Studio.

Separates pure layout calculation (`calculate_layout`) from pixel composition
(`render_meme`) so layout math and image output can be tested independently.

Supports:
- Multi-region text boxes (top, bottom, custom regions)
- Automatic word wrapping & dynamic font-size fitting
- Multilingual Unicode text shaping via Pillow + HarfBuzz (`raqm`) and Noto fonts
  for Latin (`en`), Malayalam (`ml`), Devanagari/Hindi (`hi`), Tamil (`ta`), and mixed text
- Configurable text color, outline stroke, alignment, and aspect ratio crop/fit
- Deterministic PNG and WebP output
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.core.errors import AppError
from app.core.unicode import normalize_unicode_nfc

FONT_PATHS_BY_SCRIPT: dict[str, str] = {
    "malayalam": "/usr/share/fonts/truetype/noto/NotoSansMalayalam-Bold.ttf",
    "devanagari": "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "tamil": "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "latin": "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "fallback": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}

TEMPLATE_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    "friday-455pm-deploy": ((15, 23, 42), (30, 58, 138), (249, 115, 22)),
    "could-have-been-an-email": ((17, 24, 39), (49, 46, 129), (56, 189, 248)),
    "scope-creep-exit-ramp": ((20, 83, 45), (15, 23, 42), (250, 204, 21)),
    "record-profits-pizza-party": ((67, 20, 7), (124, 45, 18), (251, 146, 60)),
    "entry-level-ten-years-experience": ((30, 27, 75), (59, 7, 100), (192, 132, 252)),
    "hi-with-no-context": ((8, 47, 73), (12, 74, 110), (45, 212, 191)),
}


def detect_script_font_path(text: str, language_hint: str = "en") -> str:
    """Select the best installed TrueType font for the Unicode code points in `text`."""
    for ch in text:
        cp = ord(ch)
        if 0x0D00 <= cp <= 0x0D7F:
            if Path(FONT_PATHS_BY_SCRIPT["malayalam"]).is_file():
                return FONT_PATHS_BY_SCRIPT["malayalam"]
        elif 0x0900 <= cp <= 0x097F:
            if Path(FONT_PATHS_BY_SCRIPT["devanagari"]).is_file():
                return FONT_PATHS_BY_SCRIPT["devanagari"]
        elif 0x0B80 <= cp <= 0x0BFF:
            if Path(FONT_PATHS_BY_SCRIPT["tamil"]).is_file():
                return FONT_PATHS_BY_SCRIPT["tamil"]

    lang = (language_hint or "en").strip().lower()
    if lang.startswith("ml") and Path(FONT_PATHS_BY_SCRIPT["malayalam"]).is_file():
        return FONT_PATHS_BY_SCRIPT["malayalam"]
    if lang.startswith("hi") and Path(FONT_PATHS_BY_SCRIPT["devanagari"]).is_file():
        return FONT_PATHS_BY_SCRIPT["devanagari"]
    if lang.startswith("ta") and Path(FONT_PATHS_BY_SCRIPT["tamil"]).is_file():
        return FONT_PATHS_BY_SCRIPT["tamil"]

    if Path(FONT_PATHS_BY_SCRIPT["latin"]).is_file():
        return FONT_PATHS_BY_SCRIPT["latin"]
    return FONT_PATHS_BY_SCRIPT["fallback"]


@dataclass(frozen=True)
class TextRegionSpec:
    region_id: str
    label: str
    x: int
    y: int
    width: int
    height: int
    align: str = "center"
    max_chars: int = 160
    default_font_size: int = 36
    min_font_size: int = 16


@dataclass(frozen=True)
class RenderCaptionInput:
    region_id: str
    text: str
    align: Optional[str] = None
    font_size_override: Optional[int] = None
    text_color: Optional[str] = None
    stroke_color: Optional[str] = None


@dataclass(frozen=True)
class CalculatedRegionLayout:
    region_id: str
    lines: List[str]
    font_path: str
    font_size: int
    line_height: int
    box_x: int
    box_y: int
    box_width: int
    box_height: int
    align: str
    text_color: str
    stroke_color: str
    stroke_width: int


@dataclass(frozen=True)
class RenderedMemeOutput:
    image_bytes: bytes
    mime_type: str
    width: int
    height: int
    layouts: List[CalculatedRegionLayout]


class TemplateRenderer:
    """Server-side deterministic meme renderer using Pillow + HarfBuzz/Noto fonts."""

    def _load_font(self, font_path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            return ImageFont.load_default()

    def _measure_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        stroke_width: int = 3,
    ) -> Tuple[int, int]:
        if not text:
            return 0, 0
        try:
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
            return max(1, int(bbox[2] - bbox[0])), max(1, int(bbox[3] - bbox[1]))
        except Exception:
            return len(text) * 12, 24

    def _wrap_lines_for_width(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        stroke_width: int,
    ) -> List[str]:
        words = text.split()
        if not words:
            return []
        lines: List[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            w, _ = self._measure_text(draw, candidate, font, stroke_width)
            if w <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)

        # Handle any single extra-long token that still exceeds max_width
        final_lines: List[str] = []
        for line in lines:
            w, _ = self._measure_text(draw, line, font, stroke_width)
            if w <= max_width or len(line) <= 6:
                final_lines.append(line)
            else:
                chunk = ""
                for ch in line:
                    cand = chunk + ch
                    cw, _ = self._measure_text(draw, cand, font, stroke_width)
                    if cw <= max_width or not chunk:
                        chunk = cand
                    else:
                        final_lines.append(chunk)
                        chunk = ch
                if chunk:
                    final_lines.append(chunk)
        return final_lines

    def calculate_layout(
        self,
        *,
        regions: Sequence[TextRegionSpec],
        captions: Sequence[RenderCaptionInput],
        language_tag: str = "en",
        default_text_color: str = "#FFFFFF",
        default_stroke_color: str = "#0F172A",
        default_stroke_width: int = 4,
    ) -> List[CalculatedRegionLayout]:
        """Calculate deterministic word wrapping and font sizing for each region."""
        region_map: Dict[str, TextRegionSpec] = {r.region_id: r for r in regions}
        scratch_img = Image.new("RGB", (800, 800))
        draw = ImageDraw.Draw(scratch_img)

        calculated: List[CalculatedRegionLayout] = []
        for cap in captions:
            cleaned = normalize_unicode_nfc(cap.text).strip()
            if not cleaned:
                continue
            spec = region_map.get(cap.region_id)
            if spec is None:
                raise AppError(
                    code="INVALID_CAPTION_REGION",
                    message=f"Unknown template caption region '{cap.region_id}'.",
                    status_code=422,
                )
            if len(cleaned) > spec.max_chars:
                raise AppError(
                    code="CAPTION_TOO_LONG",
                    message=f"Caption for region '{spec.region_id}' exceeds maximum {spec.max_chars} characters.",
                    status_code=422,
                )

            font_path = detect_script_font_path(cleaned, language_tag)
            start_size = cap.font_size_override or spec.default_font_size
            min_size = spec.min_font_size
            stroke_width = default_stroke_width

            chosen_size = min_size
            chosen_lines: List[str] = [cleaned]
            chosen_line_height = min_size + 8

            for sz in range(start_size, min_size - 1, -2):
                font = self._load_font(font_path, sz)
                lines = self._wrap_lines_for_width(
                    draw, cleaned, font, max(60, spec.width - 16), stroke_width
                )
                _, sample_h = self._measure_text(draw, "Ag", font, stroke_width)
                line_height = max(sz + 6, sample_h + 6)
                total_h = line_height * len(lines)
                if total_h <= spec.height or sz == min_size:
                    chosen_size = sz
                    chosen_lines = lines
                    chosen_line_height = line_height
                    break

            align = (cap.align or spec.align or "center").strip().lower()
            if align not in {"left", "center", "right"}:
                align = "center"

            calculated.append(
                CalculatedRegionLayout(
                    region_id=spec.region_id,
                    lines=chosen_lines,
                    font_path=font_path,
                    font_size=chosen_size,
                    line_height=chosen_line_height,
                    box_x=spec.x,
                    box_y=spec.y,
                    box_width=spec.width,
                    box_height=spec.height,
                    align=align,
                    text_color=cap.text_color or default_text_color,
                    stroke_color=cap.stroke_color or default_stroke_color,
                    stroke_width=stroke_width,
                )
            )
        return calculated

    def generate_template_canvas(
        self,
        *,
        template_slug: str,
        width: int = 800,
        height: int = 800,
    ) -> Image.Image:
        """Render a clean, copyright-safe workplace template background canvas."""
        c_top, c_bottom, c_accent = TEMPLATE_PALETTES.get(
            template_slug, ((15, 23, 42), (30, 41, 59), (249, 115, 22))
        )
        img = Image.new("RGB", (width, height), c_top)
        draw = ImageDraw.Draw(img)

        mid_y = height // 2
        # Top panel background
        draw.rectangle([(0, 0), (width, mid_y)], fill=c_top)
        # Bottom panel background
        draw.rectangle([(0, mid_y), (width, height)], fill=c_bottom)
        # Center divider bar with accent trim
        draw.rectangle([(0, mid_y - 4), (width, mid_y + 4)], fill=c_accent)

        # Subtle decorative workplace card frame inside both panels
        margin = 24
        draw.rounded_rectangle(
            [(margin, margin), (width - margin, mid_y - 18)],
            radius=16,
            outline=(255, 255, 255),
            width=2,
        )
        draw.rounded_rectangle(
            [(margin, mid_y + 18), (width - margin, height - margin)],
            radius=16,
            outline=c_accent,
            width=2,
        )

        # Central workplace visual emblem so the meme has distinct visual structure
        cx = width // 2
        draw.rounded_rectangle(
            [(cx - 130, mid_y - 44), (cx + 130, mid_y + 44)],
            radius=14,
            fill=(15, 23, 42),
            outline=c_accent,
            width=3,
        )
        label_font = self._load_font(FONT_PATHS_BY_SCRIPT["latin"], 18)
        badge_label = template_slug.replace("-", " ").upper()[:22]
        bw, bh = self._measure_text(draw, badge_label, label_font, stroke_width=0)
        draw.text(
            (cx - bw // 2, mid_y - bh // 2),
            badge_label,
            fill=c_accent,
            font=label_font,
        )
        return img

    def render_meme(
        self,
        *,
        template_slug: str,
        width: int,
        height: int,
        regions: Sequence[TextRegionSpec],
        captions: Sequence[RenderCaptionInput],
        language_tag: str = "en",
        output_format: str = "PNG",
        base_image_bytes: Optional[bytes] = None,
    ) -> RenderedMemeOutput:
        """Render a complete meme image with laid-out text overlays in PNG or WEBP."""
        fmt = output_format.strip().upper()
        if fmt not in {"PNG", "WEBP"}:
            raise AppError(
                code="UNSUPPORTED_OUTPUT_FORMAT",
                message="Output format must be PNG or WEBP.",
                status_code=422,
            )

        layouts = self.calculate_layout(
            regions=regions,
            captions=captions,
            language_tag=language_tag,
        )

        if base_image_bytes is not None:
            with Image.open(io.BytesIO(base_image_bytes)) as src_img:
                canvas = src_img.convert("RGB").resize((width, height))
        else:
            canvas = self.generate_template_canvas(
                template_slug=template_slug, width=width, height=height
            )

        draw = ImageDraw.Draw(canvas)
        for layout in layouts:
            font = self._load_font(layout.font_path, layout.font_size)
            total_text_h = len(layout.lines) * layout.line_height
            cur_y = layout.box_y + max(0, (layout.box_height - total_text_h) // 2)

            for line in layout.lines:
                line_w, _ = self._measure_text(draw, line, font, layout.stroke_width)
                if layout.align == "left":
                    cur_x = layout.box_x + 12
                elif layout.align == "right":
                    cur_x = layout.box_x + max(0, layout.box_width - line_w - 12)
                else:
                    cur_x = layout.box_x + max(0, (layout.box_width - line_w) // 2)

                draw.text(
                    (cur_x, cur_y),
                    line,
                    font=font,
                    fill=layout.text_color,
                    stroke_width=layout.stroke_width,
                    stroke_fill=layout.stroke_color,
                )
                cur_y += layout.line_height

        out_buf = io.BytesIO()
        if fmt == "WEBP":
            canvas.save(out_buf, format="WEBP", quality=90)
            mime_type = "image/webp"
        else:
            canvas.save(out_buf, format="PNG", optimize=True)
            mime_type = "image/png"

        return RenderedMemeOutput(
            image_bytes=out_buf.getvalue(),
            mime_type=mime_type,
            width=width,
            height=height,
            layouts=layouts,
        )
