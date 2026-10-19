# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Qualification native : objets imbriqués et images conservées, jamais éditées.

Ce chemin ne lève aucun refus raster. Les profils inconnus et références
auxiliaires non qualifiées restent refusés. Un clip ne couvrant pas le conteneur
peut découper les images/vecteurs conservés, jamais du texte (même imbriqué).
Les vecteurs ne doivent pas toucher les zones.
"""

from collections import Counter
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from math import isfinite

import pikepdf
import pymupdf

from substidude.pdf_engine import (
    PDFError, SUPPORTED_RGB_ICC_SHA256, _check_dictionary_keys, _check_icc_references,
    _check_image_dimensions, _check_stream_references, _open_mupdf,
)


def numbers(values, length):
    try:
        valid = len(values) == length and all(type(v) in (int, float, Decimal) and isfinite(float(v)) for v in values)
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        raise PDFError("Une géométrie native n'est pas qualifiée.")
    return [float(v) for v in values]


def matrix_value(values):
    matrix = pymupdf.Matrix(*numbers(values, 6))
    if not all(isfinite(v) for v in matrix) or matrix.a * matrix.d - matrix.b * matrix.c == 0:
        raise PDFError("Une transformation native invisible ou singulière est refusée.")
    return matrix


def color_components(space):
    if space == pikepdf.Name.DeviceRGB:
        return 3
    if space == pikepdf.Name.DeviceGray:
        return 1
    if isinstance(space, pikepdf.Array) and len(space) == 2 and space[0] == pikepdf.Name.ICCBased:
        _check_icc_references(space[1])
        if space[1].get("/N") != 3 or sha256(space[1].read_bytes()).hexdigest() != SUPPORTED_RGB_ICC_SHA256:
            raise PDFError("Le profil couleur ICC n'est pas qualifié.")
        return 3
    raise PDFError("L'espace couleur conservé n'est pas qualifié.")


def check_image(image, active=None):
    active = set() if active is None else active
    if not isinstance(image, pikepdf.Stream) or image.objgen in active:
        raise PDFError("Une référence image est invalide ou cyclique.")
    active = active | {image.objgen}
    allowed = {"/Type", "/Subtype", "/Width", "/Height", "/BitsPerComponent", "/ColorSpace", "/Length",
               "/Filter", "/DecodeParms", "/SMask", "/Metadata"}
    if (set(image.keys()) - allowed or image.get("/Subtype") != pikepdf.Name.Image
            or image.get("/Type") not in (None, pikepdf.Name.XObject)
            or image.get("/Filter") not in (None, pikepdf.Name.FlateDecode, pikepdf.Name.ASCIIHexDecode, pikepdf.Name.DCTDecode)):
        raise PDFError("Une image conservée contient des paramètres non qualifiés.")
    width, height, bits = image.get("/Width"), image.get("/Height"), image.get("/BitsPerComponent")
    if type(width) is not int or type(height) is not int or bits not in (1, 2, 4, 8) or type(bits) is not int:
        raise PDFError("Les dimensions ou composantes de l'image ne sont pas qualifiées.")
    _check_image_dimensions(width, height)
    space = image.get("/ColorSpace")
    if isinstance(space, pikepdf.Array) and len(space) == 4 and space[0] == pikepdf.Name.Indexed:
        components = color_components(space[1])
        maximum, palette = space[2], space[3]
        if type(maximum) is not int or not 0 <= maximum <= 255:
            raise PDFError("La palette de l'image n'est pas qualifiée.")
        if isinstance(palette, pikepdf.Stream):
            _check_stream_references(palette)
            palette = palette.read_bytes()
        elif isinstance(palette, pikepdf.String):
            palette = bytes(palette)
        else:
            raise PDFError("La palette contient une référence non qualifiée.")
        if len(palette) != (maximum + 1) * components:
            raise PDFError("La taille de palette n'est pas qualifiée.")
        components = 1
    else:
        components = color_components(space)
        if bits != 8:
            raise PDFError("La profondeur de l'image n'est pas qualifiée.")
    parameters = image.get("/DecodeParms")
    if parameters is not None:
        _check_dictionary_keys(parameters, {"/Predictor", "/Columns", "/Colors", "/BitsPerComponent"})
        if any(type(v) is not int for v in parameters.values()):
            raise PDFError("Les paramètres de l'image contiennent des références non qualifiées.")
        if (parameters.get("/Predictor", 1) not in (1, 2, 10, 11, 12, 13, 14, 15)
                or parameters.get("/Columns", width) != width
                or parameters.get("/Colors", components) != components
                or parameters.get("/BitsPerComponent", bits) != bits):
            raise PDFError("Le prédicteur de l'image conservée n'est pas qualifié.")
    if "/SMask" in image:
        mask = image.SMask
        check_image(mask, active)
        if (mask.get("/ColorSpace") != pikepdf.Name.DeviceGray or "/SMask" in mask
                or (mask.Width, mask.Height) != (width, height)):
            raise PDFError("Le masque conservé n'est pas qualifié.")


def canonical(value, active=None):
    """Empreinte structurelle indépendante des numéros d'objet, sans valeurs affichées."""
    active = set() if active is None else active
    if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
        if value.objgen != (0, 0) and value.objgen in active:
            raise PDFError("Une référence de l'image est cyclique.")
        active = active | ({value.objgen} if value.objgen != (0, 0) else set())
        if isinstance(value, pikepdf.Array):
            return tuple(canonical(v, active) for v in value)
        fields = tuple(sorted((key, canonical(v, active)) for key, v in value.items()
                              if key not in {"/Length", "/Metadata"}))
        return (fields, sha256(value.read_raw_bytes()).digest()) if isinstance(value, pikepdf.Stream) else fields
    if isinstance(value, pikepdf.Name):
        return ("name", str(value))
    if isinstance(value, pikepdf.String):
        return ("string", sha256(bytes(value)).digest())
    if type(value) in (int, float, Decimal):
        return ("number", float(value))
    if value is None or type(value) is bool:
        return value
    raise PDFError("Une propriété d'image n'est pas qualifiée.")


