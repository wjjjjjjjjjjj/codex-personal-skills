#!/usr/bin/env python3
"""Render a project-configured architecture diagram.

The script deliberately contains no customer, product, compliance or capability
defaults.  All business labels must be supplied by a reviewed JSON file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


FONT_CANDIDATES = {
    "regular": [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    ],
    "bold": [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf"),
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Reviewed project JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output PNG in project workdir")
    parser.add_argument("--font-regular", type=Path)
    parser.add_argument("--font-bold", type=Path)
    parser.add_argument("--mode", choices=("submission", "internal"), default="submission")
    return parser.parse_args()


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    text(data.get("title"), "title")
    layers = data.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("layers must be a non-empty array")
    if len(layers) > 10:
        raise ValueError("layers supports at most 10 items")
    for index, layer in enumerate(layers, 1):
        if not isinstance(layer, dict):
            raise ValueError(f"layers[{index}] must be an object")
        text(layer.get("label"), f"layers[{index}].label")
        rows = layer.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"layers[{index}].rows must be a non-empty array")
        for row_index, row in enumerate(rows, 1):
            if not isinstance(row, list) or not row:
                raise ValueError(f"layers[{index}].rows[{row_index}] must be non-empty")
            if len(row) > 8:
                raise ValueError(f"layers[{index}].rows[{row_index}] supports at most 8 components")
            for item_index, item in enumerate(row, 1):
                text(item, f"layers[{index}].rows[{row_index}][{item_index}]")
    pillars = data.get("pillars", [])
    if not isinstance(pillars, list) or len(pillars) > 2:
        raise ValueError("pillars must be an array with at most 2 items")
    for index, pillar in enumerate(pillars, 1):
        label = pillar.get("label") if isinstance(pillar, dict) else pillar
        text(label, f"pillars[{index}].label")
    return data


def resolve_font(explicit: Path | None, kind: str) -> Path:
    if explicit:
        if not explicit.is_file():
            raise FileNotFoundError(f"{kind} CJK font not found: {explicit}")
        return explicit
    for candidate in FONT_CANDIDATES[kind]:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No CJK {kind} font found; pass --font-{kind} with a verified font file"
    )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    regular_path = resolve_font(args.font_regular, "regular")
    bold_path = resolve_font(args.font_bold, "bold")

    def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(bold_path if bold else regular_path), size)

    width = 2200
    margin, pillar_width, gap, title_height = 40, 150, 16, 120
    pillars = config.get("pillars", [])
    left_pillar = pillar_width + gap if pillars else 0
    right_pillar = pillar_width + gap if len(pillars) == 2 else 0
    center_left = margin + left_pillar
    center_right = width - margin - right_pillar
    layer_heights = [max(150, 58 + 92 * len(layer["rows"])) for layer in config["layers"]]
    height = margin * 2 + title_height + gap + sum(h + gap for h in layer_heights) + 54

    if args.mode == "submission":
        line, layer_fill, label_fill, box_fill, pillar_fill = (
            (45, 45, 45), (238, 238, 238), (222, 222, 222), (255, 255, 255), (230, 230, 230)
        )
    else:
        line, layer_fill, label_fill, box_fill, pillar_fill = (
            (25, 69, 92), (232, 244, 248), (195, 225, 235), (255, 255, 255), (218, 235, 240)
        )
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def rounded(bounds: tuple[float, float, float, float], fill: tuple[int, int, int], radius: int = 12) -> None:
        draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=line, width=3)

    def wrap(value: str, use_font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
        lines: list[str] = []
        current = ""
        for char in value:
            candidate = current + char
            if current and draw.textlength(candidate, font=use_font) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def centered(bounds: tuple[float, float, float, float], value: str | list[str], use_font: ImageFont.FreeTypeFont) -> None:
        values = [value] if isinstance(value, str) else value
        heights = [draw.textbbox((0, 0), item, font=use_font)[3] for item in values]
        y = (bounds[1] + bounds[3] - sum(heights) - 8 * (len(values) - 1)) / 2
        for item, item_height in zip(values, heights):
            item_width = draw.textlength(item, font=use_font)
            draw.text(((bounds[0] + bounds[2] - item_width) / 2, y), item, font=use_font, fill=(0, 0, 0))
            y += item_height + 8

    centered((margin, margin, width - margin, margin + title_height), config["title"], font(48))
    y = margin + title_height + gap
    top_y = y
    for layer, band_height in zip(config["layers"], layer_heights):
        y1 = y + band_height
        rounded((center_left, y, center_right, y1), layer_fill)
        label_width = 260
        rounded((center_left, y, center_left + label_width, y1), label_fill)
        label_lines = [layer["label"]]
        if isinstance(layer.get("sublabel"), str) and layer["sublabel"].strip():
            label_lines.append(layer["sublabel"].strip())
        centered((center_left + 8, y, center_left + label_width - 8, y1), label_lines, font(27))

        area_left, area_right = center_left + label_width + 18, center_right - 14
        row_gap = 16
        row_height = (band_height - row_gap * (len(layer["rows"]) + 1)) / len(layer["rows"])
        row_y = y + row_gap
        for row in layer["rows"]:
            component_gap = 14
            box_width = (area_right - area_left - component_gap * (len(row) - 1)) / len(row)
            box_x = area_left
            component_font = font(24, False)
            for component in row:
                bounds = (box_x, row_y, box_x + box_width, row_y + row_height)
                rounded(bounds, box_fill, 9)
                centered(bounds, wrap(component, component_font, box_width - 24), component_font)
                box_x += box_width + component_gap
            row_y += row_height + row_gap
        y = y1 + gap
    bottom_y = y - gap

    def vertical_label(bounds: tuple[float, float, float, float], label: str) -> None:
        use_font = font(30)
        text_width = int(draw.textlength(label, font=use_font)) + 24
        layer = Image.new("RGBA", (text_width, use_font.size + 30), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        layer_draw.text((12, 8), label, font=use_font, fill=(0, 0, 0, 255))
        rotated = layer.rotate(90, expand=True)
        image.paste(rotated, (int((bounds[0] + bounds[2] - rotated.width) / 2), int((bounds[1] + bounds[3] - rotated.height) / 2)), rotated)

    if pillars:
        left_label = pillars[0].get("label") if isinstance(pillars[0], dict) else pillars[0]
        bounds = (margin, top_y, margin + pillar_width, bottom_y)
        rounded(bounds, pillar_fill)
        vertical_label(bounds, left_label)
    if len(pillars) == 2:
        right_label = pillars[1].get("label") if isinstance(pillars[1], dict) else pillars[1]
        bounds = (width - margin - pillar_width, top_y, width - margin, bottom_y)
        rounded(bounds, pillar_fill)
        vertical_label(bounds, right_label)

    label_font = font(22, False)
    label = "方案示意"
    draw.text((width - margin - draw.textlength(label, font=label_font), height - margin - 30), label, font=label_font, fill=(100, 100, 100))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="PNG")
    print(json.dumps({"status": "ok", "output": str(args.output), "size": image.size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
