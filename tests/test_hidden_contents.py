# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""11B : représentations internes, distinctes des occurrences indépendantes hors zone."""

from hashlib import sha256
from io import BytesIO
import struct
import unittest
from unittest.mock import patch

import pikepdf
import pymupdf

from fixtures import TARGET, TARGET_RECT, hidden_content_pdf, make_pdf
from substidude.pdf_engine import PDFError, sanitize_pdf
from test_independent import render_and_extract
from test_pipeline import outside_characters, replace_zones


FEATURES = ("font-name-record", "cmap-comment", "cmap-unused-mapping", "font-name-value",
            "cid-registry-value", "cid-ordering-value", "catalog-lang", "viewer-preferences",
            "pages-value", "trailer-value")


def recovered_target(data, feature):
    """Récupère le champ concerné, pas une recherche brute dans les octets du PDF."""
    with pikepdf.Pdf.open(BytesIO(data)) as document:
        font = document.pages[0].obj.Resources.Font.noto
        if feature == "font-name-record":
            program = font.DescendantFonts[0].FontDescriptor.FontFile2.read_bytes()
            count = struct.unpack_from(">H", program, 4)[0]
            for index in range(count):
                tag, _, offset, length = struct.unpack_from(">4sIII", program, 12 + index * 16)
                if tag != b"name":
                    continue
                names = program[offset:offset + length]
                _, records, storage = struct.unpack_from(">HHH", names)
                for record in range(records):
                    platform, _, _, name_id, size, start = struct.unpack_from(">HHHHHH", names, 6 + record * 12)
                    if platform == 3 and name_id == 10:
                        value = names[storage + start:storage + start + size].decode("utf-16-be")
                        if value == TARGET:
                            return value
        elif feature == "cmap-comment":
            for line in font.ToUnicode.read_bytes().splitlines():
                if line == b"% " + TARGET.encode():
                    return line[2:].decode()
        elif feature == "cmap-unused-mapping":
            for line in font.ToUnicode.read_bytes().splitlines():
                if line.startswith(b"<FFFF> <"):
                    return bytes.fromhex(line.split()[1][1:-1].decode()).decode("utf-16-be")
        elif feature == "font-name-value":
            return str(font.BaseFont)[1:]
        elif feature in {"cid-registry-value", "cid-ordering-value"}:
            key = "/Registry" if feature == "cid-registry-value" else "/Ordering"
            return str(font.DescendantFonts[0].CIDSystemInfo[key])
        elif feature == "catalog-lang":
            return str(document.Root.get("/Lang", ""))
        elif feature == "viewer-preferences":
            return str(document.Root.get("/ViewerPreferences", {}).get("/Private", ""))
        elif feature == "pages-value":
            return str(document.Root.Pages.get("/Private", ""))
        elif feature == "trailer-value":
            return str(document.trailer.get("/Private", ""))
    return None


