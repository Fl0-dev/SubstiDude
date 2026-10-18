# SubstiDude — Plan de développement de la V1

## 1. Mode d'emploi pour la session d'implémentation

1. Lire intégralement `spec.md`, puis ce document, et examiner l'état Git avant toute modification.
2. Suivre les phases dans l'ordre. Cocher une tâche uniquement après vérification de son résultat.
3. À chaque phase, noter ici les tests exécutés, résultats, limites et décisions utiles à la reprise. Ne pas enregistrer de données clients.
4. Ne pas affaiblir une exigence de suppression pour obtenir un export : refuser explicitement le cas non maîtrisé.
5. Si le prototype invalide le choix du moteur ou impose de réduire le périmètre, expliquer le blocage et demander une décision avant de poursuivre l'interface.
6. `spec.md` fait référence pour les exigences ; ce plan organise leur réalisation, avec les arbitrages utilisateur consignés ci-dessous. Les références A1 à A14, y compris A4b, désignent ses critères d'acceptation.
7. Ne pas créer d'infrastructure anticipée : ni serveur, ni base de données, ni plugins, ni abstraction de moteur interchangeable.
8. Commit et push uniquement sur demande explicite de l'utilisateur ; messages au format Conventional Commits.

**État initial attendu :** dépôt contenant les spécifications et ce plan, sans application implémentée. Vérifier l'état réel au démarrage plutôt que supposer qu'il est inchangé.

### Arbitrages utilisateur applicables

- **Entrées :** accepter uniquement les fichiers de taille strictement positive et strictement inférieure à 10 Mo (10 000 000 octets), contenant de 1 à 49 pages. Refuser notamment les fichiers de 0 octet, ceux de 10 Mo ou plus et les PDF de 0 ou d'au moins 50 pages.
- **Temporaires :** conserver le traitement en mémoire autant que possible ; les temporaires d'export restent dans le dossier de destination. L'usage prévu est un dossier local non synchronisé. Cet arbitrage déroge à l'obligation de répertoire local dédié de `spec.md:6.3` ; il ne supprime pas les exigences de droits adaptés, de noms neutres et de nettoyage. Aucun mécanisme de détection de synchronisation n'est demandé.
- **Périmètre PDF :** définir une liste positive de structures reconnues et traitables ; aucune promesse de support PDF général ni de détection de toutes les copies visuellement similaires d'une image. Si cette frontière ne permet pas de respecter les garanties de suppression de la spec, demander un arbitrage avant de poursuivre.

## 2. Cible technique retenue pour ce plan

| Élément | Choix |
| --- | --- |
| Plateforme | Windows 64 bits, application de bureau locale en français |
| Langage | Python, version stable compatible avec toutes les dépendances retenues |
| Interface | PySide6, Qt Widgets, `QGraphicsView` / `QGraphicsScene` |
| PDF | PyMuPDF, sous option AGPL, à valider en phase 1 |
| Images et texte raster | Pillow, avec une police redistribuable embarquée |
| Tests | `unittest` et corpus synthétique local |
| Distribution | PyInstaller en mode dossier (`onedir`), pas `onefile` |
| Licence du projet | `AGPL-3.0-only` |

Cette cible suit la recommandation discutée. Le moteur reste conditionné au prototype. Vérifier les API et licences des versions effectivement installées ; ne pas copier des options de caviardisation supposées ou obsolètes.

Épingler les versions testées pour l'exécution et la construction. Aucune dépendance HTTP, télémétrie, OCR ou IA n'est nécessaire. Les outils d'inspection indépendants sont des outils de développement, pas des dépendances obligatoires de l'application livrée.

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

- [ ] Vérifier Python disponible et choisir une version supportée par les roues Windows des dépendances.
- [ ] Créer un environnement `.venv` et les fichiers de dépendances avec versions exactes testées.
- [ ] Ajouter `.gitignore` : environnement, caches, construction, sorties de tests et documents de travail. Les seuls PDF versionnés éventuels doivent être synthétiques et explicitement identifiés.
- [ ] Ajouter le texte officiel intégral AGPLv3 dans `LICENSE` et les premières instructions du README.
- [ ] Confirmer le titulaire réel du copyright auprès de l'utilisateur avant publication ; ne pas inventer son identité depuis son pseudonyme GitHub.
- [ ] Choisir une police libre autorisant redistribution et intégration PDF, puis inclure ses mentions.
- [ ] Initialiser l'inventaire des licences, y compris Qt, MuPDF et bibliothèques transitives réellement embarquées.

