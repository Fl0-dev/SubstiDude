# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Inspection et nettoyage bornés du prototype ; pas encore un pipeline d'export."""

from pathlib import Path
from math import isfinite
from io import BytesIO
import warnings

import pikepdf
import pymupdf


# Les diagnostics natifs peuvent contenir des fragments du document non fiable.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_FILE_BYTES = 10_000_000
MAX_PAGES = 49
MAX_IMAGE_PIXELS = 40_000_000


class PDFError(ValueError):
    """Erreur présentable sans contenu documentaire ni chemin source."""


def _check_file_size(size: int) -> None:
    if size == 0:
        raise PDFError("Le fichier est vide (0 octet).")
    if size >= MAX_FILE_BYTES:
        raise PDFError("Le fichier doit faire strictement moins de 10 Mo.")


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
            continue
        keys = set(obj.keys())
        for forbidden, message in unsupported:
            if keys & forbidden:
                raise PDFError(message)
        if obj.get("/Type") in (pikepdf.Name.OCG, pikepdf.Name.OCMD):
            raise PDFError("Les couches optionnelles ne sont pas prises en charge.")
        if obj.get("/Subtype") == pikepdf.Name.Type3:
            raise PDFError("Les polices Type 3 ne sont pas prises en charge.")
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


def check_image_reuse(document: pymupdf.Document, page_number: int, rectangle) -> None:
    """Refuse une modification locale d'image réutilisée ; ne valide pas le reste du PDF."""
    if not 0 <= page_number < document.page_count:
        raise PDFError("La page sélectionnée n'existe pas.")
    rect = pymupdf.Rect(rectangle)
    page = document[page_number]
    bounds = page.rect * page.derotation_matrix
    if (not all(isfinite(value) for value in rect) or rect.is_empty
            or not bounds.contains(rect)):
        raise PDFError("La zone doit être non vide et entièrement dans la page.")
    for occurrences in repeated_image_occurrences(document):
        if any(number == page_number and area.intersects(rect) for number, area in occurrences):
            pages = ", ".join(str(number + 1) for number in sorted({n for n, _ in occurrences}))
            raise PDFError(
                f"Une image de cette zone est réutilisée (pages {pages}). "
                "Le remplacement local est refusé pour éviter une modification implicite "
                "ou des pixels sensibles résiduels."
            )


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
