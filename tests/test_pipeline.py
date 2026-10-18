# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Parcours expérimental sur corpus synthétique, pas une API d'export utilisateur."""

from collections import Counter
from hashlib import sha256
from io import BytesIO
import unittest
from unittest.mock import patch

import pikepdf
import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

from fixtures import (
    FONT, KEPT, TARGET, TARGET_RECT, auxiliary_pdf, make_pdf, repeated_images_pdf,
    shared_text_pdf, zone_case_pdf,
)
from substidude.pdf_engine import (
    PDFError, _check_simple_page, _open_mupdf, _open_supported_structure, _pdf_objects,
    classify_zone, page_to_view_matrix, sanitize_pdf,
)
from test_independent import render_and_extract, text_runs
import test_independent


FONT_NAME = "substidudePrototype"
REPLACEMENTS = ("Société Élodie", "Toto")
SECOND_RECT = (35, 150, 260, 185)


def image_key(image):
    return image.size, sha256(image.convert("RGB").tobytes()).digest()


def image_objects(document):
    return [xref for xref in range(1, document.xref_length())
            if document.xref_get_key(xref, "Subtype") == ("name", "/Image")]


def outside_characters(page, rectangles):
    # Les identités de glyphes dépendent des polices ; comparer Unicode, type et géométrie.
    return Counter((span["type"], span["opacity"], span["font"], span["color"],
                    char[0], tuple(round(v, 3) for v in char[3]))
                   for span in page.get_texttrace() for char in span["chars"]
                   if not any(pymupdf.Rect(char[3]).intersects(rect) for rect in rectangles))


def verify_result(result, geometry, outside_text, plan, expected_images):
    """Contrôles par résultat de cette expérience ; pas une qualification PDF générale."""
    with _open_supported_structure(result) as structure, _open_mupdf(result) as document:
        if len(geometry) != document.page_count or structure.check_pdf_syntax():
            raise PDFError("Le résultat n'a pas conservé la structure attendue.")
        if ("/Prev" in structure.trailer or "/Info" in structure.trailer
                or any(set(obj.keys()) & {"/Info", "/Metadata", "/Thumb"}
                       for obj in _pdf_objects(structure.objects) if not isinstance(obj, pikepdf.Array))):
            raise PDFError("Le nettoyage des contenus auxiliaires n'est pas vérifié.")
        for number, page in enumerate(document):
            if (tuple(page.mediabox), tuple(page.cropbox), page.rotation) != geometry[number]:
                raise PDFError("La géométrie des pages a changé.")
            rectangles = [rect for n, rect, _, _ in plan if n == number]
            if outside_characters(page, rectangles) != outside_text[number]:
                raise PDFError("Du texte hors zone a changé.")
        for number, rect, text, mode in plan:
            if document[number].get_textbox(rect) != (text if mode == "native" else ""):
                raise PDFError("Le retrait du texte ou son remplacement n'est pas vérifié.")
            if mode == "native" and any(
                span["type"] != 0 or span["opacity"] != 1
                for span in document[number].get_texttrace()
                if any(pymupdf.Rect(char[3]).intersects(rect) for char in span["chars"])
            ):
                raise PDFError("Le remplacement natif n'est pas du texte visible opaque.")
        recovered = Counter()
        for xref in image_objects(document):
            with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                recovered[image_key(image)] += 1
        if recovered != Counter(expected_images.values()):
            raise PDFError("Les images récupérables ne correspondent pas aux pixels attendus.")


