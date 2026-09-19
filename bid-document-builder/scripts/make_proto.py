#!/usr/bin/env python3
"""Render a reviewed, explicitly labelled functional prototype image."""

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
    ],
    "bold": [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ],
}
WATERMARK = "原型示意｜非真实产品截图"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Reviewed project JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output PNG in project workdir")
    parser.add_argument("--font-regular", type=Path)
    parser.add_argument("--font-bold", type=Path)
    parser.add_argument("--mode", choices=("submission", "internal"), default="submission")
    return parser.parse_args()


def required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    required_text(data.get("title"), "title")
    layout = data.get("layout")
    if layout not in {"dashboard", "table", "form", "flow"}:
        raise ValueError("layout must be dashboard, table, form, or flow")
    if layout == "dashboard":
        metrics = data.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            raise ValueError("dashboard.metrics must be a non-empty array")
        for index, metric in enumerate(metrics, 1):
            if not isinstance(metric, dict):
                raise ValueError(f"metrics[{index}] must be an object")
            required_text(metric.get("label"), f"metrics[{index}].label")
            value = metric.get("value", "—")
            if value is not None and not isinstance(value, (str, int, float)):
                raise ValueError(f"metrics[{index}].value must be text or number")
    elif layout == "table":
        columns = data.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError("table.columns must be a non-empty array")
        for index, column in enumerate(columns, 1):
            required_text(column, f"columns[{index}]")
        rows = data.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError("table.rows must be an array")
        for index, row in enumerate(rows, 1):
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError(f"rows[{index}] must contain exactly {len(columns)} values")
    elif layout == "form":
        fields = data.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError("form.fields must be a non-empty array")
        for index, field in enumerate(fields, 1):
            label = field.get("label") if isinstance(field, dict) else field
            required_text(label, f"fields[{index}].label")
    else:
        nodes = data.get("nodes")
        if not isinstance(nodes, list) or len(nodes) < 2:
            raise ValueError("flow.nodes must contain at least 2 labels")
        for index, node in enumerate(nodes, 1):
            required_text(node, f"nodes[{index}]")
    buttons = data.get("buttons", [])
    if not isinstance(buttons, list):
        raise ValueError("buttons must be an array")
    for index, button in enumerate(buttons, 1):
        required_text(button, f"buttons[{index}]")
    return data


