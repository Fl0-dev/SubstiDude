# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Documents synthétiques uniquement ; aucun fichier client."""

from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

import pymupdf
import pikepdf
from PIL import Image, ImageDraw, ImageFont


FONT = Path(__file__).resolve().parents[1] / "substidude/resources/NotoSans-Regular.ttf"
TARGET = "SECRET-CIBLE-123"
KEPT = "TEMOIN-CONSERVE-456"
TARGET_RECT = (35, 70, 260, 105)


def extract_with_pdftotext(data):
    with tempfile.TemporaryDirectory(prefix="substidude-test-") as directory:
        path = Path(directory) / "synthetic.pdf"
        path.write_bytes(data)
        completed = subprocess.run(
            [shutil.which("pdftotext"), "-enc", "UTF-8", str(path), "-"],
            capture_output=True, check=True, timeout=15,
        )
        return completed.stdout.decode("utf-8")


def scan_image(height=800):
    image = Image.new("RGB", (600, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), 32)
    draw.text((80, 190), TARGET, font=font, fill="black", anchor="ls")
    draw.text((80, 350), KEPT, font=font, fill="black", anchor="ls")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def make_pdf(kind="native", *, pages=1, rotation=0, cropped=False,
             encrypted=False, user_password="synthetic-user"):
    if kind not in {"native", "scan", "ocr", "mixed"}:
        raise ValueError("Type de fixture inconnu")
    with pymupdf.open() as document:
        for _ in range(pages):
            page = document.new_page(width=300, height=400)
            page.insert_font(fontname="noto", fontfile=str(FONT))
            if kind in {"scan", "ocr"}:
                page.insert_image(page.rect, stream=scan_image())
            if kind in {"native", "ocr", "mixed"}:
                mode = 3 if kind == "ocr" else 0
                page.insert_text((40, 95), TARGET, fontname="noto", fontsize=16, render_mode=mode)
                page.insert_text((40, 175), KEPT, fontname="noto", fontsize=16, render_mode=mode)
            if kind == "mixed":
                page.insert_image((0, 200, 300, 400), stream=scan_image(height=400))
            if cropped:
                page.set_cropbox(pymupdf.Rect(10, 20, 290, 390))
            page.set_rotation(rotation)
        options = {}
        if encrypted:
            options = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                           owner_pw="synthetic-owner", user_pw=user_password)
        return document.tobytes(garbage=4, deflate=True, **options)


def zero_page_pdf():
    # PDF structurellement valide, avec un arbre de pages vide.
    data = b"%PDF-1.7\n"
    offsets = [0]
    for number, body in enumerate([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 0 /Kids [] >>",
    ], start=1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 3\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return data + f"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def image_dimensions_pdf(width, height, *, inline=False, mask=False, nested=False):
    """Petite fixture structurelle ; ne jamais rendre ses fausses grandes images."""
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=400)
        if inline:
            import zlib
            content = (f"q 100 0 0 100 0 0 cm BI /W {width} /H {height} "
                       "/BPC 8 /CS /G /F /Fl ID\n").encode()
            content += zlib.compress(b"\x00") + b"\nEI Q"
            xref = document.get_new_xref()
            document.update_object(xref, "<< >>")
            document.update_stream(xref, content)
            page.set_contents(xref)
        else:
            image_xref = page.insert_image(page.rect, stream=scan_image())
            if mask:
                mask_xref = document.get_new_xref()
                document.update_object(mask_xref, (
                    f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                    "/BitsPerComponent 8 /ColorSpace /DeviceGray >>"
                ))
                document.update_stream(mask_xref, b"\x00")
                document.xref_set_key(image_xref, "SMask", f"{mask_xref} 0 R")
            else:
                document.xref_set_key(image_xref, "Width", str(width))
                document.xref_set_key(image_xref, "Height", str(height))
        if nested:
            with pymupdf.open() as wrapper:
                outer_page = wrapper.new_page(width=300, height=400)
                outer_page.show_pdf_page(outer_page.rect, document, 0)
                return wrapper.tobytes(deflate=True)
        return document.tobytes(deflate=True)


def repeated_images_pdf(*, separate_objects=False, reencoded=False, nested=False, same_page=False):
    """Deux occurrences d'un scan ; objets distincts si demandé, sans dédoublonnage."""
    first = scan_image()
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=800 if same_page else 400)
        first_xref = page.insert_image((0, 0, 300, 400), stream=first)
        if not same_page:
            page = document.new_page(width=300, height=400)
        rect = (0, 400, 300, 800) if same_page else (0, 0, 300, 400)
        if separate_objects:
            # Copier dans le même document pour conserver les références de profil couleur.
            copied = document.get_new_xref()
            document.update_object(copied, "<< >>")
            document.xref_copy(first_xref, copied)
            if reencoded:
                raw = document.xref_stream(first_xref)
                document.update_stream(copied, raw.hex().encode() + b">", compress=False)
                document.xref_set_key(copied, "Filter", "/ASCIIHexDecode")
            page.insert_image(rect, xref=copied)
        else:
            page.insert_image(rect, xref=first_xref)
        if nested:
            with pymupdf.open() as wrapper:
                for number in range(document.page_count):
                    size = document[number].rect
                    outer = wrapper.new_page(width=size.width, height=size.height)
                    outer.show_pdf_page(outer.rect, document, number)
                return wrapper.tobytes(garbage=0, deflate=False)
        return document.tobytes(garbage=0, deflate=False)


AUXILIARY_MARKER = "SECRET-AUXILIAIRE-789"