def image_inventory(structure):
    result = Counter()
    for obj in structure.objects:
        if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name.Image:
            check_image(obj)
            result[canonical(obj)] += 1
    return result


def check_image_visibility(structure, document):
    images = {obj.objgen[0]: obj for obj in structure.objects
              if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name.Image}
    # get_image_info(xrefs=True) associe par hash et confond les objets distincts
    # aux mêmes pixels. Résoudre les Do avec les ressources de leur conteneur.
    visible = set()
    def visit(container, resources, active):
        if len(active) > 32:
            raise PDFError("L'imbrication des images natives n'est pas qualifiée.")
        for item in pikepdf.parse_content_stream(container):
            if str(item.operator) != "Do":
                continue
            if len(item.operands) != 1 or not isinstance(item.operands[0], pikepdf.Name):
                raise PDFError("Une référence image native est incohérente.")
            xobjects = resources.get("/XObject", pikepdf.Dictionary())
            target = xobjects.get(item.operands[0])
            if not isinstance(target, pikepdf.Stream):
                raise PDFError("Une référence image native est incohérente.")
            if target.get("/Subtype") == pikepdf.Name.Image:
                visible.add(target.objgen[0])
            elif target.get("/Subtype") == pikepdf.Name.Form:
                if target.objgen in active:
                    raise PDFError("Une référence Form native est cyclique.")
                visit(target, target.get("/Resources", pikepdf.Dictionary()), active | {target.objgen})
            else:
                raise PDFError("Une référence graphique native n'est pas qualifiée.")
    for page in structure.pages:
        visit(page, page.obj.get("/Resources", pikepdf.Dictionary()), set())
    allowed = set(visible)
    for xref in visible:
        if xref not in images:
            raise PDFError("Une référence image native est incohérente.")
        if "/SMask" in images[xref]:
            allowed.add(images[xref].SMask.objgen[0])
    if set(images) != allowed:
        raise PDFError("Une image non affichée ne peut pas être conservée.")


