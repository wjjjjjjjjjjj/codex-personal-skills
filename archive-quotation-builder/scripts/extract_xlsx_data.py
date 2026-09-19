#!/usr/bin/env python3
"""
extract_xlsx_data.py
档案信息化项目报价清单数据提取脚本

支持两种模式：
1. 正常 xlsx 文件（直接用 openpyxl 读取）
2. 损坏的 xlsx（ZIP central directory 缺失）—— 手动扫描 PK local header 提取

输出：rows_data.json —— {行号: {列名: 单元格内容}} 格式
"""

import html
import os, sys, json, struct, zlib


# ─────────────────────────────────────────────
# 正常 xlsx 读取（优先走这条路）
# ─────────────────────────────────────────────

def read_xlsx_normal(xlsx_path: str) -> dict:
    """使用 openpyxl 读取标准 xlsx，返回 {row_num: {col_letter: value}}"""
    try:
        import openpyxl
        value_wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        formula_wb = openpyxl.load_workbook(xlsx_path, data_only=False)
        ws = value_wb.active
        formula_ws = formula_wb[ws.title]
        rows_data = {}
        uncached_formulas = []
        for row in ws.iter_rows():
            row_num = row[0].row
            row_dict = {}
            for cell in row:
                col = cell.column_letter
                val = cell.value
                formula_value = formula_ws[cell.coordinate].value
                if isinstance(formula_value, str) and formula_value.startswith('=') and val is None:
                    uncached_formulas.append(cell.coordinate)
                if val is not None:
                    row_dict[col] = str(val).strip() if isinstance(val, str) else val
            if row_dict:
                rows_data[row_num] = row_dict
        if uncached_formulas:
            preview = ', '.join(uncached_formulas[:10])
            raise ValueError(
                f"发现 {len(uncached_formulas)} 个没有缓存值的公式单元格（如 {preview}）；"
                "需先用 Excel 或兼容引擎重算并保存，不能静默当作空值。"
            )
        return rows_data
    except ValueError:
        raise
    except Exception as e:
        print(f"[normal] openpyxl 读取失败: {e}，尝试手动解析 ZIP...")
        return None


# ─────────────────────────────────────────────
# 损坏 xlsx 提取（ZIP central directory 缺失时使用）
# ─────────────────────────────────────────────

def scan_local_entries(data: bytes):
    """手动扫描 PK\x03\x04 local file header，返回 [(filename, compressed_data)] 列表"""
    entries = []
    i = 0
    while i < len(data) - 4:
        if data[i:i+4] == b'PK\x03\x04':
            try:
                version_needed = struct.unpack_from('<H', data, i+4)[0]
                flags          = struct.unpack_from('<H', data, i+6)[0]
                compression    = struct.unpack_from('<H', data, i+8)[0]
                crc32          = struct.unpack_from('<I', data, i+14)[0]
                comp_size      = struct.unpack_from('<I', data, i+18)[0]
                uncomp_size    = struct.unpack_from('<I', data, i+22)[0]
                fname_len      = struct.unpack_from('<H', data, i+26)[0]
                extra_len      = struct.unpack_from('<H', data, i+28)[0]
                if flags & 0x08:
                    raise ValueError("检测到 ZIP data descriptor，恢复解析器不支持，禁止部分成功")
                if comp_size == 0xFFFFFFFF or uncomp_size == 0xFFFFFFFF:
                    raise ValueError("检测到 Zip64 条目，恢复解析器不支持，禁止部分成功")
                header_size    = 30 + fname_len + extra_len
                fname          = data[i+30:i+30+fname_len].decode('utf-8', errors='replace')
                payload_start  = i + header_size
                payload        = data[payload_start:payload_start + comp_size]
                entries.append((fname, compression, payload, uncomp_size))
                i = payload_start + comp_size
            except ValueError:
                raise
            except Exception:
                i += 1
        else:
            i += 1
    return entries


def decompress_entry(compression: int, payload: bytes, uncomp_size: int) -> bytes:
    if compression == 0:
        return payload
    elif compression == 8:  # deflate
        return zlib.decompress(payload, -15)
    else:
        raise ValueError(f"不支持的压缩方式: {compression}")


