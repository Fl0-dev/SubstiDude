# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Frontières avec plafonds réduits, sans allocation démesurée."""

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import pikepdf
import pymupdf

from fixtures import TARGET_RECT, image_variant_pdf, make_pdf
import substidude.pdf_engine as engine


def stream_pdf(contents, encoding="flate", *, data=None):
    with pikepdf.Pdf.open(BytesIO(make_pdf() if data is None else data)) as document:
        for payload in contents:
            stream = document.make_stream(b"")
            if encoding == "flate":
                stream.write(zlib.compress(payload), filter=pikepdf.Name.FlateDecode)
            elif encoding == "hex":
                stream.write(payload.hex().encode() + b">", filter=pikepdf.Name.ASCIIHexDecode)
            else:
                stream.write(payload)
            document.pages[0].obj.Contents.append(stream)
        result = BytesIO()
        document.save(result, compress_streams=False)
        return result.getvalue()


class ResourceLimitTests(unittest.TestCase):
    def test_expansion_refused_before_content_parser_or_mupdf(self):
        source = stream_pdf([b"%" + b"X" * 4096 + b"\n"])
        with patch.object(engine, "MAX_RESOURCE_STREAM_BYTES", 600_000), \
                patch.object(engine, "MAX_TOTAL_DECODED_STREAM_BYTES", 583_000), \
                patch.object(pikepdf, "parse_content_stream") as parse, \
                patch.object(engine, "_open_mupdf") as native:
            for operation in (engine.sanitize_pdf,
                              lambda data: engine.classify_zone(data, 0, TARGET_RECT)):
                with self.assertRaisesRegex(engine.PDFError, "flux décompressés"):
                    operation(source)
            with tempfile.TemporaryDirectory(prefix="substidude-test-") as directory:
                path = Path(directory) / "synthetic.pdf"
                path.write_bytes(source)
                with self.assertRaises(engine.PDFError):
                    engine.open_pdf(path)
                self.assertEqual(source, path.read_bytes())
            parse.assert_not_called()
            native.assert_not_called()

    def test_individual_and_aggregate_stream_boundaries(self):
        for encoding in ("flate", "hex", "raw"):
            with self.subTest(encoding=encoding):
                # Programme de police de la fixture : 569208 octets, inférieur au plafond réduit.
                for size, accepted in ((600_000, True), (600_001, False)):
                    source = stream_pdf([b"%" + b"X" * (size - 2) + b"\n"], encoding)
                    with patch.object(engine, "MAX_RESOURCE_STREAM_BYTES", 600_000):
                        if accepted:
                            engine.sanitize_pdf(source)
                        else:
                            with self.assertRaisesRegex(engine.PDFError, "flux décompressés"):
                                engine.sanitize_pdf(source)
        source = stream_pdf([b"%AAA\n", b"%BBBB\n"])
        with pikepdf.Pdf.open(BytesIO(source)) as document:
            total = sum(len(obj.read_bytes()) for obj in document.objects
                        if isinstance(obj, pikepdf.Stream))
        for limit, accepted in ((total, True), (total - 1, False)):
            with self.subTest(total_limit=limit), patch.object(engine, "MAX_TOTAL_DECODED_STREAM_BYTES", limit):
                if accepted:
                    engine.sanitize_pdf(source)
                else:
                    with self.assertRaises(engine.PDFError):
                        engine.sanitize_pdf(source)

    def test_encoded_stream_is_counted_without_qpdf_decoding_it(self):
        source = stream_pdf([b"%" + b"X" * 600_000 + b"\n"])
        with patch.object(engine, "MAX_RESOURCE_STREAM_BYTES", 600_000), \
                patch.object(pikepdf.Object, "read_bytes", side_effect=AssertionError("unbounded decode")):
            with self.assertRaises(engine.PDFError):
                engine.sanitize_pdf(source)

    def test_render_limit_checked_before_allocation_and_inclusive(self):
        with pymupdf.open(stream=make_pdf()) as document:
            page = document[0]
            for limit, accepted in ((480_000, True), (479_999, False)):
                with self.subTest(limit=limit), patch.object(engine, "MAX_RENDER_PIXELS", limit), \
                        patch.object(pymupdf.Page, "get_pixmap") as raster:
                    if accepted:
                        engine.render_page(page, 2)
                        raster.assert_called_once()
                    else:
                        with self.assertRaises(engine.PDFError):
                            engine.render_page(page, 2)
                        raster.assert_not_called()
            for scale in (0, -1, float("inf"), float("nan"), 1e300):
                with self.subTest(scale=scale), patch.object(pymupdf.Page, "get_pixmap") as raster:
                    with self.assertRaises(engine.PDFError):
                        engine.render_page(page, scale)
                    raster.assert_not_called()

    def test_image_budget_distinct_from_font_and_content_budget(self):
        for source in (make_pdf("ocr"), image_variant_pdf("jpeg")):
            for limit, accepted in ((1_440_000, True), (1_439_999, False)):
                with self.subTest(limit=limit), \
                        patch.object(engine, "MAX_RESOURCE_STREAM_BYTES", 600_000), \
                        patch.object(engine, "MAX_IMAGE_STREAM_BYTES", limit):
                    if accepted:
                        engine.sanitize_pdf(source)
                    else:
                        with self.assertRaisesRegex(engine.PDFError, "flux décompressés"):
                            engine.sanitize_pdf(source)

    def test_flate_chunk_boundaries_and_truncation(self):
        with pikepdf.Pdf.new() as document:
            for size in (65_535, 65_536, 65_537, 200_000):
                with self.subTest(size=size):
                    stream = document.make_stream(b"")
                    stream.write(zlib.compress(b"X" * size), filter=pikepdf.Name.FlateDecode)
                    self.assertEqual(size, engine._bounded_stream_size(stream, size))
                    with self.assertRaises(engine.PDFError):
                        engine._bounded_stream_size(stream, size - 1)
            stream.write(zlib.compress(b"X" * 100)[:-1], filter=pikepdf.Name.FlateDecode)
            with self.assertRaises(engine.PDFError):
                engine._bounded_stream_size(stream, 1000)

    def test_asciihex_whitespace_and_odd_digit(self):
        with pikepdf.Pdf.new() as document:
            stream = document.make_stream(b"")
            stream.write(b"\t4 1 4\n2 F>", filter=pikepdf.Name.ASCIIHexDecode)
            self.assertEqual(3, engine._bounded_stream_size(stream, 3))
            with self.assertRaises(engine.PDFError):
                engine._bounded_stream_size(stream, 2)

    def test_final_stream_contamination_blocks_the_pipeline(self):
        from test_pipeline import replace_zones

        def contaminate(data):
            return stream_pdf([b"%" + b"X" * 600_000 + b"\n"], data=engine.sanitize_pdf(data))

        with patch.object(engine, "MAX_RESOURCE_STREAM_BYTES", 600_000), \
                patch("test_pipeline.sanitize_pdf", contaminate):
            with self.assertRaisesRegex(engine.PDFError, "flux décompressés"):
                replace_zones(make_pdf(), [(0, TARGET_RECT, "Toto")])
