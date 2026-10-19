# SubstiDude — Plan de développement de la V1

## 1. Mode d'emploi pour la session d'implémentation

1. Lire intégralement `spec.md`, puis ce document, et examiner l'état Git avant toute modification.
2. Suivre les phases dans l'ordre. Cocher une tâche uniquement après vérification de son résultat.
3. À chaque phase, noter ici les tests exécutés, résultats, limites et décisions utiles à la reprise. Ne pas enregistrer de données clients.
4. Ne pas affaiblir une exigence de suppression pour obtenir un export : refuser explicitement le cas non maîtrisé.
5. Si le prototype invalide le choix du moteur ou impose de réduire le périmètre, expliquer le blocage et demander une décision avant de poursuivre l'interface.
6. `spec.md` fait référence pour les exigences ; ce plan organise leur réalisation, avec les arbitrages utilisateur consignés ci-dessous. Les références A1 à A14, y compris A4b, désignent ses critères d'acceptation.
7. Ne pas créer d'infrastructure anticipée : ni serveur, ni base de données, ni plugins, ni abstraction de moteur interchangeable.
8. Consigne utilisateur courante : ne faire aucun commit ni push sans demande explicite. Elle remplace l'ancienne autorisation de commit par étape vérifiée. Implémenter pas à pas ; demander plutôt que deviner lorsqu'un arbitrage est nécessaire.

**État initial historique :** dépôt contenant seulement les spécifications et ce plan. Cet état est dépassé : un prototype existe désormais. Pour reprendre, utiliser l'état courant en section 13 et vérifier le dépôt avant toute modification.

### Arbitrages utilisateur applicables

- **Entrées :** accepter uniquement les fichiers de taille strictement positive et strictement inférieure à 10 Mo (10 000 000 octets), contenant de 1 à 49 pages. Refuser notamment les fichiers de 0 octet, ceux de 10 Mo ou plus et les PDF de 0 ou d'au moins 50 pages.
- **Temporaires :** conserver le traitement en mémoire autant que possible ; les temporaires d'export restent dans le dossier de destination. L'usage prévu est un dossier local non synchronisé. Cet arbitrage déroge à l'obligation de répertoire local dédié de `spec.md:6.3` ; il ne supprime pas les exigences de droits adaptés, de noms neutres et de nettoyage. Aucun mécanisme de détection de synchronisation n'est demandé.
- **Périmètre PDF :** définir une liste positive de structures reconnues et traitables ; aucune promesse de support PDF général ni de détection de toutes les copies visuellement similaires d'une image. Si cette frontière ne permet pas de respecter les garanties de suppression de la spec, demander un arbitrage avant de poursuivre.
- **Python :** l'utilisateur autorise la poursuite du prototype avec Python 3.12.0 sur documents synthétiques uniquement ; reporter la mise à jour avant les essais sur documents réels non fiables.
  - Reprise du 19 octobre 2026 : les anciens environnements et Python 3.12 étant absents sur le poste courant, l'utilisateur autorise explicitement Python 3.13.0. Trois environnements neufs recréés sans changement des dépendances épinglées ; les 74 tests de référence passent dans `.venv` et `.venv-check` avec `-B -W error`, aucun ignoré ; `pip check` réussit dans les trois environnements. Cela ne qualifie toujours pas les documents réels non fiables.
- **Images :** plafond utilisateur confirmé de 40 000 000 pixels par image décodée, inclusif. Ce plafond individuel n'est pas une limite de mémoire cumulée du document ni du rendu.
- **Inspection et nettoyage :** après reproduction d'un résidu `ActualText`, l'utilisateur autorise pikepdf/qpdf comme dépendance d'exécution, avec ses dépendances et obligations de distribution. Cet arbitrage remplace son usage initial réservé au développement. pypdfium2/PDFium reste exclusivement un outil de test et ne doit pas être livré.
- **Raster V1 — confirmé après l'étape 10 :** périmètre prudent accepté par l'utilisateur : un seul objet image et une seule occurrence visible dans tout le PDF pour toute substitution raster. Plusieurs zones sur cette image et les pages natives restent possibles, sous réserve des autres contrôles. Les substitutions raster sur PDF multi-images, dont les scans multipages, sont refusées sans propagation. La détection générale des copies transformées n'est pas requise ; toute extension multi-images devra être qualifiée avant levée du refus. L'arbitrage est aussi reporté dans `spec.md:5`.
- **11B différée — décision utilisateur du 19 octobre 2026 :** les contenus internes des polices/CMap, valeurs de propriétés admises et autres représentations cachées mises en évidence en 11B seront traités dans une itération future (`spec.md:6.2.1`). L'utilisateur demande de poursuivre les mesures de ressources, puis Windows. Les résidus connus sont conservés comme limite explicite de confidentialité ; aucun contrôle de 11A n'est désactivé. Aucun ajout de fontTools autorisé ni effectué. Le jalon moteur reste non validé ; les tests de protection différés restent rouges et ne doivent pas être présentés comme réussis.
- **Budgets de ressources — délégation utilisateur du 19 octobre 2026 :** « Prend des plafonds conventionnels pour ce genre de cas et continue ». Valeurs initiales retenues, sans revendication de standard : 32 Mio par flux auxiliaire, 128 Mio par flux image, 256 Mio de flux uniques cumulés par inspection, 16 MP par rendu RGB, 2 Gio d'engagement privé par processus PDF, 60 s par travail démarrage inclus, 64 Mio par réponse IPC encodée. Voir `spec.md:7.1` et `substidude/limits.py`. Les quotas 10 Mo/49 pages/40 MP restent inchangés. Gardes communes flux/rendu vérifiées et validées en 11E ; mémoire/durée/IPC appliquées au banc Windows en 11F, vérifiées et validées. Les appels directs des API hors du banc ne bénéficient pas automatiquement des trois gardes de processus ; aucun worker applicatif n'existe encore.

## 2. Cible technique retenue pour ce plan

| Élément | Choix |
| --- | --- |
| Plateforme | Windows 64 bits, application de bureau locale en français |
| Langage | Python, version stable compatible avec toutes les dépendances retenues |
| Interface | PySide6, Qt Widgets, `QGraphicsView` / `QGraphicsScene` |
| PDF | PyMuPDF sous option AGPL pour rendu/transformation ; pikepdf/qpdf pour inspection structurée et nettoyage, à valider en phase 1 |
| Images et texte raster | Pillow, avec une police redistribuable embarquée |
| Tests | `unittest` et corpus synthétique local |
| Distribution | PyInstaller en mode dossier (`onedir`), pas `onefile` |
| Licence du projet | `AGPL-3.0-only` |

Cette cible suit la recommandation discutée. Le moteur reste conditionné au prototype. Vérifier les API et licences des versions effectivement installées ; ne pas copier des options de caviardisation supposées ou obsolètes.

Épingler les versions testées pour l'exécution et la construction. Aucune dépendance HTTP, télémétrie, OCR ou IA n'est nécessaire. PDFium est réservé au développement ; pikepdf/qpdf est désormais une dépendance livrée pour l'inspection et le nettoyage, conformément à l'arbitrage utilisateur.

## 3. Structure minimale visée

Créer ces fichiers au fur et à mesure de leur utilité, pas comme des coquilles vides :

```text
substidude/
  __init__.py
  __main__.py           # python -m substidude
  model.py             # substitutions, révisions, validations simples
  pdf_engine.py        # inspection, rendu, transformation et vérification
  image_edit.py        # coordonnées image et remplacement dans les pixels
  export.py            # écriture sûre du résultat vérifié
  window.py            # fenêtre, liste, formulaires et états
  page_view.py         # affichage et rectangles manipulables
  worker.py            # traitement PDF hors du fil graphique, si nécessaire
  resources/           # police et mentions de licence
tests/
  fixtures.py          # génération des documents synthétiques
  test_engine.py
  test_workflow.py
requirements.txt
requirements-dev.txt
README.md
LICENSE
THIRD_PARTY_NOTICES.md
```

Ne pas imposer une classe par fonction. Fusionner un petit module si cela simplifie réellement le code. N'ajouter un script de construction que si utile ; une commande suffit au test précoce de conditionnement.

## 4. Invariants à préserver

- L'original reste inchangé ; conserver une empreinte dans les tests pour le vérifier.
- Les substitutions contiennent page, rectangle en coordonnées PDF canoniques, texte fictif, taille de police, fond et mode validé. Aucun ancien texte n'est nécessaire dans le modèle.
- Stocker les coordonnées indépendamment du zoom, des pixels écran et du facteur HiDPI. Centraliser les conversions et leur inverse.
- Accepter uniquement les structures dont les critères de reconnaissance ont été démontrés au prototype, puis classer chaque zone : texte natif, scan, scan avec OCR. Refuser une structure hors liste ou une superposition non maîtrisée ; la présence de texte extractible ne suffit pas à distinguer texte natif et OCR invisible.
- Analyser toutes les zones d'une page avant transformation ; retirer tous les contenus ciblés avant d'insérer les remplacements, pour ne pas effacer une substitution précédente.
- Vérifier aussi les interactions entre zones disjointes touchant un même objet ; l'absence de chevauchement des rectangles ne suffit pas à garantir leur indépendance.
- Le moteur produit un unique résultat PDF nettoyé en mémoire pour une révision donnée. L'aperçu et l'export utilisent ces mêmes octets, sans reconstruire le document après validation.
- Toute modification incrémente la révision et invalide résultat et confirmation. Un résultat asynchrone périmé ne peut pas remplacer le résultat courant.
- L'export n'est possible que si la révision du résultat et celle de la confirmation correspondent à la révision courante.
- La confirmation utilisateur ne remplace aucun contrôle technique requis. Un PDF qui se rouvre n'est pas, à ce seul titre, un PDF dont la suppression est vérifiée.
- Aucun journal ne contient de texte source, de pixels ou de chemin complet sensible.

## 5. Phase 0 — Préparer le projet et les licences

### Tâches

- [x] Vérifier Python disponible et choisir une version supportée par les roues Windows des dépendances.
- [x] Créer un environnement `.venv` et les fichiers de dépendances avec versions exactes testées.
- [x] Ajouter `.gitignore` : environnement, caches, construction, sorties de tests et documents de travail. Les seuls PDF versionnés éventuels doivent être synthétiques et explicitement identifiés.
- [x] Ajouter le texte officiel intégral AGPLv3 dans `LICENSE` et les premières instructions du README.
- [x] Confirmer le titulaire réel du copyright auprès de l'utilisateur avant publication ; ne pas inventer son identité depuis son pseudonyme GitHub.
- [x] Choisir une police libre autorisant redistribution et intégration PDF, puis inclure ses mentions.
- [x] Initialiser l'inventaire des licences, y compris Qt, MuPDF et bibliothèques transitives réellement embarquées.

### Vérification / sortie

Installation reproductible dans un environnement neuf ; imports des composants réussis. Consigner les versions choisies et les éventuelles questions de licence. La mention SPDX doit figurer dans les nouveaux fichiers source propres au projet.

**Résultat de la phase 0 :** titulaire confirmé par l'utilisateur : Girard Florian. Python 3.12.0 64 bits disponible ; roues Windows installées pour PyMuPDF/MuPDF 1.28.2, Pillow 13.0.0 et PyInstaller 6.22.3, dépendances transitives de construction épinglées. Police Noto Sans Regular et licence OFL embarquées ; texte AGPLv3 officiel téléchargé depuis GNU. Réinstallation depuis `requirements-dev.txt` dans `.venv-check` réussie ; `pip check` sans erreur dans les deux environnements. `python -m unittest discover -s tests -v` : 2 tests réussis dans chaque environnement (accents extractibles avec police intégrée, rendu PDF et pixels, présence des licences). PyInstaller démarre en version 6.22.3. Qt volontairement différé. Inventaire initial dans `THIRD_PARTY_NOTICES.md` ; audit du paquet et notices natives MuPDF à compléter avant distribution. Python 3.12.0 est ancien : demander une décision sur sa mise à jour avant de traiter des documents non fiables ; les tests actuels sont exclusivement synthétiques. Aucun moteur de suppression ni export utilisateur n'est encore implémenté.

## 6. Phase 1 — Prototype PDF et décision de faisabilité

**Aucune interface complète avant validation de cette phase.** Commencer avec les dépendances moteur et tests ; installer l'interface lorsque nécessaire.

### 1A. Corpus synthétique

- [x] Générer un PDF natif, un scan sans OCR et un scan avec texte OCR invisible, avec marqueurs distincts et données fictives ; ajouter une page mixte avec zones natives et scannées distinctes, dont le traitement doit être accepté.
- [x] Ajouter des cas multipages, rotations 0/90/180/270°, CropBox décalée et dimensions différentes.
- [x] Ajouter une image partagée entre pages, une copie d'image distincte avec les mêmes pixels, transparence/masque et contenu vectoriel traversant une zone.
- [x] Ajouter deux zones disjointes touchant un même objet textuel, vectoriel ou image ; vérifier un traitement cohérent ou un refus explicite, sans modification silencieuse hors des effets annoncés dans l'aperçu.
  - Étape 9 : deux zones d'une même image sont traitées ensemble ; deux zones dans un même groupe texte ou traversant un vecteur sont refusées. Pas encore d'aperçu applicatif : le contrôle PDFium vérifie le résultat complet et les pixels hors zones.
- [x] Ajouter une image réencodée et une image recadrée ou redimensionnée pour documenter la frontière de détection des copies, sans créer de système de reconnaissance visuelle générale.
  - Étape 10 : copies à un pixel modifié, recadrée, rééchantillonnée et JPEG testées ; la détection exacte ne les regroupe pas. Périmètre prudent à image unique confirmé par l'utilisateur, sans promesse de détection générale.
- [x] Ajouter métadonnées/XMP, annotation, formulaire, pièce jointe, action/lien, `ActualText`, couches optionnelles et révisions incrémentales.
- [x] Ajouter fichiers invalides et chiffrés ; préparer un cas signé synthétique ou une vérification manuelle documentée si sa génération nécessite un outil supplémentaire.
- [x] Définir pour chaque cas le résultat attendu et le critère permettant de le reconnaître : support ou refus motivé. Les trois types principaux et au moins une page mixte doivent être supportés pour valider la V1.
  - 11G : preuves détaillées dans la réconciliation et la matrice courantes en section 13 ; recette signée CMS exécutée séparément avec OpenSSL local. Ces coches attestent le corpus du périmètre révisé, pas la validation utilisateur du jalon.
- [x] Tester les frontières d'entrée : 0, 1, 9 999 999 et 10 000 000 octets pour le contrôle de taille ; 0, 1, 49 et 50 pages pour le contrôle du nombre de pages. Une taille admissible ne dispense pas de vérifier la validité du PDF.

### 1B. Expériences moteur

- [x] Définir la liste positive initiale : texte natif sans superposition ambiguë, scan simple à transformation maîtrisée, même scan avec couche OCR identifiable et page mixte à zones distinctes. Démontrer les critères de reconnaissance, l'inspection des objets visibles/invisibles et les transformations de coordonnées ; tester aussi les refus sur des cas proches mais hors périmètre.
  - Étape 8 : reconnaissance expérimentale `classify_zone` sur l'original, quatre cas simples et refus proches testés. La tâche globale reste ouverte : les représentations cachées et les postconditions du pipeline ne sont pas encore qualifiées.
  - 11G : périmètre prudent et postconditions consolidés ci-dessous, exception 11B explicite. La réserve de l'étape 8 décrit son état historique.
- [x] Contrôler la taille avant lecture complète et le nombre de pages après ouverture, avant rendu ou transformation. Dès le prototype, fixer des plafonds conservateurs de pixels décodés et de rendu ; les limites de poids et de pages ne protègent pas à elles seules contre une décompression excessive. Tester une image démesurée et un refus maîtrisé.
- [x] Tester suppression réelle du texte natif puis insertion d'un remplacement accentué extractible.
- [x] Tester remplacement dans une image : modifier ses pixels à la résolution d'origine et réencoder sans perte supplémentaire, sans rasteriser la page.
- [x] Vérifier la correspondance point PDF → pixel image, y compris rotation et transformations. Refuser dans la V1 les transformations non maîtrisées plutôt que déformer le scan.
- [x] Retirer le texte OCR ciblé sans supprimer celui hors zone et sans ajouter de texte extractible pour le remplacement raster.
- [x] Valider l'identification d'un même objet image réutilisé, y compris via objets imbriqués, et de copies distinctes aux pixels décodés identiques. Définir les formats, masques et transformations couverts ; ne pas limiter l'analyse au seul numéro d'objet. Documenter explicitement les copies réencodées avec pixels différents, recadrées ou redimensionnées non détectées. Si ces limites compromettent les garanties de `spec.md:5`, bloquer le jalon et demander un arbitrage, sans annoncer de détection générale.
  - 11G : preuves des étapes 6/8/9/10 rattachées ; périmètre raster à une image/occurrence déjà arbitré, aucune extension aux Form ou copies transformées.
