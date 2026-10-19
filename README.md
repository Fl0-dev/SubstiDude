# SubstiDude

Application Windows locale de substitution d'informations dans des PDF, en cours
de développement. Le lecteur, l'édition, l'aperçu réel et l'export sont disponibles
pour la recette **synthétique uniquement**. Ce n'est pas une version livrable ni
une autorisation de traiter des documents clients ou réels non fiables.
Les exigences et les étapes de réalisation figurent dans `spec.md` et `plan.md`.

## Préparer le prototype

Poste courant : Python 3.13.0 **64 bits**, Windows, PowerShell, synthétique seulement :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m substidude
```

Les téléchargements d'installation nécessitent Internet. Les traitements futurs
fonctionnent sans service distant. PySide6 Essentials/Qt et shiboken6 6.12.0 sont
épinglés pour l'interface ; les modules Addons ne sont pas installés.
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
Seule exception à l'ouverture d'un **source** : le diagnostic exact qpdf d'entrée
propre manquante du flux XRef, avec lecture MuPDF sans réparation. Aucune sortie
ne bénéficie de cette exception.
Le moteur, l'état de session et leur interface locale existent ; la qualification
manuelle et la distribution finale restent ouvertes.

`classify_zone` reconnaît expérimentalement les zones natives, scannées et avec
OCR invisible, y compris les zones distinctes d'une page mixte. La liste positive
reste limitée aux pages simples du corpus : scans gris/RGB 8 bits sans masque,
axes positifs à 2 pixels par point PDF ; textes horizontaux opaques sans
superposition ambiguë. Pour les substitutions **natives uniquement**, le corpus
qualifie désormais Type1 avec ToUnicode, TrueType simple, Form imbriqués et
vecteurs hors zone. Les images gris/RGB, palettes et masques admis sont conservés
sans retouche, avec empreintes de flux et de propriétés couleur contrôlées.
Une découpe rectangulaire doit couvrir le conteneur ou tous ses caractères,
vérifiés dans une copie en mémoire sans clips explicites. Une découpe plus complexe
peut concerner les images/vecteurs conservés, mais pas masquer du texte, même
imbriqué. Les autres ressources graphiques complexes restent refusées. Cette reconnaissance ne transforme pas
le document et n'autorise aucun export ; elle ne prouve pas la suppression.

Le parcours qualifié a été extrait dans `substidude/pipeline.py`. Les tests de
`tests/test_pipeline.py` appellent maintenant ce même moteur, avec comparaison
indépendante PDFium/qpdf maintenue dans les tests uniquement. Il couvre plusieurs
zones sur une image, pages mixtes et multipages avec un seul scan ; les groupes
texte partagés par plusieurs zones et les images non affichées restent refusés.
`Substitution` contient uniquement la page, le rectangle et le texte accentué
multiligne. La taille est ajustée automatiquement (sans troncature) et le fond est
blanc opaque ; les images grises conservent leur espace couleur.
La police embarquée reste Noto Sans, avec marge de 1 pt native et de 2 px raster
dans le périmètre à 2 px/point. Les débordements ne sont jamais tronqués.
Ce moteur et son interface restent réservés à la recette synthétique.
Un diagnostic ciblé demandé sur un fichier extérieur ne constitue pas une
qualification client : ouverture, structure native et aperçu d'un remplacement
neutre ont passé les contrôles en mémoire, source inchangé, sans export. Cela ne
valide pas toutes les sélections ou tailles de remplacement dans ce document.
Aucun contenu réel n'est utilisé dans `tests/test_native_documents.py`.
`tests/diagnose_structure.py --check-preview --path <fichier-choisi>` est une
vérification locale explicitement demandée, bornée et sans écriture du résultat.

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

## Moteur applicatif (phase 2)

- `substidude.model` : substitutions immuables, session, révisions et confirmation
  liée aux octets exacts du résultat courant. Modification, régénération, échec ou
  annulation du travail courant invalident la confirmation. Une réponse d'une
  ancienne session, requête ou révision ne restaure pas un ancien résultat.
- `substidude.pipeline.transform` : préinspection, transformation groupée,
  nettoyage et postconditions sur les octets finaux. Pas de dépendance à PDFium,
  aux fixtures ou aux fichiers de tests. Appel direct réservé aux tests contrôlés :
  il ne borne pas à lui seul mémoire/durée du processus.
- `substidude.worker.PDFJob` : opérations `open`, `inspect`, `render`, `transform`
  et opérations d'export/nettoyage dans un processus Windows `spawn` par travail.
  Parent sans moteur PDF, un seul
  travail actif/non collecté, pas de file ; chaque enfant ferme ses objets.
  Job Object de 2 Gio établi avant les imports PDF, échéance de 60 s démarrage
  inclus, réponse binaire limitée à 64 Mio enveloppe comprise, sans pickle de
  réponse. Les commandes transportent uniquement des octets et options JSON
  bornés. Une identité unique de requête, une révision et le PID sont vérifiés.
- `SessionController` relie le travail de transformation à la session, sans
  confirmer automatiquement le résultat. `PDFJob.done` permet une future collecte
  hors attente longue ; `receive()` est bloquant et ne doit pas être appelé en
  boucle dans le fil graphique. `cancel()`/`close()` libèrent les travaux.
- La réponse de rendu contient largeur/hauteur (`>II`, 8 octets), puis les pixels
  RGB sans alpha. L'inspection renvoie géométrie des pages et avertissements JSON,
  jamais le texte source dans les diagnostics. Seule une demande explicite
  d'export écrit le résultat sur disque ; pas de copie automatique des originaux.

La limite du banc reste applicable au worker : pas de sandbox, pas de garantie
temps réel ni de préemption de l'appel système synchrone de création du processus.
Le watchdog vit dans le parent ; sa mort brutale et le parcours applicatif gelé
ne sont pas qualifiés par ces essais source/runtime. Le banc `SubstiDudeProbe`
reste une recette distincte, pas un exécutable applicatif.

La phase 1 a été explicitement validée dans son périmètre révisé. La phase 2 est
testée en source et dans l'environnement runtime sans PDFium. Les avertissements
de confidentialité 11B restent obligatoires avant tout partage.

## Parcours synthétique et précautions (phases 3–5)

1. Ouvrir un PDF synthétique admissible (`Ctrl+O`). Naviguer avec Page précédente/
   suivante, zoomer ou ajuster (`Ctrl+0`). L'original reste une copie mémoire.
2. Dessiner une zone englobant tous les caractères/pixels à retirer. Les zones
   d'édition bleues ne sont **pas** le résultat. Déplacer le rectangle ou tirer
   son coin inférieur droit. La grille visuelle est de 0,5 point dans ce périmètre.
3. Saisir le remplacement : les changements modifient automatiquement la zone
   sélectionnée. Aucun réglage manuel de taille, fond ou coordonnées n'est proposé.
   Les valeurs proposées sont fictives ; le texte saisi reste local.
   Double-cliquer la liste ramène à la page ; Suppr dans la vue retire une zone.
4. L'aperçu réel est généré automatiquement après 400 ms sans modification.
   Original à gauche et résultat à droite s'affichent côte à côte au même zoom,
   avec défilement synchronisé. Aucun bouton de génération ou de basculement.
   Un résultat périmé est retiré immédiatement ; un refus est indiqué dans le panneau
   « Après », sans boîte modale pendant l'édition.
   Contrôler toutes les pages du résultat et les identifiants indirects : signatures,
   photos, QR codes, codes-barres, coordonnées, références et numéros uniques.
   Le choix « J'ai vérifié le document » ne s'active qu'après affichage de chaque
   page du résultat courant. Toute modification invalide résultat et confirmation.
5. Exporter dans un **dossier local non synchronisé**. Le nom proposé est neutre,
   `substidude-export.pdf`. Le fichier source et ses alias sont refusés ; une
   destination existante demande confirmation. Les octets sont ceux du résultat
   confirmé, pas une nouvelle transformation. L'interface indique « Exporté »
   seulement après finalisation réussie.

Le temporaire d'export est dans le dossier de destination, avec DACL Windows
protégée (utilisateur courant et SYSTEM). Après écriture/flush, ses octets sont
comparés et rouverts avant finalisation. Un échec **avant finalisation** laisse
source et ancienne destination intactes ; si l'accusé est perdu, le délai expire
ou l'utilisateur interrompt après une finalisation possible, l'état est annoncé
**incertain**, sans succès ni promesse de conservation de l'ancienne destination.
Contrôler alors la copie avant de recommencer. Le budget de réponse doit permettre
l'accusé avant qu'une écriture puisse être lancée. L'application ne promet pas une atomicité de stockage
réseau/cloud ni un effacement forensique. Les chemins des temporaires seuls sont
consignés dans des entrées locales à droits restreints sous
`%LOCALAPPDATA%/SubstiDude/temporaries`, sans source ni contenu documentaire.
Le journal est écrit et synchronisé **avant la création** du temporaire PDF ;
son nom contient le PID pour nettoyer aussi un journal interrompu d'un processus
terminé, sans parcourir ni supprimer des fichiers non enregistrés.
Le démarrage retire uniquement les temporaires enregistrés dont le processus est
terminé. Un PID réutilisé ou inaccessible retarde prudemment ce nettoyage ; un
arrêt entre finalisation et réponse peut laisser une copie valide non annoncée.
Ne pas utiliser de documents clients pour tester ces situations.

Les appels PDF longs restent dans l'enfant ; navigation/édition sont désactivées
pendant un travail et l'annulation libère l'enfant. La fermeture ou l'ouverture
d'un autre document demande confirmation si des modifications ne sont pas exportées.
« À propos / Licences » est lisible hors ligne et n'ouvre aucun lien automatiquement.

## Construction de développement (pas une distribution qualifiée)

```powershell
.\.venv\Scripts\python.exe -B -m PyInstaller --onedir --windowed --name SubstiDudeDevelopment --specpath build --workpath build --distpath dist --paths "$PWD" --add-data "$PWD\substidude\resources;substidude/resources" --add-data "$PWD\LICENSE;." --add-data "$PWD\THIRD_PARTY_NOTICES.md;." --exclude-module pypdfium2 --exclude-module PySide6.QtTest substidude/__main__.py
.\dist\SubstiDudeDevelopment\SubstiDudeDevelopment.exe --smoke-test
```

L'option `--smoke-test` lance le nettoyage borné et la fenêtre, puis la ferme
automatiquement sans ouvrir de document. La construction et ce démarrage gelé
ne qualifient pas à eux seuls tout le parcours PDF gelé ni un poste sans Python.
`dist/` et `build/` sont des artefacts locaux ignorés, non publiés. Les licences/
sources natives complètes et obligations LGPL du paquet restent à auditer ; les
roues Qt de cette version ne fournissent pas les textes libres complets dans leur
répertoire de notices (voir `THIRD_PARTY_NOTICES.md`). Aucun paquet à redistribuer.

Une recette distincte, `tests/gui_workflow_probe.py`, pilote les méthodes et
callbacks de la fenêtre réelle sans QtTest ni moteur PDF dans son parent. Elle
reçoit quatre fixtures synthétiques dans un dossier temporaire et vérifie
ouverture → édition → aperçu → confirmation → export exact. Elle ne remplace
aucune sortie existante. Cette recette a réussi dans `.venv-runtime` et dans un
`onedir` **de recette** `SubstiDudeGuiProbe`, avec contrôle indépendant des sorties
par PDFium/qpdf dans l'environnement de développement. Le binaire de recette
utilise les mêmes classes applicatives, mais un autre point d'entrée ; il n'est
pas l'exécutable à livrer. La recette humaine des gestes/dialogues et un Windows
réellement sans Python, non administrateur et hors réseau restent à vérifier.

## Limites décidées

- Fichier non vide et strictement inférieur à 10 000 000 octets.
- De 1 à 49 pages ; les autres limites seront validées au prototype.
- Au maximum 40 000 000 pixels par image ; contrôle des dimensions des images
  XObject, masques et images inline. Ce plafond individuel ne borne pas la mémoire
  totale ni le rendu. Les dimensions indirectes des XObject sont refusées à ce stade.
- Flux décompressés : 32 Mio par flux auxiliaire, 128 Mio par flux image et
  256 Mio cumulés ; contrôle commun avant analyse des contenus et ouverture MuPDF.
  Le rendu du prototype passe par une garde de 16 MP, sans réduction silencieuse.
- Banc Windows et worker applicatif bornés : 2 Gio d'engagement par processus PDF (Job Object natif),
  60 s par travail et 64 Mio par réponse IPC encodée. Les 15 scénarios du banc
  source/runtime/gelé vérifient notamment les dépassements avec budgets réduits.
  Le worker applique ces budgets à l'ouverture, l'inspection, le rendu et la
  transformation applicatifs ; les API appelées directement hors worker ne
  bénéficient pas automatiquement des trois gardes de processus.
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