def extract_shared_strings(xml_bytes: bytes) -> list:
    """从 sharedStrings.xml 提取字符串表"""
    import re
    strings = []
    # 提取 <si> 块内所有 <t> 文本
    for si_match in re.finditer(rb'<si>(.*?)</si>', xml_bytes, re.DOTALL):
        texts = re.findall(rb'<t[^>]*>(.*?)</t>', si_match.group(1), re.DOTALL)
        combined = html.unescape(''.join(t.decode('utf-8', errors='replace') for t in texts))
        strings.append(combined)
    return strings


def col_letter(col_idx: int) -> str:
    """1-indexed列号 → 列字母，如 1→A, 26→Z, 27→AA"""
    result = ''
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def parse_col(col_str: str) -> int:
    """列字母 → 1-indexed列号，如 A→1, AA→27"""
    result = 0
    for ch in col_str.upper():
        result = result * 26 + (ord(ch) - 64)
    return result


def read_xlsx_manual(xlsx_path: str) -> dict:
    """手动解析损坏的 xlsx（ZIP central directory 缺失）"""
    import re

    with open(xlsx_path, 'rb') as f:
        data = f.read()

    entries = scan_local_entries(data)
    file_map = {}
    for fname, compression, payload, uncomp_size in entries:
        try:
            content = decompress_entry(compression, payload, uncomp_size)
            file_map[fname] = content
        except Exception as e:
            print(f"[warn] 无法解压 {fname}: {e}")

    # 共享字符串
    shared_strings = []
    for key in ['xl/sharedStrings.xml', 'xl\\sharedStrings.xml']:
        if key in file_map:
            shared_strings = extract_shared_strings(file_map[key])
            break

    # 找 sheet1
    sheet_xml = None
    for key in ['xl/worksheets/sheet1.xml', 'xl\\worksheets\\sheet1.xml']:
        if key in file_map:
            sheet_xml = file_map[key]
            break
    if sheet_xml is None:
        for key in file_map:
            if 'sheet1' in key.lower():
                sheet_xml = file_map[key]
                break
    if sheet_xml is None:
        raise ValueError("找不到 sheet1.xml")

    # 解析单元格
    rows_data = {}
    for row_match in re.finditer(rb'<row[^>]*r="(\d+)"[^>]*>(.*?)</row>', sheet_xml, re.DOTALL):
        row_num = int(row_match.group(1))
        row_xml = row_match.group(2)
        row_dict = {}
        for cell_match in re.finditer(rb'<c r="([A-Z]+\d+)"([^>]*)>(.*?)</c>', row_xml, re.DOTALL):
            cell_ref  = cell_match.group(1).decode()
            cell_attr = cell_match.group(2).decode()
            cell_body = cell_match.group(3)
            col_str   = re.sub(r'\d+', '', cell_ref)

            # 判断类型
            if 't="inlineStr"' in cell_attr:
                texts = re.findall(rb'<t[^>]*>(.*?)</t>', cell_body, re.DOTALL)
                value = html.unescape(''.join(t.decode('utf-8', errors='replace') for t in texts))
            else:
                v_match = re.search(rb'<v>(.*?)</v>', cell_body, re.DOTALL)
                if not v_match:
                    continue
                raw_val = html.unescape(v_match.group(1).decode('utf-8', errors='replace'))
                if 't="s"' in cell_attr:
                    idx = int(raw_val)
                    value = shared_strings[idx] if idx < len(shared_strings) else ''
                else:
                    value = raw_val

            if value:
                row_dict[col_str] = value
        if row_dict:
            rows_data[row_num] = row_dict

    return rows_data


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def extract(xlsx_path: str, output_json: str = None) -> dict:
    """
    提取 xlsx 数据。优先 openpyxl，失败则手动解析。
    output_json: 若指定，同时写入 JSON 文件。
    返回: {行号: {列字母: 值}} 的字典（键为 int）
    """
    result = read_xlsx_normal(xlsx_path)
    if result is None:
        print("[recovery] 数据抢救模式不保证公式、样式、合并、批注、图片或完整 ZIP 兼容性；结果必须人工复核。")
        result = read_xlsx_manual(xlsx_path)

    if output_json:
        os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[done] 提取 {len(result)} 行，已写入 {output_json}")

    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python extract_xlsx_data.py <input.xlsx> [output.json]")
        sys.exit(1)
    xlsx_in  = sys.argv[1]
    json_out = sys.argv[2] if len(sys.argv) > 2 else 'rows_data.json'
    data = extract(xlsx_in, json_out)
    print(f"提取完成，共 {len(data)} 行有效数据。")