- [x] Tester nettoyage des contenus auxiliaires et réécriture complète avec suppression des objets inutilisés. Métadonnées/XMP, miniatures et anciennes révisions testées ; autres structures explicitement refusées dans le périmètre initial. Une option de sauvegarde ne vaut pas preuve de nettoyage.
- [x] Refuser champs et annotations avant transformation : aucun aplatissement implicite ni perte silencieuse de leur contenu visible dans ce prototype.

### 1C. Inspection indépendante et jalon

- [x] Choisir les lecteurs de contrôle : pypdfium2/PDFium pour rendu/extraction, pikepdf/qpdf pour structure/images des sorties MuPDF, et MuPDF comme second lecteur après réécriture qpdf. Versions et licences vérifiées ; seul PDFium reste exclusivement en développement. Un contrôle qpdf de sa propre sortie n'est pas une inspection indépendante.
- [x] Examiner texte, images récupérables, structures auxiliaires et anciennes révisions, pas seulement le rendu ou une recherche brute dans les octets.
- [x] Comparer les rendus hors zones, les dimensions d'images, le texte conservé et l'intégrité du source.
- [x] Ajouter dans ce plan une matrice « structure / critère de reconnaissance / support ou refus / contrôle automatique à chaque génération / preuve sur corpus » et les limites exactes du prototype.
- [x] Séparer les contrôles : réouverture pour la lisibilité, contrôles techniques exécutés sur chaque résultat, inspection indépendante pour la qualification du corpus. Définir pour chaque structure acceptée les postconditions testables : retrait des contenus ciblés dans leurs représentations concernées, remplacement sous la forme attendue, nettoyage auxiliaire et conservation hors zones selon les limites documentées. Un contrôle requis absent ou en échec interdit la confirmation et l'export ; la recette du corpus ne constitue pas une preuve exhaustive sur tout PDF utilisateur.
  - 11G : voir les trois niveaux de contrôle en section 13. Inspection limitée au périmètre positif avec exception 11B ; aucun export applicatif ni jalon utilisateur validé par ces coches.

### 1D. Exécution et test précoce Windows

- [x] Décider avant le lecteur où s'exécutent ouverture, inspection, rendu et transformation, et qui possède les objets PDF. Les tâches longues doivent rester hors du fil graphique ; ne pas utiliser PyMuPDF concurremment depuis des threads Qt. Si nécessaire, retenir un processus dédié via `multiprocessing` et `spawn`, sans partager les objets PDF, avec un seul travail PDF actif et sans pool généraliste.
- [x] Tester erreurs, durée excessive et arrêt du traitement avec le modèle retenu ; borner les données en attente. Un processus séparé ne constitue pas un bac à sable de sécurité.
- [x] Construire un exécutable minimal PyInstaller `onedir` et vérifier ouverture, rendu et transformation. Si un processus dédié est retenu, tester son lancement et son arrêt dans l'exécutable gelé (`freeze_support` et point d'entrée protégé si requis). Consigner la commande ; ne pas attendre la distribution finale pour cette vérification.

**Preuves 11D/11F validées par l'utilisateur :** banc `tests/windows_probe.py`, processus `spawn` par travail, parent sans moteur PDF, une seule réponse/travail actif, ouverture/rendu/transformation native, erreurs/arrêt et budgets mémoire/durée/IPC vérifiés en source et dans un `onedir` sans PDFium. Les trois tâches de prototype 1D sont vérifiées dans ce périmètre. Ce n'est pas un worker applicatif ni une qualification du parcours raster complet gelé, d'une machine sans Python ou du crash brutal du parent. L'intégration et ces limites restent celles décrites en 11F ; le jalon moteur global reste ouvert.

**Passage à la phase 2 :** natif, scan, scan+OCR et page mixte du périmètre positif fonctionnent ; reconnaissance des structures acceptées et refus proches démontrés ; risques de résidus connus traités ou bloqués par un contrôle explicite. Les contrôles par résultat, limites initiales et modèle d'exécution sont définis, et le test Windows minimal réussit. Une inspection incomplète ne permet pas d'annoncer un support général. Si un cas impossible à détecter compromet les garanties, arrêter et soumettre une révision technique à l'utilisateur.

**Exception décidée le 19 octobre 2026 :** les risques 11B listés dans `spec.md:6.2.1` sont explicitement différés ; leur correction n'est plus un préalable aux mesures, à Windows ni au futur passage de phase dans ce périmètre révisé. Leur absence de traitement reste une limite à communiquer, pas un contrôle réussi. Toutes les autres conditions ci-dessus restent à satisfaire ; le jalon moteur n'est pas validé.

**Critères :** A2, A3, A4, A4b, A5, A6, A7, A8, A12.

## 7. Phase 2 — Moteur applicatif et état de session

- [ ] Transformer le prototype validé en fonctions réutilisées par l'application et les tests ; supprimer le code expérimental devenu inutile.
- [ ] Définir les substitutions et validations : limites de page, taille non nulle, valeurs de police valides, chevauchements, interactions entre zones disjointes touchant un même objet et débordement du texte. Traiter ces interactions de façon maîtrisée avec effet visible dans l'aperçu, ou refuser explicitement.
- [ ] Utiliser la même police et les mêmes métriques pour vérifier l'encombrement et dessiner le remplacement ; gérer explicitement les retours à la ligne et caractères non supportés.
- [ ] Implémenter inspection préalable et messages de refus stables : chiffré, contenu ambigu, image partagée incompatible, nettoyage non maîtrisé.
- [ ] Garder l'original ouvert en lecture seule ou sous forme d'octets immuables ; repartir de lui pour chaque transformation.
- [ ] Produire résultat nettoyé et avertissements sans écrire de copie persistante par défaut.
- [ ] Exécuter à chaque génération les contrôles techniques définis en phase 1 sur les octets du résultat rouvert ; exposer leurs échecs sans permettre de les contourner par confirmation utilisateur.
- [ ] Implémenter les révisions et la confirmation liée au résultat, sans dépendance à Qt pour leur logique.
- [ ] Tester modification après validation, résultat périmé, zones multiples et absence de mutation de l'original.

**Sortie :** pipeline testable sans interface, de l'original et des substitutions aux octets du PDF final rouvert, avec tous les contrôles techniques requis réussis. La confirmation visuelle utilisateur reste une étape distincte.

**Critères :** A2 à A8, A11 à A13.

## 8. Phase 3 — Lecteur et édition des zones

- [ ] Ajouter le point d'entrée `python -m substidude`, une fenêtre et le sélecteur de fichier.
- [ ] Utiliser dès l'ouverture et le rendu le modèle d'exécution validé en phase 1, avec messages clairs pour les limites de taille, de pages et de ressources.
- [ ] Afficher une page à la fois avec numéro, navigation, zoom et ajustement à la fenêtre ; ne pas rendre tout le document à chaque action.
- [ ] Tester le placement sur pages tournées/recadrées et avec mise à l'échelle Windows différente de 100 %.
- [ ] Dessiner, déplacer, redimensionner et supprimer les rectangles ; borner les opérations à la page.
- [ ] Ajouter le formulaire : texte libre, valeurs prédéfinies, taille, fond et mode appliqué visible.
- [ ] Conserver les substitutions au changement de page et proposer le dernier texte fictif utilisé.
- [ ] Ajouter la liste des substitutions et l'accès direct à la zone sélectionnée.
- [ ] Prévoir labels accessibles, focus, raccourcis des commandes principales et erreurs non fondées uniquement sur la couleur.
- [ ] Confirmer avant fermeture ou ouverture d'un autre PDF si du travail n'a pas été exporté.

**Sortie :** édition complète en mémoire, aucun export présenté comme sûr à ce stade.

**Critères :** A1, A5, A11, A12.

## 9. Phase 4 — Aperçu réel et validation utilisateur

- [ ] Relier la génération du résultat au moteur unique ; ne jamais utiliser les rectangles d'édition comme aperçu final.
- [ ] Basculer original/résultat en conservant page, zoom et position.
- [ ] Afficher « À vérifier », « Vérifié par l'utilisateur », « Exporté » et les avertissements pertinents, notamment absence de nouvelle couche OCR pour les remplacements raster.
- [ ] Ajouter la checklist des identifiants indirects et la confirmation « J'ai vérifié le document ».
- [ ] N'autoriser la confirmation que lorsque les contrôles techniques du résultat courant ont réussi ; interdire l'export sans cette confirmation et la réinitialiser après toute modification. La confirmation porte sur le contrôle visuel et les identifiants oubliés, pas sur l'acceptation d'un défaut technique connu.
- [ ] Relier la génération au modèle d'exécution déjà validé en phase 1, avec un seul travail PDF actif et sans appels PyMuPDF concurrents depuis des threads Qt.
- [ ] En cas de processus dédié, gérer erreurs et fermeture, borner les données en attente et ignorer les résultats d'une ancienne session/révision. Éviter un pool de processus ou un système de tâches généraliste.
- [ ] Tester la fermeture pendant traitement et la succession modification → génération → modification.

**Sortie :** le résultat visualisé, sa révision et sa confirmation sont liés sans ambiguïté.

**Critères :** A13, A14 et prévention des traitements concurrents.

## 10. Phase 5 — Export sûr et cycle de vie local

- [ ] Proposer `substidude-export.pdf` et refuser le fichier source, y compris les alias de chemin détectables avec `samefile` lorsque le fichier existe.
- [ ] Confirmer un remplacement existant sans jamais tronquer la destination avant validation complète.
- [ ] Écrire les octets exacts du résultat confirmé dans un fichier temporaire sécurisé du dossier de destination, conformément à l'arbitrage utilisateur. Vérifier l'identité des octets écrits et la réouverture, puis finaliser par remplacement atomique lorsque le système de fichiers le permet ; cette vérification d'écriture ne remplace pas les contrôles techniques déjà effectués sur le résultat.
- [ ] Gérer permissions insuffisantes, disque plein, destination verrouillée et échec de finalisation ; conserver l'original et l'ancienne destination.
- [ ] Documenter l'usage prévu sur dossier local non synchronisé ; ne pas ajouter de détection de synchronisation ni de qualification spécifique réseau/cloud en V1, et ne pas promettre leurs propriétés d'atomicité ou de confidentialité.
- [ ] Supprimer les temporaires sur succès/erreur. Pour les abandons après crash, utiliser des noms neutres et un suivi minimal des seuls emplacements temporaires nécessaires au nettoyage au prochain lancement, avec droits restreints, sans chemin source ni contenu documentaire ; retirer les entrées après nettoyage et ne supprimer que les fichiers identifiés comme appartenant à l'application et à une session terminée. Ne pas supposer le nom neutre de la destination exempt de chemin sensible ; ne pas journaliser ces emplacements.
- [ ] N'ajouter aucun rapport de plantage transmis, historique documentaire ou sauvegarde automatique.
- [ ] Tester sans connexion Internet le parcours complet ; vérifier dans le code l'absence de fonctions réseau. Aucun dispositif spécialisé d'audit réseau n'est demandé.

**Sortie :** A9 et A10 réussis ; résultat exporté identique aux octets confirmés ; tests d'erreur et nettoyage réussis.

## 11. Phase 6 — Qualification du corpus et limites de ressources

- [ ] Exécuter `python -m unittest discover -s tests -v` sur tout le corpus.
- [ ] Compléter l'inspection indépendante sur les sorties représentatives, avec commandes et résultats reproductibles documentés.
- [ ] Vérifier hors zones les pixels décodés des scans simples ; pour les rendus, définir et justifier une tolérance aux différences d'anticrénelage. Aucun seuil ne doit masquer un changement réel de contenu.
- [ ] Tester accents, texte multiligne, effacement sans remplacement, police trop grande, petites zones, pages mixtes et sélections proches des bords.
- [ ] Mesurer ouverture, rendu, transformation, export et mémoire sur plusieurs tailles de documents synthétiques.
- [ ] Conserver les limites décidées : 0 < taille < 10 000 000 octets et 1 à 49 pages. Ajuster à partir des mesures les plafonds de pixels décodés et de rendu introduits en phase 1 ; vérifier les limites avant allocations importantes lorsque possible. Toute modification des limites de poids ou de pages nécessite une nouvelle décision utilisateur.
- [ ] Documenter les erreurs propres aux fichiers dépassant ces limites. Ne pas annoncer de support « illimité ».
- [ ] Effectuer une recette manuelle de tous les critères A1 à A14, y compris A4b, et des confirmations de fermeture.

**Sortie :** matrice d'acceptation complétée avec preuve ou refus attendu, liste précise des limites et aucun défaut connu permettant un faux succès d'export.

## 12. Phase 7 — Distribution Windows et documentation

