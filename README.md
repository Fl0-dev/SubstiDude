# SubstiDude

Application Windows locale de substitution d'informations dans des PDF, en cours
de développement. Aucun export utilisateur n'est encore disponible ni validé.
Les exigences et les étapes de réalisation figurent dans `spec.md` et `plan.md`.

## Préparer le prototype

Python 3.12 **64 bits**, Windows, PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Les téléchargements d'installation nécessitent Internet. Les traitements futurs
doivent fonctionner hors ligne. Qt sera installé lorsque le prototype l'exigera.
Utiliser une version corrective à jour de Python 3.12 pour le traitement de
documents non fiables ; le poste de préparation dispose actuellement de 3.12.0.

Les tests utilisent uniquement des données synthétiques générées en mémoire.
Ne pas déposer de documents clients dans le dépôt, même à titre d'exemple.

Le prototype sait ouvrir en mémoire les PDF respectant les limites ci-dessous,
avec refus des fichiers chiffrés, invalides ou réparés par le moteur. Le corpus
couvre les contenus natifs, scans, scans avec OCR invisible et pages mixtes,
ainsi que les rotations et le recadrage. L'ouverture ne signifie pas que le
contenu est pris en charge pour une suppression : cette validation reste à faire.
Une expérience automatisée de suppression native vérifie le remplacement accentué,
les rotations/recadrages et l'absence de différences de rendu hors zone. Si
`pdftotext` est installé, un test indépendant contrôle aussi le texte extrait ;
sinon ce test est signalé comme ignoré, pas comme une qualification réussie.
Les expériences scan/OCR modifient les pixels sans perte supplémentaire et
vérifient la disparition du texte OCR ciblé sans ajout de texte PDF fictif.
Les tests indépendants utilisent **pikepdf/qpdf** pour la structure et la récupération
des images, et **pypdfium2/PDFium** pour le rendu et le texte. Ils sont installés
uniquement par `requirements-dev.txt`, pas avec les dépendances d'exécution.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_independent.py -v
```

Ces contrôles couvrent les sorties simples du corpus et détectent une image
originale résiduelle cachée ou inutilisée. Le nettoyage des contenus auxiliaires,
des anciennes révisions et le traitement complet restent à qualifier.

Le contrôle préalable des images réutilisées repère les occurrences visibles
identiques, même avec des objets distincts, un encodage PDF différent ou des
objets imbriqués. Il refuse leur modification locale sans modifier le document.
À ce stade, masques et mélanges d'espaces couleur sont refusés par ce contrôle ;
les copies dont les pixels ont changé et les couches cachées restent à qualifier.

## Limites décidées

- Fichier non vide et strictement inférieur à 10 000 000 octets.
- De 1 à 49 pages ; les autres limites seront validées au prototype.
- Au maximum 40 000 000 pixels par image ; contrôle des dimensions des images
  XObject, masques et images inline. Ce plafond individuel ne borne pas la mémoire
  totale ni le rendu. Les dimensions indirectes des XObject sont refusées à ce stade.
- Temporaires d'export près de la destination, prévue locale et non synchronisée.
- Aucune garantie d'anonymisation exhaustive ; contrôle humain nécessaire.

## Licence

Copyright (C) 2026 Girard Florian.

SubstiDude est distribué sous **AGPL-3.0-only** : voir le texte intégral dans
[`LICENSE`](LICENSE). Le logiciel est fourni sans garantie, selon cette licence.
Les composants tiers conservent leurs licences : voir
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Sources : https://github.com/Fl0-dev/SubstiDude.
Toute distribution devra identifier les sources exactes de l'exécutable et
inclure les notices des composants réellement embarqués ; la branche courante
ne suffit pas à identifier ces sources. Les documents traités ne deviennent
pas AGPL du seul fait de leur traitement.
