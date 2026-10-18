# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import pikepdf
import pymupdf
from PIL import Image

from fixtures import AUXILIARY_MARKER, TARGET_RECT, auxiliary_pdf, incremental_pdf, make_pdf, scan_image
from substidude.pdf_engine import PDFError, open_pdf, sanitize_pdf
from test_independent import render_and_extract


class AuxiliaryTests(unittest.TestCase):
    def test_unsupported_content_refused_at_open_and_cleanup(self):
        for feature in ("actualtext", "escaped-actualtext", "properties", "annotation",
                        "form", "attachment", "action", "layer", "structure", "destination", "type3",
                        "unknown-root", "postscript", "alternate-image"):
            for nested in (False, True) if feature in {"actualtext", "escaped-actualtext"} else (False,):
                with self.subTest(feature=feature, nested=nested):
                    source = auxiliary_pdf(feature, nested=nested)
                    with self.assertRaises(PDFError):
                        sanitize_pdf(source)
                    with tempfile.TemporaryDirectory(prefix="substidude-test-") as directory:
                        path = Path(directory) / "synthetic.pdf"
                        path.write_bytes(source)
                        with self.assertRaises(PDFError) as caught:
                            open_pdf(path)
                        self.assertNotIn(AUXILIARY_MARKER, str(caught.exception))
                        self.assertEqual(source, path.read_bytes())
                        self.assertEqual([path], list(Path(directory).iterdir()))

    def test_native_scrub_alone_is_not_an_actualtext_safety_check(self):
        # Reproduction du blocage découvert : ne pas réutiliser ce parcours comme export.
        with pymupdf.open(stream=auxiliary_pdf("escaped-actualtext")) as document:
            page = document[0]
            page.add_redact_annot(TARGET_RECT)
            page.apply_redactions(images=0, graphics=0, text=0)
            document.scrub(hidden_text=False, redactions=False)
            unsafe_result = document.tobytes(garbage=4, deflate=True)
        with pikepdf.Pdf.open(BytesIO(unsafe_result)) as inspected:
            blocks = [item for item in pikepdf.parse_content_stream(inspected.pages[0])
                      if str(item.operator) == "BDC"]
            self.assertTrue(any(str(item.operands[1].get("/ActualText")) == AUXILIARY_MARKER
                                for item in blocks))
        with self.assertRaises(PDFError):
            sanitize_pdf(unsafe_result)

    def test_metadata_and_thumbnail_removed_without_changing_render(self):
        for feature in ("metadata", "thumbnail"):
            with self.subTest(feature=feature):
                source = auxiliary_pdf(feature)
                before, before_text, before_size, before_rotation = render_and_extract(source)
                result = sanitize_pdf(source)
                after, after_text, after_size, after_rotation = render_and_extract(result)
                self.assertEqual(before.tobytes(), after.tobytes())
                self.assertEqual((before_text, before_size, before_rotation),
                                 (after_text, after_size, after_rotation))
                # Après réécriture qpdf, MuPDF constitue ici le second lecteur structurel.
                with pymupdf.open(stream=result) as independent:
                    self.assertFalse(independent.is_repaired)
                    self.assertFalse(independent.metadata.get("title"))
                    self.assertEqual("", independent.get_xml_metadata())
                    self.assertEqual("null", independent.xref_get_key(independent[0].xref, "Thumb")[0])
                with pikepdf.Pdf.open(BytesIO(result), attempt_recovery=False) as document:
                    self.assertEqual([], document.check_pdf_syntax())
                    self.assertNotIn("/Info", document.trailer)
                    self.assertNotIn("/Info", document.Root)
                    self.assertNotIn("/Metadata", document.Root)
                    self.assertNotIn("/Metadata", document.pages[0].obj)
                    self.assertNotIn("/Thumb", document.pages[0].obj)
                    self.assertFalse(any(isinstance(obj, pikepdf.Stream)
                                         and obj.get("/Type") == pikepdf.Name.Metadata
                                         for obj in document.objects))

    def test_ambiguous_metadata_refused(self):
        with self.assertRaisesRegex(PDFError, "ambiguë"):
            sanitize_pdf(auxiliary_pdf("ambiguous-metadata"))

    def test_save_failure_never_returns_a_result_or_document_content(self):
        source = auxiliary_pdf("metadata")
        with patch.object(pikepdf.Pdf, "save", side_effect=RuntimeError(AUXILIARY_MARKER)):
            with self.assertRaisesRegex(PDFError, "aucun résultat") as caught:
                sanitize_pdf(source)
        self.assertNotIn(AUXILIARY_MARKER, str(caught.exception))

    def test_structural_verification_failure_blocks_the_result(self):
        with patch.object(pikepdf.Pdf, "check_pdf_syntax", return_value=[AUXILIARY_MARKER]):
            with self.assertRaisesRegex(PDFError, "contrôles structurels") as caught:
                sanitize_pdf(make_pdf())
        self.assertNotIn(AUXILIARY_MARKER, str(caught.exception))

    def test_parser_warnings_are_refused_without_disclosing_content(self):
        def malformed_content(*args):
            warnings.warn(AUXILIARY_MARKER, UserWarning)
            return []

        with warnings.catch_warnings(record=True) as emitted:
            with patch("substidude.pdf_engine.pikepdf.parse_content_stream", malformed_content):
                with self.assertRaisesRegex(PDFError, "inspecté") as caught:
                    sanitize_pdf(make_pdf())
        self.assertEqual([], emitted)
        self.assertNotIn(AUXILIARY_MARKER, str(caught.exception))

    def test_jpeg_is_not_recompressed(self):
        jpeg = BytesIO()
        with Image.open(BytesIO(scan_image())) as image:
            image.save(jpeg, format="JPEG", quality=80)
        with pymupdf.open() as document:
            page = document.new_page(width=300, height=400)
            page.insert_image(page.rect, stream=jpeg.getvalue())
            source = document.tobytes()
        result = sanitize_pdf(source)
        with pikepdf.Pdf.open(BytesIO(source)) as a, pikepdf.Pdf.open(BytesIO(result)) as b:
            original_image = next(iter(a.pages[0].get_images().values()))
            cleaned_image = next(iter(b.pages[0].get_images().values()))
            self.assertEqual(original_image.read_raw_bytes(), cleaned_image.read_raw_bytes())
        self.assertEqual(render_and_extract(source)[0].tobytes(), render_and_extract(result)[0].tobytes())

    def test_incremental_revisions_rewritten_and_identifiers_regenerated(self):
        previous, source = incremental_pdf()
        self.assertTrue(source.startswith(previous))
        with pikepdf.Pdf.open(BytesIO(previous)) as original:
            self.assertEqual(AUXILIARY_MARKER + "-OLD", str(original.docinfo.Title))
        with pikepdf.Pdf.open(BytesIO(source)) as current:
            self.assertIn("/Prev", current.trailer)
            self.assertEqual(AUXILIARY_MARKER + "-CURRENT", str(current.docinfo.Title))
            previous_ids = [bytes(value) for value in current.trailer.ID]
        result = sanitize_pdf(source)
        with pikepdf.Pdf.open(BytesIO(result), attempt_recovery=False) as document:
            self.assertNotIn("/Prev", document.trailer)
            self.assertNotIn("/Info", document.trailer)
            self.assertTrue(set(previous_ids).isdisjoint(bytes(value) for value in document.trailer.ID))
            # Vérification sur tous les objets courants, pas seulement docinfo.
            self.assertFalse(any(isinstance(obj, pikepdf.Dictionary) and "/Title" in obj
                                 for obj in document.objects))
        self.assertEqual(1, result.count(b"\nstartxref\n"))
        with pymupdf.open(stream=result) as independent:
            self.assertFalse(independent.is_repaired)
            self.assertEqual("null", independent.xref_get_key(-1, "Prev")[0])
            self.assertFalse(independent.metadata.get("title"))
        before = render_and_extract(source)
        after = render_and_extract(result)
        self.assertEqual(before[0].tobytes(), after[0].tobytes())
        self.assertEqual(before[1:], after[1:])

    def test_simple_documents_keep_text_and_scan_pixels(self):
        for kind in ("native", "scan", "ocr", "mixed"):
            with self.subTest(kind=kind):
                source = make_pdf(kind, rotation=270, cropped=True)
                result = sanitize_pdf(source)
                before, after = render_and_extract(source), render_and_extract(result)
                self.assertEqual(before[0].tobytes(), after[0].tobytes())
                self.assertEqual(before[1:], after[1:])
                with pikepdf.Pdf.open(BytesIO(source)) as a, pikepdf.Pdf.open(BytesIO(result)) as b:
                    def images(pdf):
                        return [pikepdf.PdfImage(obj).as_pil_image().tobytes()
                                for obj in pdf.objects if isinstance(obj, pikepdf.Stream)
                                and obj.get("/Subtype") == pikepdf.Name.Image]
                    self.assertEqual(images(a), images(b))


if __name__ == "__main__":
    unittest.main()