### Vérification / sortie

Installation reproductible dans un environnement neuf ; imports des composants réussis. Consigner les versions choisies et les éventuelles questions de licence. La mention SPDX doit figurer dans les nouveaux fichiers source propres au projet.

## 6. Phase 1 — Prototype PDF et décision de faisabilité

**Aucune interface complète avant validation de cette phase.** Commencer avec les dépendances moteur et tests ; installer l'interface lorsque nécessaire.

### 1A. Corpus synthétique

- [ ] Générer un PDF natif, un scan sans OCR et un scan avec texte OCR invisible, avec marqueurs distincts et données fictives ; ajouter une page mixte avec zones natives et scannées distinctes, dont le traitement doit être accepté.
- [ ] Ajouter des cas multipages, rotations 0/90/180/270°, CropBox décalée et dimensions différentes.
- [ ] Ajouter une image partagée entre pages, une copie d'image distincte avec les mêmes pixels, transparence/masque et contenu vectoriel traversant une zone.
- [ ] Ajouter deux zones disjointes touchant un même objet textuel, vectoriel ou image ; vérifier un traitement cohérent ou un refus explicite, sans modification silencieuse hors des effets annoncés dans l'aperçu.
- [ ] Ajouter une image réencodée et une image recadrée ou redimensionnée pour documenter la frontière de détection des copies, sans créer de système de reconnaissance visuelle générale.
- [ ] Ajouter métadonnées/XMP, annotation, formulaire, pièce jointe, action/lien, `ActualText`, couches optionnelles et révisions incrémentales.
- [ ] Ajouter fichiers invalides et chiffrés ; préparer un cas signé synthétique ou une vérification manuelle documentée si sa génération nécessite un outil supplémentaire.
- [ ] Définir pour chaque cas le résultat attendu et le critère permettant de le reconnaître : support ou refus motivé. Les trois types principaux et au moins une page mixte doivent être supportés pour valider la V1.
- [ ] Tester les frontières d'entrée : 0, 1, 9 999 999 et 10 000 000 octets pour le contrôle de taille ; 0, 1, 49 et 50 pages pour le contrôle du nombre de pages. Une taille admissible ne dispense pas de vérifier la validité du PDF.

### 1B. Expériences moteur

- [ ] Définir la liste positive initiale : texte natif sans superposition ambiguë, scan simple à transformation maîtrisée, même scan avec couche OCR identifiable et page mixte à zones distinctes. Démontrer les critères de reconnaissance, l'inspection des objets visibles/invisibles et les transformations de coordonnées ; tester aussi les refus sur des cas proches mais hors périmètre.
- [ ] Contrôler la taille avant lecture complète et le nombre de pages après ouverture, avant rendu ou transformation. Dès le prototype, fixer des plafonds conservateurs de pixels décodés et de rendu ; les limites de poids et de pages ne protègent pas à elles seules contre une décompression excessive. Tester une image démesurée et un refus maîtrisé.
- [ ] Tester suppression réelle du texte natif puis insertion d'un remplacement accentué extractible.
- [ ] Tester remplacement dans une image : modifier ses pixels à la résolution d'origine et réencoder sans perte supplémentaire, sans rasteriser la page.
- [ ] Vérifier la correspondance point PDF → pixel image, y compris rotation et transformations. Refuser dans la V1 les transformations non maîtrisées plutôt que déformer le scan.
- [ ] Retirer le texte OCR ciblé sans supprimer celui hors zone et sans ajouter de texte extractible pour le remplacement raster.
- [ ] Valider l'identification d'un même objet image réutilisé, y compris via objets imbriqués, et de copies distinctes aux pixels décodés identiques. Définir les formats, masques et transformations couverts ; ne pas limiter l'analyse au seul numéro d'objet. Documenter explicitement les copies réencodées avec pixels différents, recadrées ou redimensionnées non détectées. Si ces limites compromettent les garanties de `spec.md:5`, bloquer le jalon et demander un arbitrage, sans annoncer de détection générale.
- [ ] Tester nettoyage des contenus auxiliaires et réécriture complète avec suppression des objets inutilisés. Une option de sauvegarde ne vaut pas preuve de nettoyage.
- [ ] Vérifier que l'aplatissement éventuel de champs/annotations visibles précède leur suppression et ne réintroduit pas les données retirées ; sinon refuser ces cas.

