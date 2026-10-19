# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Structures natives synthétiques, jamais une facture ou ses données réelles."""

from hashlib import sha256
from io import BytesIO
import unittest
import zlib
import re
import json
import struct
from PIL import Image, ImageDraw

import pikepdf
import pymupdf

from fixtures import FONT, TARGET, TARGET_RECT, make_pdf
from substidude.model import Substitution
from substidude.pdf_engine import PDFError, classify_zone, sanitize_pdf
from substidude.pipeline import transform
import test_pipeline
from test_independent import render_and_extract


def missing_self_xref_pdf(data=None, *, free_entry=False):
    """Index cohérent sauf l'entrée propre du flux XRef : cas qpdf précisément connu."""
    with pikepdf.Pdf.open(BytesIO(make_pdf() if data is None else data)) as document:
        output = BytesIO()
        document.save(output, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=False)
    source = output.getvalue()
    offset = int(re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", source)[1])
    with pikepdf.Pdf.open(BytesIO(source)) as document:
        number = int(document.trailer.Size) - 1
        stream = document.get_object((number, 0))
        width = sum(stream.W)
        payload = stream.read_bytes()
        fields = pikepdf.Dictionary({key: value for key, value in stream.items()
                                     if key not in {"/Filter", "/DecodeParms", "/Length"}})
        if free_entry:
            payload = payload[:-width] + b"\x00" * width
        else:
            payload = payload[:-width]
            fields.Index = [0, number]
        fields.Length = len(payload)
        dictionary = fields.unparse()
    return (source[:offset] + f"{number} 0 obj\n".encode() + dictionary + b"\nstream\n"
            + payload + b"\nendstream\nendobj\nstartxref\n" + str(offset).encode() + b"\n%%EOF\n")


def native_layout_pdf(*, nested=True, clipped=False):
    with pymupdf.open(stream=native_font_pdf("type1")) as document:
        page = document[0]
        page.draw_rect((30, 60, 270, 120), width=0.5)
        for index, rectangle in enumerate(((5, 5, 25, 25), (270, 360, 290, 380))):
            encoded = BytesIO()
            image = Image.new("RGBA", (8, 8), (30 + index * 80, 60, 90, 120 + index * 20))
            ImageDraw.Draw(image).point((index, 0), fill=(0, 0, 0, 255))
            image.save(encoded, format="PNG")
            page.insert_image(rectangle, stream=encoded.getvalue())
        # Une petite image indexée, hors zone ; aucune substitution raster admise.
        encoded = BytesIO()
        Image.new("RGB", (4, 4), "white").save(encoded, format="PNG")
        palette_xref = page.insert_image((5, 350, 25, 370), stream=encoded.getvalue())
        data = document.tobytes()
    with pikepdf.Pdf.open(BytesIO(data)) as document:
        for image in list(document.objects):
            if not isinstance(image, pikepdf.Stream) or image.get("/Subtype") != pikepdf.Name.Image:
                continue
            if image.objgen[0] == palette_xref:
                image.ColorSpace = pikepdf.Array([pikepdf.Name.Indexed, pikepdf.Name.DeviceRGB, 1,
                                                pikepdf.String(b"\xff\xff\xff\x00\x00\x00")])
                image.BitsPerComponent = 1
                image.write(zlib.compress(b"\x00\xf0\x00\xf0"), filter=pikepdf.Name.FlateDecode)
            else:
                channels = 1 if image.ColorSpace == pikepdf.Name.DeviceGray else 3
                raw = image.read_bytes()
                row = image.Width * channels
                encoded = b"".join(b"\x00" + raw[offset:offset + row] for offset in range(0, len(raw), row))
                image.write(zlib.compress(encoded), filter=pikepdf.Name.FlateDecode)
                image.DecodeParms = pikepdf.Dictionary(Predictor=15, Columns=image.Width, Colors=channels, BitsPerComponent=8)
        output = BytesIO()
        document.save(output)
        data = output.getvalue()
    if nested:
        for _ in range(2):
            with pymupdf.open(stream=data) as original, pymupdf.open() as document:
                document.new_page(width=300, height=400).show_pdf_page(pymupdf.Rect(0, 0, 300, 400), original, 0)
                data = document.tobytes()
    with pikepdf.Pdf.open(BytesIO(data)) as document:
        document.pages[0].obj.Group = pikepdf.Dictionary(Type=pikepdf.Name.Group, S=pikepdf.Name.Transparency, CS=pikepdf.Name.DeviceRGB)
        for form in list(document.objects):
            if isinstance(form, pikepdf.Stream) and form.get("/Subtype") == pikepdf.Name.Form:
                form.Group = pikepdf.Dictionary(Type=pikepdf.Name.Group, S=pikepdf.Name.Transparency)
                if clipped:
                    form.write(b"q 0 0 300 400 re W n\n" + form.read_bytes() + b"\nQ")
        output = BytesIO()
        document.save(output)
        return output.getvalue()


def unicode_map():
    mappings = b"\n".join(f"<{code:02X}> <{code:04X}>".encode() for code in range(32, 127))
    return (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            b"/CMapName /SyntheticUnicode def /CMapType 2 def\n"
            b"1 begincodespacerange <00> <FF> endcodespacerange\n95 beginbfchar\n"
            + mappings + b"\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end")


def native_font_pdf(kind):
    with pikepdf.Pdf.open(BytesIO(make_pdf())) as document:
        page = document.pages[0]
        if kind == "cid-coverage":
            descriptor = next(iter(page.obj.Resources.Font.values())).DescendantFonts[0].FontDescriptor
            descriptor.MissingWidth = 0
            descriptor.CIDSet = document.make_stream(b"\xff" * 32)
        else:
            font = pikepdf.Dictionary(Type=pikepdf.Name.Font, BaseFont=pikepdf.Name.Helvetica,
                                     Subtype=pikepdf.Name.Type1, Encoding=pikepdf.Name.WinAnsiEncoding,
                                     ToUnicode=document.make_stream(unicode_map()))
            if kind in {"truetype", "truetype-unused-last"}:
                descriptor = next(iter(page.obj.Resources.Font.values())).DescendantFonts[0].FontDescriptor
                descriptor.MissingWidth = 0
                metrics = pymupdf.Font(fontfile=str(FONT))
                font.Subtype, font.BaseFont = pikepdf.Name.TrueType, descriptor.FontName
                font.FirstChar, font.LastChar = 32, 126
                font.Widths = [round(metrics.glyph_advance(code) * 1000) for code in range(32, 127)]
                font.FontDescriptor = descriptor
                if kind == "truetype-unused-last":
                    font.LastChar = 127
            page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Synthetic=document.make_indirect(font)))
            page.obj.Contents = document.make_stream(
                b"q BT /Synthetic 16 Tf 1 0 0 1 40 305 Tm [(SECRET-CIBLE-123)] TJ ET Q\n"
                b"q BT /Synthetic 16 Tf 1 0 0 1 40 225 Tm [(TEMOIN-CONSERVE)] TJ ET Q")
        output = BytesIO()
        document.save(output)
        return output.getvalue()


