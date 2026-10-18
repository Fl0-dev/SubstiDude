# Inventaire initial des composants tiers

Cet inventaire décrit l'environnement du prototype Windows 64 bits. Ce n'est
pas encore l'inventaire d'un exécutable livré : aucun paquet applicatif n'est
distribué à cette étape. Les mentions des auteurs et textes de licence doivent
être conservés intégralement dans toute distribution concernée.

## Exécution et ressources

| Composant | Version testée | Licence / notice de référence |
| --- | --- | --- |
| Python | 3.12.0, 64 bits | PSF et licences historiques, `C:\Python312\LICENSE.txt` sur le poste de préparation ; utiliser une version corrective à jour avant documents non fiables. |
| PyMuPDF / MuPDF | 1.28.2 / 1.28.2 | Option GNU AGPLv3 retenue, pas de licence commerciale. Métadonnées et `pymupdf-1.28.2.dist-info/COPYING` ; ce dernier ne contient qu'une déclaration de double licence. |
| Pillow | 13.0.0 | MIT-CMU et notices des bibliothèques embarquées, `pillow-13.0.0.dist-info/licenses/LICENSE`. |
| Noto Sans Regular | Fichier TTF versionné dans les ressources | Copyright 2018 The Noto Project Authors ; SIL OFL 1.1, texte intégral dans `substidude/resources/OFL.txt`. Redistribution et intégration autorisées sous ses conditions. |
| PySide6 / Qt | Non installés à cette étape | À inventorier lors de leur ajout : versions, modules, notices et obligations LGPL des composants réellement livrés. |

Les chemins `*.dist-info` ci-dessus sont relatifs à `.venv/Lib/site-packages`.
Les sources amont de PyMuPDF et MuPDF sont respectivement
https://github.com/pymupdf/PyMuPDF et https://github.com/ArtifexSoftware/mupdf.
Avant distribution, obtenir les notices intégrales correspondant aux versions
exactes de MuPDF et de ses composants tiers ; la seule déclaration de double
licence de la roue ne suffit pas.

### Bibliothèques natives de Pillow

La notice intégrale de la roue installée contient les sections suivantes :
Brotli 1.2.0, FreeType 2.14.3, HarfBuzz 14.5.0, Little CMS 2.19.1,
libavif 1.4.2 et ses composants, libjpeg-turbo 3.2.0, libpng 1.6.58,
libwebp 1.6.0, OpenJPEG 2.5.4, libtiff 4.7.2, xz 5.8.4 et zlib-ng 2.3.3.
Conserver cette notice complète plutôt que la remplacer par « licence Pillow ».
`PIL.features.pilinfo()` permet de contrôler les codecs effectivement disponibles ;
les versions annoncées à l'exécution peuvent différer des titres de la notice.

## Construction seulement

| Composant | Version | Licence déclarée / texte fourni dans sa distribution |
| --- | --- | --- |
| PyInstaller | 6.22.3 | GPLv2 ou ultérieure avec exception de distribution du programme construit ; `licenses/COPYING.txt`. |
| altgraph | 0.17.5 | MIT ; `LICENSE`. |
| packaging | 26.3 | Apache-2.0 OU BSD-2-Clause ; `licenses/LICENSE*`. |
| pefile | 2024.8.26 | MIT ; `LICENSE`. |
| pyinstaller-hooks-contrib | 2026.8 | GPL-2.0-or-later pour les hooks standard, conditions distinctes pour les hooks d'exécution ; conserver `licenses/LICENSE` intégralement. |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause ; `LICENSE.txt`. |
| setuptools | 84.0.0 | MIT et notices de ses composants vendus ; `licenses/LICENSE` et notices sous `setuptools/_vendor`. |

Les dépendances de construction sont épinglées dans `requirements-dev.txt`.
Leur installation n'implique pas leur inclusion intégrale dans l'application.
La qualification du paquet devra identifier les hooks d'exécution, le bootloader,
l'interpréteur et les bibliothèques réellement embarqués, joindre leurs textes,
et fournir les sources correspondantes exigées par leurs licences. Ne pas
annoncer cet audit de distribution comme terminé avant le conditionnement.

## Inspection indépendante — développement seulement

Ajout autorisé par l'utilisateur. Ces composants ne figurent pas dans
`requirements.txt` et ne doivent pas être embarqués dans l'application.

| Composant | Version testée | Licence / notices de la roue installée |
| --- | --- | --- |
| pikepdf | 10.17.0 | MPL-2.0, `pikepdf-10.17.0.dist-info/licenses/LICENSE.txt` ; notices sous `third-party-licenses/`. |
| qpdf, inclus dans pikepdf | 12.4.2 | Apache-2.0, `third-party-licenses/qpdf.txt` dans les notices de pikepdf. |
| pypdfium2 | 5.14.0 | Apache-2.0 / BSD-3-Clause selon les fichiers, textes dans `pypdfium2-5.14.0.dist-info/licenses/LICENSES/`. |
| PDFium, inclus dans pypdfium2 | 156.0.8076.0 | Licence BSD à 3 clauses des auteurs PDFium et notices des dépendances dans `licenses/data/windows_x64/BUILD_LICENSES/`. |
| lxml, dépendance de pikepdf | 6.1.3 | BSD-3-Clause et exceptions ; conserver `lxml-6.1.3.dist-info/licenses/LICENSE.txt` et `LICENSES.txt`, notamment les notices libxml2, libxslt, iconv et zlib de la roue. |

Sources amont : https://github.com/pikepdf/pikepdf,
https://github.com/qpdf/qpdf, https://github.com/pypdfium2-team/pypdfium2,
https://pdfium.googlesource.com/pdfium/ et https://github.com/lxml/lxml.
Ces outils sont installés dans les environnements virtuels de développement,
sans installation système ni téléchargement pendant les tests.
