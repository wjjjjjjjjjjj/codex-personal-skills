// lib.js — 共享样式、编号、封面、页眉页脚、辅助函数
const {
  Paragraph, TextRun, Table, TableRow, TableCell, Header, Footer,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak
} = require("docx");

const BODY_FONT = "宋体";
const HEAD_FONT = "黑体";
const BLUE = "000000";
const LIGHTBLUE = "ECECEC";
const GRAY = "808080";
const SZ_BODY = 24, SZ_H1 = 32, SZ_H2 = 28, SZ_H3 = 25, SZ_H4 = 24;

function p(text, opts = {}) {
  const runs = Array.isArray(text) ? text
    : [new TextRun({ text: text || "", font: BODY_FONT, size: SZ_BODY, bold: !!opts.bold })];
  return new Paragraph({ children: runs, spacing: { line: 360, after: 80, ...(opts.spacing || {}) },
    indent: opts.noIndent ? undefined : { firstLine: 480 },
    alignment: opts.align || AlignmentType.JUSTIFIED, pageBreakBefore: !!opts.pageBreakBefore });
}
function run(text, o = {}) {
  return new TextRun({ text, font: o.font || BODY_FONT, size: o.size || SZ_BODY,
    bold: !!o.bold, color: o.color, italics: !!o.italics });
}
function heading(text, level, opts = {}) {
  const map = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3, 4: HeadingLevel.HEADING_4 };
  return new Paragraph({ heading: map[level],
    numbering: opts.noNum ? undefined : { reference: "h", level: level - 1 },
    pageBreakBefore: !!opts.pageBreakBefore,
    children: [new TextRun({ text, font: HEAD_FONT, bold: true, color: BLUE,
      size: level === 1 ? SZ_H1 : level === 2 ? SZ_H2 : level === 3 ? SZ_H3 : SZ_H4 })],
    spacing: { before: 200, after: 120 } });
}
function plainTitle(text, size = SZ_H2, align = AlignmentType.CENTER) {
  return new Paragraph({ alignment: align, spacing: { before: 160, after: 160 },
    children: [new TextRun({ text, font: HEAD_FONT, bold: true, size, color: BLUE })] });
}
function placeholder(label) {
  const b = { style: BorderStyle.DASHED, size: 6, color: GRAY };
  return new Table({ width: { size: 9000, type: WidthType.DXA }, columnWidths: [9000],
    rows: [new TableRow({ children: [new TableCell({ width: { size: 9000, type: WidthType.DXA },
      borders: { top: b, bottom: b, left: b, right: b }, shading: { fill: "F5F5F5", type: ShadingType.CLEAR },
      margins: { top: 220, bottom: 220, left: 160, right: 160 },
      children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: label, font: BODY_FONT, size: SZ_BODY, color: GRAY, italics: true })] })] })] })] });
}
function cell(content, o = {}) {
  const b = { style: BorderStyle.SINGLE, size: 4, color: "999999" };
  const children = Array.isArray(content) ? content
    : [new Paragraph({ alignment: o.align || AlignmentType.LEFT, spacing: { line: 300 },
        children: [new TextRun({ text: String(content), font: BODY_FONT, size: o.size || 22, bold: !!o.bold, color: o.color })] })];
  return new TableCell({ width: { size: o.w, type: WidthType.DXA },
    borders: { top: b, bottom: b, left: b, right: b },
    shading: undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER, columnSpan: o.span, rowSpan: o.rowSpan, children });
}
function headerRow(labels, widths) {
  return new TableRow({ tableHeader: true,
    children: labels.map((l, i) => cell(l, { w: widths[i], bold: true, align: AlignmentType.CENTER })) });
}
function table(widths, headerLabels, dataRows, opt = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const rows = [];
  if (headerLabels) rows.push(headerRow(headerLabels, widths));
  for (const r of dataRows) {
    rows.push(new TableRow({ children: r.map((c, i) => {
      if (c && typeof c === "object" && c.__cell) return cell(c.v, { ...c, w: c.w || widths[i] });
      return cell(c, { w: widths[i], size: opt.size, align: opt.align });
    }) }));
  }
  return new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths, rows });
}
function blank(n = 1) { const a = []; for (let i = 0; i < n; i++) a.push(new Paragraph({ children: [new TextRun("")] })); return a; }
function requireText(config, key) {
  const value = config && typeof config[key] === "string" ? config[key].trim() : "";
  if (!value) throw new Error(`Missing required document config: ${key}`);
  return value;
}
function cover(config = {}) {
  const documentTitle = requireText(config, "documentTitle");
  const copyLabel = requireText(config, "copyLabel");
  const projectName = requireText(config, "projectName");
  const projectCode = requireText(config, "projectCode");
  const packageNo = requireText(config, "packageNo");
  const bidderName = requireText(config, "bidderName");
  const submissionDate = requireText(config, "submissionDate");
  return [ ...blank(3),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
      children: [new TextRun({ text: documentTitle, font: HEAD_FONT, bold: true, size: 72, color: BLUE })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
      children: [new TextRun({ text: `（${copyLabel}）`, font: HEAD_FONT, bold: true, size: 32, color: GRAY })] }),
    ...blank(3),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 140 },
      children: [new TextRun({ text: `项目名称：${projectName}`, font: BODY_FONT, size: 28 })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 140 },
      children: [new TextRun({ text: `项目编号/包号：${projectCode}/${packageNo}`, font: BODY_FONT, size: 28 })] }),
    ...blank(5),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: `供应商名称（加盖公章）：${bidderName}`, font: BODY_FONT, size: 26 })] }),
    new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: `日期：${submissionDate}`, font: BODY_FONT, size: 26 })] }),
    new Paragraph({ children: [new PageBreak()] }) ];
}
function makeHeader(config = {}) {
  const projectName = requireText(config, "projectName");
  const documentTitle = requireText(config, "documentTitle");
  const packageNo = requireText(config, "packageNo");
  return new Header({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 1 } },
    children: [new TextRun({ text: `${projectName}  ${documentTitle}  （包号：${packageNo}）`, font: BODY_FONT, size: 18, color: GRAY })] })] });
}
function makeFooter() {
  return new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
    children: [ new TextRun({ text: "第 ", font: BODY_FONT, size: 18, color: GRAY }),
      new TextRun({ children: [PageNumber.CURRENT], font: BODY_FONT, size: 18, color: GRAY }),
      new TextRun({ text: " 页  共 ", font: BODY_FONT, size: 18, color: GRAY }),
      new TextRun({ children: [PageNumber.TOTAL_PAGES], font: BODY_FONT, size: 18, color: GRAY }),
      new TextRun({ text: " 页", font: BODY_FONT, size: 18, color: GRAY }) ] })] });
}
const numberingConfig = [
  { reference: "h", levels: [
    { level: 0, format: LevelFormat.DECIMAL, text: "%1", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 0, hanging: 0 } } } },
    { level: 1, format: LevelFormat.DECIMAL, text: "%1.%2", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 0, hanging: 0 } } } },
    { level: 2, format: LevelFormat.DECIMAL, text: "%1.%2.%3", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 0, hanging: 0 } } } },
    { level: 3, format: LevelFormat.DECIMAL, text: "%1.%2.%3.%4", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 0, hanging: 0 } } } },
  ] },
  { reference: "bul", levels: [ { level: 0, format: LevelFormat.BULLET, text: "●", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } } ] },
];
const docStyles = {
  default: { document: { run: { font: BODY_FONT, size: SZ_BODY }, paragraph: { spacing: { line: 360 } } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: SZ_H1, bold: true, font: HEAD_FONT, color: BLUE }, paragraph: { spacing: { before: 240, after: 140 }, outlineLevel: 0, keepNext: true } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: SZ_H2, bold: true, font: HEAD_FONT, color: BLUE }, paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1, keepNext: true } },
    { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: SZ_H3, bold: true, font: HEAD_FONT, color: BLUE }, paragraph: { spacing: { before: 160, after: 100 }, outlineLevel: 2, keepNext: true } },
    { id: "Heading4", name: "Heading 4", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: SZ_H4, bold: true, font: HEAD_FONT, color: "333333" }, paragraph: { spacing: { before: 120, after: 80 }, outlineLevel: 3, keepNext: true } },
  ],
};
function bullet(text) {
  return new Paragraph({ numbering: { reference: "bul", level: 0 }, spacing: { line: 360, after: 40 },
    children: [new TextRun({ text, font: BODY_FONT, size: SZ_BODY })] });
}
module.exports = { p, run, heading, plainTitle, placeholder, table, cell, headerRow, cover,
  makeHeader, makeFooter, numberingConfig, docStyles, blank, bullet, requireText,
  BODY_FONT, HEAD_FONT, BLUE, LIGHTBLUE, GRAY, SZ_BODY, AlignmentType, Paragraph, TextRun, PageBreak };