class NativeFontTests(unittest.TestCase):
    def test_type1_unicode_simple_truetype_and_cid_coverage(self):
        for kind in ("type1", "truetype", "truetype-unused-last", "cid-coverage"):
            with self.subTest(kind=kind):
                source = native_font_pdf(kind)
                digest = sha256(source).digest()
                self.assertEqual("native", classify_zone(source, 0, TARGET_RECT))
                result = transform(source, [Substitution(0, TARGET_RECT, "Société Élodie")])
                text = test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Société Élodie")])
                self.assertNotIn(TARGET, text)
                self.assertIn("Société Élodie", text)
                self.assertEqual(digest, sha256(source).digest())

    def test_font_coverage_metadata_is_removed_without_changing_render(self):
        source = native_font_pdf("cid-coverage")
        result = sanitize_pdf(source)
        self.assertEqual(render_and_extract(source)[0].tobytes(), render_and_extract(result)[0].tobytes())
        with pikepdf.Pdf.open(BytesIO(result)) as document:
            self.assertFalse(any(isinstance(obj, pikepdf.Dictionary) and "/CIDSet" in obj for obj in document.objects))

    def test_new_font_containers_do_not_allow_hidden_references(self):
        for kind in ("type1", "truetype", "cid-coverage"):
            for feature in ("unicode-reference", "unknown-font-property", "numeric-reference"):
                with self.subTest(kind=kind, feature=feature):
                    with pikepdf.Pdf.open(BytesIO(native_font_pdf(kind))) as document:
                        font = next(iter(document.pages[0].obj.Resources.Font.values()))
                        if feature == "unicode-reference":
                            font.ToUnicode.Private = document.make_stream(b"SYNTHETIC-AUXILIARY")
                        elif feature == "unknown-font-property":
                            font.Private = document.make_stream(b"SYNTHETIC-AUXILIARY")
                        elif kind == "truetype":
                            font.Widths[0] = document.make_stream(b"SYNTHETIC-AUXILIARY")
                        elif kind == "cid-coverage":
                            font.DescendantFonts[0].FontDescriptor.CIDSet.Private = document.make_stream(b"SYNTHETIC-AUXILIARY")
                        else:
                            font.ToUnicode.DecodeParms = pikepdf.Dictionary(Private=document.make_stream(b"SYNTHETIC-AUXILIARY"))
                        output = BytesIO()
                        document.save(output)
                    with self.assertRaises(PDFError):
                        sanitize_pdf(output.getvalue())

    def test_known_self_xref_omission_qualifies_source_but_not_a_final_result(self):
        from unittest.mock import patch
        from substidude import pipeline
        for free in (False, True):
            with self.subTest(free=free):
                source = missing_self_xref_pdf(free_entry=free)
                with pikepdf.Pdf.open(BytesIO(source), attempt_recovery=False) as inspected:
                    self.assertEqual(0 if free else 1, len(inspected.get_warnings()))
                with pymupdf.open(stream=source) as inspected:
                    self.assertFalse(inspected.is_repaired)
                self.assertEqual("native", classify_zone(source, 0, TARGET_RECT))
                result = transform(source, [Substitution(0, TARGET_RECT, "Toto")])
                test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Toto")])
                with pikepdf.Pdf.open(BytesIO(result), attempt_recovery=False) as inspected:
                    self.assertEqual([], inspected.get_warnings())
        cleanup = pipeline.sanitize_pdf
        with patch.object(pipeline, "sanitize_pdf", lambda value: missing_self_xref_pdf(cleanup(value))):
            with self.assertRaisesRegex(PDFError, "anomalies"):
                transform(make_pdf(), [Substitution(0, TARGET_RECT, "Toto")])