def resolve_font(explicit: Path | None, kind: str) -> Path:
    if explicit:
        if not explicit.is_file():
            raise FileNotFoundError(f"{kind} CJK font not found: {explicit}")
        return explicit
    for candidate in FONT_CANDIDATES[kind]:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No CJK {kind} font found; pass --font-{kind}")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    regular_path = resolve_font(args.font_regular, "regular")
    bold_path = resolve_font(args.font_bold, "bold")

    def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(bold_path if bold else regular_path), size)

    width, height = 1320, 840
    if args.mode == "submission":
        ink, muted, panel, accent, canvas = (20, 20, 20), (100, 100, 100), (248, 248, 248), (70, 70, 70), (255, 255, 255)
    else:
        ink, muted, panel, accent, canvas = (24, 48, 60), (85, 108, 118), (241, 248, 250), (17, 116, 143), (255, 255, 255)
    image = Image.new("RGB", (width, height), canvas)
    draw = ImageDraw.Draw(image)

    def box(bounds: tuple[float, float, float, float], fill=panel, outline=(180, 180, 180), radius=10, line_width=2) -> None:
        draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=line_width)

    draw.rectangle((0, 0, width, 92), fill=(238, 238, 238) if args.mode == "submission" else (223, 239, 244))
    draw.text((42, 24), config["title"], font=font(34, True), fill=ink)
    subtitle = config.get("subtitle")
    if isinstance(subtitle, str) and subtitle.strip():
        draw.text((42, 100), subtitle.strip(), font=font(21), fill=muted)
    content_top = 145

    buttons = config.get("buttons", [])
    button_x = width - 42
    for label in reversed(buttons):
        label_width = draw.textlength(label, font=font(19)) + 34
        button_x -= label_width
        box((button_x, 104, button_x + label_width, 140), fill=(245, 245, 245), outline=accent, radius=6)
        draw.text((button_x + 17, 110), label, font=font(19), fill=accent)
        button_x -= 12

    layout = config["layout"]
    if layout == "dashboard":
        metrics = config["metrics"]
        gap = 18
        card_width = (width - 84 - gap * (len(metrics) - 1)) / len(metrics)
        x = 42
        for metric in metrics:
            box((x, content_top, x + card_width, content_top + 150))
            draw.text((x + 22, content_top + 24), metric["label"], font=font(21), fill=muted)
            value = metric.get("value", "—")
            value_text = "—" if value in (None, "") else str(value)
            draw.text((x + 22, content_top + 67), value_text, font=font(36, True), fill=ink)
            x += card_width + gap
        box((42, content_top + 180, width - 42, height - 80))
        empty_label = config.get("empty_state", "—")
        draw.text((62, content_top + 205), str(empty_label), font=font(24), fill=muted)
    elif layout == "table":
        columns = config["columns"]
        rows = config.get("rows", [])
        left, right, row_height = 42, width - 42, 58
        column_width = (right - left) / len(columns)
        draw.rectangle((left, content_top, right, content_top + row_height), fill=(225, 225, 225), outline=(140, 140, 140), width=2)
        for index, column in enumerate(columns):
            x = left + index * column_width
            draw.text((x + 14, content_top + 15), column, font=font(20, True), fill=ink)
            draw.line((x, content_top, x, content_top + row_height * (max(len(rows), 1) + 1)), fill=(160, 160, 160), width=1)
        for row_index, row in enumerate(rows[:8], 1):
            y = content_top + row_index * row_height
            draw.rectangle((left, y, right, y + row_height), fill=(255, 255, 255), outline=(190, 190, 190), width=1)
            for column_index, value in enumerate(row):
                draw.text((left + column_index * column_width + 14, y + 15), str(value), font=font(19), fill=ink)
        if not rows:
            draw.text((left + 18, content_top + row_height + 18), "—", font=font(20), fill=muted)
    elif layout == "form":
        fields = config["fields"]
        column_count = 2 if len(fields) > 4 else 1
        field_width = (width - 102 - 24 * (column_count - 1)) / column_count
        for index, field in enumerate(fields):
            label = field.get("label") if isinstance(field, dict) else field
            value = field.get("value", "") if isinstance(field, dict) else ""
            column = index % column_count
            row = index // column_count
            x = 42 + column * (field_width + 24)
            y = content_top + row * 108
            draw.text((x, y), label, font=font(20, True), fill=ink)
            box((x, y + 34, x + field_width, y + 88), fill=(255, 255, 255), radius=5)
            if value not in (None, ""):
                draw.text((x + 14, y + 49), str(value), font=font(19), fill=ink)
    else:
        nodes = config["nodes"]
        left, right = 70, width - 70
        gap = 28
        node_width = (right - left - gap * (len(nodes) - 1)) / len(nodes)
        if node_width < 120:
            raise ValueError("too many flow nodes for a readable prototype")
        y0, y1 = 300, 440
        for index, node in enumerate(nodes):
            x0 = left + index * (node_width + gap)
            box((x0, y0, x0 + node_width, y1), fill=(255, 255, 255), outline=accent, radius=12, line_width=3)
            text_width = draw.textlength(node, font=font(22, True))
            draw.text((x0 + (node_width - text_width) / 2, y0 + 51), node, font=font(22, True), fill=ink)
            if index < len(nodes) - 1:
                arrow_start = x0 + node_width + 5
                arrow_end = arrow_start + gap - 10
                draw.line((arrow_start, (y0 + y1) / 2, arrow_end, (y0 + y1) / 2), fill=accent, width=4)
                draw.polygon(((arrow_end, (y0 + y1) / 2), (arrow_end - 10, (y0 + y1) / 2 - 7), (arrow_end - 10, (y0 + y1) / 2 + 7)), fill=accent)

    watermark_font = font(27, True)
    watermark_width = draw.textlength(WATERMARK, font=watermark_font)
    draw.rectangle((width - watermark_width - 66, height - 62, width - 30, height - 20), fill=(245, 245, 245), outline=(130, 130, 130), width=2)
    draw.text((width - watermark_width - 48, height - 56), WATERMARK, font=watermark_font, fill=(80, 80, 80))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="PNG")
    print(json.dumps({"status": "ok", "output": str(args.output), "watermark": WATERMARK}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
