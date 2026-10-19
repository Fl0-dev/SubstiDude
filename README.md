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
documents non fiables. Après les premiers essais en 3.12.0, le poste courant
utilise Python 3.13.0 64 bits, explicitement autorisé sur documents synthétiques
uniquement ; les environnements ont été recréés avec les versions épinglées.
Sur ce poste sans lanceur `py`, utiliser `python -m venv .venv` avec cet interpréteur.

Les tests utilisent uniquement des données synthétiques générées par le corpus ;
les essais de fichiers et de révisions utilisent des répertoires temporaires nettoyés.
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
**pikepdf/qpdf** est désormais une dépendance d'exécution pour l'inspection
structurelle et le nettoyage, en complément de PyMuPDF. **pypdfium2/PDFium** reste
réservé aux tests de rendu et d'extraction de texte ; il n'est pas livré dans l'application.
Après une réécriture qpdf, les tests utilisent aussi MuPDF comme second lecteur.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_independent.py -v
```

Ces contrôles couvrent les sorties simples du corpus et détectent une image
originale résiduelle cachée ou inutilisée. Le nettoyage retire les métadonnées
documentaires/XMP et miniatures, régénère les identifiants et réécrit les révisions
dans un nouveau PDF. Les tests contrôlent le rendu, le texte, les pixels des scans
et l'absence de recompression JPEG. Ce nettoyage seul n'effectue aucune substitution.

Le prototype refuse actuellement les textes alternatifs (`ActualText`, `Alt`),
contenus balisés, couches, formulaires/signatures, annotations/liens, pièces jointes,
scripts/actions, destinations nommées, signets et autres structures auxiliaires non
maîtrisées. Ces refus ont lieu avant transformation, y compris dans les objets Form.
Une référence XMP ambiguë ou un avertissement de parsing interdit le résultat.
Le pipeline complet et son état de validation restent à construire.

`classify_zone` reconnaît expérimentalement les zones natives, scannées et avec
OCR invisible, y compris les zones distinctes d'une page mixte. La liste positive
reste limitée aux pages simples du corpus : scans gris/RGB 8 bits sans masque,
axes positifs à 2 pixels par point PDF ; textes horizontaux opaques sans
superposition ambiguë. Form, vecteurs, découpes et ressources graphiques complexes
font refuser la page entière à ce stade. Cette reconnaissance ne transforme pas
le document et n'autorise aucun export ; elle ne prouve pas la suppression.

Le parcours multi-zones de `tests/test_pipeline.py` assemble ces expériences en
mémoire, avec contrôles des octets nettoyés et comparaison indépendante PDFium/qpdf.
Il couvre plusieurs zones sur une image, pages mixtes et multipages ; il refuse
notamment les groupes texte partagés par plusieurs zones et les images non affichées.
Ce code reste réservé au corpus synthétique, avec fond blanc, texte monoligne et
police 14 pt fixes ; ce n'est pas un export utilisateur ni un moteur validé.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pipeline.py -v
```

L'expérience de regroupement des images repère les occurrences visibles identiques,
même avec des objets distincts, un encodage PDF différent ou des objets imbriqués.
Elle ne reconnaît pas toutes les copies recadrées, rééchantillonnées ou modifiées :
un seul pixel changé ailleurs suffit à laisser la zone sensible hors détection.
**Périmètre V1 confirmé : toute substitution raster dans un document contenant plusieurs
images ou plusieurs occurrences est refusée**, sans propagation automatique. Plusieurs
zones sur une seule image et les pages natives restent possibles. Les scans multipages
sont hors périmètre raster V1 ; le moteur reste à qualifier avant toute utilisation client.

Sur le corpus à image unique, le parcours conserve les canaux et l'espace couleur
PDF avant/après remplacement, sans recompression JPEG supplémentaire. DeviceGray,
DeviceRGB et le profil sRGB MuPDF connu sont qualifiés ; profils inconnus et
paramètres complexes restent refusés. Des pixels identiques ne suffisent pas à
prouver la conservation du rendu si le profil couleur change.

L'inspection commune refuse aussi les références inconnues dans les dictionnaires
de polices, leurs descripteurs/flux, les profils ICC et les flux de page. Le corpus
reproduit des résidus référencés malgré une réécriture complète, puis vérifie leur
refus avant transformation et sur le résultat. Cela ne qualifie pas encore les
contenus internes des programmes de police/CMap ni toutes les représentations cachées.

Sur décision utilisateur, leur traitement approfondi est reporté à une itération
future : voir `spec.md:6.2.1`. Des copies cachées de la cible peuvent donc subsister.
Les contre-exemples sont conservés dans `tests/test_hidden_contents.py` : deux
tests de protection restent rouges (19 sous-cas), sans être ignorés. La réussite
des autres tests ne constitue pas une garantie d'anonymisation exhaustive.

Les premières mesures de ressources et un banc Windows `spawn`/PyInstaller `onedir`
sont décrits avec leurs commandes dans `plan.md` (§ 13, étapes 11C/11D). Le binaire
`SubstiDudeProbe` ne réalise que des essais fixes sur fixtures synthétiques ;
ce n'est ni l'application SubstiDude, ni un export utilisateur, ni un paquet à distribuer.

## Limites décidées

- Fichier non vide et strictement inférieur à 10 000 000 octets.
- De 1 à 49 pages ; les autres limites seront validées au prototype.
- Au maximum 40 000 000 pixels par image ; contrôle des dimensions des images
  XObject, masques et images inline. Ce plafond individuel ne borne pas la mémoire
  totale ni le rendu. Les dimensions indirectes des XObject sont refusées à ce stade.
- Flux décompressés : 32 Mio par flux auxiliaire, 128 Mio par flux image et
  256 Mio cumulés ; contrôle commun avant analyse des contenus et ouverture MuPDF.
  Le rendu du prototype passe par une garde de 16 MP, sans réduction silencieuse.
- Banc Windows borné : 2 Gio d'engagement par processus PDF (Job Object natif),
  60 s par travail et 64 Mio par réponse IPC encodée. Les 15 scénarios du banc
  source/runtime/gelé vérifient notamment les dépassements avec budgets réduits.
  Cela ne crée pas un worker applicatif : les API appelées directement hors du
  banc ne bénéficient pas automatiquement des trois gardes de processus.
  Voir `spec.md:7.1` et les suivis 11E/11F de `plan.md`.
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
