# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Ouverture bornée du prototype ; aucune garantie de suppression à ce stade."""

from pathlib import Path
from math import isfinite

import pymupdf


# Les diagnostics natifs peuvent contenir des fragments du document non fiable.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_FILE_BYTES = 10_000_000
MAX_PAGES = 49
MAX_IMAGE_PIXELS = 40_000_000


class PDFError(ValueError):
    """Erreur présentable sans contenu documentaire ni chemin source."""


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


def open_pdf(path: str | Path) -> pymupdf.Document:
    """Ouvre une copie mémoire ; l'appelant doit fermer le document retourné."""
    try:
        with open(path, "rb") as source:
            # Lire un octet au seuil suffit à refuser, même si le fichier grossit.
            size = source.seek(0, 2)
            if size == 0:
                raise PDFError("Le fichier est vide (0 octet).")
            if size >= MAX_FILE_BYTES:
                raise PDFError("Le fichier doit faire strictement moins de 10 Mo.")
            source.seek(0)
            data = source.read(MAX_FILE_BYTES)
    except OSError:
        raise PDFError("Impossible de lire le fichier sélectionné.") from None

    if not data:
        raise PDFError("Le fichier est vide (0 octet).")
    if len(data) >= MAX_FILE_BYTES:
        raise PDFError("Le fichier doit faire strictement moins de 10 Mo.")

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
