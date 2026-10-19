# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Inspection et nettoyage bornés du prototype ; pas encore un pipeline d'export."""

from pathlib import Path
from math import isfinite
from io import BytesIO
from hashlib import sha256
from decimal import Decimal
import warnings
import zlib

import pikepdf
import pymupdf

from substidude.limits import (
    MAX_IMAGE_STREAM_BYTES, MAX_RENDER_PIXELS, MAX_RESOURCE_STREAM_BYTES,
    MAX_TOTAL_DECODED_STREAM_BYTES,
)


# Les diagnostics natifs peuvent contenir des fragments du document non fiable.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_FILE_BYTES = 10_000_000
MAX_PAGES = 49
MAX_IMAGE_PIXELS = 40_000_000
# Profil sRGB intégré par MuPDF 1.28.2, qualifié avec les fixtures PNG du corpus.
SUPPORTED_RGB_ICC_SHA256 = "eddaf344b5edea13269e0d20055f335610e5e0b6e33e6e536f2701bc18c5f7d5"


class PDFError(ValueError):
    """Erreur présentable sans contenu documentaire ni chemin source."""


def _check_file_size(size: int) -> None:
    if size == 0:
        raise PDFError("Le fichier est vide (0 octet).")
    if size >= MAX_FILE_BYTES:
        raise PDFError("Le fichier doit faire strictement moins de 10 Mo.")