- [ ] Construire sur Windows avec PyInstaller `onedir`, police et notices incluses ; documenter la commande exacte.
- [ ] Vérifier le lancement d'un éventuel processus de traitement dans l'exécutable gelé (`freeze_support` et point d'entrée protégé si requis).
- [ ] Tester sur un poste ou environnement Windows sans Python installé, avec compte non administrateur et réseau coupé.
- [ ] Tester chemins avec espaces/accents et document ouvert depuis un dossier en lecture seule.
- [ ] Vérifier la présence des bibliothèques Qt remplaçables et les obligations LGPL applicables à la distribution concrète.
- [ ] Fournir une rubrique « À propos / Licences » hors ligne, licence complète, notices transitives et absence de garantie.
- [ ] Documenter installation, lancement, parcours, refus supportés, limites de confidentialité, perte éventuelle de fonctions PDF et risque de disparition du bug reproduit.
- [ ] Préparer un artefact versionné et les sources exactes correspondantes avec instructions de construction. Publication/tag uniquement après autorisation.

**Sortie :** paquet autonome testé, notices vérifiées et tous les éléments de la définition de terminé de `spec.md` satisfaits.

## 13. Suivi de reprise

À compléter après chaque phase :

| Phase | État | Vérifications effectuées / résultats | Limites ou prochaine action |
| --- | --- | --- | --- |
| 0 — Préparation | Terminée | Installation neuve reproduite ; 2 tests réussis dans chaque environnement ; `pip check` réussi ; PyInstaller 6.22.3 démarre | Girard Florian confirmé ; Python 3.12.0 autorisé sur synthétique seulement ; audit des notices du paquet avant distribution |
| 1 — Prototype PDF | Terminée dans le périmètre révisé ; jalon explicitement validé après 11G | 101 tests reproduits, puis 102 tests par environnement ; uniquement 19 sous-cas 11B en échec ; trois `pip check`, 15 scénarios runtime et recette signée CMS réussis | Choix utilisateur « Commit et terminer » ; phase 2 non commencée ; limites 11B et banc conservées, aucun push |
| 2 — Moteur et session | À faire | — | — |
| 3 — Lecteur et zones | À faire | — | — |
| 4 — Aperçu et validation | À faire | — | — |
| 5 — Export et confidentialité | À faire | — | — |
| 6 — Qualification | À faire | — | — |
| 7 — Distribution | À faire | — | — |

### État de reprise faisant foi

**Décision finale faisant foi — 19 octobre 2026 :** après présentation du bilan 11G, l'utilisateur choisit **« Commit et terminer »** à la question explicite de validation du jalon. **Phase 1 clôturée et jalon moteur validé dans le périmètre révisé documenté**, avec exception 11B et limites du banc conservées. Cette décision autorise le commit local des six fichiers de 11G et du suivi documentaire préexistant présenté, puis l'arrêt ; elle n'autorise aucun push ni démarrage automatique de phase 2. Le commit effectif est à identifier par Git (message prévu : `test: close phase 1 qualification with signed PDF and color checks`). À la prochaine reprise, préserver tout travail ultérieur et utiliser la référence **102 tests / 19 sous-cas 11B / aucun ignoré**. Les paragraphes suivants gardent la trace du bilan avant cette validation, pas un jalon encore en attente.

**Vérification 11G avant validation et commit :** référence initiale de 101 tests reproduite ; référence après complément : **102 tests par environnement, uniquement les 19 sous-cas 11B en échec, aucun ignoré**. Corpus réconcilié et cases 1A–1C rattachées aux preuves ; lien ajouté, signature CMS synthétique vérifiée, contrôle final des espaces couleur complété après reproduction du manque. Git après fetch au départ : `main=15228f2`, `origin/main=15c0cdf`, écart **0/2**. La mise à jour documentaire préexistante est préservée dans cette unité. La décision finale ci-dessus valide le bilan ; **phase 2 non commencée**.

Le paragraphe suivant conserve l'état au démarrage de 11G ; il ne demande pas sa réimplémentation.

**État au départ de 11G : phase 1, après 11F.** Les étapes 8 à 11A sont publiées dans `7e00893`, suivies du commit documentaire `15c0cdf`. Le report 11B et les mesures 11C sont committés dans **`72bee42`**, 11D–11F dans **`15228f2`**, tous deux locaux sans push. La phase 0 est terminée ; ne pas la reprendre, réimplémenter 11A–11F ou rouvrir 11B. Flux/rendu sont bornés au point commun ; processus/durée/IPC dans le banc Windows uniquement, pas dans un worker applicatif. La référence de départ était de 101 tests par environnement avec 19 sous-cas 11B en échec, aucun ignoré. Le bilan 11G actualise cette référence à 102 tests et attend la validation explicite du jalon avant phase 2. Les autorisations de commit précédentes sont consommées ; aucun nouveau commit/push sans demande explicite.

**Reprise 11B du 19 octobre 2026 (reproductions ensuite committées dans `72bee42`) :** le commit documentaire `15c0cdf` est vérifié publié et synchronisé avec `origin/main` au départ. Après accord explicite sur Python 3.13.0, référence de 74 tests reproduite. Les nouvelles fixtures et quatre tests de `tests/test_hidden_contents.py` précèdent tout correctif ; deux tests de reproduction/conservation réussissent, deux tests de protection échouent avec **19 sous-cas en échec**, aucun ignoré. Les neuf résidus réellement reproduits et la contamination finale du trailer sont détaillés dans l'historique 11B ci-dessous. Aucun changement de moteur n'est effectué. **L'utilisateur a ensuite demandé le report de 11B à une itération future et la poursuite des mesures**, avec limite de confidentialité inscrite dans `spec.md:6.2.1`. Ne pas considérer la suite étendue comme verte ; les exigences différées ne bloquent plus les mesures ni, ensuite, la qualification Windows. Tous les autres contrôles restent applicables.

**Il n'y a pas encore d'application lançable :** pas de `__main__.py`, pas d'interface Qt, pas de moteur applicatif complet de substitutions, pas de modèle de révisions/confirmation, pas de worker ni d'export utilisateur. Un parcours expérimental existe maintenant dans `tests/test_pipeline.py`, exclusivement pour le corpus synthétique et dépendant des outils de développement. `python -m substidude` ne constitue donc pas une commande disponible. Ne pas annoncer les sorties expérimentales comme sûres pour des documents clients.

#### Instantané Git pour le transfert de session

Vérification du 19 octobre 2026, après `rtk git fetch origin` : branche **`main` sur `15228f2`**, `origin/main` sur **`15c0cdf`**, écart `origin/main...HEAD` **`0 / 2`**. Les commits locaux non poussés sont `72bee42` et `15228f2`. Le répertoire était propre avant cette mise à jour documentaire ; aucun merge, rebase, reset ou push effectué.

- Les quatre fichiers de tests des étapes 8–11A sont suivis dans `7e00893` ; les tests de contenus cachés et la sonde de ressources dans `72bee42` ; les gardes, constantes et tests/banc Windows dans `15228f2`. Ne pas les recréer ni les supprimer comme s'ils étaient des fichiers temporaires.
- Le paquet `dist/SubstiDudeProbe/` et les sorties `build/` sont des artefacts locaux ignorés, pas des fichiers suivis ni une application publiée. Leur présence n'est pas garantie dans une nouvelle session ; reconstruire seulement si nécessaire avec la commande 11D.
- Cette préparation de reprise modifie **uniquement `plan.md`**, sans code, nouvelle exécution de tests, commit ou push. Le fichier peut donc être modifié au démarrage de la session suivante : préserver cette mise à jour et tout travail ultérieur.

Cet instantané n'est pas une garantie de l'état d'une session future : refaire les contrôles Git au démarrage, sans écraser les modifications ni supposer les deux commits publiés.

#### Code à réutiliser avant d'écrire

| Fichier / élément | État actuel |
| --- | --- |
| `substidude/pdf_engine.py` — `open_pdf(path)` | Lit une copie mémoire, vérifie les quotas, inspecte avec qpdf puis ouvre avec MuPDF ; l'appelant ferme le document retourné. Refuse les structures non maîtrisées. |
| `page_to_view_matrix(page, scale)` | Coordonnées canoniques : points non tournés relatifs à la CropBox. La matrice applique rotation et échelle zoom × HiDPI ; `~matrix` donne l'inverse. Ne pas stocker les coordonnées écran. |
| `repeated_image_occurrences(document)` | Regroupe les occurrences visibles aux pixels identiques ; objets partagés ou distincts, réencodage et Form imbriqués testés. Analyse à faire sur l'original avant transformation. |
| `check_image_reuse(document, page_number, rectangle)` | Périmètre V1 confirmé : refuse une zone raster si le document contient plusieurs objets image ou plusieurs occurrences visibles. Contrôle de dimensions et comptage avant tout hash/décodage demandé par ce garde-fou. Ne prétend pas reconnaître des copies transformées ; le regroupement exact reste un outil distinct de qualification. |
| `classify_zone(data, page_number, rectangle)` | Reconnaissance expérimentale `native` / `scan` / `ocr` sur l'original ; une page mixte est traitée par zone. Liste positive de page/ressources/opérateurs ; refus des superpositions et transformations non qualifiées. N'effectue aucune substitution et n'autorise aucun export. |
| `sanitize_pdf(data)` | Nettoie Info du trailer **et** du catalogue, XMP et miniatures ; réécrit sans anciennes révisions et régénère les identifiants. Ne remplace aucun texte/pixel et ne constitue pas un export confirmé. |
| `_check_auxiliary_structure`, `_check_font_references`, `_check_icc_references`, `_check_stream_references` | Contrôle commun des conteneurs et références introduit/complété en 11A ; ne pas le dupliquer dans les appelants. Contrôler les octets des programmes/CMap reste à qualifier séparément. |
| `tests/fixtures.py` | Générateurs synthétiques : quatre contenus de base, quotas, rotations/recadrages, images répétées, contenus auxiliaires et révisions incrémentales. Réutiliser ces fixtures plutôt que les recréer. |
| `tests/test_engine.py` — `NativeExperimentTests.replace_native` | Preuve de transformation native sur fixture connue ; pas une fonction applicative prenant des substitutions utilisateur. |
| `tests/test_raster.py` — `replace_scan` | Preuve raster/OCR/mixte sur fixture connue ; image simple sans masque ni cisaillement, à 2 px/point. Marge interne de 2 pixels validée seulement à cette échelle : ne pas la généraliser sans test. |
| `tests/test_independent.py`, `tests/test_auxiliary.py` | Contrôles croisés qpdf/MuPDF/PDFium, pixels/rendu/texte, anciennes révisions, refus et erreurs injectées. |
| `tests/test_repeated_images.py`, `tests/test_setup.py` | Contrôles des répétitions, quotas liés et ressources/licences/police. |
| `tests/test_classification.py`, `tests/fixtures.py` — `zone_case_pdf` | Reconnaissance, refus proches, contrôle des transformations image et validation des entrées ; fixtures réutilisables pour les prochaines interactions multi-zones. |
| `tests/test_pipeline.py` — `replace_zones` / `verify_result` | Parcours expérimental sans écriture de fichier : tuples (page, rectangle, texte), fond blanc, police embarquée 14 pt, texte monoligne. Analyse de l'original avant transformation, édition groupée d'une image, nettoyage et contrôles finaux. Pas une API d'export utilisateur ni un module d'exécution à livrer. |
| `tests/test_image_boundaries.py`, `tests/fixtures.py` — `image_variant_pdf` | Frontières des copies, reproduction du changement de rendu malgré pixels identiques, qualification gris/RGB/JPEG à image unique, refus des profils/paramètres non qualifiés. |
| `tests/test_hidden_references.py`, `tests/fixtures.py` — `hidden_reference_pdf` | Références cachées ICC/polices/flux, reproduction de résidus après réécriture, refus commun avant transformation et après contamination finale ; flux entièrement inutilisé éliminé. Ne qualifie pas le contenu interne des programmes de police/CMap. |
| `tests/measure_resources.py`, `tests/test_resource_measurements.py` | Sonde Windows mémoire native/Python et durées, 135 mesures + 18 runtime ; aucun plafond produit ajouté. |
| `tests/windows_probe.py`, `tests/test_windows_probe.py` | Banc de qualification `spawn` et `onedir` sur fixture native fixe ; parent sans moteur PDF, erreurs/arrêt/révision/IPC, pas un worker ni un export applicatif. |
| `substidude/limits.py`, `_check_stream_budgets`, `render_page`, `tests/test_resource_limits.py` | Flux/rendu contrôlés avant matérialisation complète/allocation. Budgets processus qualifiés séparément dans le banc Windows, pas appliqués automatiquement aux appels directs. |
| `tests/windows_memory.py`, `tests/test_windows_limits.py` | Job Object Windows anonyme et tests des limites natives/durée/IPC avec budgets réduits ; aucune dépendance externe. |
| `substidude/resources/` | Noto Sans Regular et licence OFL déjà embarquées ; ne pas ajouter une autre police sans nécessité. |

Les aides internes `_check_file_size`, `_check_image_dimensions` et l'inspection structurée existent déjà dans `pdf_engine.py`. Ne pas dupliquer ces contrôles dans chaque futur appelant. Le copyright confirmé est **Girard Florian**, année 2026 ; conserver les mentions SPDX AGPL-3.0-only.

#### Vérification de départ de la prochaine session

**Incident initial de reprise du 19 octobre 2026 — résolu :** lecture intégrale de `spec.md` et `plan.md` effectuée. Après `git fetch origin`, `main` et `origin/main` pointent sur `15c0cdf` (commit documentaire de reprise après `7e00893`), écart `0 / 0`, répertoire initial propre ; les quatre fichiers de tests cités ci-dessus sont suivis. Les anciens environnements, Python 3.12 et le lanceur `py` étaient absents. L'utilisateur a autorisé Python 3.13.0 ; les trois environnements ont été recréés et les 74 tests réexécutés avec succès avant 11B. Aucun changement du Python système ni des dépendances épinglées ; aucun commit/push.

Depuis la racine, dans PowerShell :

```powershell
rtk git status --short --branch
rtk git log -8 --oneline
rtk git fetch origin
rtk git rev-list --left-right --count origin/main...HEAD
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -v
.\.venv-check\Scripts\python.exe -m pip check
.\.venv-check\Scripts\python.exe -B -W error -m unittest discover -s tests -v
.\.venv-runtime\Scripts\python.exe -m pip check
.\.venv-runtime\Scripts\python.exe -B -W error tests/windows_probe.py --self-test
```

**Référence courante après 11G : 102 tests exécutés dans chacun de `.venv` et `.venv-check` avec `-B -W error`, aucun ignoré ; 19 échecs de sous-cas dans exactement deux tests 11B différés.** Ce sont `test_hidden_target_cannot_be_returned_as_a_verified_result` (9 sous-cas) et `test_final_internal_contamination_blocks_result` (10), dans `tests/test_hidden_contents.py`. Le code de sortie global est donc non nul : ne pas le présenter comme une réussite complète, ni « corriger » ces échecs en réactivant 11B, en supprimant les tests ou en ajoutant des `skip`/`expectedFailure`. Investiguer toute erreur ou tout échec supplémentaire avant modification.

Dernières vérifications 11G : `pip check` réussi dans les trois environnements ; **15 scénarios** source (via les suites) et runtime réussis sans PDFium runtime. La preuve `onedir` sans PDFium reste celle de 11F, non réexécutée en 11G. Recette signée CMS réussie séparément dans les deux environnements de développement. Gardes ressources et refus 11A/couleurs/multi-images conservés ; contrôle final de conservation couleur complété. Les références de 74/78/82/85/93/101 tests sont historiques ; reproduire les 102 tests à la prochaine reprise.

Si l'environnement n'existe pas :

```powershell
python -VV
# Vérifier Python 3.13.0 64 bits autorisé avant création ; ne pas changer le Python système.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-dev.txt
```

Les versions exactes font référence dans `requirements.txt` et `requirements-dev.txt`. Python **3.13.0 64 bits** est autorisé sur le poste courant pour les documents **synthétiques seulement** ; ne pas mettre le Python système à jour ni changer de version sans accord. Si absents, recréer `.venv-check` depuis `requirements-dev.txt` et `.venv-runtime` depuis `requirements.txt` uniquement, sans PDFium. Utiliser `rtk` pour Git, ou Git directement si `rtk` est indisponible. `pdftotext` Xpdf 4.00 était disponible sur ce poste ; vérifier sa présence/version avant les tests correspondants. Ne pas annoncer une recette complète si des tests sont ignorés.

#### Consigne initiale de 11G — exécutée, bilan et validation ci-dessous

**Prochaine unité — 11G : revue ciblée de clôture de phase 1.** Le développement du prototype a déjà commencé ; il ne reste pas à choisir une nouvelle architecture ou à refaire les campagnes 11C–11F. La prochaine session doit établir précisément ce qui manque encore pour autoriser le moteur applicatif, sans lancer une nouvelle exploration générale du format PDF.

| Ordre | Travail de 11G | Livrable / condition de validation |
| --- | --- | --- |
| 1 | Refaire les contrôles Git, dépendances et référence de tests ci-dessus ; relire les contrôles communs, `replace_zones` et `verify_result` | 101 tests par environnement, uniquement les 19 sous-cas 11B connus, aucun ignoré ; toute autre régression investiguée avant modification |
| 2 | Réconcilier les tâches regroupées ouvertes des sections 1A–1C avec les preuves existantes | Tableau « exigence / test ou preuve / support ou refus / manque réel » ; cocher seulement les tâches effectivement couvertes, ne pas recréer les fixtures déjà présentes |
| 3 | Compléter le cas signé synthétique, ou la vérification manuelle documentée prévue au plan si une génération fiable demande un nouvel outil | Refus explicite vérifié sur le type de signature réellement représenté, source intact et absence de résultat accepté ; distinguer une simple structure `/Sig` d'une signature cryptographique valide, ne pas revendiquer davantage que la preuve obtenue |
| 4 | Consolider la matrice V1 et les postconditions par génération sur natif, scan, OCR et page mixte | Séparer réouverture, contrôles techniques systématiques et inspection indépendante du corpus ; retrait texte/pixels ciblés, forme du remplacement, nettoyage applicable, géométrie/rendu hors zone et original conservés ; exception 11B explicite |
| 5 | Ne compléter que les manques avérés de cette recette et restituer le bilan du jalon | Tests avant correctifs si un nouveau défaut est découvert ; preuves/refus/limites exacts et proposition de clôture de phase 1 soumise à validation explicite utilisateur avant phase 2 |

**Ne pas traiter toutes les cases ouvertes comme autant de fonctionnalités absentes.** Les contenus auxiliaires, entrées invalides/chiffrées, rotations/recadrages, images répétées, contrôles hors zones et plusieurs postconditions sont déjà couverts par les étapes précédentes. Distinguer « preuve existante à rattacher », « cas manquant dans le périmètre V1 », « refus déjà qualifié » et « travail d'une phase/itération future ». Ne pas cocher en bloc une tâche regroupée sur la réussite d'un seul sous-cas.

**Ce qui ne doit pas bloquer le démarrage de la phase 2 :** reprise de 11B reportée, ajout de fontTools, prise en charge de nouveaux formats/profils/transformation d'image actuellement refusés, nouvelle campagne complète de ressources ou répétition de la qualification Windows déjà validée. L'audit du paquet final, la machine sans Python et la recette de distribution relèvent des phases ultérieures. Ne pas imposer ces travaux comme de nouveaux préalables ; conserver leurs limites visibles, sans les annoncer comme résolus.

**Après validation explicite du jalon uniquement :** commencer la phase 2, en consolidant le moteur réutilisable depuis `tests/test_pipeline.py` sans dépendance livrée à PDFium, puis intégrer le modèle `spawn` borné aux quatre modes. Le modèle de substitutions/révisions/confirmation appartient aussi à cette phase ; la fenêtre/lecteur arrive en phase 3. Ne pas créer d'interface complète, d'export utilisateur ou de structure vide anticipée pendant 11G. L'intégration des gardes de processus à ces appels applicatifs est du développement de phase 2, pas un nouveau banc à exiger avant son démarrage.

**Invariants de reprise :** classification par zone sur l'original ; une seule image et une seule occurrence dans tout le PDF pour le raster, plusieurs zones possibles ; gris/RGB 8 bits sans masque, axes positifs à 2 px/point dans le prototype ; espaces couleur conservés et profils inconnus/multi-images refusés. Garder tous les contrôles 11A et les refus de page pour Form, vecteurs, découpes et superpositions non maîtrisées. Ne pas réduire les contrôles de rendu hors zone, propager des modifications ou ajouter de similarité approximative pour étendre le périmètre. Les valeurs de `spec.md:7.1` sont déjà choisies et qualifiées dans leur périmètre : aucun nouvel arbitrage à solliciter pour ces mêmes valeurs, mais toute modification nécessite un accord.

11B reste une **limite de confidentialité acceptée pour cette itération**, pas une correction à effectuer ni une preuve de suppression globale. Une occurrence indépendante hors zone reste distincte d'un résidu de la cible. Le checksum ICC ne valide pas tout son dictionnaire ; les contrôles communs de 11A restent obligatoires. Si un nouveau manque remet en cause les garanties encore exigées du périmètre V1, le signaler et faire refuser le cas ou demander un arbitrage, jamais le masquer pour clôturer le jalon.

#### Bilan 11G — vérifié puis validé explicitement par l'utilisateur

**Vérifications du 19 octobre 2026 :** lecture intégrale de la spec et du plan ; état Git préservé, fetch effectué, écart distant/local 0/2 inchangé. Python 3.13.0 64 bits confirmé. Avant modification : **101 tests dans chacun de `.venv` et `.venv-check` avec `-B -W error`**, uniquement les 19 sous-cas des deux tests 11B connus, aucun ignoré. Trois `pip check` réussis ; recette runtime : **15 scénarios réussis**, PDFium absent, budgets 2 Gio/60 s/64 Mio affichés. Pas de nouvelle campagne de mesures, reconstruction ni recette `onedir` : les preuves 11D–11F restent celles déjà validées.

##### Réconciliation des cases ouvertes 1A–1C

Les chemins ci-dessous sont dans `tests/`. Une preuve sur un sous-cas n'est pas étendue à une famille non qualifiée ; les coches portent sur les tâches de prototype dans le périmètre révisé par les arbitrages.

| Exigence regroupée | Test ou preuve rattachée | Support / refus démontré | Manque réel et traitement 11G |
| --- | --- | --- | --- |
| 1A — Info/XMP, annotations, formulaires, pièces jointes, actions/liens, ActualText, couches, révisions | `test_auxiliary.py` : `test_metadata_and_thumbnail_removed_without_changing_render`, `test_incremental_revisions_rewritten_and_identifiers_regenerated`, `test_unsupported_content_refused_at_open_and_cleanup`, reproduction ActualText | Info du catalogue/trailer, XMP, miniatures et anciennes révisions nettoyés ; autres structures refusées | Lien URI explicite ajouté à `auxiliary_pdf` et à la boucle de refus existante ; ni suivi de lien ni nouveau support |
| 1A — invalides, chiffrés, signé | `test_engine.py::InputTests` (taille, pages, réparation, autre format, chiffrement avec/sans mot de passe d'ouverture) ; `check_signed_pdf.py` ci-dessous | Refus sans modification du source ; signature CMS réellement vérifiée puis refusée | Cas signé absent de l'ancien corpus : recette explicite exécutée, sans dépendance supplémentaire installée |
| 1A — résultats attendus / reconnaissance | `test_classification.py`, `test_pipeline.py`, `test_image_boundaries.py` ; matrice ci-dessous | Natif, scan, OCR et mixte à zones distinctes acceptés ; proches non qualifiés refusés | Consolidation documentaire des preuves déjà présentes |
| 1B — liste positive / visible-invisible | `test_modes_crop_and_rotation_without_mutating_source`, `test_ambiguous_or_unqualified_structures_are_refused`, `test_invisible_text_is_not_assumed_to_be_native` ; tests 11A | Reconnaissance sur l'original, OCR type 3 sur image admissible ; ambiguïtés refusées | 11B reste une exception explicite, pas une qualification des octets internes |
| 1B — poids, pages, pixels, ressources | `InputTests` : bornes 0/1/9 999 999/10 000 000 octets, 0/1/49/50 pages, dimensions/masques/inline ; `test_resource_limits.py` | Lecture bornée, quotas et refus avant décodage/rendu coûteux ; flux/rendu bornés 11E | Aucun seuil nouveau ; processus borné seulement dans le banc 11F |
| 1B — points PDF → pixels | `CoordinateTests`, `test_raster.py`, `test_two_zones_on_native_scan_and_ocr`, `test_image_transform_refusals_reach_the_transform_guard` | 4 rotations de page, recadrage, zoom/HiDPI ; raster axes positifs à 2 px/point ; cisaillement, rotation/reflet/échelle d'image non qualifiés refusés | Aucune extension ; grille entière et marges expérimentales conservées |
| 1B — objets répétés / copies / Form | `test_repeated_images.py` ; `test_transformed_copies_are_not_exact_repetitions`, `test_unqualified_multi_image_raster_edit_is_refused` | Regroupement exact visible démontré, y compris Form pour l'analyse ; édition raster multi-images/occurrences refusée | Arbitrage image unique déjà acquis ; Form reste refusé à la transformation |
| 1C — texte, objets images, auxiliaires, révisions | `test_independent.py`, `test_auxiliary.py`, `test_hidden_references.py`, injections de défaut de `test_pipeline.py` | Extraction et objets/flux relus, images cachées détectées, anciennes révisions retirées, refus 11A maintenus | Exception 11B documentée ; aucun contre-exemple différé supprimé |
| 1C — hors zones, géométrie, source | `test_engine.py`, `test_raster.py`, `test_independent.py`, `test_pipeline.py`, `test_single_gray_rgb_and_jpeg_image_qualification` | Rendus PDFium strictement identiques hors zones ; images et géométrie conservées ; empreintes sources et lecture mémoire vérifiées | Conservation couleur démontrée sur corpus mais garde final incomplet : test d'injection ajouté puis contrôle corrigé |
| 1C — matrice et postconditions | Matrice et trois niveaux ci-dessous ; `replace_zones` / `verify_result` relus | Contrat expérimental explicite, réutilisable en phase 2 | Consolidation ; pas de moteur applicatif ou d'export créé |

##### Recette signée reproductible

`tests/check_signed_pdf.py` est une recette explicite de développement, séparée de la découverte des tests et non livrée. Elle réutilise le PDF natif synthétique ; ajoute un champ `/FT /Sig`, son widget et une valeur `/Type /Sig` avec `/adbe.pkcs7.detached`. Elle réserve `/Contents`, calcule un `/ByteRange` couvrant tout le PDF sauf cette valeur, puis signe ces octets en CMS détaché SHA-256/RSA 2048 avec un certificat auto-signé éphémère. Aucune réécriture du PDF après insertion du CMS. qpdf relit sans récupération ni erreur syntaxique, confirme ByteRange et CMS incorporé ; OpenSSL vérifie les octets extraits du PDF final et rejette le témoin altéré.

**Ce n'est donc pas seulement un dictionnaire `/Sig` factice.** `-noverify` désactive la vérification de confiance du certificat, pas celle de la signature du contenu. Aucune confiance PKI, révocation, signature qualifiée, horodatage, signature de certification ou conformité PAdES générale n'est revendiquée. La recette démontre un refus pour cette signature d'approbation CMS/AcroForm, pas toutes les formes de signature PDF.

Commande PowerShell, avec le chemin explicite d'un OpenSSL local fonctionnel :

```powershell
$openssl = 'C:\laragon\bin\git\mingw64\bin\openssl.exe'
.\.venv\Scripts\python.exe -B -W error tests/check_signed_pdf.py --openssl $openssl
.\.venv-check\Scripts\python.exe -B -W error tests/check_signed_pdf.py --openssl $openssl
```

Exécutée avec **OpenSSL 1.1.1q (5 juillet 2022)** déjà installé, réservé à cette recette synthétique locale. Le premier OpenSSL du PATH (distribution Apache) ne démarrait pas ; son échec a été constaté, puis l'exécutable Git existant a été utilisé explicitement. Aucun téléchargement ni changement de dépendance. Dans les deux environnements : intégrité CMS vraie, témoin altéré rejeté, refus `open_pdf`, `sanitize_pdf`, `classify_zone`, `replace_zones` avant caviardisation ; injection du PDF signé comme résultat final également refusée. Empreinte source inchangée, aucun fichier de sortie produit par ces appels. PDF, clé et certificat synthétiques temporaires supprimés en fin de recette ; seul le résumé neutre est affiché.

##### Matrice V1 consolidée

| Structure | Critère de reconnaissance | Support / refus | Contrôle automatique par génération expérimentale | Preuve sur corpus |
| --- | --- | --- | --- | --- |
| Natif simple | Page/ressources/opérateurs dans la liste positive ; texte ciblé horizontal opaque type 0, sans superposition | Support ; remplacement monoligne Noto 14 pt, fond blanc, marge 1 pt ; effacement vide possible | Classification sur original ; retrait avant insertion ; texte de zone égal au remplacement, type 0/opacité 1 ; texte extérieur et géométrie conservés | `test_pipeline.py` : 24 variantes natif/scan/OCR à deux zones, PDFium, chaînes TJ qpdf pour le natif ; extraction Xpdf dans `test_engine.py` |
| Scan | Une seule image et occurrence dans tout le PDF ; sélection contenue ; gris/RGB 8 bits, axes positifs à 2 px/point ; pas de texte ciblé | Support ; pixels, police 28 px, marge 2 px, sans nouveau texte PDF | Grille entière, débordement refusé, édition groupée ; tous les objets image finaux comparés aux pixels attendus avec dimensions/multiplicité ; espaces couleur conservés | `test_raster.py`, `test_independent.py`, multi-zones du pipeline ; pixels qpdf et rendu PDFium hors zones exacts |
| Scan avec OCR | Même image, textes ciblés uniquement invisibles type 3 | Support ; retrait conjoint pixels/OCR, aucun nouvel OCR | Contrôles scan + texte de zone vide ; caractères OCR hors zones préservés | Tests raster/OCR et `test_local_replacement_and_untouched_ocr` ; occurrence indépendante conservée dans `test_hidden_contents.py` |
| Mixte à zones distinctes / pages natives avec scan unique | Mode choisi par zone sur l'original ; mêmes contraintes locales et image unique globale | Support ; zone traversant régions ou superposition ambiguë refusée | Analyse de toutes les zones avant mutation, contrôles respectifs natif/raster et interactions | `test_mixed_native_and_raster_zones`, `test_native_and_scan_on_different_pages`, classification des deux régions |
| Images / couleurs admises | DeviceGray, DeviceRGB ou seul ICC sRGB MuPDF qualifié ; filtres simples absent/Flate/ASCIIHex/DCT, paramètres absents/vides | Support dans la géométrie qualifiée ; profils inconnus, masques, prédicteurs, intent/interpolation explicites, chaînes de filtres refusés | Garde commun 11A + liste positive ; restauration de ColorSpace ; comparaison finale dimensions, profondeur, espace et contenu/propriétés ICC en plus des pixels | `test_image_boundaries.py`, dont nouveau `test_final_colorspace_change_is_refused_even_with_equal_components` |
| Répétitions, copies transformées, images non affichées | Comptage objets/occurrences avant hash pour le refus raster ; regroupement exact distinct | Raster multi-images refusé, sans propagation ; aucune reconnaissance approximative | `check_image_reuse`, refus d'image non affichée, inventaire final de tous les objets image | `test_repeated_images.py`, variantes pixel/crop/resize/JPEG, contamination par image cachée |
| Form, vecteurs, découpes, transparences, superpositions, caractères partiels / groupes partagés | Hors liste positive ou interaction non indépendante | Refus conservateur, parfois de la page entière | `_check_simple_page`, traces/rectangles ; aucun remplacement appliqué au cas refusé | `test_classification.py`, refus et perte d'espace reproduite dans `test_pipeline.py` |
| Info/XMP, miniatures, révisions | Conteneurs reconnus, références XMP non ambiguës | Nettoyage qualifié par `sanitize_pdf` ; transformation seulement si toute la préinspection du parcours admet aussi la source | Réécriture complète ; absence finale Info/Metadata/Thumb/Prev, syntaxe et gardes communs | `test_auxiliary.py`, notamment révisions et identifiants régénérés ; injection de nettoyage absent dans le pipeline |
| ActualText, accessibilité, couches, annotations/liens, formulaires/signatures, pièces jointes, actions et références 11A inconnues | Clés/types/opérateurs structurés, conteneurs directs et indirects | Refus, pas d'aplatissement | Garde commun à l'entrée et à la relecture finale ; aucun résultat accepté | `test_auxiliary.py`, `test_hidden_references.py`, recette CMS 11G |
| Internes de polices/CMap et propriétés 11B | Représentations listées dans `spec.md:6.2.1` | **Différé : copies possibles**, pas une suppression réussie | Aucun contrôle exhaustif revendiqué ; refus 11A inchangés | 19 sous-cas rouges conservés dans exactement deux tests, sans skip/expectedFailure |
| Quotas et budgets | Taille/pages/pixels ; flux uniques décompressés ; rendu demandé | Refus aux dépassements convenus | 10 Mo exclus, 49 pages, 40 MP/image ; flux 32/128/256 Mio et rendu 16 MP au point commun ; **2 Gio/60 s/64 Mio seulement dans le banc natif spawn/onedir** | Tests limites et preuves 11E–11F déjà validées ; intégration applicative en phase 2 |

##### Trois niveaux de contrôle et contrat de phase 2

1. **Réouverture / lisibilité** : qpdf sans récupération, syntaxe, MuPDF sans réparation ni chiffrement ; nombre de pages valide. Ce niveau seul n'atteste aucune suppression.
2. **Contrôles techniques systématiques de `replace_zones`** : sur original immuable, préinspection commune et classification de chaque zone, liste positive des pages, validation des interactions et de l'encombrement ; sur les octets finaux rouverts, refus structurés/ressources 11A, absence Info/XMP/miniatures/Prev, géométrie exacte, texte de zone conforme au mode, remplacement natif visible opaque, caractères extérieurs comparés (Unicode/type/opacité/police/couleur/positions à 0,001 point), tous les objets image comparés aux pixels attendus par SHA-256/dimensions/multiplicité. Ajout 11G : inventaire final des dimensions, profondeur et ColorSpace, propriétés N/Alternate/Range et octets ICC décodés contre l'original. Une erreur interdit le retour d'un résultat accepté ; la future confirmation ne pourra pas la contourner. Pas de recherche globale du marqueur qui ferait rejeter une occurrence indépendante hors zone.
3. **Qualification indépendante du corpus** : PDFium compare avant/après à 144 dpi, sans tolérance hors union des zones ; qpdf récupère les objets image et chaînes TJ après transformation MuPDF ; MuPDF relit les sorties de nettoyage qpdf ; Xpdf complète l'extraction textuelle. Les pixels raster attendus sont calculés séparément sur la grille connue des fixtures. Les tests contrôlent aussi l'empreinte source, les révisions et les contaminations injectées. Le rendu PDFium est une preuve sur corpus, **pas un contrôle livré par génération** ; PDFium reste hors runtime. Le garde final couleur ne constitue pas à lui seul une comparaison de rendu ni une inspection générale des contenus cachés.

Le contrat applicatif de phase 2 est de reprendre ces pré/postconditions sur les mêmes octets que l'aperçu et l'export futurs, en liant résultat et confirmation à la révision et en intégrant le processus borné aux quatre modes. Les tests indépendants restent dans la qualification, pas dans les dépendances livrées. Les réglages fixes, la liste positive et l'exception 11B demeurent explicites ; l'intégration du worker, les révisions, l'interface et l'export ne sont pas réalisés par 11G.

##### Complément effectif et résultat

Le test d'injection couleur a d'abord échoué : remplacer le profil ICC qualifié par DeviceRGB dans les octets finaux passait le contrôle des composantes RGB. `image_colors` / `verify_result` dans le parcours expérimental comparent maintenant aussi les propriétés couleur avant/après ; le test réussit sans affaiblir pixels ni rendu hors zone. Aucun module moteur de production ni format accepté n'est étendu.

Après les compléments, suites complètes dans `.venv` et `.venv-check` avec `-B -W error` : **102 tests chacune**, **uniquement 19 sous-cas 11B différés en échec**, aucun ignoré ni nouvelle régression. Le lien est un sous-cas supplémentaire d'un test existant ; la recette CMS reste séparée des 102 tests. Les dépendances n'ont pas changé depuis les trois `pip check` réussis ; la recette runtime à 15 scénarios a été reproduite au départ. Aucun document client, nouveau paquet, commit ou push.

**Bilan accepté :** l'utilisateur choisit « Commit et terminer » après présentation des preuves et limites, et valide explicitement la clôture de phase 1. 11B reste une limite de confidentialité acceptée, les gardes de processus restent limitées au banc et la distribution finale reste ultérieure. **Jalon validé dans ce périmètre ; phase 2 non commencée.** Fichiers autorisés au commit local : `plan.md` (mise à jour préexistante préservée et incluse), `tests/fixtures.py`, `tests/test_auxiliary.py`, `tests/test_pipeline.py`, `tests/test_image_boundaries.py`, nouveau `tests/check_signed_pdf.py`. Aucun push autorisé ; terminer cette unité après vérification du commit.

**Unité 11B différée — consignes initiales historiques, à réviser dans l'itération future :**

Les reproductions demandées initialement existent maintenant dans `tests/test_hidden_contents.py` et l'historique 11B ci-dessous. La liste suivante conserve la démarche de recherche d'origine, pas des travaux de la prochaine session : ne pas repartir de la référence historique de 74 tests ni considérer ces résidus comme encore non reproduits. La prochaine unité faisant foi est 11G ci-dessus.

1. Après reproduction des 74 tests, lire les contrôles communs de 11A, `hidden_reference_pdf`, les quatre tests de `test_hidden_references.py`, puis `replace_zones` et `verify_result`. Le contrôle des clés/types de dictionnaires n'est pas une validation du contenu des flux qu'ils autorisent.
2. Ajouter de petites variantes synthétiques contenant des marqueurs dans les programmes de police/CMap et les valeurs textuelles de propriétés déjà admises ; qualifier aussi les autres conteneurs et le texte invisible hors sélection. Ces pistes ne sont **pas encore des résidus reproduits**. Distinguer une représentation résiduelle de la cible retirée d'une occurrence indépendante hors zone, que la substitution locale ne promet pas de supprimer.
3. Pour chaque contre-exemple réel, conserver un test de reproduction puis un test de suppression démontrée ou de refus, avant le correctif au point commun approprié. Croiser les objets/flux récupérables avec un lecteur indépendant ; ne pas conclure sur le seul rendu, le hash, le texte extrait ou une recherche brute. Vérifier aussi le blocage d'un résultat contaminé, la conservation hors zones et l'absence de mutation du source.
4. Ne pas remplacer cette qualification par l'acceptation implicite de tout programme de police, par une police de substitution modifiant silencieusement le document, ni par un verrou limité à la seule empreinte de la fixture Noto présenté comme un support général. Si le traitement fiable nécessite une nouvelle dépendance, un périmètre plus étroit ou une réduction des garanties, exposer le blocage et demander l'arbitrage avant de poursuivre.
5. L'ancien préalable de qualification complète avant les mesures est levé par le report utilisateur de 11B (`spec.md:6.2.1`). Les premières mesures et le banc Windows gelé sont désormais disponibles (11C/11D) ; proposer les seuils à l'utilisateur avant de les imposer. Le corpus, le cas signé et les tâches regroupées restent ouverts ; aucun worker applicatif n'existe.

Les cases regroupées encore ouvertes des sections 1A à 1C incluent parfois des sous-cas déjà vérifiés : s'appuyer sur les tests et l'état courant, ne pas réécrire les fixtures existantes ni cocher toute une tâche sur la réussite d'un seul sous-cas. Les matrices des étapes 8 et 9 dans l'historique décrivent leur état à l'époque ; elles doivent être consolidées avec les restrictions confirmées de l'étape 10 avant validation du jalon.

Ne pas passer à l'interface complète ni déclarer la phase 1 terminée après la seule réussite d'un parcours simple. La phase 2 consolidera ensuite le moteur applicatif et l'état de session, une fois le jalon de faisabilité satisfait.

#### Limites et décisions encore ouvertes

- **Limite acceptée pour l'itération actuelle :** 11B reportée à une itération future. Des copies de la cible dans les programmes de police/CMap et les propriétés/conteneurs listés dans `spec.md:6.2.1` peuvent subsister. Ne pas ajouter implicitement fontTools, ne pas désactiver 11A et ne pas annoncer une suppression exhaustive. Les 19 échecs de sous-cas dans les deux tests de protection restent connus et conservés, sans `skip` ni faux résultat vert.

- `ActualText`, contenus balisés/accessibilité, couches, champs/signatures, annotations/liens, pièces jointes, actions, signets/destinations, polices Type 3, images alternatives, objets PostScript et extensions inconnues du catalogue sont actuellement **refusés**, pas nettoyés ni aplatis. Leur reconnaissance/refus est déjà testée : ne pas désactiver ces garde-fous pour faire passer un exemple.
- Les répétitions exactes sont démontrées dans le périmètre visible sans masque et avec un seul espace couleur gris/RGB. L'étape 10 démontre l'absence de regroupement pour les copies recadrées, rééchantillonnées, JPEG ou à un pixel modifié. L'utilisateur a confirmé le refus raster multi-images en V1, sans promesse de résolution de cette détection. Les représentations cachées restent à qualifier.
- Les masques et espaces couleur mélangés sont refusés par le contrôle de répétition. Le remplacement simultané de toutes les occurrences d'une image répétée n'est pas implémenté ; aucune propagation automatique autorisée.
- Reconnaissance simple et parcours multi-zones disponibles, mais pas de moteur applicatif. La qualification approfondie 11B est différée. Les plafonds sont maintenant choisis et contrôlés : flux/rendu au point commun, mémoire/durée/IPC dans le banc `spawn`/`onedir` (11F). Cela ne valide ni tout le parcours dans le paquet gelé ni un poste sans Python.
- Le parcours de test refuse les caractères partiellement sélectionnés, les groupes texte touchés par plusieurs zones, les images non affichées et les sélections raster hors grille entière de pixels. Il utilise une marge intérieure de 1 point pour le natif et 2 pixels pour les scans à 2 px/point, sans tolérance de rendu ajoutée. Ces bornes expérimentales ne remplacent pas les réglages de la future interface.
- Pour les images, la liste positive ajoute DeviceGray/DeviceRGB et le seul profil ICC sRGB MuPDF 1.28.2 qualifié (empreinte des octets décodés), filtres simples absent/Flate/ASCIIHex/DCT et paramètres de décodage absents ou vides. Profils inconnus, chaînes de filtres, prédicteurs, intent et interpolation explicites restent refusés. La qualification des couleurs ne prouve pas le nettoyage de toutes les données auxiliaires arbitraires du PDF.
- Étape 11A : conteneurs de police limités à Type0/CIDFontType2 et Type1 simple sans descripteur, encodages nommés ; autres types/propriétés refusés. Les références de programmes TrueType et CMap autorisées ont des dictionnaires de flux étroits, sans qualification générale de leurs octets internes. Les flux de ressource/page inspectés acceptent seulement l'absence de filtre, Flate ou ASCIIHex et des paramètres absents/vides ; aucun nouveau seuil de taille n'est ajouté.
- Clôture du corpus à établir en 11G : cas signé et seuls manques avérés de la recette V1. Les transformations/échelles/encodages/profils hors liste peuvent rester refusés ; leur prise en charge n'est pas une extension à entreprendre pour démarrer la phase 2. Vecteurs traversants et interactions simples sont déjà couverts par support ou refus ; rattacher ces preuves aux tâches regroupées.
- Les contrôles du corpus ne prouvent pas l'anonymisation de tout PDF utilisateur. La confirmation humaine ne devra jamais contourner un échec technique. Pas de documents clients tant que le prototype et l'environnement ne sont pas qualifiés.
- Licences : pikepdf/qpdf et ses dépendances sont autorisés à l'exécution ; PDFium reste hors distribution. Notices et accès aux sources exactes, obligations natives et Qt devront être vérifiés sur le paquet final.

### Historique des étapes du prototype

Les paragraphes suivants décrivent les résultats **au moment de chaque étape** ; leurs anciennes limites et rôles de dépendances sont remplacés par l'état de reprise et les arbitrages ci-dessus.

**Reprise après l'étape 1 du prototype :** `tests/fixtures.py` génère en mémoire les quatre contenus de base, des multipages et des pages tournées/recadrées. Les tests prouvent la présence des marqueurs, l'identité du rendu scan/scan+OCR, le caractère invisible de l'OCR et les dimensions tournées/recadrées ; ils ne prouvent pas encore une suppression. `open_pdf` refuse les tailles hors limites avant parsing, borne aussi la lecture en cas de croissance du fichier, contrôle 1 à 49 pages, refuse les PDF chiffrés (même sans mot de passe d'ouverture), les fichiers d'un autre format et les PDF réparés par le moteur. Le source est lu en mémoire et reste inchangé. Les diagnostics natifs ne sont pas affichés pour éviter des fragments documentaires dans les journaux. Les cas d'images partagées, objets auxiliaires, coordonnées de sélection et suppression restent à développer. Python 3.12.0 est autorisé pour ce corpus synthétique seulement. Aucun export utilisateur ni contrôle de sûreté général n'existe à ce stade.

**Étape 2 — plafond individuel des images :** `open_pdf` inspecte avant tout calcul d'empreinte ou extraction de pixels les dimensions des XObject image, y compris masques, objets imbriqués et non affichés. Les dimensions absentes, non entières ou indirectes sont refusées dans ce prototype. L'inspection des pages via `get_image_info(hashes=False, xrefs=False)` contrôle aussi les images inline ; les API installées ont été examinées pour éviter la voie de décodage destinée aux empreintes. Tests : 40 MP accepté par le contrôle de dimensions, dépassement et dimensions invalides refusés ; petites fixtures déclarant de grandes images/masques/objets imbriqués refusées avant inspection des pages ; voie inline vérifiée avec plafond réduit, sans allouer une grande image. Les 14 tests passent dans les deux environnements. Ce contrôle de dimensions n'est ni un bac à sable ni une borne de mémoire globale : décodage des flux, annotations, codecs et rendu nécessitent encore qualification. Les fixtures de grandes dimensions sont structurelles et ne doivent jamais être rendues. `pdftotext` est disponible sur le poste ; `pdftoppm` et `qpdf` n'ont pas été trouvés dans le PATH.

**Étape 3 — coordonnées et texte natif :** `page_to_view_matrix` centralise le passage des points non tournés relatifs à la CropBox vers la vue tournée, avec zoom et HiDPI ; `~matrix` donne l'inverse. Tests sur 4 rotations, 3 zooms et 4 facteurs HiDPI, avec points attendus calculés indépendamment et refus des facteurs invalides/non représentables. L'expérience native dans `tests/test_engine.py` applique les API de caviardisation installées, insère « Société Élodie » avec la police embarquée et réécrit avec `garbage=4, deflate=True`. Sur les 8 variantes rotation/recadrage, le marqueur ciblé disparaît du texte extrait, le témoin reste, le remplacement accentué est extractible et les pixels hors zone restent strictement identiques ; rotation, CropBox et source conservés. Le test indépendant exécute `pdftotext -enc UTF-8 <fixture.pdf> -` sur source et résultat temporaires synthétiques : mêmes constats textuels. L'outil installé est **Xpdf pdftotext 4.00**, pas Poppler ; il est ancien et réservé ici au corpus synthétique. Les 18 tests passent dans les deux environnements, aucun test ignoré. Ce contrôle textuel indépendant ne qualifie pas encore images, objets auxiliaires, objets inutilisés et anciennes révisions. Aucune fonction de substitution utilisateur n'est exposée tant que reconnaissance et nettoyage ne sont pas validés.

**Étape 4 — scans et OCR :** `tests/test_raster.py` expérimente le remplacement dans l'image d'origine à sa résolution native, avec réencodage PNG sans perte et retrait du texte OCR ciblé. Les 24 variantes scan/scan+OCR/zone scannée de page mixte × rotations × recadrages passent : tous les objets image du résultat contiennent les pixels nettoyés attendus, une seule image subsiste après réécriture, dimensions et pixels hors zone conservés exactement, aucun texte PDF de remplacement ajouté, OCR témoin et texte natif hors zone conservés. L'extraction indépendante Xpdf confirme les modes textuels attendus. Une marge interne de 2 pixels évite un halo d'interpolation observé lorsque le remplacement touchait la limite ; les comparaisons de rendu restent strictes, sans tolérance ajoutée. Cette marge est validée uniquement pour les fixtures à 2 pixels/point. Les 20 tests passent dans les deux environnements, sans test ignoré. Les expériences ne gèrent pas encore images partagées, masques, cisaillements, autres échelles et contenus auxiliaires ; elles ne sont pas une API de substitution utilisateur. Aucun outil indépendant de rendu ou d'extraction d'images n'a été trouvé dans le PATH (`pdftoppm`, `pdftopng`, `pdfimages`, `qpdf`, `mutool`) ; seul le texte bénéficie pour l'instant d'un contrôle indépendant.

**Étape 5 — inspection indépendante :** outils autorisés et installés dans les deux environnements : pikepdf 10.17.0 / qpdf 12.4.2, pypdfium2 5.14.0 / PDFium 156.0.8076.0 et lxml 6.1.3. Versions épinglées uniquement dans `requirements-dev.txt`, licences inventoriées. `tests/test_independent.py` vérifie les 32 variantes natives et raster : PDFium rend avant/après à 144 dpi avec conservation stricte des pixels hors zone, dimensions, rotation et modes textuels attendus ; qpdf ouvre sans récupération ni erreur syntaxique, contrôle les chaînes des opérateurs TJ natifs et récupère tous les objets image avec pixels nettoyés identiques à l'attendu. La structure simple de sortie ne contient pas de chaînage `/Prev`, ni les structures auxiliaires recherchées. Attention : ces sources simples ne possèdent pas ces contenus auxiliaires ; ce test ne démontre pas encore leur suppression. Deux sorties volontairement contaminées par une image originale non affichée, référencée ou entièrement inutilisée, sont détectées : le contrôle ne se limite pas aux ressources visibles. Les 23 tests passent sans test ignoré et `pip check` réussit dans les deux environnements. Commande ciblée : `python -m unittest discover -s tests -p test_independent.py -v`. Les anciennes révisions et le nettoyage auxiliaire restent à qualifier ; aucun support général annoncé.

**Étape 6 — images réutilisées :** `repeated_image_occurrences` regroupe les occurrences visibles par dimensions, espace couleur et empreinte des pixels décodés, sans se limiter au numéro d'objet. Les fixtures couvrent même objet, copies physiques, réencodage Flate/ASCIIHex, objets Form imbriqués, deux occurrences sur la même page et changement d'échelle d'affichage. qpdf confirme les objets distincts et les flux différents aux mêmes pixels. `check_image_reuse` refuse une modification locale visant un groupe répété, indique les pages et ne modifie pas le document ; une page sans rapport n'est pas bloquée. Les masques, espaces couleur mélangés et formats autres que gris/RGB sont refusés avant calcul des empreintes. Une empreinte native utilisée pour détecter une répétition n'est pas un certificat de suppression ; une collision ne ferait qu'ajouter un refus. Les 33 tests passent dans les deux environnements. Limites encore ouvertes : copies avec pixels modifiés, couches masquées, masques et qualification complète des images non affichées ; le traitement de plusieurs occurrences sélectionnées simultanément n'est pas implémenté, le garde-fou refuse pour l'instant toute édition locale d'une image répétée. Les expériences de transformation des étapes précédentes ne sont pas encore reliées en pipeline utilisateur.

**Étape 7 — inspection structurée et nettoyage :** pikepdf est autorisé et épinglé à l'exécution, avec lxml et packaging ; PDFium reste réservé aux tests. `open_pdf` inspecte la structure avec qpdf avant ouverture MuPDF. Les textes alternatifs et contenus balisés (y compris noms échappés et Form imbriqués), couches, champs/signatures, annotations/liens, pièces jointes, actions, destinations nommées, signets et structures auxiliaires non maîtrisées sont refusés. Le résidu `ActualText` après caviardisation + `scrub` est reproduit dans un test ; ce résultat est ensuite refusé par le nouveau contrôle. `sanitize_pdf` retire Info, références XMP et miniatures, régénère les identifiants et réécrit intégralement avec élimination des objets inutilisés, sans recompression JPEG ni promesse PDF/A. Un contrôle syntaxique, une référence XMP ambiguë, une erreur ou un avertissement de parsing bloquent le résultat sans exposer les diagnostics documentaires. Tests d'anciennes révisions avec titre sensible, de pixels/rendu/texte préservés, de flux JPEG inchangés et d'erreurs injectées. MuPDF relit les sorties qpdf ; PDFium compare le rendu et le texte. Le nettoyage ne remplace pas les substitutions et les expériences ne forment pas encore un pipeline d'export.

Validation finale de l'étape 7 : 43 tests réussis dans `.venv` et `.venv-check`, sans test ignoré ni avertissement ; `pip check` réussi dans ces deux environnements et dans `.venv-runtime`. Ce dernier a été créé neuf depuis `requirements.txt` uniquement ; ouverture et nettoyage OCR synthétique réussis, absence de PDFium vérifiée. Les tests couvrent aussi le refus des extensions inconnues du catalogue, objets PostScript et images alternatives. La liste positive du catalogue inclut explicitement `Info`, présent à cet emplacement dans certaines sources du corpus : ce conteneur est supprimé en plus de l'Info du trailer, et sa disparition est vérifiée. L'inventaire des licences et les instructions reflètent le nouveau rôle de pikepdf ; sources et notices complètes des bibliothèques natives restent à joindre lors du conditionnement. Les refus sont conservateurs : pas de support général des PDF balisés ni d'aplatissement de champs/annotations annoncé.

**Étape 8 — classification expérimentale par zone :** après réexécution des 43 tests de référence, ajout de `classify_zone(data, page_number, rectangle)` sur les octets originaux. L'inspection structurée et la seconde ouverture MuPDF sont réutilisées ; la validation de rectangle est partagée avec le contrôle de répétition. Les erreurs du constructeur de rectangles (y compris ses assertions sur une entrée invalide) sont converties en refus sans contenu documentaire. Aucun fichier source ni résultat final n'est écrit par cette fonction ; aucun pipeline de substitution n'est ajouté.

Les 8 nouveaux tests couvrent les quatre cas simples, 4 rotations et le recadrage, les deux zones distinctes d'une page mixte, une autre page native, les préconditions d'entrée et les refus proches. Les fixtures comprennent superposition visible sur scan, textes superposés/transparents/invisibles, masque, vecteur traversant, découpe, cisaillement, rotation/reflet/changement d'échelle de l'image, plusieurs images, Form, mode texte découpant, opérateur inconnu et ressources absentes/invalides. Les tests des quatre transformations vérifient le motif de refus pour éviter de réussir seulement parce que la sélection serait hors image. Une image répétée reste bloquée. Les textes OCR sont reconnus par leur rendu invisible sur une image admissible ; aucun OCR n'est exécuté et aucune correspondance sémantique pixels/texte n'est affirmée.

Matrice provisoire de reconnaissance — **aucune de ces lignes ne vaut autorisation d'export** :

| Structure | Critère de reconnaissance initial | Support / refus actuel | Contrôle exécuté à chaque appel | Preuve sur corpus / contrôle restant |
| --- | --- | --- | --- | --- |
| Texte natif simple | Texte horizontal opaque de type 0, sans image ciblée ni superposition de spans | Reconnaissance `native` | Préinspection globale, liste positive page/ressources/opérateurs et traces texte | Rotations/recadrages et autre page native ; retrait effectif couvert séparément par l'expérience native, pas encore relié |
| Scan simple | Une image couvre la sélection, gris/RGB 8 bits sans masque, axes positifs à 2 px/point ; pas de texte ciblé | Reconnaissance `scan` | Même préinspection, format/transformation et garde des répétitions | Rotations/recadrages ; autres échelles et copies cachées à qualifier |
| Scan avec OCR | Même image et texte ciblé uniquement invisible de type 3 | Reconnaissance `ocr` | Contrôles scan et traces invisibles opaques/horizontales | OCR isolé démontré ; pipeline conjoint pixels/texte et postconditions finales à relier |
| Page mixte à zones distinctes | Chaque sélection satisfait indépendamment l'une des lignes ci-dessus | Reconnaissance locale | Aucun mode global par page ; zone traversant les deux régions refusée | Les deux régions sont reconnues ; interactions multi-zones à tester |
| Image répétée | Pixels visibles identiques, objets partagés ou distincts | Refus local conservé | `check_image_reuse`, sans propagation automatique | Fixtures existantes ; représentations non affichées et copies modifiées restent ouvertes |
| Superposition, masque, transparence, découpe, vecteur, Form, opérateur ou ressource inconnus | Hors liste positive de cette expérience | Refus explicite | Préinspection et inspection de page, sans mode par défaut | Refus proches automatisés ; refus de page entier conservateur, pas une réduction définitive de la V1 |

Validation de l'étape 8 : `python -m unittest discover -s tests -v` donne **51 tests réussis dans chacun des environnements `.venv` et `.venv-check`**, aucun ignoré. `pip check` réussit dans `.venv`, `.venv-check` et `.venv-runtime`. Vérification synthétique des quatre cas dans `.venv-runtime` avec absence de PDFium confirmée. Aucun ajout de dépendance, interface, export utilisateur, commit ou push. Pas de nouvel arbitrage bloquant pour cette reconnaissance limitée ; demander une décision si les prochains essais imposent de réduire les garanties ou de fixer de nouvelles limites d'usage. Le jalon moteur reste non validé.

**Étape 9 — parcours expérimental multi-zones :** `tests/test_pipeline.py` assemble les opérations déjà démontrées : classification de toutes les zones sur l'original, liste positive sur toutes les pages, contrôles de chevauchement/interactions, retrait des textes natifs/OCR, modification groupée des pixels par image, insertion fictive, réécriture complète et `sanitize_pdf`, puis contrôles des octets finaux. Le parcours reste dans les tests comme les expériences précédentes ; aucune API d'export utilisateur ni logique de session de phase 2 n'est créée. Les réglages fixes de cette expérience sont fond blanc, police Noto Sans embarquée 14 pt / 28 px pour les scans à 2 px/point, monoligne, sans espaces de bord ni caractères hors police. Le débordement est refusé, jamais tronqué silencieusement.

Les pixels sont convertis en double précision avec les axes déjà qualifiés : l'inverse des matrices MuPDF en simple précision produisait de petits écarts sur des bords entiers. Les sélections hors grille entière sont refusées à ce stade. Une marge intérieure de 1 point pour le texte natif évite un débordement visible du glyphe « T » détecté par PDFium ; la comparaison hors zones est restée strictement identique, sans tolérance supplémentaire.

Un contre-exemple de texte partagé est conservé : sur un unique opérateur TJ, deux sélections disjointes peuvent faire disparaître un espace voisin hors zone. Le test reproduit la perte ; la préinspection refuse désormais plusieurs zones touchant un même groupe texte. Les caractères partiels/communs et vecteurs sont également refusés. Deux zones sur la même image sont au contraire regroupées et vérifiées ensemble ; aucune image répétée n'est modifiée automatiquement et les images non affichées font refuser l'expérience.

| Structure / étape | Contrôle à chaque génération expérimentale | Qualification indépendante sur corpus | Limite restante |
| --- | --- | --- | --- |
| Natif / OCR | Texte attendu dans chaque zone ; remplacement natif visible et opaque ; aucune nouvelle extraction de texte raster ; Unicode, type, opacité, police, couleur et positions des caractères hors zones conservés | PDFium : texte et rendu ; qpdf : chaînes TJ natives retirées | Positions textuelles comparées à 0,001 point ; inspection générale des flux cachés non qualifiée |
| Images | Empreinte SHA-256 des pixels RGB et dimensions de tous les objets image finaux, avec multiplicité, contre l'état attendu ; pas seulement les ressources affichées | qpdf récupère tous les objets et compare exactement les pixels aux images attendues calculées sur la grille connue du corpus ; PDFium compare le rendu complet | Formats/profils/échelles hors corpus et mémoire cumulée à qualifier ; aucune reconnaissance générale des copies visuellement similaires |
| Géométrie et rendu | Nombre, MediaBox, CropBox et rotation conservés ; pas de rasterisation générale | PDFium à 144 dpi : identité stricte hors union des zones, y compris rotation/recadrage et multipage mixte | Le rendu indépendant est une qualification du corpus, pas un contrôle livré par génération ; plafond de rendu à définir avant application |
| Nettoyage et erreurs | Réouverture avec les deux lecteurs, syntaxe qpdf, refus auxiliaires existants, absence d'Info/XMP/miniatures et de `/Prev` | Tests de résultat contaminé, nettoyage défaillant, retrait textuel/pixel ignoré et remplacement natif invisible : tous bloqués | Qualification globale des représentations cachées et exécution Windows encore ouverte |

Vérifications de l'étape 9 : **64 tests réussis dans `.venv` et `.venv-check`**, sans test ignoré ni avertissement, avec `python -m unittest discover -s tests -v`. Les 13 nouveaux tests incluent 24 variantes à deux zones (natif/scan/OCR × 4 rotations × recadrage), une page mixte avec zones native/raster, un multipage natif/scan, effacement simple et OCR hors zone conservé, les refus et les erreurs injectées. Commande ciblée : `python -m unittest discover -s tests -p test_pipeline.py -v`. `render_and_extract` accepte maintenant un numéro de page facultatif, sans changer les contrôles existants. Aucun document réel, dépendance, interface, export final, commit ou push ajouté. Aucun nouvel arbitrage requis pour ce périmètre expérimental ; les garanties sur copies/représentations et les limites globales restent des jalons obligatoires avant validation du moteur.

**Étape 10 — frontières des images et conservation des couleurs :** `image_variant_pdf` et `tests/test_image_boundaries.py` ajoutent des copies à un pixel modifié, recadrée, rééchantillonnée et réencodée en JPEG, ainsi qu'une mire couleur non confidentielle. Les quatre copies ne sont pas regroupées par le détecteur exact. Pour la copie à un pixel modifié hors zone et la copie recadrée, les octets des pixels de la zone cible restent exactement identiques ; un rééchantillonnage NEAREST double peut également être inversé sur cette fixture. Un hash de l'image entière ne garantit donc pas l'absence de ces copies.

Le garde-fou partagé `check_image_reuse` compte désormais objets et occurrences avant tout calcul de hash demandé par ce garde-fou. Une substitution touchant une image est refusée si le document contient plusieurs objets image ou plusieurs occurrences visibles, même avec des pixels distincts ; aucun traitement n'est propagé. Le test vérifie que cette décision n'utilise ni hashes ni recherche d'xrefs avec décodage. `repeated_image_occurrences` reste une expérience distincte de regroupement exact, pas une preuve de sûreté. Les pages natives et une page scannée unique au milieu de pages natives restent couvertes ; des scans multipages ordinaires sont désormais bloqués par ce verrou provisoire. **Cela demande un arbitrage de périmètre, pas une déclaration de fin de phase 1.**

Une seconde erreur du parcours est corrigée : `replace_image` insère un PNG dans l'espace couleur par défaut de MuPDF. Avec des composantes identiques mais un autre espace/profil d'entrée, PDFium détectait un changement hors zone. Le parcours garde maintenant les canaux RGB ou gris d'origine, restaure explicitement le `ColorSpace` PDF qualifié et nettoie les ressources inutilisées de la page avec `clean_contents`. Ce dernier point est nécessaire : après restauration, la ressource d'insertion temporaire créée par `replace_image` pouvait sinon conserver une seconde image au profil par défaut ; le contrôle final des objets image a bloqué ces premiers essais, sans être affaibli.

La liste positive refuse les profils ICC non qualifiés et les paramètres/encodages non démontrés. Le seul profil ICC accepté ici est celui intégré par MuPDF 1.28.2, reconnu par SHA-256 des octets décodés ; aucun nom descriptif de profil n'est pris pour une preuve. Les fixtures DeviceGray, DeviceRGB, ICC sRGB connu et JPEG RGB passent avec identité stricte des rendus hors zone, pixels récupérables attendus, canaux/ColorSpace conservés et absence de nouvelle compression JPEG. Le contre-exemple de profil inconnu conserve les mêmes nombres de composantes mais change le rendu ; il est refusé avant transformation. Intent, interpolation explicite, prédicteur et chaîne de filtres non qualifiés sont également refusés.

Vérifications de l'étape 10 : **70 tests réussis dans chacun des environnements `.venv` et `.venv-check`**, aucun ignoré, avec `python -W error -m unittest discover -s tests -v`. Six nouveaux tests regroupent ces cas et leurs refus. Commande ciblée : `python -W error -m unittest discover -s tests -p test_image_boundaries.py -v`. Aucune dépendance ajoutée : ImageCms/Little CMS, utilisé pour une fixture seulement, appartient déjà à Pillow et figure dans les notices natives existantes. Aucun document client, fichier PDF persistant, interface, export utilisateur, commit ou push. Les ressources globales, représentations cachées et exécution Windows restent non qualifiées ; aucune sortie n'est annoncée sûre pour des clients.

**Décision de reprise demandée :** maintenir pour la V1 un périmètre prudent à une seule image/occurrence dans tout le document, ou conserver le verrou en prolongeant la phase 1 pour étudier une stratégie multi-images démontrable. Ne pas remplacer ce choix par une similarité visuelle approximative ni par une garantie affaiblie implicitement.

**Réponse utilisateur consignée : périmètre prudent accepté.** Le refus multi-images devient le périmètre raster V1, et non plus seulement un verrou provisoire ; la spécification et les arbitrages courants sont mis à jour. Aucune garantie de suppression n'est diminuée pour obtenir un export. Poursuivre la qualification des ressources et de Windows sur ce périmètre ; il n'y a plus d'arbitrage multi-images en attente.

**Étape 11A — références auxiliaires cachées (qualification partielle) :** référence de 70 tests réexécutée avant modification. Ajout initial des tests de refus : neuf sous-cas échouaient car `sanitize_pdf` acceptait les références synthétiques inconnues. L'expérience du parcours complet a ensuite retourné un résultat contenant encore un flux marqueur via ICC, police, descripteur, programme de police, CMap et CIDSystemInfo ; le flux de page et la police inutilisée ne conservaient pas le marqueur sur ces fixtures, sans constituer une garantie générale. Le test conservé reproduit les six résidus après caviardisation MuPDF puis réécriture qpdf, avec relecture des flux par MuPDF.

Le correctif ajoute une liste positive de clés et de types pour les conteneurs de police et leurs descendants, descripteurs, informations CID, programmes, CMap, profils ICC et dictionnaires de flux de page. Les références détournées via noms de police, largeurs numériques ou espace alternatif ICC sont refusées. Les onze variantes sont bloquées avant transformation par le contrôle partagé, avec erreurs neutres ; une référence ICC réinjectée dans les octets finaux bloque aussi le résultat. Un flux entièrement non référencé est démontré éliminé, sans le confondre avec un flux référencé mais non peint. Les contrôles existants couleur, pixels, rendu, OCR conservé et refus multi-images restent inchangés.

Validation : **74 tests réussis dans chacun des environnements `.venv` et `.venv-check`**, aucun ignoré, avec `python -B -W error -m unittest discover -s tests -v`. Commande ciblée : `python -B -W error -m unittest discover -s tests -p test_hidden_references.py -v` (4 tests). `pip check` réussi dans les trois environnements ; huit admissions et onze refus vérifiés dans `.venv-runtime` sans PDFium. Aucune dépendance, interface, fichier PDF persistant, limite d'usage, commit ou push ajouté. **Étape 11 non terminée :** qualifier les programmes/CMap et autres représentations cachées avant les mesures globales et le modèle Windows ; aucun jalon moteur validé.

**Publication Git après 11A :** sur demande explicite de l'utilisateur, les étapes 8 à 11A, les quatre nouveaux fichiers de tests et leur documentation ont été commitées ensemble dans `7e00893`, puis poussées sur `origin/main` avec les sept commits précédemment en attente. Synchronisation distante vérifiée et répertoire propre après push. Une seconde demande explicite autorise le commit/push de la présente mise à jour documentaire de reprise. Ces autorisations ne valent pas autorisation de commit/push pour les travaux suivants.

**Étape 11B — reproduction avant correctifs, arbitrage requis (19 octobre 2026) :** environnements initiaux absents ; après autorisation utilisateur, installation neuve des dépendances épinglées sous Python 3.13.0 dans `.venv`, `.venv-check` et `.venv-runtime`. Référence complète : 74 tests réussis dans chacun des deux environnements de développement, aucun ignoré, avec `python -B -W error -m unittest discover -s tests -v` ; `pip check` réussi dans les trois environnements. Python système et fichiers de dépendances inchangés.

`hidden_content_pdf` réutilise le scan OCR à une seule image et ajoute une copie synthétique du marqueur ciblé dans des contenus non peints. La variante TrueType ajoute un vrai enregistrement descriptif ID 10 de la table `name`, avec reconstruction des offsets et checksums ; cet assembleur limité aux fixtures n'est pas un validateur à livrer. Les variantes CMap ajoutent soit un commentaire, soit une correspondance Unicode pour le code inutilisé `FFFF`. Les autres variantes utilisent des valeurs déjà admises ou des conteneurs encore insuffisamment inspectés.

| Représentation synthétique | Après retrait OCR MuPDF et réécriture qpdf sans garde-fou | Parcours complet actuel | Contrôle final après réinjection |
| --- | --- | --- | --- |
| Description TrueType (`name`, ID 10) | Marqueur récupérable dans l'enregistrement | Résidu accepté | Non bloquée |
| Commentaire et correspondance inutilisée de `ToUnicode` (2 variantes) | Marqueur récupérable dans le flux/CMap | Résidus acceptés | Non bloquées |
| `BaseFont`, CID `Registry` et `Ordering` (3 variantes) | Valeurs récupérables | Résidus acceptés | Non bloquées |
| Catalogue `Lang`, `ViewerPreferences/Private`, `Pages/Private` (3 variantes) | Valeurs récupérables | Résidus acceptés | Non bloquées |
| Champ privé du trailer | Éliminé sur cette fixture par la réécriture MuPDF | Éliminé sur cette fixture | Réinjection non bloquée |
| Occurrence OCR indépendante du même marqueur hors sélection | Hors de la promesse de suppression locale | Conservée, Unicode/type/géométrie et rendu hors zone identiques | Ce témoin ne doit pas être rejeté par une recherche globale du marqueur |

Les champs/flux récupérés par qpdf sont relus directement par MuPDF ; PDFium confirme indépendamment le retrait du texte OCR et la conservation du rendu dans l'expérience sans édition des pixels. Cette expérience de réécriture seule ne prétend pas nettoyer le scan original. Le test du parcours complet contrôle séparément les postconditions de suppression/refus et l'intégrité des octets sources. La distinction avec l'occurrence invisible indépendante est vérifiée par sa géométrie hors zone et les traces de texte, pas par la seule présence de la chaîne dans le document.

Commande ciblée : `python -B -W error -m unittest discover -s tests -p test_hidden_contents.py -v`. Résultat dans `.venv` avant correctif : 4 tests exécutés, 2 réussis ; 2 tests de protection échouent (19 sous-cas : 9 résidus acceptés et 10 contaminations finales non bloquées), aucun ignoré. Aucun correctif de production, seuil, dépendance, réduction de périmètre, interface, fichier PDF persistant, commit ou push ajouté. La frontière interne des polices n'est pas qualifiée : demander l'arbitrage avant ajout d'un outil spécialisé ou restriction du support ; ne pas remplacer cette décision par une empreinte de Noto ni par un parseur TrueType improvisé. Mesures globales et modèle Windows/`onedir` non commencés.

Suite étendue réexécutée ensuite dans **les deux environnements** avec `-B -W error` : **78 tests, 19 échecs de sous-cas dans les deux nouveaux tests de protection**, aucun ignoré ni autre régression constatée. `git diff --check` réussi. Fichiers de travail : `tests/fixtures.py`, nouveau `tests/test_hidden_contents.py` (non encore suivi par Git, à préserver), `plan.md` ; aucun fichier moteur modifié.

**Décision utilisateur après explication de 11B :** « Ce n'est pas prioritaire et ça fera parti d'une autre itération future. Note le dans la spec et dans le plan et passe à la suite ». Report consigné en `spec.md:6.2.1` et dans les arbitrages courants. Aucune dépendance ajoutée, aucun refus existant retiré ; les tests rouges restent des contre-exemples différés, pas des critères corrigés. Poursuite des mesures autorisée sans attendre leur correction.

**Étape 11C — premières mesures de ressources (19 octobre 2026), validées par l'utilisateur :** ajout de `tests/measure_resources.py` et de quatre tests dans `tests/test_resource_measurements.py`. Sonde de développement Windows, pas un point d'entrée applicatif ni un worker. Elle réutilise les fixtures et le parcours expérimental ; aucun PDF client, fichier PDF persistant, nouveau seuil, dépendance ou changement moteur. Chaque opération est mesurée dans un processus neuf, sans concurrence entre mesures ; les PDF synthétiques sont générés dans le parent et transmis en mémoire. Ce choix isole les compteurs de mesure, mais ne qualifie pas encore le modèle d'exécution applicatif `spawn`/arrêt/erreurs ni PyInstaller.

Protocole reproductible (JSON agrégé uniquement, sans contenu ni chemin documentaire ; exemple de destination locale ignorée par Git) :

```powershell
New-Item -ItemType Directory -Force test-output | Out-Null
.\.venv\Scripts\python.exe -B -W error tests/measure_resources.py --phases open streams render-1x render-2x pipeline | Set-Content -Encoding utf8 test-output/resources.json
.\.venv-runtime\Scripts\python.exe -B -W error tests/measure_resources.py --samples ocr-7.68mp stream-8mib --phases open streams render-2x | Set-Content -Encoding utf8 test-output/resources-runtime.json
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -p test_resource_measurements.py -v
```

Campagne effectuée sur Windows 11 build 26200, Python 3.13.0 64 bits, versions épinglées inchangées. Neuf cas × cinq opérations × trois répétitions = **135 mesures isolées** dans `.venv`. Durées ci-dessous : médiane de trois mesures, hors lancement/imports et transfert d'entrée ; mémoire : maximum des pics observés, **incluant** interpréteur, bibliothèques et entrée. Compteurs natifs Windows `GetProcessMemoryInfo` (résident/engagement privé) en plus de `tracemalloc` (allocations Python seulement). Les mesures sont instrumentées, locales et non des garanties de performances sur un autre poste. `pipeline` inclut transformation, nettoyage et vérification de `tests/test_pipeline.py`, donc des imports de développement dont PDFium ; il ne représente pas le futur paquet runtime.

| Cas synthétique | Entrée (octets) | Ouverture (ms) | Rendu page 1 à 2× (ms) | Parcours (ms) | Pic résident parcours (Mio) | Pic engagement parcours (Mio) | Pic tracé Python parcours (Mio) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Natif 1 page | 304 226 | 48,4 | 50,2 | 338,2 | 77,8 | 66,0 | 1,6 |
| Natif 12 pages | 305 800 | 54,3 | 53,4 | 416,3 | 78,4 | 66,5 | 1,7 |
| Natif 49 pages | 311 091 | 70,6 | 69,5 | 564,6 | 79,5 | 67,9 | 2,1 |
| OCR 0,48 MP | 316 402 | 45,8 | 52,1 | 323,1 | 87,7 | 75,5 | 4,0 |
| OCR 1,92 MP | 320 670 | 46,4 | 57,2 | 468,2 | 120,3 | 107,9 | 12,3 |
| OCR 7,68 MP | 342 189 | 46,7 | 85,0 | 1 033,0 | 252,4 | 240,5 | 45,4 |
| Natif + flux commentaire 1 Mio | 306 207 | 57,7 | 55,2 | 379,3 | 78,0 | 66,4 | 1,6 |
| Natif + flux commentaire 4 Mio | 309 255 | 66,9 | 76,5 | 455,1 | 82,0 | 72,5 | 1,6 |
| Natif + flux commentaire 8 Mio | 313 332 | 87,3 | 103,0 | 574,8 | 88,8 | 81,7 | 1,6 |

Volumes décodés uniques récupérés par qpdf : programme TrueType **569 208 octets**, CMap **12 922 octets**, profil ICC des scans **2 576 octets**. Ensemble des flux : **582 366 octets** pour les natifs (ressources et contenus identiques dédupliqués, même à 49 pages) ; **2 025 005 / 6 345 007 / 23 625 012 octets** pour les scans 0,48 / 1,92 / 7,68 MP. Le flux image du dernier fait 23 040 000 octets. Les flux commentaire font réellement 1 / 4 / 8 Mio après décompression, sans dimensions mensongères ; l'entrée du cas 8 Mio ne pèse que 313 332 octets, mais l'ensemble des flux décodés atteint **8 970 974 octets**. La sonde lit un flux à la fois pour ce comptage, sans conserver tous les flux décodés simultanément.

Rendu d'une seule page : 1× et 2×, soit au maximum **7,68 MP / 23 040 000 octets de composantes RGB** à 2× dans cette campagne. Pour le scan 7,68 MP, le pic résident du rendu 2× est **125,6 Mio**, contre **252,4 Mio** pour le parcours complet. Ce dernier inclut les copies transitoires des images, conversions, extractions, réécritures et vérifications : la taille des seuls octets source/résultat (342 189 / 338 073) ou le pic Python (45,4 Mio) ne borne pas la mémoire native. Le nombre exact et la contribution de chaque copie interne ne sont pas attribués par cette sonde. Les résultats natifs atteignent environ 595–603 ko avec l'insertion de la police ; aucun export disque utilisateur n'existe et aucune durée d'export n'est revendiquée.

Contrôle runtime sans PDFium : **18 mesures supplémentaires**, trois répétitions des opérations ouverture/flux/rendu 2× pour OCR 7,68 MP et flux 8 Mio. OCR : médianes 46,4 / 54,4 / 84,8 ms ; pics résidents 59,8 / 100,5 / 125,6 Mio. Flux 8 Mio : 85,2 / 29,2 / 100,0 ms ; pics 72,8 / 73,1 / 72,9 Mio. Le parcours expérimental n'est pas exécuté dans cet environnement.

**Limites et décisions restantes :** aucune mesure à 40 MP, de très grandes pages, de nombreux flux distincts, de polices/profils volumineux ou d'une entrée proche de 10 Mo. Les 49 pages natives réutilisent des ressources dédupliquées ; ce n'est pas un pire cas. Aucun seuil ne peut être déduit automatiquement de ces seuls points. Les plafonds de flux décompressés (individuel/cumulé), rendu par page, mémoire globale et durée sont toujours **à arbitrer**, ainsi que le mécanisme de refus/arrêt avant épuisement des ressources. Les mesures confirment la nécessité de compter la mémoire native et les allocations transitoires ; ne pas extrapoler une garantie à 40 MP ni modifier le quota individuel existant. Prochaine unité après validation : compléter les mesures si demandé, puis qualifier le modèle d'exécution Windows et `onedir` sans inventer de limites produit.

Vérification finale de cette unité : quatre tests de sonde réussis ; suite complète avec `-B -W error` dans `.venv` et `.venv-check` : **82 tests exécutés, aucun ignoré ; seuls les 19 sous-cas des deux tests de protection 11B différés échouent**. La suite globale n'est donc pas verte. `pip check` réussi dans les trois environnements ; absence de PDFium du runtime vérifiée ; `git diff --check` réussi. Les garde-fous 11A/couleurs/multi-images et les contrôles hors zone restent inchangés. Aucun commit/push.

**Validation et publication locale demandées ensuite :** l'utilisateur répond « commit et continue » après présentation des mesures et des 19 échecs différés. Cette demande autorise un commit de l'unité courante (spécification/plan, fixtures et tests 11B, sonde et tests de ressources), puis le passage à la qualification Windows sans nouveau plafond produit. Elle n'autorise ni push ni commit anticipé de l'unité suivante.

**Commit local vérifié :** `72bee42` — `test: measure prototype resources and document deferred hidden content limits`. Six fichiers inclus, répertoire propre après commit, aucun push ; le commit est en avance d'un sur `origin/main` au début de 11D.

**Étape 11D — banc d'exécution Windows et test précoce `onedir` (19 octobre 2026), validée sans commit :** `tests/windows_probe.py` propose un processus `multiprocessing` en contexte `spawn` par travail. Le parent n'importe ni MuPDF ni qpdf ; les fixtures, objets PDF, rendu, transformation, nettoyage et relecture restent dans l'enfant. Un seul processus actif ou résultat non collecté est admis, aucun pool ni file de travaux. La réponse contient des octets immuables, un identifiant de révision et un statut ; aucun objet PDF/Pixmap ne traverse le pipe. Réception des octets avant `join` pour éviter le blocage d'un résultat plus gros que le tampon IPC. Fermeture normale après réponse ; `terminate`, `join` et libération des handles pour annulation ou attente dépassée. Les erreurs et crashs ne transmettent ni traceback, chemins ni contenu documentaire. Les résultats périmés sont refusés et un nouveau travail peut démarrer après arrêt.

Le banc réutilise `NativeExperimentTests.replace_native` sur la fixture native tournée à 90° et recadrée, puis les contrôles communs/classification/nettoyage et la comparaison stricte du rendu hors zone. Cette preuve de transport/exécution ne remplace pas le parcours multi-zones de `tests/test_pipeline.py` et ne prétend pas qualifier les scans/OCR/mixte dans le paquet gelé. Les PDF sont synthétiques, générés dans l'enfant et jamais écrits sur disque. `tests/fixtures.py` retrouve la même police embarquée via `_MEIPASS` en mode gelé. Le parent ne traite actuellement que des commandes de scénario fixes : le transport des entrées/rendus d'une future interface reste à concevoir.

Recette identique en source et dans l'exécutable gelé : **9 scénarios réussis** — refus d'un second travail ; ouverture/rendu/transformation native avec réponse PDF dépassant 64 Kio ; refus d'un PDF chiffré ; erreur injectée avec diagnostic neutre ; sortie brutale enfant ; résultat périmé ; annulation d'un enfant prêt en attente ; interruption après échéance de surveillance du test ; redémarrage après arrêt. Le watchdog de 15 s des petites fixtures, l'échéance forcée à zéro pour le scénario d'attente et le timeout de 90 s du lanceur de recette sont des dispositifs de test, **pas des limites de durée d'un document utilisateur**. Aucun plafond produit de mémoire, flux, rendu ou durée n'est ajouté. Le processus séparé n'est pas un bac à sable ; le modèle n'est pas intégré à Qt et ne prouve pas une interface réactive ni une borne en octets des échanges.

Commandes reproductibles depuis la racine (les chemins de données sont absolus car `--specpath build` change leur base de résolution) :

```powershell
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -p test_windows_probe.py -v
.\.venv-runtime\Scripts\python.exe -B -W error tests/windows_probe.py --self-test
.\.venv\Scripts\python.exe -B -m PyInstaller --onedir --console --name SubstiDudeProbe --specpath build --workpath build --distpath dist --paths "$PWD\tests" --add-data "$PWD\substidude\resources;substidude/resources" --add-data "$PWD\LICENSE;." --add-data "$PWD\THIRD_PARTY_NOTICES.md;." --exclude-module pypdfium2 tests/windows_probe.py
.\dist\SubstiDudeProbe\SubstiDudeProbe.exe --self-test
```

Construction effective avec PyInstaller 6.22.3/hooks 2026.8, Python 3.13.0 sur Windows 11 build 26200. Les sorties `build/` et `dist/` sont locales et ignorées ; aucun paquet publié. Le paquet contient 59 fichiers (environ 92 Mo décimaux), dont `python313.dll`, les ressources Noto/OFL, `LICENSE` et l'inventaire tiers. `pdfium_available` vaut **false** dans le runtime et le binaire gelé ; aucune bibliothèque PDFium détectée dans les fichiers du paquet. Les avertissements d'analyse PyInstaller concernent des modules conditionnels/optionnels non utilisés dans cette recette ; aucune dépendance n'a été ajoutée pour les faire disparaître. L'audit complet des licences/sources natives et la construction de l'application finale restent à faire.

Recette gelée également réussie après copie du dossier `onedir` hors du dépôt dans un chemin contenant espaces et accents, répertoire courant déplacé, variables `PYTHONHOME`/`PYTHONPATH`/`VIRTUAL_ENV` retirées et `PATH` limité au dossier système Windows. Copie temporaire nettoyée après recette. Ce test ne remplace **pas** une machine sans Python installé, un compte non administrateur ou une recette réseau coupé ; ces conditions ne sont pas déclarées validées. Il n'existe toujours ni `substidude.__main__`, ni interface, ni worker applicatif, ni export utilisateur.

Vérification finale 11D : **3 nouveaux tests réussis** ; suite complète `python -B -W error -m unittest discover -s tests -v` dans `.venv` et `.venv-check` : **85 tests exécutés dans chacun**, aucun ignoré, uniquement les **19 échecs de sous-cas des deux tests 11B différés**. Aucun nouvel échec constaté ; ne pas déclarer la suite globale verte. `pip check` réussi dans les trois environnements. Recette runtime sans PDFium et recette du paquet reconstruit après mise à jour des notices réussies ; `git diff --check` réussi. Fichiers de cette unité : `tests/windows_probe.py`, `tests/test_windows_probe.py`, `tests/fixtures.py`, `README.md`, `THIRD_PARTY_NOTICES.md`, `plan.md`. Aucun fichier moteur modifié, aucun nouveau commit/push.

Matrice consolidée de périmètre à ce point, **sans validation du jalon moteur** :

| Structure / risque | Reconnaissance et comportement courant | Contrôles / preuves | Limite restante |
| --- | --- | --- | --- |
| Natif simple | `classify_zone` ; retrait réel et remplacement texte accentué | Parcours expérimental, texte/géométrie/style, qpdf/PDFium ; banc natif tourné/recadré source et gelé | Moteur applicatif et réglages utilisateur absents |
| Scan, OCR, page mixte à zones distinctes | Une seule image/occurrence dans tout le PDF, gris/RGB 8 bits, axes positifs, 2 px/point | Pixels récupérables, texte OCR ciblé retiré sans texte fictif ajouté, rendu hors zone exact, ColorSpace conservé | Pas de qualification raster du paquet gelé ; autres transformations hors périmètre expérimental |
| Copies/réutilisations d'images, profils inconnus, masques et superpositions non maîtrisées | Refus existants maintenus, aucune propagation | Refus avant transformation, tests des variantes d'images et contrôles finaux | Pas de détection générale des copies transformées |
| Info/XMP, miniatures, anciennes révisions | Nettoyage/réécriture qualifiés sur corpus | Contrôles communs et inspections indépendantes existants | Pas de promesse PDF générale |
| Références cachées 11A, ActualText, couches, annotations/formulaires et autres structures refusées | Refus commun maintenu, avant transformation et en contrôle final selon corpus | Tests 11A/auxiliaires inchangés | Cas signé cryptographique synthétique ou recette manuelle toujours à compléter |
| Internes polices/CMap et propriétés 11B | Traitement différé, résidus possibles | Contre-exemples conservés, limite `spec.md:6.2.1` | Pas une suppression exhaustive, information préalable au partage à prévoir |
| Ressources et exécution | Quotas historiques ; flux/rendu bornés 11E ; banc `spawn`/`onedir` borné 11F | Mémoire native/Python ; 15 scénarios d'exécution fixes | Valider 11F ; corpus et intégration applicative restant à finaliser |

**Étape 11E — choix des budgets et gardes communes flux/rendu (19 octobre 2026), validation attendue :** après explication des plafonds, l'utilisateur délègue leur choix et demande de poursuivre. Valeurs centralisées dans `substidude/limits.py` et documentées en `spec.md:7.1`. Ce sont des points de départ prudents, pas une norme ni des seuils déduits des seules mesures. Première sous-unité implémentée : contrôle des flux et rendu ; **mémoire 2 Gio, durée 60 s et réponse IPC 64 Mio restent choisis mais non appliqués** dans le banc Windows, à traiter ensuite. Les quotas historiques ne sont pas modifiés et aucune recompression/dégradation d'image n'est introduite.

Tests de refus/frontières ajoutés avant le correctif : l'ancien moteur ne refusait pas les dépassements de flux (cinq échecs de sous-cas) et ne disposait pas de fonction de rendu bornée. Le contrôle commun `_check_stream_budgets` est maintenant appelé dans `_open_supported_structure` **avant** `parse_content_stream` et avant ouverture MuPDF : ouverture, classification, nettoyage et contrôle final du parcours le réutilisent. Tous les objets flux uniques sont comptés, y compris non affichés ou inutilisés. Flux sans filtre : longueur brute ; ASCIIHex : comptage des chiffres/espaces et dernier demi-octet ; Flate : décompression par blocs de sortie d'au plus 64 Kio, interruption dès le dépassement individuel ou cumulé, sans `read_bytes` qpdf matérialisant tout le flux. Les encodages non qualifiés sont refusés, pas devinés. JPEG : estimation des composantes décodées d'après les dimensions/espace, pas extraction des pixels pour ce contrôle. Les contrôles de structure/couleur et 11A restent ensuite obligatoires.

Les 32 Mio auxiliaires/128 Mio image/256 Mio cumulés sont inclusifs, par inspection du PDF, sans double comptage d'un flux partagé entre pages. Ce comptage ne borne pas les allocations de qpdf avant retour de son ouverture, notamment pour les objets compressés : il ne remplace pas le futur plafond du processus. Il n'est pas non plus une qualification interne des polices/CMap reportée en 11B.

`render_page` vérifie facteur fini/positif et rectangle entier du rendu avant `get_pixmap`, refuse au-delà de 16 000 000 pixels, produit du RGB sans alpha, sans réduire silencieusement l'échelle. Les expériences native/raster, la sonde de ressources et le banc Windows réutilisent cette fonction pour leurs rendus de prototype. Les lecteurs indépendants de qualification du corpus restent distincts ; aucune interface ni aperçu applicatif n'est ajouté.

`tests/test_resource_limits.py` : **8 tests réussis**, avec plafonds réduits sur petites fixtures — limites individuelles/cumulées exactes et +1, Flate/ASCIIHex/sans filtre, sortie Flate aux frontières de blocs et flux tronqué, ASCIIHex impair, budget JPEG/image distinct des polices, refus avant parseur/MuPDF sans mutation du source, contamination finale bloquée, rendu autorisé au plafond et refus avant allocation au-delà/facteur invalide. Aucun gros fichier ni grande image artificielle rendue.

Vérification complète après modification : **93 tests dans `.venv` et `.venv-check`**, chacun avec `-B -W error`, aucun ignoré ; uniquement les **19 échecs de sous-cas dans les deux tests 11B différés**. `pip check` réussi dans les trois environnements. Recette runtime sans PDFium réussie ; paquet `onedir` reconstruit avec les nouvelles gardes, ses 9 scénarios réussissent et PDFium reste absent. `git diff --check` réussi. Aucun ajout de dépendance, application, export utilisateur, commit ou push. Les modifications 11D antérieures sont préservées.

**Validation 11E :** l'utilisateur répond « Valider et continuer » ; les gardes flux/rendu sont acceptées sans commit et la qualification mémoire/durée/IPC du banc est autorisée.

**Étape 11F — budgets Windows mémoire/durée/IPC (19 octobre 2026), vérifiée et validée :** huit tests ajoutés dans `tests/test_windows_limits.py` ; les cinq premiers précèdent l'implémentation et constatent l'absence de cette API de budgets (cinq erreurs attendues avant correctif). Ajout de `tests/windows_memory.py`, extension du banc existant, sans module de worker applicatif ni dépendance externe. Le parent reste sans moteur PDF.

- **Mémoire native :** Job Object Windows anonyme, `JOB_OBJECT_LIMIT_PROCESS_MEMORY`, plafond de **2 147 483 648 octets**, appliqué et relu par `QueryInformationJobObject` dans l'enfant **avant les imports/ouvertures PDF**. La limite porte sur l'engagement du processus, pas seulement les allocations Python. Une impossibilité de créer/configurer/affecter le job fait échouer le travail : aucun mode de repli non borné. Le handle est fermé, sans `KILL_ON_JOB_CLOSE` dans ce job détenu par l'enfant ; la limite reste associée au processus jusqu'à sa sortie. Test de refus natif effectif avec un budget réduit de 64 Mio et une allocation supplémentaire de cette taille ; aucune tentative de consommation réelle de 2 Gio.
- **Durée :** origine `monotonic` enregistrée avant `Process.start`, plafond **60 s**. Un `Timer` du parent termine l'enfant à échéance même si `receive` n'est pas appelé. L'attente de réponse, le transfert et la fermeture normale après réponse utilisent la même échéance ; une réponse complète n'autorise pas un enfant à rester actif indéfiniment. Un thread de lecture IPC, sans appel PDF, permet au parent de rester maître du délai pendant une réception potentiellement bloquée. À l'arrêt : annulation/jonction du timer, terminaison/jonction du processus si nécessaire, fermeture du pipe et jonction du lecteur ; aucun résultat périmé ou arrivé après échéance accepté.
- **IPC :** une seule réponse et `Queue(maxsize=1)`, plafond de **67 108 864 octets**, enveloppe comprise. Protocole binaire fixe de **13 octets** (statut, révision 64 bits signée, PID) suivi des seuls octets du résultat ; plus de désérialisation `pickle` de réponse. Contrôle de longueur côté envoi avant concaténation et `recv_bytes(maxlength=...)` côté réception avant analyse de l'enveloppe. PID/révision vérifiés, diagnostics neutres construits dans le parent. Tests à 1 024 octets : borne exacte autorisée, +1 refusé à l'envoi, message surdimensionné injecté refusé à la réception. Les constructeurs d'essai autorisent uniquement des budgets réduits, jamais au-delà des constantes retenues.

**15 scénarios réussis dans chacun des modes source/runtime/gelé :** les 9 de 11D conservés, plus refus mémoire natif, borne IPC exacte, dépassement à l'envoi, dépassement injecté sur le transport, échéance après réponse complète et arrêt automatique sans collecte. Les essais réduisent mémoire/délai/IPC pour tester les refus, sans gros fichier ni attente réelle de 60 s. Huit tests unitaires de 11F couvrent également les budgets invalides, l'échec de configuration du Job Object avec fermeture du handle sans repli et l'échéance incluant l'attente avant collecte. Les 3 tests 11D restent réussis ; leur recette attend maintenant 15 scénarios.

Commandes complémentaires (la construction `onedir` reste celle documentée en 11D) :

```powershell
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -p 'test_windows*.py' -v
.\.venv-runtime\Scripts\python.exe -B -W error tests/windows_probe.py --self-test
.\dist\SubstiDudeProbe\SubstiDudeProbe.exe --self-test
```

Recettes runtime et `onedir` reconstruit réussies avec budgets affichés dans le JSON : 2 Gio / 60 s / 64 Mio, PDFium absent. Nouvelle recette gelée réussie après déplacement hors dépôt dans un chemin à espaces/accents avec `PATH` limité au dossier système et variables Python retirées ; copie temporaire nettoyée. Aucun test sur une machine réellement dépourvue de Python ni audit final de distribution revendiqué.

**Limites de la preuve :** budgets appliqués au banc de fixture native, pas automatiquement aux API `open_pdf`/`replace_zones` appelées directement dans le processus de tests. L'intégration du modèle à l'application appartient à la phase 2 ; le parcours raster/multi-zones gelé n'est pas qualifié. Le compteur commence avant le lancement, mais le timer est installé après le retour de l'appel système de création du processus ; cet appel système synchrone lui-même n'est pas préempté par le banc. Pas de garantie temps réel, de sandbox ni de qualification du crash brutal du parent (le watchdog vit dans celui-ci). Ces limites restent à prendre en compte dans le futur worker. Les choix conventionnels ne prouvent pas l'acceptation de tous les PDF à 40 MP/49 pages.

Vérification finale : **101 tests exécutés dans chacun de `.venv` et `.venv-check` avec `-B -W error`**, aucun ignoré ; uniquement les **19 échecs de sous-cas des deux tests 11B différés**. Les nouveaux tests passent ; la suite globale reste explicitement rouge pour ces contre-exemples, pas pour un nouveau défaut de ressources. `pip check` réussi dans les trois environnements, recettes source/runtime/gelée réussies, contrôle de patch sans erreur. `72bee42` reste le seul nouveau commit local, sans push ; aucun commit des travaux 11D/11E/11F. Aucun document client, export utilisateur ou interface ajoutés, jalon moteur non validé.

**Validation et publication locale demandées ensuite :** l'utilisateur choisit « Commit 11D–11F et terminer ». Cette demande autorise le commit commun des quinze fichiers modifiés/nouveaux de ces unités (gardes moteur et constantes, expériences/tests Windows/ressources et documentation), puis l'arrêt de l'unité. Elle n'autorise ni push ni démarrage de l'interface/phase 2. Les 19 échecs différés et les limites du banc ont été présentés avant cette validation. Identifier le commit effectif par `git log` ; ne pas confondre la fin de cette unité avec une validation du jalon moteur.

**Publication locale effectivement vérifiée :** commit **`15228f2`** — `test: enforce PDF resource budgets and qualify bounded Windows execution`, quinze fichiers inclus. Après commit, répertoire propre et `main` en avance de deux commits (`72bee42`, `15228f2`) sur `origin/main`, sans push. La préparation de reprise suivante ne modifie que `plan.md`, sans nouveau test exécuté ni autorisation de publication supplémentaire.

### Consigne prête à copier dans une nouvelle session

**Actualisation après validation :** le bilan 11G a été accepté par « Commit et terminer ». La consigne suivante prépare une reprise en phase 2 sur demande, sans autoriser de publication.

> Lis intégralement `spec.md` et `plan.md`, notamment la décision finale et le bilan 11G en section 13. L'utilisateur a validé explicitement le jalon phase 1 dans le périmètre révisé en choisissant « Commit et terminer ». Vérifie Git et le commit local de clôture (`test: close phase 1 qualification with signed PDF and color checks`), après `72bee42` et `15228f2`, sans supposer de push ; préserve tout travail ultérieur. La phase 2 n'a pas commencé : reprends son moteur applicatif pas à pas depuis `tests/test_pipeline.py`, sans refaire 11G ni créer d'interface complète. Référence : 102 tests par environnement avec `-B -W error`, aucun ignoré, uniquement les 19 sous-cas connus de deux tests 11B différés ; trois `pip check` et 15 scénarios runtime réussis. Recette CMS synthétique exécutée avec OpenSSL local dans les deux environnements, source intacte, cinq voies refusées. Un manque du contrôle final couleur a été reproduit puis corrigé, avec test conservé. Réutilise la matrice et les postconditions consolidées. Conserve les refus 11A, l'image/occurrence raster unique, plusieurs zones possibles et les espaces couleur. Flux 32/128/256 Mio et rendu 16 MP sont bornés au point commun ; 2 Gio/60 s/64 Mio seulement dans le banc natif spawn/onedir, à intégrer au moteur applicatif de phase 2. Python 3.13.0 64 bits sur synthétique seulement ; aucun document client, reprise de 11B, campagne ressources/Windows ou extension des formats refusés. Aucun audit final de paquet/poste sans Python comme nouveau préalable. Aucun nouveau commit/push sans demande explicite.

### Consigne utilisée au démarrage de 11G — historique

> Lis intégralement `spec.md` et `plan.md`, surtout l'état de reprise et l'unité 11G en section 13. Reprends la clôture ciblée de la phase 1 après 11F, pas la phase 0. `origin/main` était sur `15c0cdf` ; `72bee42` et `15228f2` sont committés localement sans push (écart 0/2). Vérifie Git et préserve cette mise à jour documentaire de `plan.md` ainsi que tout travail ultérieur. Python 3.13.0 64 bits est autorisé sur documents synthétiques seulement. Réexécute les 101 tests dans `.venv` et `.venv-check` avec `-B -W error`, aucun ignoré, les trois `pip check` et la recette runtime à 15 scénarios. Seuls les 19 sous-cas de deux tests de `test_hidden_contents.py` échouent dans la référence connue : 11B est reportée, ne pas la reprendre, supprimer ses tests ou ajouter des skip/expectedFailure pour obtenir du vert. Investiguer toute autre régression. Réalise 11G : rattacher les preuves existantes aux cases ouvertes de 1A–1C, compléter le cas signé synthétique ou une vérification manuelle documentée, consolider la matrice V1 et les postconditions systématiques, puis présenter le bilan pour validation explicite du jalon avant phase 2. Ne pas refaire les campagnes ressources/Windows ni étendre les formats refusés. Les budgets de `spec.md:7.1` sont choisis et qualifiés : flux 32/128/256 Mio, rendu 16 MP ; processus 2 Gio/60 s/64 Mio dans le banc natif spawn/onedir uniquement, pas sur les appels directs hors du banc. Leur intégration au moteur applicatif appartient à la phase 2 ; pas d'interface complète maintenant. Conserver les contrôles 11A, une seule image/occurrence raster dans tout le PDF, plusieurs zones possibles, les espaces couleur et refus multi-images/profils inconnus. Aucun audit final du paquet ou poste sans Python n'est un nouveau préalable à la phase 2. Jalon moteur encore non validé, aucun document client, aucun nouveau commit/push sans demande explicite ; mettre à jour le suivi sans données confidentielles.