def auxiliary_pdf(feature, *, nested=False):
    with pikepdf.Pdf.open(BytesIO(make_pdf())) as document:
        page = document.pages[0]
        if feature in {"actualtext", "escaped-actualtext"}:
            key = b"/ActualText" if feature == "actualtext" else b"/#41ctualText"
            content = b"\n".join(stream.read_bytes() for stream in page.obj.Contents)
            page.obj.Contents = document.make_stream(
                b"/Span << " + key + b" (" + AUXILIARY_MARKER.encode() + b") >> BDC\n"
                + content + b"\nEMC"
            )
        elif feature == "properties":
            page.obj.Resources.Properties = pikepdf.Dictionary(
                P=pikepdf.Dictionary(ActualText=AUXILIARY_MARKER)
            )
        elif feature == "metadata":
            document.docinfo.Title = AUXILIARY_MARKER
            document.Root.Info = pikepdf.Dictionary(Title=AUXILIARY_MARKER + "-CATALOG")
            with document.open_metadata(set_pikepdf_as_editor=False) as metadata:
                metadata["dc:description"] = AUXILIARY_MARKER
            # Une deuxième référence XMP sur la page, pas seulement dans le catalogue.
            page.obj.Metadata = document.Root.Metadata
        elif feature == "thumbnail":
            image = document.make_stream(b"\xff\xff\xff" * 4)
            image.Type, image.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            image.Width, image.Height = 2, 2
            image.BitsPerComponent, image.ColorSpace = 8, pikepdf.Name.DeviceRGB
            page.obj.Thumb = image
        elif feature == "annotation":
            page.obj.Annots = pikepdf.Array([document.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Text,
                Rect=[20, 20, 40, 40], Contents=AUXILIARY_MARKER,
            ))])
        elif feature == "form":
            document.Root.AcroForm = pikepdf.Dictionary(Fields=[document.make_indirect(
                pikepdf.Dictionary(FT=pikepdf.Name.Tx, T="synthetic", V=AUXILIARY_MARKER)
            )])
        elif feature == "attachment":
            document.attachments["synthetic.txt"] = pikepdf.AttachedFileSpec(
                document, AUXILIARY_MARKER.encode(), filename="synthetic.txt"
            )
        elif feature == "action":
            document.Root.OpenAction = pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=AUXILIARY_MARKER)
        elif feature == "layer":
            group = document.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name=AUXILIARY_MARKER))
            document.Root.OCProperties = pikepdf.Dictionary(OCGs=[group], D=pikepdf.Dictionary(OFF=[group]))
        elif feature == "structure":
            document.Root.StructTreeRoot = pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot)
        elif feature == "destination":
            document.Root.Names = pikepdf.Dictionary(Dests=pikepdf.Dictionary(
                Names=[AUXILIARY_MARKER, pikepdf.Array([page.obj, pikepdf.Name.Fit])]
            ))
        elif feature == "type3":
            page.obj.Resources.Font.SyntheticType3 = document.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type3,
                FontBBox=[0, 0, 1000, 1000], FontMatrix=[0.001, 0, 0, 0.001, 0, 0],
                CharProcs=pikepdf.Dictionary(A=document.make_stream(b"1000 0 d0")),
                Encoding=pikepdf.Dictionary(Type=pikepdf.Name.Encoding, Differences=[65, pikepdf.Name.A]),
                FirstChar=65, LastChar=65, Widths=[1000], Resources=pikepdf.Dictionary(),
            ))
        elif feature == "ambiguous-metadata":
            page.obj.Metadata = pikepdf.Dictionary(Private=AUXILIARY_MARKER)
        elif feature == "unknown-root":
            document.Root.Unqualified = pikepdf.Dictionary(Contents=AUXILIARY_MARKER)
        elif feature == "postscript":
            stream = document.make_stream(b"%!\n")
            stream.Type, stream.Subtype = pikepdf.Name.XObject, pikepdf.Name.PS
            page.obj.Resources.XObject = pikepdf.Dictionary(Synthetic=stream)
        elif feature == "alternate-image":
            images = []
            for color in (b"\xff\xff\xff", b"\x00\x00\x00"):
                image = document.make_stream(color)
                image.Type, image.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
                image.Width, image.Height = 1, 1
                image.BitsPerComponent, image.ColorSpace = 8, pikepdf.Name.DeviceRGB
                images.append(image)
            images[0].Alternates = [pikepdf.Dictionary(Image=images[1], DefaultForPrinting=True)]
            page.obj.Resources.XObject = pikepdf.Dictionary(Synthetic=images[0])
        else:
            raise ValueError("Contenu auxiliaire synthétique inconnu")
        if nested:
            content = b"\n".join(s.read_bytes() for s in page.obj.Contents) if isinstance(
                page.obj.Contents, pikepdf.Array
            ) else page.obj.Contents.read_bytes()
            form = document.make_stream(content)
            form.Type, form.Subtype = pikepdf.Name.XObject, pikepdf.Name.Form
            form.BBox, form.Resources = [0, 0, 300, 400], page.obj.Resources
            page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm=form))
            page.obj.Contents = document.make_stream(b"/Fm Do")
        output = BytesIO()
        document.save(output)
        return output.getvalue()


def incremental_pdf():
    with tempfile.TemporaryDirectory(prefix="substidude-test-") as directory:
        path = Path(directory) / "synthetic.pdf"
        with pymupdf.open(stream=make_pdf()) as document:
            document.set_metadata({"title": AUXILIARY_MARKER + "-OLD"})
            document.save(path)
        previous = path.read_bytes()
        with pymupdf.open(path) as document:
            document.set_metadata({"title": AUXILIARY_MARKER + "-CURRENT"})
            document.saveIncr()
        return previous, path.read_bytes()
