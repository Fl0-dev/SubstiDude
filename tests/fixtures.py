# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Documents synthétiques uniquement ; aucun fichier client."""

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont


FONT = Path(__file__).resolve().parents[1] / "substidude/resources/NotoSans-Regular.ttf"
TARGET = "SECRET-CIBLE-123"
KEPT = "TEMOIN-CONSERVE-456"
TARGET_RECT = (35, 70, 260, 105)


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