def replace_zones(source, zones):
    """Expérience : tuples (page, rectangle, texte), fond blanc et police 14 pt fixes.

    Aucun fichier écrit. La phase 2 consolidera ce parcours après qualification du moteur.
    """
    try:
        if type(source) is not bytes or not isinstance(zones, (list, tuple)) or not zones:
            raise PDFError("Cette expérience demande un original en octets et des zones explicites.")
        plan = []
        font = pymupdf.Font(fontfile=str(FONT))
        for number, rectangle, text in zones:
            if (not isinstance(text, str) or text != text.strip()
                    or any(not c.isprintable() or not font.has_glyph(ord(c), fallback=False) for c in text)):
                raise PDFError("Le texte de remplacement contient des caractères non pris en charge.")
            # ponytail: réinspection par zone ; réutiliser une inspection unique en phase 2 si coûteux.
            mode = classify_zone(source, number, rectangle)
            rect = pymupdf.Rect(rectangle)
            if any(n == number and rect.intersects(other) for n, other, _, _ in plan):
                raise PDFError("Les zones se chevauchent ; corriger les sélections.")
            with pymupdf.open() as scratch:
                page = scratch.new_page(width=rect.width, height=rect.height)
                page.insert_font(fontname=FONT_NAME, fontfile=str(FONT))
                if text and page.insert_textbox(page.rect + (1, 1, -1, -1), text,
                                                fontname=FONT_NAME, fontsize=14) < 0:
                    raise PDFError("Le remplacement ne tient pas dans la zone ; corriger le texte.")
            plan.append((number, rect, text, mode))

        with _open_supported_structure(source) as structure, _open_mupdf(source) as document:
            for page in structure.pages:
                _check_simple_page(page)
            geometry, outside_text = [], []
            visible_images = set()
            image_infos = {}
            for number, page in enumerate(document):
                rectangles = [rect for n, rect, _, _ in plan if n == number]
                geometry.append((tuple(page.mediabox), tuple(page.cropbox), page.rotation))
                outside_text.append(outside_characters(page, rectangles))
                if any(entry[4] == FONT_NAME for entry in page.get_fonts()):
                    raise PDFError("Le nom de police du prototype existe déjà dans le document.")
                for info in page.get_image_info(xrefs=True):
                    if not info["xref"]:
                        raise PDFError("Une image ne peut pas être associée à son objet PDF.")
                    visible_images.add(info["xref"])
                    image_infos.setdefault(number, []).append(info)
                for block in page.get_text(
                    "rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
                )["blocks"]:
                    if block["type"] != 0:
                        continue
                    for line in block["lines"]:
                        for span in line["spans"]:
                            for char in span["chars"]:
                                box = pymupdf.Rect(char["bbox"])
                                touched = [rect for rect in rectangles if box.intersects(rect)]
                                if len(touched) > 1:
                                    raise PDFError("Deux zones disjointes touchent le même caractère.")
                                if touched and not touched[0].contains(box):
                                    raise PDFError("Un caractère traverse la limite de la sélection.")
                for span in page.get_texttrace():
                    if sum(any(pymupdf.Rect(char[3]).intersects(rect) for char in span["chars"])
                           for rect in rectangles) > 1:
                        raise PDFError("Deux zones touchent le même groupe de texte ; traitement refusé.")
            if set(image_objects(document)) != visible_images:
                raise PDFError("Une image non affichée ne peut pas être qualifiée dans cette expérience.")

            expected_images, edited, raster_text, colorspaces = {}, {}, [], {}
            for xref in visible_images:
                with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                    expected_images[xref] = image_key(image)
            raster_font = ImageFont.truetype(str(FONT), 28)
            for number, rect, text, mode in plan:
                if mode == "native":
                    continue
                info, = [info for info in image_infos[number]
                         if pymupdf.Rect(info["bbox"]).intersects(rect)]
                xref = info["xref"]
                if xref not in edited:
                    with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                        if image.mode not in ("RGB", "L"):
                            raise PDFError("Le mode des pixels décodés n'est pas qualifié.")
                        edited[xref] = (number, image.copy())
                    colorspaces[xref] = document.xref_get_key(xref, "ColorSpace")[1]
                image = edited[xref][1]
                # Les axes positifs sans cisaillement sont déjà imposés par la classification.
                # Calcul en double précision : les Matrix MuPDF arrondissent les bords entiers.
                a, _, _, d, e, f = info["transform"]
                pixels = ((rect.x0 - e) * image.width / a, (rect.y0 - f) * image.height / d,
                          (rect.x1 - e) * image.width / a, (rect.y1 - f) * image.height / d)
                if any(abs(v - round(v)) > 1e-5 for v in pixels):
                    raise PDFError("La sélection doit suivre les pixels dans cette expérience.")
                x0, y0, x1, y1 = (round(v) for v in pixels)
                if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
                    raise PDFError("La conversion de la zone en pixels est invalide.")
                if text:
                    left, top, right, bottom = ImageDraw.Draw(image).textbbox(
                        (x0 + 2, y0 + 2), text, font=raster_font, anchor="lt")
                    if left < x0 + 2 or top < y0 + 2 or right > x1 - 2 or bottom > y1 - 2:
                        raise PDFError("Le remplacement raster ne tient pas dans la zone.")
                ImageDraw.Draw(image).rectangle((x0, y0, x1 - 1, y1 - 1), fill="white")
                raster_text.append((xref, (x0, y0, x1, y1), text))

            # Retirer tous les textes natifs/OCR avant toute insertion fictive.
            for number, page in enumerate(document):
                targets = [(rect, mode) for n, rect, _, mode in plan if n == number and mode != "scan"]
                for rect, mode in targets:
                    page.add_redact_annot(rect, fill=(1, 1, 1) if mode == "native" else None)
                if targets:
                    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            for xref, (x0, y0, x1, y1), text in raster_text:
                draw = ImageDraw.Draw(edited[xref][1])
                # Marge déjà qualifiée à 2 px/point ; aucune extension d'échelle implicite.
                position = (x0 + 2, y0 + 2)
                if text:
                    draw.text(position, text, font=raster_font, fill="black", anchor="lt")
            for xref, (number, image) in edited.items():
                encoded = BytesIO()
                image.save(encoded, format="PNG")
                document[number].replace_image(xref, stream=encoded.getvalue())
                # Le PNG inséré reprend sinon l'espace couleur par défaut de MuPDF.
                # Garder les canaux d'origine et leur espace/profil PDF déjà qualifié.
                document.xref_set_key(xref, "ColorSpace", colorspaces[xref])
                # replace_image laisse une ressource d'insertion inutilisée ; ne pas
                # conserver une seconde image au profil par défaut après restauration.
                document[number].clean_contents()
                expected_images[xref] = image_key(image)
            for number, rect, text, mode in plan:
                if mode == "native" and text:
                    page = document[number]
                    page.insert_font(fontname=FONT_NAME, fontfile=str(FONT))
                    if page.insert_textbox(rect + (1, 1, -1, -1), text, fontname=FONT_NAME, fontsize=14) < 0:
                        raise PDFError("Le remplacement natif ne tient pas dans la zone.")
            result = sanitize_pdf(document.tobytes(garbage=4, deflate=True))
        verify_result(result, geometry, outside_text, plan, expected_images)
        return result
    except PDFError:
        raise
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, pikepdf.PdfError):
        raise PDFError("Le parcours expérimental a échoué ; aucun résultat n'est validé.") from None


