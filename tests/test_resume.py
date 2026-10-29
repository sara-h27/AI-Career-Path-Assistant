"""Resume intake stays local, bounded, and independent from the dialogue contract."""
import unittest
from io import BytesIO
from zipfile import ZipFile

from dialogue.resume import ResumeError, extract_resume_text


class ResumeTests(unittest.TestCase):
    @staticmethod
    def _pdf_with_text(text):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj\n",
            b"4 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj\n",
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        ]
        pdf = b"%PDF-1.4\n"
        offsets = [0]
        for item in objects:
            offsets.append(len(pdf))
            pdf += item
        xref = len(pdf)
        pdf += b"xref\n0 6\n0000000000 65535 f \n"
        pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
        return pdf + f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()

    def test_txt_is_cleaned_and_bounded(self):
        document = extract_resume_text("resume.txt", "  تحلیلگر داده\r\n\r\n  SQL  ".encode(), max_chars=13)
        self.assertEqual(document.file_type, "TXT")
        self.assertEqual(document.text, "تحلیلگر داده")
        self.assertTrue(document.truncated)

    def test_docx_uses_paragraph_text(self):
        content = BytesIO()
        with ZipFile(content, "w") as archive:
            archive.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8"?>
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body><w:p><w:r><w:t>Python</w:t></w:r><w:r><w:t> و SQL</w:t></w:r></w:p></w:body>
                </w:document>''')
        document = extract_resume_text("resume.docx", content.getvalue())
        self.assertEqual(document.text, "Python و SQL")
        self.assertFalse(document.truncated)

    def test_pdf_uses_text_layer(self):
        document = extract_resume_text("resume.pdf", self._pdf_with_text("Data analyst with Python"))
        self.assertEqual(document.file_type, "PDF")
        self.assertIn("Data analyst with Python", document.text)

    def test_invalid_or_empty_files_are_rejected(self):
        with self.assertRaises(ResumeError):
            extract_resume_text("resume.exe", b"content")
        with self.assertRaises(ResumeError):
            extract_resume_text("resume.txt", b"")
        with self.assertRaises(ResumeError):
            extract_resume_text("resume.docx", b"not-a-zip")


if __name__ == "__main__":
    unittest.main()
