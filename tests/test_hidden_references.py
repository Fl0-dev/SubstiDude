# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Qualification des références, distincte de celle des octets des programmes de police."""

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pikepdf
import pymupdf

from fixtures import AUXILIARY_MARKER, TARGET_RECT, hidden_reference_pdf, make_pdf
from substidude.pdf_engine import PDFError, classify_zone, open_pdf, sanitize_pdf
from test_pipeline import replace_zones
import test_pipeline


class HiddenReferenceTests(unittest.TestCase):
    def test_unknown_references_refused_before_transformation(self):
        for feature in ("icc", "font", "descriptor", "font-program", "cmap", "content",
                        "cid-info", "font-name", "font-widths", "icc-alternate", "unused-font"):
            with self.subTest(feature=feature):
                source = hidden_reference_pdf(feature)
                # Le marqueur est dans un flux décodé, pas forcément dans les octets PDF.
                with pikepdf.Pdf.open(BytesIO(source)) as document:
                    self.assertTrue(any(isinstance(obj, pikepdf.Stream)
                                        and obj.read_bytes() == AUXILIARY_MARKER.encode()
                                        for obj in document.objects))
                with patch.object(pymupdf.Page, "apply_redactions") as redact:
                    for operation in (sanitize_pdf,
                                      lambda data: classify_zone(data, 0, TARGET_RECT),
                                      lambda data: replace_zones(data, [(0, TARGET_RECT, "Toto")])):
                        with self.assertRaises(PDFError) as caught:
                            operation(source)
                        self.assertNotIn(AUXILIARY_MARKER, str(caught.exception))
                    redact.assert_not_called()
                with tempfile.TemporaryDirectory(prefix="substidude-test-") as directory:
                    path = Path(directory) / "synthetic.pdf"
                    path.write_bytes(source)
                    with self.assertRaises(PDFError):
                        open_pdf(path)
                    self.assertEqual(source, path.read_bytes())

    def test_rewrite_alone_preserves_referenced_residual_stream(self):
        # Contre-exemple sans contrôle de production : une réécriture n'est pas un nettoyage.
        for feature in ("icc", "font", "descriptor", "font-program", "cmap", "cid-info"):
            with self.subTest(feature=feature):
                with pymupdf.open(stream=hidden_reference_pdf(feature)) as document:
                    document[0].add_redact_annot(TARGET_RECT)
                    document[0].apply_redactions(images=0, graphics=0, text=0)
                    rewritten = document.tobytes(garbage=4, deflate=True)
                with pikepdf.Pdf.open(BytesIO(rewritten)) as document:
                    output = BytesIO()
                    document.save(output)
                # MuPDF relit la sortie qpdf : pas seulement qpdf qui se contrôle lui-même.
                with pymupdf.open(stream=output.getvalue()) as document:
                    self.assertTrue(any(document.xref_is_stream(xref)
                                        and document.xref_stream(xref) == AUXILIARY_MARKER.encode()
                                        for xref in range(1, document.xref_length())))

    def test_final_reference_contamination_blocks_result(self):
        def contaminate(data):
            with pikepdf.Pdf.open(BytesIO(sanitize_pdf(data))) as document:
                image, = document.pages[0].get_images().values()
                image.ColorSpace[1].Private = document.make_stream(AUXILIARY_MARKER.encode())
                output = BytesIO()
                document.save(output)
                return output.getvalue()

        with patch("substidude.pipeline.sanitize_pdf", contaminate):
            with self.assertRaises(PDFError) as caught:
                replace_zones(make_pdf("ocr"), [(0, TARGET_RECT, "Toto")])
        self.assertNotIn(AUXILIARY_MARKER, str(caught.exception))

    def test_unreferenced_stream_is_removed(self):
        with pymupdf.open(stream=make_pdf("ocr")) as document:
            xref = document.get_new_xref()
            document.update_object(xref, "<< >>")
            document.update_stream(xref, AUXILIARY_MARKER.encode())
            source = document.tobytes(garbage=0)
        with pikepdf.Pdf.open(BytesIO(source)) as document:
            self.assertTrue(any(isinstance(obj, pikepdf.Stream)
                                and obj.read_bytes() == AUXILIARY_MARKER.encode()
                                for obj in document.objects))
        result = replace_zones(source, [(0, TARGET_RECT, "Toto")])
        with pikepdf.Pdf.open(BytesIO(result)) as document:
            self.assertFalse(any(isinstance(obj, pikepdf.Stream)
                                 and obj.read_bytes() == AUXILIARY_MARKER.encode()
                                 for obj in document.objects))


if __name__ == "__main__":
    unittest.main()