def rectangular_path(path):
    """Un rectangle unique, y compris écrit m/l/h, jamais sa seule enveloppe."""
    if len(path) == 1 and isinstance(path[0], pymupdf.Rect):
        return path[0]
    if not path or any(not isinstance(item, tuple) for item in path):
        return None
    if path[0][0] != "m" or path[-1][0] != "h" or any(item[0] != "l" for item in path[1:-1]):
        return None
    points = [item[1] for item in path[:-1]]
    if len(points) == 5 and points[0] == points[-1]:
        points.pop()
    if len(points) != 4:
        return None
    for first, last in zip(points, points[1:] + points[:1]):
        if first == last or (first.x != last.x and first.y != last.y):
            return None
    xs, ys = {p.x for p in points}, {p.y for p in points}
    if len(xs) != 2 or len(ys) != 2 or len({(p.x, p.y) for p in points}) != 4:
        return None
    return pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))


def unclipped_characters(current, media_box):
    """Sonde en mémoire : enlever les clips explicites dans une copie seulement.

    Les caractères sont remis dans le repère PDF du conteneur. Chaque Form
    est également sondé séparément pour contrôler sa boîte implicite.
    """
    with pikepdf.Pdf.new() as probe:
        copied = probe.copy_foreign(current)
        page_copy = probe.add_blank_page()
        page_copy.obj.MediaBox = media_box
        page_copy.obj.Resources = copied.Resources
        content = copied if isinstance(copied, pikepdf.Stream) else pikepdf.Page(copied)
        instructions = pikepdf.parse_content_stream(content)
        page_copy.obj.Contents = probe.make_stream(pikepdf.unparse_content_stream(
            [item for item in instructions if str(item.operator) not in {"W", "W*"}]))
        for form in list(probe.objects):
            if isinstance(form, pikepdf.Stream) and form.get("/Subtype") == pikepdf.Name.Form:
                instructions = pikepdf.parse_content_stream(form)
                form.write(pikepdf.unparse_content_stream(
                    [item for item in instructions if str(item.operator) not in {"W", "W*"}]))
        output = BytesIO()
        probe.save(output)
    with _open_mupdf(output.getvalue()) as inspected:
        inverse = ~inspected[0].transformation_matrix
        return [pymupdf.Rect(char[3]) * inverse for span in inspected[0].get_texttrace() for char in span["chars"]]