def _bounded_stream_size(stream, limit):
    """Compte les flux admis sans matérialiser leur décompression entière."""
    def checked(size):
        if size > limit:
            raise PDFError("La limite des flux décompressés est dépassée.")
        return size

    encoding = stream.get("/Filter")
    if encoding == pikepdf.Name.DCTDecode and stream.get("/Subtype") == pikepdf.Name.Image:
        width, height = stream.get("/Width"), stream.get("/Height")
        if type(width) is not int or type(height) is not int:
            raise PDFError("Les dimensions d'une image ne sont pas prises en charge.")
        _check_image_dimensions(width, height)
        colorspace = stream.get("/ColorSpace")
        components = 4  # Comptage prudent pour un espace non encore qualifié.
        if colorspace == pikepdf.Name.DeviceGray:
            components = 1
        elif colorspace == pikepdf.Name.DeviceRGB:
            components = 3
        elif (isinstance(colorspace, pikepdf.Array) and len(colorspace) == 2
              and colorspace[0] == pikepdf.Name.ICCBased
              and isinstance(colorspace[1], pikepdf.Stream)
              and type(colorspace[1].get("/N")) is int
              and colorspace[1].N in (1, 3, 4)):
            components = colorspace[1].N
        return checked(width * height * components)

    # Le fichier d'entrée est borné à 10 Mo ; ces octets restent compressés.
    raw = stream.read_raw_bytes()
    if encoding is None:
        return checked(len(raw))
    if encoding == pikepdf.Name.ASCIIHexDecode:
        digits = 0
        for value in raw:
            if value == ord(">"):
                break
            if value in b"\x00\t\n\x0c\r ":
                continue
            if value not in b"0123456789abcdefABCDEF":
                raise PDFError("L'encodage d'un flux ne peut pas être inspecté.")
            digits += 1
            checked((digits + 1) // 2)
        return (digits + 1) // 2
    if encoding != pikepdf.Name.FlateDecode:
        raise PDFError("L'encodage des flux décompressés n'est pas qualifié.")
    decoder = zlib.decompressobj()
    size = 0
    try:
        for offset in range(0, len(raw), 65_536):
            pending = raw[offset:offset + 65_536]
            while True:
                capacity = min(65_536, limit - size + 1)
                block = decoder.decompress(pending, capacity)
                size = checked(size + len(block))
                pending = decoder.unconsumed_tail
                if not pending and len(block) < capacity:
                    break
        if not decoder.eof:
            raise PDFError("Un flux compressé est incomplet.")
    except zlib.error:
        raise PDFError("L'encodage d'un flux compressé est invalide.") from None
    return size


def _check_stream_budgets(document):
    total = 0
    for stream in document.objects:
        if not isinstance(stream, pikepdf.Stream):
            continue
        individual = (MAX_IMAGE_STREAM_BYTES if stream.get("/Subtype") == pikepdf.Name.Image
                      else MAX_RESOURCE_STREAM_BYTES)
        total += _bounded_stream_size(stream, min(individual, MAX_TOTAL_DECODED_STREAM_BYTES - total))


def _pdf_objects(objects):
    """Parcourt aussi les conteneurs directs, sans boucler sur les références PDF."""
    pending = list(objects)
    seen = set()
    while pending:
        obj = pending.pop()
        if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
            continue
        if obj.objgen != (0, 0):
            if obj.objgen in seen:
                continue
            seen.add(obj.objgen)
        yield obj
        pending.extend(obj if isinstance(obj, pikepdf.Array) else obj.values())


def _check_dictionary_keys(obj, allowed):
    if not isinstance(obj, pikepdf.Dictionary) or set(obj.keys()) - allowed:
        raise PDFError("Un dictionnaire de ressource contient des références non qualifiées.")


def _check_numeric_array(value):
    if not isinstance(value, pikepdf.Array):
        raise PDFError("Une ressource numérique contient une référence non qualifiée.")
    for array in _pdf_objects([value]):
        if not isinstance(array, pikepdf.Array) or any(
            not isinstance(item, pikepdf.Array) and type(item) not in (int, float, Decimal)
            for item in array
        ):
            raise PDFError("Une ressource numérique contient une référence non qualifiée.")


def _check_stream_references(stream, extra_keys=()):
    if (not isinstance(stream, pikepdf.Stream)
            or set(stream.keys()) - {"/Length", "/Filter", "/DecodeParms", *extra_keys}
            or type(stream.get("/Length")) is not int
            or stream.get("/Filter") not in (None, pikepdf.Name.FlateDecode, pikepdf.Name.ASCIIHexDecode)):
        raise PDFError("Un flux de ressource contient des références ou un encodage non qualifiés.")
    parameters = stream.get("/DecodeParms")
    if parameters is not None and (not isinstance(parameters, pikepdf.Dictionary) or parameters):
        raise PDFError("Les paramètres du flux de ressource ne sont pas qualifiés.")


def _check_font_references(font):
    """Frontière des conteneurs ; ne qualifie pas les octets du programme de police."""
    # ponytail: conteneurs seulement ; qualifier programmes et CMap avant le jalon moteur.
    subtype = font.get("/Subtype") if isinstance(font, pikepdf.Dictionary) else None
    common = {"/Type", "/Subtype", "/BaseFont"}
    fields = {
        pikepdf.Name.Type0: {"/Encoding", "/DescendantFonts", "/ToUnicode"},
        pikepdf.Name.CIDFontType2: {"/CIDSystemInfo", "/FontDescriptor", "/W", "/DW", "/CIDToGIDMap"},
        pikepdf.Name.Type1: {"/Encoding"},
    }
    if not isinstance(subtype, pikepdf.Name) or subtype not in fields:
        raise PDFError("Ce type de police n'est pas qualifié pour l'inspection des références.")
    _check_dictionary_keys(font, common | fields[subtype])
    if font.get("/Type") != pikepdf.Name.Font or not isinstance(font.get("/BaseFont"), pikepdf.Name):
        raise PDFError("Les propriétés de police contiennent des références non qualifiées.")
    if "/Encoding" in font and not isinstance(font.Encoding, pikepdf.Name):
        raise PDFError("L'encodage de police n'est pas qualifié.")
    if "/ToUnicode" in font:
        _check_stream_references(font.ToUnicode)
    if subtype == pikepdf.Name.Type0:
        children = font.get("/DescendantFonts")
        if (not isinstance(children, pikepdf.Array) or len(children) != 1
                or not isinstance(children[0], pikepdf.Dictionary)
                or children[0].get("/Subtype") != pikepdf.Name.CIDFontType2):
            raise PDFError("Les polices descendantes ne sont pas qualifiées.")
        _check_font_references(children[0])
    if subtype == pikepdf.Name.CIDFontType2:
        info = font.get("/CIDSystemInfo")
        _check_dictionary_keys(info, {"/Registry", "/Ordering", "/Supplement"})
        if (not isinstance(info.get("/Registry"), pikepdf.String)
                or not isinstance(info.get("/Ordering"), pikepdf.String)
                or type(info.get("/Supplement")) is not int):
            raise PDFError("Les propriétés CID de police ne sont pas qualifiées.")
        if "/W" in font:
            _check_numeric_array(font.W)
        if "/DW" in font and type(font.DW) not in (int, float, Decimal):
            raise PDFError("La largeur de police n'est pas qualifiée.")
        if "/CIDToGIDMap" in font and font.CIDToGIDMap != pikepdf.Name.Identity:
            raise PDFError("La table de glyphes de police n'est pas qualifiée.")
        descriptor = font.get("/FontDescriptor")
        _check_dictionary_keys(descriptor, {
            "/Type", "/FontName", "/Flags", "/FontBBox", "/ItalicAngle", "/Ascent",
            "/Descent", "/CapHeight", "/StemV", "/FontFile2",
        })
        if (descriptor.get("/Type") != pikepdf.Name.FontDescriptor
                or not isinstance(descriptor.get("/FontName"), pikepdf.Name)):
            raise PDFError("Le descripteur de police n'est pas qualifié.")
        _check_numeric_array(descriptor.get("/FontBBox"))
        for key in set(descriptor.keys()) - {"/Type", "/FontName", "/FontBBox", "/FontFile2"}:
            if type(descriptor[key]) not in (int, float, Decimal):
                raise PDFError("Le descripteur de police contient une référence non qualifiée.")
        if "/FontFile2" in descriptor:
            _check_stream_references(descriptor.FontFile2, {"/Length1"})
            if type(descriptor.FontFile2.get("/Length1")) is not int:
                raise PDFError("La taille du programme de police n'est pas qualifiée.")


def _check_icc_references(profile):
    _check_stream_references(profile, {"/N", "/Alternate", "/Range"})
    if (type(profile.get("/N")) is not int
            or profile.get("/Alternate") not in (None, pikepdf.Name.DeviceRGB, pikepdf.Name.DeviceGray)):
        raise PDFError("Le dictionnaire du profil ICC n'est pas qualifié.")
    if "/Range" in profile:
        _check_numeric_array(profile.Range)


def _check_auxiliary_structure(document: pikepdf.Pdf) -> None:
    # Refus conservateurs : ne pas supprimer un conteneur susceptible d'être visible.
    unsupported = (
        ({"/ActualText", "/Alt", "/StructTreeRoot", "/StructParents", "/StructParent"},
         "Les textes alternatifs et structures d'accessibilité ne sont pas pris en charge."),
        ({"/OCProperties", "/OC"}, "Les couches optionnelles ne sont pas prises en charge."),
        ({"/AcroForm", "/XFA"}, "Les formulaires et signatures PDF ne sont pas pris en charge."),
        ({"/EmbeddedFiles", "/AF", "/PieceInfo", "/Threads", "/Collection", "/PresSteps",
          "/Names", "/Dests", "/Outlines", "/PageLabels", "/SpiderInfo",
          "/Alternates", "/OPI", "/Ref"},
         "Ce contenu auxiliaire du PDF n'est pas pris en charge."),
        ({"/OpenAction", "/AA", "/JavaScript"},
         "Les scripts et actions PDF ne sont pas pris en charge."),
    )
    actions = {"/GoTo", "/GoToR", "/GoToE", "/Launch", "/Thread", "/URI", "/Sound",
               "/Movie", "/Hide", "/Named", "/SubmitForm", "/ResetForm", "/ImportData",
               "/JavaScript", "/SetOCGState", "/Rendition", "/Trans", "/GoTo3DView"}
    known_catalog = {"/Type", "/Pages", "/Version", "/Metadata", "/Info", "/Lang",
                     "/PageLayout", "/PageMode", "/ViewerPreferences"}
    known_catalog.update(key for keys, _ in unsupported for key in keys)
    if set(document.Root.keys()) - known_catalog:
        raise PDFError("Le catalogue PDF contient une extension non prise en charge.")

    def check_content(container):
        with warnings.catch_warnings(record=True) as diagnostics:
            warnings.simplefilter("always")
            instructions = pikepdf.parse_content_stream(container)
        if diagnostics:
            raise PDFError("Un flux de contenu ne peut pas être inspecté de façon fiable.")
        for instruction in instructions:
            if str(instruction.operator) == "INLINE IMAGE":
                _check_image_dimensions(instruction.iimage.width, instruction.iimage.height)
            if str(instruction.operator) in {"BMC", "BDC", "EMC", "MP", "DP"}:
                raise PDFError("Les contenus balisés, dont ActualText, ne sont pas pris en charge.")

    for obj in _pdf_objects(document.objects):
        if isinstance(obj, pikepdf.Array):
            if obj and obj[0] == pikepdf.Name.ICCBased:
                if len(obj) != 2:
                    raise PDFError("La référence de profil ICC n'est pas qualifiée.")
                _check_icc_references(obj[1])
            continue
        keys = set(obj.keys())
        for forbidden, message in unsupported:
            if keys & forbidden:
                raise PDFError(message)
        if obj.get("/Type") in (pikepdf.Name.OCG, pikepdf.Name.OCMD):
            raise PDFError("Les couches optionnelles ne sont pas prises en charge.")
        if obj.get("/Subtype") == pikepdf.Name.Type3:
            raise PDFError("Les polices Type 3 ne sont pas prises en charge.")
        if obj.get("/Type") == pikepdf.Name.Font:
            _check_font_references(obj)
        if "/Font" in obj:
            fonts = obj["/Font"]
            if not isinstance(fonts, pikepdf.Dictionary):
                raise PDFError("Le dictionnaire des polices n'est pas qualifié.")
            for font in fonts.values():
                _check_font_references(font)
        if obj.get("/Type") == pikepdf.Name.XObject and obj.get("/Subtype") not in (
            pikepdf.Name.Image, pikepdf.Name.Form
        ):
            raise PDFError("Ce type d'objet graphique PDF n'est pas pris en charge.")
        if obj.get("/Subtype") == pikepdf.Name.Image:
            width, height = obj.get("/Width"), obj.get("/Height")
            if type(width) is not int or type(height) is not int:
                raise PDFError("Les dimensions d'une image ne sont pas prises en charge.")
            _check_image_dimensions(width, height)
        action = obj.get("/S")
        if isinstance(action, pikepdf.Name) and str(action) in actions:
            raise PDFError("Les scripts et actions PDF ne sont pas pris en charge.")
        if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name.Form:
            check_content(obj)
    for page in document.pages:
        if page.obj.get("/Annots", []):
            raise PDFError("Les annotations et liens PDF ne sont pas pris en charge.")
        contents = page.obj.get("/Contents", pikepdf.Array())
        for stream in contents if isinstance(contents, pikepdf.Array) else [contents]:
            _check_stream_references(stream)
        check_content(page)
    if document.get_warnings():
        raise PDFError("Le PDF présente des anomalies structurelles non prises en charge.")


def _open_supported_structure(data: bytes) -> pikepdf.Pdf:
    _check_file_size(len(data))
    try:
        document = pikepdf.Pdf.open(BytesIO(data), attempt_recovery=False)
    except pikepdf.PasswordError:
        raise PDFError("Les PDF chiffrés ne sont pas pris en charge.") from None
    except pikepdf.PdfError:
        raise PDFError("Le fichier est invalide ou le PDF est malformé.") from None
    try:
        if document.is_encrypted:
            raise PDFError("Les PDF chiffrés ne sont pas pris en charge.")
        if not 1 <= len(document.pages) <= MAX_PAGES:
            raise PDFError("Le PDF doit contenir de 1 à 49 pages.")
        _check_stream_budgets(document)
        _check_auxiliary_structure(document)
    except PDFError:
        document.close()
        raise
    except (pikepdf.PdfError, RecursionError, TypeError, ValueError):
        document.close()
        raise PDFError("La structure de ce PDF ne peut pas être inspectée de façon fiable.") from None
    except Exception:
        document.close()
        raise
    return document


def sanitize_pdf(data: bytes) -> bytes:
    """Nettoie les contenus auxiliaires acceptés, sans effectuer de substitution.

    Ce résultat n'est pas un export confirmé ; les contrôles de transformation
    et la vérification utilisateur restent obligatoires dans le futur pipeline.
    """
    try:
        with _open_supported_structure(data) as document:
            for obj in _pdf_objects(document.objects):
                if isinstance(obj, pikepdf.Array) or "/Metadata" not in obj:
                    continue
                metadata = obj["/Metadata"]
                if not isinstance(metadata, pikepdf.Stream) or metadata.get("/Type") != pikepdf.Name.Metadata:
                    raise PDFError("Une référence de métadonnées est ambiguë et ne peut pas être nettoyée.")
                del obj["/Metadata"]
            for page in document.pages:
                if "/Thumb" in page.obj:
                    del page.obj["/Thumb"]
            for key in ("/Info", "/ID"):
                if key in document.trailer:
                    del document.trailer[key]
            # Certaines sources placent aussi Info directement dans le catalogue.
            if "/Info" in document.Root:
                del document.Root["/Info"]
            output = BytesIO()
            # qpdf réécrit entièrement et élimine les objets non référencés ; aucune
            # recompression JPEG ni normalisation des opérateurs de contenu demandée.
            document.save(output, preserve_pdfa=False, fix_metadata_version=False, recompress_flate=False)
            result = output.getvalue()
        with pikepdf.Pdf.open(BytesIO(result), attempt_recovery=False) as verified:
            if (verified.check_pdf_syntax() or "/Prev" in verified.trailer
                    or "/Info" in verified.trailer or "/Info" in verified.Root):
                raise PDFError("Le résultat du nettoyage ne satisfait pas les contrôles structurels.")
            if any("/Metadata" in obj for obj in _pdf_objects(verified.objects)
                   if not isinstance(obj, pikepdf.Array)):
                raise PDFError("Des métadonnées subsistent après le nettoyage.")
        return result
    except PDFError:
        raise
    except (pikepdf.PdfError, pikepdf.PasswordError, TypeError, ValueError, RuntimeError):
        raise PDFError("Le nettoyage de ce PDF a échoué ; aucun résultat n'est validé.") from None


def render_page(page: pymupdf.Page, scale: float = 1) -> pymupdf.Pixmap:
    """Rendu RGB d'une page, refus avant allocation ; aucun sous-échantillonnage implicite."""
    if type(scale) not in (int, float) or not isfinite(scale) or scale <= 0:
        raise PDFError("Le facteur de rendu doit être positif et fini.")
    width, height = page.rect.width * scale, page.rect.height * scale
    if (not isfinite(width) or not isfinite(height) or width <= 0 or height <= 0
            or width > MAX_RENDER_PIXELS or height > MAX_RENDER_PIXELS):
        raise PDFError("Le rendu dépasse la limite de 16 mégapixels.")
    matrix = pymupdf.Matrix(scale, scale)
    bounds = (page.rect * matrix).irect
    if bounds.width <= 0 or bounds.height <= 0 or bounds.width * bounds.height > MAX_RENDER_PIXELS:
        raise PDFError("Le rendu dépasse la limite de 16 mégapixels.")
    return page.get_pixmap(matrix=matrix, colorspace=pymupdf.csRGB, alpha=False)


def page_to_view_matrix(page: pymupdf.Page, scale: float) -> pymupdf.Matrix:
    """Page non tournée, relative à la CropBox → vue tournée, en pixels.

    `scale` inclut le zoom et le facteur HiDPI ; l'inverse s'obtient par `~matrix`.
    Les décalages de fenêtre et de défilement relèvent de la vue, pas du PDF.
    """
    if not isfinite(scale) or scale <= 0:
        raise PDFError("Le facteur d'affichage doit être positif et fini.")
    try:
        matrix = page.rotation_matrix * pymupdf.Matrix(scale, scale)
    except (TypeError, OverflowError):
        raise PDFError("Le facteur d'affichage dépasse la précision du moteur.") from None
    # MuPDF représente les matrices en précision finie ; refuser un inverse inutilisable.
    inverse = pymupdf.Matrix()
    if (not all(isfinite(value) for value in matrix)
            or inverse.invert(matrix) != 0
            or not all(isfinite(value) for value in inverse)):
        raise PDFError("Le facteur d'affichage ne permet pas une conversion fiable.")
    return matrix


def _check_image_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise PDFError("Une image possède des dimensions invalides.")
    if width * height > MAX_IMAGE_PIXELS:
        raise PDFError("Une image dépasse la limite de 40 mégapixels.")


def _check_images(document: pymupdf.Document) -> None:
    # Examiner aussi les masques et objets non affichés, sans extraire leurs pixels.
    for xref in range(1, document.xref_length()):
        if document.xref_get_key(xref, "Subtype") != ("name", "/Image"):
            continue
        dimensions = [document.xref_get_key(xref, key) for key in ("Width", "Height")]
        if any(kind != "int" for kind, _ in dimensions):
            raise PDFError("Les dimensions d'une image ne sont pas prises en charge.")
        _check_image_dimensions(*(int(value) for _, value in dimensions))

    # Sans empreintes : pas de décodage des pixels pour calculer un hash.
    # Couvre notamment les images inline absentes de la table des objets.
    for page in document:
        for image in page.get_image_info(hashes=False, xrefs=False):
            _check_image_dimensions(image["width"], image["height"])


def repeated_image_occurrences(document: pymupdf.Document) -> list[list[tuple[int, pymupdf.Rect]]]:
    """Groupes d'occurrences identiques sur l'original, avant toute transformation.

    Prototype limité aux images visibles sans masque, dans un même espace couleur.
    Ce résultat ne qualifie pas les couches masquées ni les contenus auxiliaires.
    """
    _check_images(document)
    colorspaces = set()
    for page in document:
        for image in page.get_image_info(hashes=False, xrefs=False):
            if image["has-mask"]:
                raise PDFError("La détection des copies d'images avec masque n'est pas prise en charge.")
            colorspaces.add((image["colorspace"], image["cs-name"]))
    if len(colorspaces) > 1 or any(components not in (1, 3) for components, _ in colorspaces):
        raise PDFError("La comparaison des images entre espaces couleur n'est pas prise en charge.")

    groups = {}
    for page in document:
        for image in page.get_image_info(hashes=True, xrefs=False):
            key = (image["width"], image["height"], image["cs-name"], image["digest"])
            # L'empreinte native sert à refuser les répétitions, pas à certifier un export.
            # Une collision ne ferait qu'ajouter un refus conservateur.
            groups.setdefault(key, []).append((page.number, pymupdf.Rect(image["bbox"])))
    return [occurrences for occurrences in groups.values() if len(occurrences) > 1]


def _zone_rectangle(document: pymupdf.Document, page_number: int, rectangle) -> pymupdf.Rect:
    if type(page_number) is not int or not 0 <= page_number < document.page_count:
        raise PDFError("La page sélectionnée n'existe pas.")
    try:
        rect = pymupdf.Rect(rectangle)
    except (TypeError, ValueError, OverflowError, AssertionError):
        raise PDFError("La zone doit être un rectangle valide.") from None
    page = document[page_number]
    bounds = page.rect * page.derotation_matrix
    if (not all(isfinite(value) for value in rect) or rect.is_empty
            or not bounds.contains(rect)):
        raise PDFError("La zone doit être non vide et entièrement dans la page.")
    return rect


def check_image_reuse(document: pymupdf.Document, page_number: int, rectangle) -> None:
    """Périmètre raster V1 à image unique ; ne qualifie pas le reste du PDF."""
    rect = _zone_rectangle(document, page_number, rectangle)
    _check_images(document)
    visible = [(page.number, pymupdf.Rect(image["bbox"])) for page in document
               for image in page.get_image_info(hashes=False, xrefs=False)]
    if any(number == page_number and area.intersects(rect) for number, area in visible):
        objects = sum(document.xref_get_key(xref, "Subtype") == ("name", "/Image")
                      for xref in range(1, document.xref_length()))
        # ponytail: V1 à image unique ; qualifier une stratégie multi-images avant élargissement.
        if len(visible) > 1 or objects > 1:
            pages = ", ".join(str(n + 1) for n in sorted({number for number, _ in visible}))
            raise PDFError(
                f"Plusieurs images sont présentes (pages {pages}) : une image pourrait être réutilisée "
                "sous une forme transformée. Les copies ne peuvent pas être exclues. "
                "La substitution raster est refusée dans la V1, sans propagation automatique."
            )


def _check_simple_page(page: pikepdf.Page) -> None:
    """Liste positive expérimentale ; un contenu inconnu n'est jamais ignoré."""
    if set(page.obj.keys()) - {
        "/Type", "/Parent", "/Contents", "/Resources", "/MediaBox", "/CropBox",
        "/Rotate", "/Metadata", "/Thumb",
    }:
        raise PDFError("La page contient une structure non qualifiée pour la classification.")
    resources = page.obj.get("/Resources")
    if not isinstance(resources, pikepdf.Dictionary):
        raise PDFError("Les ressources de page absentes ou indirectement héritées ne sont pas qualifiées.")
    if set(resources.keys()) - {"/Font", "/XObject", "/ProcSet"}:
        raise PDFError("Les états graphiques, transparences et ressources complexes sont refusés.")
    objects = resources.get("/XObject", pikepdf.Dictionary())
    if not isinstance(objects, pikepdf.Dictionary):
        raise PDFError("Les ressources graphiques ne peuvent pas être inspectées de façon fiable.")
    for image in objects.values():
        if not isinstance(image, pikepdf.Stream) or image.get("/Subtype") != pikepdf.Name.Image:
            raise PDFError("La classification dans les objets Form n'est pas encore qualifiée.")
        if set(image.keys()) & {"/SMask", "/Mask", "/ImageMask", "/Matte", "/Decode"}:
            raise PDFError("Les images avec masque ou décodage particulier sont refusées.")
        parameters = image.get("/DecodeParms")
        if (set(image.keys()) - {
            "/Type", "/Subtype", "/Width", "/Height", "/BitsPerComponent", "/ColorSpace",
            "/Length", "/Filter", "/Metadata", "/DecodeParms",
        } or (parameters is not None and (not isinstance(parameters, pikepdf.Dictionary) or parameters))
                or image.get("/Filter") not in (
            None, pikepdf.Name.FlateDecode, pikepdf.Name.ASCIIHexDecode, pikepdf.Name.DCTDecode,
        )):
            raise PDFError("Les paramètres ou l'encodage de cette image ne sont pas qualifiés.")
        colorspace = image.get("/ColorSpace")
        if isinstance(colorspace, pikepdf.Array):
            if (len(colorspace) != 2 or colorspace[0] != pikepdf.Name.ICCBased
                    or not isinstance(colorspace[1], pikepdf.Stream) or colorspace[1].get("/N") != 3
                    or sha256(colorspace[1].read_bytes()).hexdigest() != SUPPORTED_RGB_ICC_SHA256):
                raise PDFError("Le profil couleur ICC de cette image n'est pas qualifié.")
        elif colorspace not in (pikepdf.Name.DeviceGray, pikepdf.Name.DeviceRGB):
            raise PDFError("L'espace couleur de cette image n'est pas qualifié.")

    # ponytail: opérateurs des fixtures seulement ; élargir après preuve sur corpus.
    operators = {"q", "Q", "cm", "BT", "ET", "Tf", "Tm", "TJ", "Do", "Tr", "w", "M"}
    for item in pikepdf.parse_content_stream(page):
        operator = str(item.operator)
        if operator not in operators:
            raise PDFError("Un opérateur de page n'est pas qualifié (vecteur, découpe ou autre contenu).")
        if operator == "Tr" and (len(item.operands) != 1 or item.operands[0] not in (0, 3)):
            raise PDFError("Ce mode de rendu du texte, notamment la découpe, est refusé.")


def classify_zone(data: bytes, page_number: int, rectangle) -> str:
    """Reconnaît native/scan/ocr sur les octets originaux, sans les modifier.

    Résultat expérimental, pas une autorisation d'export : interactions entre zones,
    transformation et contrôles des octets finaux restent à effectuer.
    """
    try:
        with _open_supported_structure(data) as structure, _open_mupdf(data) as document:
            rect = _zone_rectangle(document, page_number, rectangle)
            _check_simple_page(structure.pages[page_number])
            page = document[page_number]
            images = [image for image in page.get_image_info(hashes=False, xrefs=False)
                      if pymupdf.Rect(image["bbox"]).intersects(rect)]
            spans = [span for span in page.get_texttrace()
                     if pymupdf.Rect(span["bbox"]).intersects(rect)]
            if any(span["opacity"] != 1 or span["wmode"] != 0 or span["dir"] != (1, 0)
                   or span["type"] not in (0, 3) for span in spans):
                raise PDFError("Ce rendu de texte n'est pas qualifié pour une substitution.")
            # ponytail: comparaison O(n²) des spans ciblés ; indexer si leur volume l'exige.
            for index, span in enumerate(spans):
                if any((pymupdf.Rect(span["bbox"]) & pymupdf.Rect(other["bbox"])).intersects(rect)
                       for other in spans[:index]):
                    raise PDFError("Une superposition de textes rend la zone ambiguë.")
            if not images:
                if not spans:
                    raise PDFError("Aucun contenu pris en charge n'est reconnu dans cette zone.")
                if any(span["type"] != 0 for span in spans):
                    raise PDFError("Un texte invisible sans scan ne peut pas être classé comme natif.")
                return "native"
            if len(images) != 1 or not pymupdf.Rect(images[0]["bbox"]).contains(rect):
                raise PDFError("La zone doit être entièrement dans une seule image sans superposition.")
            if any(span["type"] != 3 for span in spans):
                raise PDFError("La superposition de texte visible et d'image est ambiguë.")
            image = images[0]
            a, b, c, d, _, _ = image["transform"]
            # ponytail: scans à 2 px/point seulement ; qualifier les autres échelles avant extension.
            if (image["has-mask"] or image["colorspace"] not in (1, 3) or image["bpc"] != 8
                    or not all(isfinite(value) for value in image["transform"])
                    or b != 0 or c != 0 or a <= 0 or d <= 0
                    or abs(image["width"] / a - 2) > 1e-6
                    or abs(image["height"] / d - 2) > 1e-6):
                raise PDFError("Le format ou la transformation de cette image n'est pas qualifié.")
            check_image_reuse(document, page_number, rect)
            return "ocr" if spans else "scan"
    except PDFError:
        raise
    except (pikepdf.PdfError, RuntimeError, ValueError, TypeError, OverflowError, KeyError):
        raise PDFError("La zone ne peut pas être classée de façon fiable ; traitement refusé.") from None


def open_pdf(path: str | Path) -> pymupdf.Document:
    """Ouvre une copie mémoire ; l'appelant doit fermer le document retourné."""
    try:
        with open(path, "rb") as source:
            # Lire un octet au seuil suffit à refuser, même si le fichier grossit.
            size = source.seek(0, 2)
            _check_file_size(size)
            source.seek(0)
            data = source.read(MAX_FILE_BYTES)
    except OSError:
        raise PDFError("Impossible de lire le fichier sélectionné.") from None

    with _open_supported_structure(data):
        pass
    return _open_mupdf(data)


def _open_mupdf(data: bytes) -> pymupdf.Document:
    """Seconde lecture après inspection structurée ; mêmes contrôles pour tous les appelants."""
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (RuntimeError, ValueError):
        raise PDFError("Le fichier n'est pas un PDF valide pris en charge.") from None

    try:
        if not document.is_pdf:
            raise PDFError("Le fichier sélectionné n'est pas un PDF.")
        if document.is_encrypted or document.xref_get_key(-1, "Encrypt")[0] != "null":
            raise PDFError("Les PDF chiffrés ne sont pas pris en charge.")
        if document.is_repaired:
            raise PDFError("Le PDF est malformé et nécessite une réparation non prise en charge.")
        if not 1 <= document.page_count <= MAX_PAGES:
            raise PDFError("Le PDF doit contenir de 1 à 49 pages.")
        _check_images(document)
    except PDFError:
        document.close()
        raise
    except (RuntimeError, ValueError, OverflowError):
        document.close()
        raise PDFError("Impossible d'inspecter les images de ce PDF.") from None
    except Exception:
        document.close()
        raise
    return document