class HiddenContentTests(unittest.TestCase):
    def assert_independent_recovery(self, data, feature):
        # MuPDF relit les objets de la sortie qpdf ; PDFium contrôle séparément
        # texte/rendu. Le contenu récupéré ne dépend pas de l'extraction de page.
        with pikepdf.Pdf.open(BytesIO(data)) as structure, pymupdf.open(stream=data) as reader:
            font = structure.pages[0].obj.Resources.Font.noto
            if feature in {"font-name-record", "cmap-comment", "cmap-unused-mapping"}:
                stream = (font.DescendantFonts[0].FontDescriptor.FontFile2
                          if feature == "font-name-record" else font.ToUnicode)
                self.assertEqual(stream.read_bytes(), reader.xref_stream(stream.objgen[0]))
            else:
                container, key = {
                    "font-name-value": (font, "BaseFont"),
                    "cid-registry-value": (font.DescendantFonts[0], "CIDSystemInfo/Registry"),
                    "cid-ordering-value": (font.DescendantFonts[0], "CIDSystemInfo/Ordering"),
                    "catalog-lang": (structure.Root, "Lang"),
                    "viewer-preferences": (structure.Root, "ViewerPreferences/Private"),
                    "pages-value": (structure.Root.Pages, "Private"),
                    "trailer-value": (None, "Private"),
                }[feature]
                kind, value = reader.xref_get_key(-1 if container is None else container.objgen[0], key)
                self.assertEqual("name" if feature == "font-name-value" else "string", kind)
                self.assertEqual(("/" if kind == "name" else "") + TARGET, value)

    def test_internal_residue_after_unchecked_rewrite(self):
        for feature in FEATURES:
            with self.subTest(feature=feature):
                source = hidden_content_pdf(feature)
                self.assertEqual(TARGET, recovered_target(source, feature))
                self.assert_independent_recovery(source, feature)
                before, original_text, _, _ = render_and_extract(source)
                self.assertIn(TARGET, original_text)
                with pymupdf.open(stream=source) as document:
                    document[0].add_redact_annot(TARGET_RECT)
                    document[0].apply_redactions(images=0, graphics=0, text=0)
                    rewritten = document.tobytes(garbage=4, deflate=True)
                with pikepdf.Pdf.open(BytesIO(rewritten)) as document:
                    output = BytesIO()
                    document.save(output)
                result = output.getvalue()
                # Le scan original est volontairement intact ici : cette expérience
                # porte seulement sur la suppression OCR et les conteneurs survivants.
                after, final_text, _, _ = render_and_extract(result)
                self.assertEqual(before.tobytes(), after.tobytes())
                self.assertNotIn(TARGET, final_text)
                if feature == "trailer-value":
                    # MuPDF élimine ce champ sur la fixture ; ne pas inventer un résidu.
                    self.assertEqual("", recovered_target(result, feature))
                else:
                    self.assertEqual(TARGET, recovered_target(result, feature))
                    self.assert_independent_recovery(result, feature)

    def test_independent_invisible_occurrence_is_preserved(self):
        with pymupdf.open(stream=make_pdf("ocr")) as document:
            document[0].insert_text((40, 235), TARGET, fontname="noto", fontsize=16, render_mode=3)
            source = document.tobytes(garbage=4, deflate=True)
        digest = sha256(source).digest()
        result = replace_zones(source, [(0, TARGET_RECT, "Toto")])
        with pymupdf.open(stream=source) as original, pymupdf.open(stream=result) as final:
            self.assertEqual(outside_characters(original[0], [pymupdf.Rect(TARGET_RECT)]),
                             outside_characters(final[0], [pymupdf.Rect(TARGET_RECT)]))
            self.assertNotIn(TARGET, final[0].get_textbox(TARGET_RECT))
            self.assertIn(TARGET, final[0].get_textbox((35, 210, 260, 245)))
            self.assertEqual(3, final[0].get_texttrace()[-1]["type"])
        before, _, _, _ = render_and_extract(source)
        after, text, _, _ = render_and_extract(result)
        # Occurrence indépendante hors zone conservée, pas un résidu de l'OCR ciblé.
        self.assertIn(TARGET, text)
        before.paste((255, 255, 255), (70, 140, 520, 210))
        after.paste((255, 255, 255), (70, 140, 520, 210))
        self.assertEqual(before.tobytes(), after.tobytes())
        self.assertEqual(digest, sha256(source).digest())

    def test_hidden_target_cannot_be_returned_as_a_verified_result(self):
        # Test de postcondition ajouté avant correctif : retrait démontré OU refus.
        # Aucun contrôle n'est contourné et aucun test n'est ignoré.
        for feature in FEATURES:
            with self.subTest(feature=feature):
                source = hidden_content_pdf(feature)
                digest = sha256(source).digest()
                try:
                    result = replace_zones(source, [(0, TARGET_RECT, "Toto")])
                except PDFError as error:
                    self.assertNotIn(TARGET, str(error))
                else:
                    self.assertNotEqual(TARGET, recovered_target(result, feature))
                self.assertEqual(digest, sha256(source).digest())

    def test_final_internal_contamination_blocks_result(self):
        for feature in FEATURES:
            with self.subTest(feature=feature):
                def contaminate(data):
                    return hidden_content_pdf(feature, data=sanitize_pdf(data))

                with patch("substidude.pipeline.sanitize_pdf", contaminate):
                    with self.assertRaises(PDFError) as caught:
                        replace_zones(make_pdf("ocr"), [(0, TARGET_RECT, "Toto")])
                self.assertNotIn(TARGET, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