def check_page(page):
    """Liste positive native avec Form ; les nouvelles images sont copie-seule."""
    obj = page.obj
    _check_dictionary_keys(obj, {"/Type", "/Parent", "/Contents", "/Resources", "/MediaBox", "/CropBox", "/Rotate", "/Metadata", "/Thumb", "/Annots", "/Group"})
    if obj.get("/Annots"):
        raise PDFError("Les annotations et liens PDF ne sont pas pris en charge.")
    def check_group(group):
        if group is not None:
            _check_dictionary_keys(group, {"/Type", "/S", "/CS"})
            if group.get("/Type") not in (None, pikepdf.Name.Group) or group.get("/S") != pikepdf.Name.Transparency:
                raise PDFError("Le groupe graphique natif n'est pas qualifié.")
            if "/CS" in group:
                color_components(group.CS)
    check_group(obj.get("/Group"))
    forms = {}
    character_cache = {}
    operators = {"q", "Q", "cm", "BT", "ET", "Tf", "Tm", "TJ", "Tj", "Td", "TD", "T*", "Tc", "Tw", "Tz", "TL", "Ts", "Tr",
                 "Do", "w", "M", "J", "j", "d", "g", "G", "rg", "RG", "k", "K", "m", "l", "c", "v", "y", "h", "re",
                 "S", "s", "f", "f*", "B", "B*", "n", "W", "W*"}

    def container(current, bounds, active, text_clip_safe=True):
        if len(active) > 32:
            raise PDFError("L'imbrication des objets Form n'est pas qualifiée.")
        resources = current.get("/Resources")
        _check_dictionary_keys(resources, {"/Font", "/XObject", "/ProcSet"})
        fonts = resources.get("/Font", pikepdf.Dictionary())
        xobjects = resources.get("/XObject", pikepdf.Dictionary())
        if not isinstance(fonts, pikepdf.Dictionary) or not isinstance(xobjects, pikepdf.Dictionary):
            raise PDFError("Les ressources natives ne sont pas qualifiées.")
        for value in xobjects.values():
            if not isinstance(value, pikepdf.Stream) or value.get("/Subtype") not in (pikepdf.Name.Image, pikepdf.Name.Form):
                raise PDFError("Un objet graphique natif n'est pas qualifié.")
            if value.get("/Subtype") == pikepdf.Name.Image:
                check_image(value)
        content = page if current is obj else current
        def characters():
            if current.objgen not in character_cache:
                character_cache[current.objgen] = unclipped_characters(current, list(bounds))
            return character_cache[current.objgen]
        matrix, font, stack, path = pymupdf.Matrix(1, 1), None, [], []
        for instruction in pikepdf.parse_content_stream(content):
            op, args = str(instruction.operator), instruction.operands
            if op not in operators:
                raise PDFError("Un opérateur de page native n'est pas qualifié.")
            if op == "q":
                stack.append((pymupdf.Matrix(matrix), font, text_clip_safe))
            elif op == "Q":
                if not stack:
                    raise PDFError("L'état graphique natif n'est pas équilibré.")
                matrix, font, text_clip_safe = stack.pop()
            elif op == "cm":
                matrix = matrix_value(args) * matrix
                matrix_value(tuple(matrix))
            elif op == "Tf":
                if len(args) != 2 or not isinstance(args[0], pikepdf.Name) or args[0] not in fonts:
                    raise PDFError("Une référence de police native n'est pas qualifiée.")
                font = fonts[args[0]]
            elif op in {"Tj", "TJ"}:
                if not text_clip_safe:
                    raise PDFError("Un découpage peut masquer du texte natif ; traitement refusé.")
                if font is None:
                    raise PDFError("Le contexte de police natif n'est pas qualifié.")
                strings = args[0] if op == "TJ" else args
                if font.get("/Subtype") == pikepdf.Name.TrueType and len(font.Widths) != font.LastChar - font.FirstChar + 1:
                    if any(isinstance(v, pikepdf.String) and font.LastChar in bytes(v) for v in strings):
                        raise PDFError("Un caractère utilise une largeur de police manquante ; traitement refusé.")
            elif op == "Tr" and (len(args) != 1 or args[0] not in (0, 3)):
                raise PDFError("Le mode de rendu natif n'est pas qualifié.")
            elif op == "re":
                x, y, width, height = numbers(args, 4)
                # La boîte englobante d'un rectangle cisaillé/tourné ne prouve
                # pas que le conteneur est entièrement couvert.
                axis_aligned = (matrix.b == matrix.c == 0 or matrix.a == matrix.d == 0)
                rectangle = pymupdf.Rect(min(x, x + width), min(y, y + height), max(x, x + width), max(y, y + height))
                path.append(rectangle * matrix if axis_aligned else None)
            elif op in {"m", "l"}:
                path.append((op, pymupdf.Point(numbers(args, 2)) * matrix))
            elif op == "h":
                path.append((op,))
            elif op in {"c", "v", "y"}:
                path.append(None)
            elif op in {"W", "W*"}:
                if not path:
                    raise PDFError("Un découpage sans chemin n'est pas qualifié.")
                rectangle = rectangular_path(path)
                text_clip_safe = (text_clip_safe and rectangle is not None
                                  and (rectangle.contains(bounds)
                                       or all(rectangle.contains(char) for char in characters())))
            elif op in {"S", "s", "f", "f*", "B", "B*", "n"}:
                path = []
            elif op == "Do":
                if len(args) != 1 or not isinstance(args[0], pikepdf.Name) or args[0] not in xobjects:
                    raise PDFError("Une référence graphique native n'est pas qualifiée.")
                form = xobjects[args[0]]
                if form.get("/Subtype") != pikepdf.Name.Form:
                    continue
                if form.objgen in active:
                    raise PDFError("Une référence Form native est cyclique.")
                _check_stream_references(form, {"/Type", "/Subtype", "/BBox", "/Matrix", "/Resources", "/FormType", "/Group"})
                if type(form.get("/FormType", 1)) is not int or form.get("/FormType", 1) != 1:
                    raise PDFError("Ce type de Form natif n'est pas qualifié.")
                bbox = pymupdf.Rect(numbers(form.get("/BBox"), 4))
                if bbox.is_empty or bbox.is_infinite:
                    raise PDFError("La boîte du Form natif est invalide.")
                if "/Matrix" in form:
                    matrix_value(form.Matrix)
                check_group(form.get("/Group"))
                forms[form.objgen] = form
                container(form, bbox, active | {form.objgen}, text_clip_safe)
        if stack:
            raise PDFError("L'état graphique natif n'est pas équilibré.")
        # Une ressource peut être partagée par plusieurs conteneurs. La garde
        # documentaire vérifie chaque objet Form, pas chaque alias de ressource.

    container(obj, pymupdf.Rect(numbers(obj.get("/MediaBox"), 4)), set())
    # La sonde retire aussi les clips explicites pour ne pas laisser ceux-ci
    # dissimuler un caractère hors de la boîte implicite du Form.
    for form in forms.values():
        bounds = pymupdf.Rect(numbers(form.BBox, 4))
        characters = character_cache.get(form.objgen)
        if characters is None:
            characters = unclipped_characters(form, list(bounds))
        if any(not bounds.contains(char) for char in characters):
            raise PDFError("Un texte est masqué par la boîte d'un Form ; traitement refusé.")
    return set(forms)


