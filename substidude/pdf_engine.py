# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Ouverture bornée du prototype ; aucune garantie de suppression à ce stade."""

from pathlib import Path

import pymupdf


# Les diagnostics natifs peuvent contenir des fragments du document non fiable.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_FILE_BYTES = 10_000_000
MAX_PAGES = 49


class PDFError(ValueError):
    """Erreur présentable sans contenu documentaire ni chemin source."""


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
    except Exception:
        document.close()
        raise
    return document
