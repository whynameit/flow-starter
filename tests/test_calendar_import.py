import unittest
import zipfile
from pathlib import Path

from flow_starter.calendar_import import read_busy_slots_csv, read_busy_slots_ics, read_busy_slots_xlsx


class CalendarImportTests(unittest.TestCase):
    def test_read_busy_slots_csv(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "busy.csv"
            path.write_text("title,start,end\nA,2026-06-19 09:00,2026-06-19 10:00\n", encoding="utf-8")

            slots = read_busy_slots_csv(path)

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].title, "A")
        self.assertEqual(slots[0].start.hour, 9)

    def test_read_busy_slots_ics(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calendar.ics"
            path.write_text(
                "\r\n".join(
                    [
                        "BEGIN:VCALENDAR",
                        "BEGIN:VEVENT",
                        "SUMMARY:Class",
                        "DTSTART:20260619T090000",
                        "DTEND:20260619T103000",
                        "END:VEVENT",
                        "END:VCALENDAR",
                    ]
                ),
                encoding="utf-8",
            )

            slots = read_busy_slots_ics(path)

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].title, "Class")
        self.assertEqual(slots[0].end.hour, 10)

    def test_read_busy_slots_xlsx_with_inline_strings(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wemust.xlsx"
            write_minimal_wemust_xlsx(path)

            slots = read_busy_slots_xlsx(path)

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].title, "信號與系統 EIE220 D1 @ O603")
        self.assertEqual(slots[0].start.strftime("%Y-%m-%d %H:%M"), "2026-09-01 09:00")
        self.assertEqual(slots[0].end.strftime("%Y-%m-%d %H:%M"), "2026-09-01 11:50")


def write_minimal_wemust_xlsx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>課室</t></is></c>
      <c r="B1" t="inlineStr"><is><t>日期</t></is></c>
      <c r="C1" t="inlineStr"><is><t>科目名稱</t></is></c>
      <c r="D1" t="inlineStr"><is><t>科目編號</t></is></c>
      <c r="E1" t="inlineStr"><is><t>班別名稱</t></is></c>
      <c r="F1" t="inlineStr"><is><t>開始時間</t></is></c>
      <c r="G1" t="inlineStr"><is><t>結束時間</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>O603</t></is></c>
      <c r="B2" t="inlineStr"><is><t>2026-09-01</t></is></c>
      <c r="C2" t="inlineStr"><is><t>信號與系統</t></is></c>
      <c r="D2" t="inlineStr"><is><t>EIE220</t></is></c>
      <c r="E2" t="inlineStr"><is><t>D1</t></is></c>
      <c r="F2" t="inlineStr"><is><t>09:00</t></is></c>
      <c r="G2" t="inlineStr"><is><t>11:50</t></is></c>
    </row>
  </sheetData>
</worksheet>""",
        )


if __name__ == "__main__":
    unittest.main()