class PipelineTests(unittest.TestCase):
    def assert_local_render(self, source, result, zones, page_number=0):
        before, _, size, rotation = render_and_extract(source, page_number)
        after, text, final_size, final_rotation = render_and_extract(result, page_number)
        self.assertEqual((size, rotation), (final_size, final_rotation))
        difference = ImageChops.difference(before, after)
        self.assertIsNotNone(difference.getbbox())
        with pymupdf.open(stream=source) as original:
            matrix = page_to_view_matrix(original[page_number], 2)
            for number, rect, _ in zones:
                if number == page_number:
                    box = (pymupdf.Rect(rect) * matrix).irect
                    difference.paste((0, 0, 0), (box.x0, box.y0, box.x1, box.y1))
        self.assertIsNone(difference.getbbox())
        return text

    def test_two_zones_on_native_scan_and_ocr(self):
        for kind in ("native", "scan", "ocr"):
            for rotation in (0, 90, 180, 270):
                for cropped in (False, True):
                    with self.subTest(kind=kind, rotation=rotation, cropped=cropped):
                        source = make_pdf(kind, rotation=rotation, cropped=cropped)
                        digest = sha256(source).digest()
                        rects = [pymupdf.Rect(TARGET_RECT), pymupdf.Rect(SECOND_RECT)]
                        if cropped:
                            rects = [rect + (-10, -20, -10, -20) for rect in rects]
                        zones = [(0, rect, text) for rect, text in zip(rects, REPLACEMENTS)]
                        result = replace_zones(source, zones)
                        text = self.assert_local_render(source, result, zones)
                        self.assertNotIn(TARGET, text)
                        self.assertNotIn(KEPT, text)
                        for replacement in REPLACEMENTS:
                            self.assertEqual(kind == "native", replacement in text)
                        self.assertEqual(digest, sha256(source).digest())
                        if kind != "native":
                            expected = self.source_image(source)
                            draw = ImageDraw.Draw(expected)
                            font = ImageFont.truetype(str(FONT), 28)
                            # Calcul indépendant sur la grille connue de la fixture, sans matrice.
                            for box, replacement in zip(((70, 140, 520, 210), (70, 300, 520, 370)), REPLACEMENTS):
                                x0, y0, x1, y1 = box
                                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill="white")
                                draw.text((x0 + 2, y0 + 2), replacement, font=font, fill="black", anchor="lt")
                            test_independent.IndependentTests().assert_cleaned_images(result, expected)
                        else:
                            with pikepdf.Pdf.open(BytesIO(source)) as original, pikepdf.Pdf.open(BytesIO(result)) as final:
                                encoded = b"".join(text_runs(final.pages[0]))
                                for old_run in text_runs(original.pages[0]):
                                    self.assertNotIn(old_run, encoded)

    def source_image(self, source):
        with pikepdf.Pdf.open(BytesIO(source)) as checked:
            obj, = checked.pages[0].get_images().values()
            with pikepdf.PdfImage(obj).as_pil_image() as image:
                return image.convert("RGB")

    def test_mixed_native_and_raster_zones(self):
        source = make_pdf("mixed")
        zones = [(0, TARGET_RECT, REPLACEMENTS[0]),
                 (0, pymupdf.Rect(TARGET_RECT) + (0, 200, 0, 200), REPLACEMENTS[1])]
        result = replace_zones(source, zones)
        text = self.assert_local_render(source, result, zones)
        self.assertNotIn(TARGET, text)
        self.assertIn(KEPT, text)
        self.assertIn(REPLACEMENTS[0], text)
        self.assertNotIn(REPLACEMENTS[1], text)

    def test_native_and_scan_on_different_pages(self):
        with pymupdf.open(stream=make_pdf()) as document:
            with pymupdf.open(stream=make_pdf("scan", rotation=90, cropped=True)) as scan:
                document.insert_pdf(scan)
            source = document.tobytes()
        zones = [(0, TARGET_RECT, REPLACEMENTS[0]),
                 (1, pymupdf.Rect(TARGET_RECT) + (-10, -20, -10, -20), REPLACEMENTS[1])]
        result = replace_zones(source, zones)
        self.assertIn(REPLACEMENTS[0], self.assert_local_render(source, result, zones, 0))
        self.assertNotIn(REPLACEMENTS[1], self.assert_local_render(source, result, zones, 1))

    def test_disjoint_zones_in_one_text_object_are_refused(self):
        source, rectangles = shared_text_pdf()
        with pikepdf.Pdf.open(BytesIO(source)) as checked:
            self.assertEqual(1, len(text_runs(checked.pages[0])))
        zones = [(0, rect, text) for rect, text in zip(rectangles, ("Toto", "John Doe"))]
        digest = sha256(source).digest()
        with patch.object(pymupdf.Page, "apply_redactions") as redact:
            with self.assertRaisesRegex(PDFError, "même groupe de texte"):
                replace_zones(source, zones)
            redact.assert_not_called()
        self.assertEqual(digest, sha256(source).digest())

    def test_local_replacement_and_untouched_ocr(self):
        for kind in ("native", "scan", "ocr"):
            for replacement in ("", REPLACEMENTS[0]):
                with self.subTest(kind=kind, empty=not replacement):
                    source = make_pdf(kind)
                    zones = [(0, TARGET_RECT, replacement)]
                    result = replace_zones(source, zones)
                    text = self.assert_local_render(source, result, zones)
                    self.assertNotIn(TARGET, text)
                    self.assertEqual(kind != "scan", KEPT in text)
                    if replacement:
                        self.assertEqual(kind == "native", replacement in text)

    def test_shared_text_regression_reproduces_a_lost_neighbouring_space(self):
        source, rectangles = shared_text_pdf()
        with pymupdf.open(stream=source) as document:
            page = document[0]
            before = outside_characters(page, rectangles)
            for rect in rectangles:
                page.add_redact_annot(rect, fill=None)
            page.apply_redactions(images=0, graphics=0, text=0)
            after = outside_characters(page, rectangles)
        self.assertTrue(before - after)
        self.assertEqual({32}, {key[-2] for key in before - after})
        self.assertFalse(after - before)

    def test_unshown_images_and_fractional_pixels_are_refused(self):
        with pymupdf.open(stream=make_pdf("scan")) as document:
            copied = document.get_new_xref()
            document.update_object(copied, "<< >>")
            document.xref_copy(document[0].get_images()[0][0], copied)
            source = document.tobytes(garbage=0)
        with self.assertRaisesRegex(PDFError, "image non affichée|Plusieurs images"):
            replace_zones(source, [(0, TARGET_RECT, "Toto")])
        with self.assertRaisesRegex(PDFError, "suivre les pixels"):
            replace_zones(make_pdf("scan"), [(0, (35.1, 70, 260, 105), "Toto")])

    def test_corrupted_final_bytes_block_the_result(self):
        cleanup = sanitize_pdf

        def corrupt(data):
            with pymupdf.open(stream=cleanup(data)) as document:
                xref = document.get_new_xref()
                document.update_object(xref, "<< >>")
                document.xref_copy(document[0].get_images()[0][0], xref)
                return document.tobytes(garbage=0)

        with patch(__name__ + ".sanitize_pdf", corrupt):
            with self.assertRaisesRegex(PDFError, "images récupérables"):
                replace_zones(make_pdf("scan"), [(0, TARGET_RECT, "Toto")])
        with patch(__name__ + ".sanitize_pdf", lambda data: data):
            with self.assertRaisesRegex(PDFError, "nettoyage"):
                replace_zones(auxiliary_pdf("metadata"), [(0, TARGET_RECT, "Toto")])

    def test_refusals_before_mutation(self):
        cases = [
            (make_pdf(), [(0, TARGET_RECT, "Toto"), (0, TARGET_RECT, "Autre")], "chevauch"),
            (make_pdf(), [(0, TARGET_RECT, "X" * 1000)], "tient"),
            (make_pdf("scan"), [(0, TARGET_RECT, "X" * 1000)], "tient"),
            (make_pdf(), [(0, TARGET_RECT, "ligne\nsuivante")], "caractères"),
            (make_pdf(), [(0, TARGET_RECT, "\U0010ffff")], "caractères"),
            (make_pdf("mixed"), [(0, TARGET_RECT, "Toto"), (0, (35, 70, 260, 305), "")], "refus|image|chevauch"),
            (repeated_images_pdf(), [(0, TARGET_RECT, ""), (1, TARGET_RECT, "")], "réutilisée"),
            (zone_case_pdf("vector"), [(0, TARGET_RECT, "")], "opérateur"),
            (zone_case_pdf("vector"), [(0, (35, 70, 100, 105), ""), (0, (150, 70, 260, 105), "")], "opérateur"),
            (zone_case_pdf("visible-overlay"), [(0, TARGET_RECT, "")], "superposition"),
            (auxiliary_pdf("actualtext"), [(0, TARGET_RECT, "")], "balisés|alternatifs"),
        ]
        for source, zones, message in cases:
            with self.subTest(message=message), patch.object(pymupdf.Page, "apply_redactions") as redact:
                with self.assertRaisesRegex(PDFError, message):
                    replace_zones(source, zones)
                redact.assert_not_called()

    def test_shared_or_partial_character_is_refused(self):
        source = make_pdf()
        with pymupdf.open(stream=source) as document:
            char = document[0].get_texttrace()[0]["chars"][0][3]
        midpoint = (char[0] + char[2]) / 2
        zones = [(0, (char[0], 70, midpoint - 0.01, 105), ""),
                 (0, (midpoint + 0.01, 70, char[2], 105), "")]
        with self.assertRaisesRegex(PDFError, "même caractère"):
            replace_zones(source, zones)
        with self.assertRaisesRegex(PDFError, "traverse"):
            replace_zones(source, zones[:1])

    def test_failed_removal_is_not_reported_as_success(self):
        def discard_redactions(page, **options):
            for annotation in list(page.annots() or []):
                page.delete_annot(annotation)
            return True

        for kind in ("native", "ocr"):
            with self.subTest(kind=kind), patch.object(pymupdf.Page, "apply_redactions", discard_redactions):
                with self.assertRaisesRegex(PDFError, "texte"):
                    replace_zones(make_pdf(kind), [(0, TARGET_RECT, "Toto")])
        with patch.object(pymupdf.Page, "replace_image"):
            with self.assertRaisesRegex(PDFError, "images récupérables"):
                replace_zones(make_pdf("scan"), [(0, TARGET_RECT, "Toto")])

    def test_cleanup_failure_does_not_disclose_document_content(self):
        with patch(__name__ + ".sanitize_pdf", side_effect=RuntimeError(TARGET)):
            with self.assertRaises(PDFError) as caught:
                replace_zones(make_pdf(), [(0, TARGET_RECT, "Toto")])
        self.assertNotIn(TARGET, str(caught.exception))

    def test_invisible_native_replacement_is_refused(self):
        insert = pymupdf.Page.insert_textbox

        def insert_invisible(page, *args, **options):
            return insert(page, *args, **options, render_mode=3)

        with patch.object(pymupdf.Page, "insert_textbox", insert_invisible):
            with self.assertRaisesRegex(PDFError, "natif.*visible"):
                replace_zones(make_pdf(), [(0, TARGET_RECT, "Toto")])


if __name__ == "__main__":
    unittest.main()