def check_document(structure, document):
    reached = set()
    for page in structure.pages:
        reached.update(check_page(page))
    existing = {obj.objgen for obj in structure.objects
                if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name.Form}
    if existing != reached:
        raise PDFError("Un Form non affiché ne peut pas être conservé.")
    check_image_visibility(structure, document)


def check_zone(page, rectangle):
    """Refuser tout vecteur touchant la zone, sans bloquer les traits voisins."""
    rect = pymupdf.Rect(rectangle)
    for drawing in page.get_drawings(extended=True):
        if drawing["type"] in {"clip", "group"}:
            continue  # Les clips et groupes sont déjà qualifiés structurellement.
        bounds = pymupdf.Rect(drawing["rect"])
        margin = float(drawing.get("width", 0) or 0) / 2 + 0.5
        if not (bounds + (-margin, -margin, margin, margin)).intersects(rect):
            continue
        if drawing["type"] == "s":
            segments = []
            for item in drawing["items"]:
                if item[0] == "l":
                    segments.append((item[1], item[2]))
                elif item[0] == "re":
                    box = item[1]
                    segments.extend(((box.tl, box.tr), (box.tr, box.br), (box.br, box.bl), (box.bl, box.tl)))
                else:
                    raise PDFError("Un opérateur vectoriel proche de la zone n'est pas qualifié.")
            for first, last in segments:
                if first.x != last.x and first.y != last.y:
                    raise PDFError("Un opérateur vectoriel proche de la zone n'est pas qualifié.")
                box = pymupdf.Rect(min(first.x, last.x) - margin, min(first.y, last.y) - margin,
                                  max(first.x, last.x) + margin, max(first.y, last.y) + margin)
                if box.intersects(rect):
                    raise PDFError("Un opérateur vectoriel traverse la zone ; traitement refusé.")
        else:
            raise PDFError("Un opérateur vectoriel rempli touche la zone ; traitement refusé.")