class NativeLayoutTests(unittest.TestCase):
    def test_worker_generates_real_preview_and_explains_hidden_clip_refusal(self):
        from substidude.worker import PDFJob, WorkerError
        job = PDFJob()
        self.addCleanup(job.cancel)
        for hidden in (False, True):
            with self.subTest(hidden=hidden):
                with pikepdf.Pdf.open(BytesIO(native_font_pdf("type1"))) as document:
                    content = document.pages[0].obj.Contents
                    path = b"0 0 50 50 re" if hidden else b"30 200 240 140 re"
                    content.write(b"q " + path + b" W n\n" + content.read_bytes() + b"\nQ")
                    output = BytesIO()
                    document.save(output)
                    source = output.getvalue()
                job.start("generate", source, substitutions=[Substitution(0, TARGET_RECT, "Toto")])
                if hidden:
                    with self.assertRaisesRegex(WorkerError, "découpage graphique") as caught:
                        job.receive()
                    self.assertNotIn(TARGET, str(caught.exception))
                else:
                    payload = job.receive()
                    size, = struct.unpack_from(">I", payload)
                    self.assertEqual(["native"], json.loads(payload[4:4 + size])["modes"])
                    result = payload[4 + size:]
                    self.assertTrue(result.startswith(b"%PDF-"))
                    job.start("render", result, page=0, scale=1)
                    rendered = job.receive()
                    width, height = struct.unpack_from(">II", rendered)
                    self.assertEqual(8 + width * height * 3, len(rendered))

    def test_fractional_native_zone_does_not_paint_a_border_outside_selection(self):
        source = native_font_pdf("type1")
        rectangle = (35.75, 70.75, 259.25, 104.25)
        result = transform(source, [Substitution(0, rectangle, "Toto")])
        test_pipeline.PipelineTests().assert_local_render(source, result, [(0, rectangle, "Toto")])

    def test_identical_but_distinct_image_objects_are_kept_if_invoked(self):
        with pikepdf.Pdf.open(BytesIO(native_layout_pdf(nested=False))) as document:
            page = document.pages[0]
            image = next(obj for obj in document.objects if isinstance(obj, pikepdf.Stream)
                         and obj.get("/Subtype") == pikepdf.Name.Image and "/SMask" in obj)
            duplicate = document.make_stream(image.read_raw_bytes())
            for key, value in image.items():
                if key != "/Length":
                    duplicate[key] = value
            page.obj.Resources.XObject.Duplicate = duplicate
            page.obj.Contents.append(document.make_stream(b"q 10 0 0 10 270 340 cm /Duplicate Do Q"))
            output = BytesIO()
            document.save(output)
            source = output.getvalue()
        result = transform(source, [Substitution(0, TARGET_RECT, "Toto")])
        test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Toto")])

    def test_rectangular_clips_containing_all_text_are_qualified(self):
        paths = (b"30 200 240 140 re", b"30 200 m 270 200 l 270 340 l 30 340 l h",
                 b"30 200 m 270 200 l 270 340 l 30 340 l 30 200 l h",
                 b"270 340 -240 -140 re")
        for path in paths:
            for nested in (False, True):
                with self.subTest(path=path, nested=nested):
                    with pikepdf.Pdf.open(BytesIO(native_font_pdf("type1"))) as document:
                        content = document.pages[0].obj.Contents
                        content.write(b"q " + path + b" W n\n" + content.read_bytes() + b"\nQ")
                        output = BytesIO()
                        document.save(output)
                        source = output.getvalue()
                    if nested:
                        with pymupdf.open(stream=source) as original, pymupdf.open() as document:
                            document.new_page(width=300, height=400).show_pdf_page(pymupdf.Rect(0, 0, 300, 400), original, 0)
                            source = document.tobytes()
                    result = transform(source, [Substitution(0, TARGET_RECT, "Toto")])
                    test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Toto")])

    def test_partial_hidden_and_nested_clipped_text_remain_refused(self):
        paths = (b"0 0 50 50 re", b"50 300 200 30 re",  # caché / caractère tronqué
                 b"30 200 m 270 200 l 270 340 l 30 340 l h 100 250 50 50 re",  # trou pair-impair
                 b"30 200 m 270 200 l 270 340 l 30 340 l h 0 0 m",  # sous-chemin supplémentaire
                 b"1 0.5 0 1 0 0 cm 0 0 300 400 re")  # enveloppe != rectangle
        for path in paths:
            for nested in (False, True):
                with self.subTest(path=path, nested=nested):
                    with pikepdf.Pdf.open(BytesIO(native_font_pdf("type1"))) as document:
                        page = document.pages[0]
                        content = page.obj.Contents.read_bytes()
                        if nested:
                            form = document.make_stream(content)
                            form.Type, form.Subtype = pikepdf.Name.XObject, pikepdf.Name.Form
                            form.BBox, form.Resources = [0, 0, 300, 400], page.obj.Resources
                            page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Child=form))
                            content = b"/Child Do"
                        # Un q/Q intermédiaire ne doit pas lever le clip hérité.
                        page.obj.Contents = document.make_stream(b"q " + path + b" W* n q\n" + content + b"\nQ Q")
                        output = BytesIO()
                        document.save(output)
                    with self.assertRaises(PDFError):
                        transform(output.getvalue(), [Substitution(0, TARGET_RECT, "Toto")])

    def test_nonrectangular_image_clip_is_preserved_and_state_restored(self):
        with pymupdf.open(stream=native_font_pdf("type1")) as document:
            encoded = BytesIO()
            Image.new("RGB", (8, 8), "blue").save(encoded, format="PNG")
            document[0].insert_image((5, 5, 25, 25), stream=encoded.getvalue(), overlay=False)
            source = document.tobytes()
        with pikepdf.Pdf.open(BytesIO(source)) as document:
            for stream in document.pages[0].obj.Contents:
                if any(str(item.operator) == "Do" for item in pikepdf.parse_content_stream(stream)):
                    stream.write(b"q 5 375 m 25 375 l 15 395 l h W n\n" + stream.read_bytes() + b"\nQ")
            output = BytesIO()
            document.save(output)
            source = output.getvalue()
        result = transform(source, [Substitution(0, TARGET_RECT, "Toto")])
        test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Toto")])

    def test_unknown_groups_cycles_and_singular_forms_are_refused(self):
        for feature in ("group-property", "singular-form", "cycle", "hidden-bbox-text"):
            with self.subTest(feature=feature):
                with pikepdf.Pdf.open(BytesIO(native_layout_pdf())) as document:
                    form = next(obj for obj in document.objects if isinstance(obj, pikepdf.Stream)
                                and obj.get("/Subtype") == pikepdf.Name.Form)
                    if feature == "group-property":
                        document.pages[0].obj.Group.Private = document.make_stream(b"SYNTHETIC-HIDDEN")
                    elif feature == "singular-form":
                        form.Matrix = [0, 0, 0, 0, 0, 0]
                    elif feature == "cycle":
                        form.Resources.XObject = pikepdf.Dictionary(Recursive=form)
                        form.write(b"/Recursive Do")
                    else:
                        form.BBox = [0, 0, 5, 5]
                    output = BytesIO()
                    document.save(output)
                with self.assertRaises(PDFError):
                    transform(output.getvalue(), [Substitution(0, TARGET_RECT, "Toto")])

    def test_nested_forms_table_lines_and_images_conserved(self):
        for nested in (False, True):
            for clipped in (False, True):
                with self.subTest(nested=nested, clipped=clipped):
                    source = native_layout_pdf(nested=nested, clipped=clipped)
                    digest = sha256(source).digest()
                    self.assertEqual("native", classify_zone(source, 0, TARGET_RECT))
                    result = transform(source, [Substitution(0, TARGET_RECT, "Société Élodie")])
                    text = test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Société Élodie")])
                    self.assertNotIn(TARGET, text)
                    self.assertIn("Société Élodie", text)
                    self.assertEqual(digest, sha256(source).digest())

    def test_crossing_vectors_and_raster_with_multiple_images_remain_refused(self):
        source = native_layout_pdf()
        for rectangle in ((25, 70, 270, 105), (0, 0, 30, 30)):
            with self.subTest(rectangle=rectangle), self.assertRaises(PDFError):
                transform(source, [Substitution(0, rectangle, "Toto")])

    def test_hidden_form_and_image_changes_block_the_result(self):
        from unittest.mock import patch
        from substidude import pipeline
        cleanup = pipeline.sanitize_pdf
        for feature in ("extra-form", "image-pixels", "image-palette"):
            def contaminate(data):
                with pikepdf.Pdf.open(BytesIO(cleanup(data))) as document:
                    if feature == "extra-form":
                        form = document.make_stream(b"BT /Unknown 12 Tf (SYNTHETIC-HIDDEN) Tj ET")
                        form.Type, form.Subtype = pikepdf.Name.XObject, pikepdf.Name.Form
                        form.BBox, form.Resources = [0, 0, 300, 400], pikepdf.Dictionary()
                        document.pages[0].obj.Resources.XObject.Hidden = form
                    else:
                        images = [obj for obj in document.objects if isinstance(obj, pikepdf.Stream)
                                  and obj.get("/Subtype") == pikepdf.Name.Image]
                        if feature == "image-pixels":
                            image = images[0]
                            image.write(image.read_bytes()[::-1])
                        else:
                            image = next(obj for obj in images if isinstance(obj.ColorSpace, pikepdf.Array)
                                         and obj.ColorSpace[0] == pikepdf.Name.Indexed)
                            image.ColorSpace[3] = pikepdf.String(b"\xff\x00\x00\x00\x00\x00")
                    output = BytesIO()
                    document.save(output)
                    return output.getvalue()
            with self.subTest(feature=feature), patch.object(pipeline, "sanitize_pdf", contaminate):
                with self.assertRaises(PDFError):
                    transform(native_layout_pdf(), [Substitution(0, TARGET_RECT, "Toto")])

    def test_used_missing_font_width_and_effective_clipping_are_refused(self):
        with pikepdf.Pdf.open(BytesIO(native_font_pdf("truetype-unused-last"))) as document:
            document.pages[0].obj.Contents = document.make_stream(
                document.pages[0].obj.Contents.read_bytes() + b"\nBT /Synthetic 16 Tf 40 200 Td (\x7f) Tj ET")
            output = BytesIO()
            document.save(output)
        with self.assertRaises(PDFError):
            classify_zone(output.getvalue(), 0, TARGET_RECT)
        with pikepdf.Pdf.open(BytesIO(native_layout_pdf())) as document:
            form = next(obj for obj in document.objects if isinstance(obj, pikepdf.Stream)
                        and obj.get("/Subtype") == pikepdf.Name.Form)
            form.write(b"q 0 0 50 50 re W n\n" + form.read_bytes() + b"\nQ")
            output = BytesIO()
            document.save(output)
        with self.assertRaises(PDFError):
            classify_zone(output.getvalue(), 0, TARGET_RECT)


if __name__ == "__main__":
    unittest.main()
