# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Transformation en mémoire du périmètre qualifié, sans Qt ni outil de test.

Les appels directs ne bornent pas le processus : utiliser PDFJob dans l'application.
Limite de confidentialité 11B : les copies internes différées peuvent subsister.
"""

from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pikepdf
import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageChops

from substidude.model import WARNINGS, SessionError, validate_substitutions
from substidude.pdf_engine import (
    PDFError, _check_simple_page, _open_mupdf, _open_supported_structure, _pdf_objects, classify_zone, render_page, page_to_view_matrix,
)
from substidude.pdf_engine import sanitize_pdf

FONT = Path(__file__).resolve().parent / "resources" / "NotoSans-Regular.ttf"
FONT_NAME = "substidudePrototype"


def native_text_size(rect, text):
    """Ajustement automatique borné, sans tronquer le texte ni réglage utilisateur."""
    with pymupdf.open() as scratch:
        page = scratch.new_page(width=rect.width, height=rect.height)
        page.insert_font(fontname=FONT_NAME, fontfile=str(FONT))
        for half_points in range(28, 0, -1):
            size = half_points / 2
            shape = page.new_shape()
            if not text or shape.insert_textbox(page.rect + (1, 1, -1, -1), text,
                                               fontname=FONT_NAME, fontsize=size) >= 0:
                return size
    raise PDFError("Le remplacement ne tient pas dans la zone ; agrandir la sélection ou raccourcir le texte.")


def image_key(image):
    return image.size, sha256(image.convert("RGB").tobytes()).digest()


def image_objects(document):
    return [xref for xref in range(1, document.xref_length())
            if document.xref_get_key(xref, "Subtype") == ("name", "/Image")]


def outside_characters(page, rectangles):
    return Counter((span["type"], span["opacity"], span["font"], span["color"],
                    char[0], tuple(round(v, 3) for v in char[3]))
                   for span in page.get_texttrace() for char in span["chars"]
                   if not any(pymupdf.Rect(char[3]).intersects(rect) for rect in rectangles))


def image_colors(structure):
    colors = Counter()
    for obj in structure.objects:
        if not isinstance(obj, pikepdf.Stream) or obj.get("/Subtype") != pikepdf.Name.Image:
            continue
        space = obj.get("/ColorSpace")
        if isinstance(space, pikepdf.Array):
            profile = space[1]
            color = (str(space[0]), profile.get("/N"), str(profile.get("/Alternate")),
                     tuple(profile.get("/Range", [])), sha256(profile.read_bytes()).digest())
        else:
            color = str(space)
        colors[(obj.get("/Width"), obj.get("/Height"), obj.get("/BitsPerComponent"), color)] += 1
    return colors


def verify_result(result, geometry, outside_text, plan, expected_images, expected_colors, expected_native_images=None):
    with _open_supported_structure(result, allow_missing_self_xref=False) as structure, _open_mupdf(result) as document:
        if len(geometry) != document.page_count or structure.check_pdf_syntax():
            raise PDFError("Le résultat n'a pas conservé la structure attendue.")
        if ("/Prev" in structure.trailer or "/Info" in structure.trailer
                or any(set(obj.keys()) & {"/Info", "/Metadata", "/Thumb", "/CIDSet"}
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
        if expected_native_images is not None:
            from substidude.native import check_document, image_inventory
            if image_inventory(structure) != expected_native_images:
                raise PDFError("Les images conservées ou leurs espaces couleur ont changé.")
            check_document(structure, document)
        else:
            recovered = Counter()
            for xref in image_objects(document):
                with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                    recovered[image_key(image)] += 1
            if recovered != Counter(expected_images.values()):
                raise PDFError("Les images récupérables ne correspondent pas aux pixels attendus.")
            if image_colors(structure) != expected_colors:
                raise PDFError("Les espaces couleur des images n'ont pas été conservés.")


def verify_native_render(source, result, plan):
    # Garde du moteur en plus de la qualification indépendante PDFium du corpus.
    # Une page à la fois, RGB à 2x, plafond commun 16 MP inchangé.
    with _open_mupdf(source) as original, _open_mupdf(result) as final:
        for number, page in enumerate(original):
            before, after = render_page(page, 2), render_page(final[number], 2)
            if (before.width, before.height) != (after.width, after.height):
                raise PDFError("Les dimensions du rendu natif ont changé.")
            first = Image.frombytes("RGB", (before.width, before.height), before.samples)
            second = Image.frombytes("RGB", (after.width, after.height), after.samples)
            difference = ImageChops.difference(first, second)
            matrix = page_to_view_matrix(page, 2)
            for n, rect, _, _ in plan:
                if n == number:
                    box = (rect * matrix).irect
                    difference.paste((0, 0, 0), (box.x0, box.y0, box.x1, box.y1))
            if difference.getbbox() is not None:
                raise PDFError("Le rendu natif hors zones a changé ; résultat refusé.")


def transform(source, substitutions):
    """Renvoie les octets contrôlés ; aucun export ni confirmation implicite."""
    try:
        if type(source) is not bytes:
            raise PDFError("L'original doit être une copie immuable en octets.")
        zones = validate_substitutions(substitutions)
        plan, settings = [], {}
        font = pymupdf.Font(fontfile=str(FONT))
        for zone in zones:
            number, rectangle, text = zone.page, zone.rectangle, zone.text
            if (text != text.strip() or any(
                c != "\n" and (not c.isprintable() or not font.has_glyph(ord(c), fallback=False)) for c in text
            )):
                raise PDFError("Le texte de remplacement contient des caractères non pris en charge.")
            mode = classify_zone(source, number, rectangle)
            rect = pymupdf.Rect(rectangle)
            plan.append((number, rect, text, mode))
            if mode == "native":
                settings[(number, tuple(rect))] = native_text_size(rect, text)

        native_only = all(mode == "native" for _, _, _, mode in plan)
        expected_native_images = None
        with _open_supported_structure(source) as structure, _open_mupdf(source) as document:
            for page in structure.pages:
                if not native_only:
                    _check_simple_page(page)
            if native_only:
                from substidude.native import check_document, image_inventory
                expected_native_images = image_inventory(structure)
                check_document(structure, document)
            expected_colors = None if native_only else image_colors(structure)
            geometry, outside_text, visible_images, image_infos = [], [], set(), {}
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
            if not native_only and set(image_objects(document)) != visible_images:
                raise PDFError("Une image non affichée ne peut pas être qualifiée dans cette expérience.")

            expected_images, edited, raster_text, colorspaces = {}, {}, [], {}
            for xref in (() if native_only else visible_images):
                with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                    expected_images[xref] = image_key(image)
            for number, rect, text, mode in plan:
                if mode == "native":
                    continue
                info, = [info for info in image_infos[number] if pymupdf.Rect(info["bbox"]).intersects(rect)]
                xref = info["xref"]
                if xref not in edited:
                    with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                        if image.mode not in ("RGB", "L"):
                            raise PDFError("Le mode des pixels décodés n'est pas qualifié.")
                        edited[xref] = (number, image.copy())
                    colorspaces[xref] = document.xref_get_key(xref, "ColorSpace")[1]
                image = edited[xref][1]
                a, _, _, d, e, f = info["transform"]
                pixels = ((rect.x0 - e) * image.width / a, (rect.y0 - f) * image.height / d,
                          (rect.x1 - e) * image.width / a, (rect.y1 - f) * image.height / d)
                if any(abs(v - round(v)) > 1e-5 for v in pixels):
                    raise PDFError("La sélection doit suivre les pixels dans cette expérience.")
                x0, y0, x1, y1 = (round(v) for v in pixels)
                if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
                    raise PDFError("La conversion de la zone en pixels est invalide.")
                draw = ImageDraw.Draw(image)
                for pixels in range(28, 0, -1):
                    raster_font = ImageFont.truetype(str(FONT), pixels)
                    ascent, descent = raster_font.getmetrics()
                    lines = []
                    for index, line in enumerate(text.split("\n")):
                        left, top, _, _ = draw.textbbox((0, 0), line, font=raster_font, anchor="lt")
                        lines.append((line, (x0 + 2 - min(0, left),
                                             y0 + 2 + index * (ascent + descent + 4) - min(0, top))))
                    boxes = [draw.textbbox(position, line, font=raster_font, anchor="lt") for line, position in lines]
                    if all(left >= x0 + 2 and top >= y0 + 2 and right <= x1 - 2 and bottom <= y1 - 2
                           for left, top, right, bottom in boxes):
                        break
                else:
                    raise PDFError("Le remplacement raster ne tient pas dans la zone ; agrandir la sélection.")
                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255 if image.mode == "L" else (255, 255, 255))
                raster_text.append((xref, lines, raster_font))

            for number, page in enumerate(document):
                targets = [(rect, mode) for n, rect, _, mode in plan if n == number and mode != "scan"]
                for rect, mode in targets:
                    page.add_redact_annot(rect, fill=None)
                if targets:
                    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
                    for rect, mode in targets:
                        if mode == "native":
                            # Le remplissage intégré de MuPDF ajoute un contour
                            # de 1 pt débordant des sélections fractionnaires.
                            page.draw_rect(rect, color=None, fill=(1, 1, 1),
                                           width=0, overlay=True)
            for xref, lines, raster_font in raster_text:
                for text, position in lines:
                    if text:
                        ImageDraw.Draw(edited[xref][1]).text(
                            position, text, font=raster_font, fill="black", anchor="lt")
            for xref, (number, image) in edited.items():
                encoded = BytesIO()
                image.save(encoded, format="PNG")
                document[number].replace_image(xref, stream=encoded.getvalue())
                document.xref_set_key(xref, "ColorSpace", colorspaces[xref])
                document[number].clean_contents()
                expected_images[xref] = image_key(image)
            for number, rect, text, mode in plan:
                if mode == "native" and text:
                    page = document[number]
                    page.insert_font(fontname=FONT_NAME, fontfile=str(FONT))
                    if page.insert_textbox(rect + (1, 1, -1, -1), text, fontname=FONT_NAME,
                                           fontsize=settings[(number, tuple(rect))]) < 0:
                        raise PDFError("Le remplacement natif ne tient pas dans la zone.")
            if native_only:
                for page in document:
                    page.clean_contents()
            # Garder distincts les objets image conservés, même aux mêmes pixels.
            result = sanitize_pdf(document.tobytes(garbage=2 if native_only else 4, deflate=True))
        verify_result(result, geometry, outside_text, plan, expected_images, expected_colors, expected_native_images)
        if native_only:
            verify_native_render(source, result, plan)
        return result
    except PDFError:
        raise
    except SessionError:
        raise PDFError("Les paramètres de substitution sont invalides ou les zones se chevauchent.") from None
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, OverflowError, pikepdf.PdfError):
        raise PDFError("Le traitement a échoué ; aucun résultat n'est validé.") from None
