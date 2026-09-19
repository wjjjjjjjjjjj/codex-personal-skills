from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from extract_xlsx_data import extract_shared_strings, read_xlsx_manual, scan_local_entries


def local_entry(name: str, payload: bytes, flags: int = 0) -> bytes:
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(payload) + compressor.flush()
    name_bytes = name.encode("utf-8")
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = struct.pack(
        "<4s5H3I2H",
        b"PK\x03\x04",
        20,
        flags,
        8,
        0,
        0,
        crc,
        len(compressed),
        len(payload),
        len(name_bytes),
        0,
    )
    return header + name_bytes + compressed


class RecoveryTests(unittest.TestCase):
    def test_shared_strings_decode_xml_entities(self) -> None:
        values = extract_shared_strings(b"<sst><si><t>A&amp;B</t></si></sst>")
        self.assertEqual(values, ["A&B"])

    def test_inline_string_and_shared_string_are_recovered(self) -> None:
        shared = b"<sst><si><t>A&amp;B</t></si></sst>"
        sheet = (
            b'<worksheet><sheetData><row r="1">'
            b'<c r="A1" t="inlineStr"><is><t>inline&amp;text</t></is></c>'
            b'<c r="B1" t="s"><v>0</v></c>'
            b"</row></sheetData></worksheet>"
        )
        payload = local_entry("xl/sharedStrings.xml", shared) + local_entry("xl/worksheets/sheet1.xml", sheet)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.xlsx"
            path.write_bytes(payload)
            rows = read_xlsx_manual(str(path))
        self.assertEqual(rows[1]["A"], "inline&text")
        self.assertEqual(rows[1]["B"], "A&B")

    def test_data_descriptor_is_rejected(self) -> None:
        payload = local_entry("xl/worksheets/sheet1.xml", b"x", flags=0x08)
        with self.assertRaises(ValueError):
            scan_local_entries(payload)


if __name__ == "__main__":
    unittest.main()