### 1C. Inspection indépendante et jalon

- [ ] Choisir un outil indépendant du moteur : par exemple Poppler pour rendu/extraction, et qpdf pour inspection structurelle si nécessaire. Vérifier disponibilité et licences ; ne pas les embarquer par défaut.
- [ ] Examiner texte, images récupérables, structures auxiliaires et anciennes révisions, pas seulement le rendu ou une recherche brute dans les octets.
- [ ] Comparer les rendus hors zones, les dimensions d'images, le texte conservé et l'intégrité du source.
- [ ] Ajouter dans ce plan une matrice « structure / critère de reconnaissance / support ou refus / contrôle automatique à chaque génération / preuve sur corpus » et les limites exactes du prototype.
- [ ] Séparer les contrôles : réouverture pour la lisibilité, contrôles techniques exécutés sur chaque résultat, inspection indépendante pour la qualification du corpus. Définir pour chaque structure acceptée les postconditions testables : retrait des contenus ciblés dans leurs représentations concernées, remplacement sous la forme attendue, nettoyage auxiliaire et conservation hors zones selon les limites documentées. Un contrôle requis absent ou en échec interdit la confirmation et l'export ; la recette du corpus ne constitue pas une preuve exhaustive sur tout PDF utilisateur.

### 1D. Exécution et test précoce Windows

- [ ] Décider avant le lecteur où s'exécutent ouverture, inspection, rendu et transformation, et qui possède les objets PDF. Les tâches longues doivent rester hors du fil graphique ; ne pas utiliser PyMuPDF concurremment depuis des threads Qt. Si nécessaire, retenir un processus dédié via `multiprocessing` et `spawn`, sans partager les objets PDF, avec un seul travail PDF actif et sans pool généraliste.
- [ ] Tester erreurs, durée excessive et arrêt du traitement avec le modèle retenu ; borner les données en attente. Un processus séparé ne constitue pas un bac à sable de sécurité.
- [ ] Construire un exécutable minimal PyInstaller `onedir` et vérifier ouverture, rendu et transformation. Si un processus dédié est retenu, tester son lancement et son arrêt dans l'exécutable gelé (`freeze_support` et point d'entrée protégé si requis). Consigner la commande ; ne pas attendre la distribution finale pour cette vérification.

**Passage à la phase 2 :** natif, scan, scan+OCR et page mixte du périmètre positif fonctionnent ; reconnaissance des structures acceptées et refus proches démontrés ; risques de résidus connus traités ou bloqués par un contrôle explicite. Les contrôles par résultat, limites initiales et modèle d'exécution sont définis, et le test Windows minimal réussit. Une inspection incomplète ne permet pas d'annoncer un support général. Si un cas impossible à détecter compromet les garanties, arrêter et soumettre une révision technique à l'utilisateur.

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
| 0 — Préparation | À faire | — | Confirmer copyright avant publication |
| 1 — Prototype PDF | À faire | — | Jalon bloquant avant interface complète |
| 2 — Moteur et session | À faire | — | — |
| 3 — Lecteur et zones | À faire | — | — |
| 4 — Aperçu et validation | À faire | — | — |
| 5 — Export et confidentialité | À faire | — | — |
| 6 — Qualification | À faire | — | — |
| 7 — Distribution | À faire | — | — |

### Instruction de lancement pour la prochaine session

> Lis `spec.md` et `plan.md`, examine le dépôt, puis commence par la phase 0 et le prototype de la phase 1. Implémente et teste progressivement. Ne développe pas l'interface complète avant validation du moteur. Refuse explicitement les traitements non sûrs et signale tout blocage nécessitant une décision. Mets à jour le suivi de reprise sans inclure de données confidentielles. Ne commit et ne pousse que sur demande.
