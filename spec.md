# SubstiDude — Spécifications fonctionnelles et contraintes techniques

## 1. Objet du document

Ce document sert de base à la planification du développement. Il décrit le besoin, le périmètre initial, les exigences de confidentialité et les critères d'acceptation. Il ne constitue ni une certification de sécurité ni un choix définitif d'architecture.

**Nom :** SubstiDude.  
**Signature proposée :** « Les mêmes documents. D'autres identités. »  
**Plateforme initiale :** poste Windows, utilisation locale.  
**Langue initiale :** français.

## 2. Problème à résoudre

L'utilisateur développe et débogue des applications d'OCR et des traitements utilisant des LLM. Il travaille sur des documents clients : PDF natifs, tickets de caisse, factures et contrats scannés, avec ou sans couche OCR.

Avant de transmettre une copie à une application ou à un service externe, il veut remplacer rapidement les informations confidentielles par des données fictives telles que « Toto » ou « John Doe ».

L'outil doit supprimer réellement les informations ciblées, et non simplement les masquer à l'affichage. Il doit préserver autant que possible le document utile au débogage.

## 3. Objectifs et limites

### Objectifs

- Lire un PDF et naviguer dans ses pages.
- Sélectionner visuellement une zone et remplacer son contenu par un texte fictif.
- Utiliser le même parcours sur les PDF natifs, scannés et mixtes.
- Traiter les documents sans transfert réseau.
- Produire une nouvelle copie nettoyée, sans modifier l'original.
- Réduire les manipulations répétitives sans dépendre d'une détection automatique.

### Limites à rendre explicites

- La sélection manuelle ne garantit pas que toutes les données identifiantes ont été repérées.
- Le remplacement des noms ne constitue pas nécessairement une anonymisation au sens juridique : le contexte peut permettre une réidentification.
- L'outil contribue aux mesures de confidentialité, mais ne garantit ni conformité réglementaire ni maintien d'une certification ISO 27001.
- Toute réécriture peut modifier la structure interne du PDF et faire disparaître un bug. L'identité binaire et la préservation de tous les comportements OCR ne sont pas garanties.
- Aucun export de cette première version ne doit être présenté comme automatiquement « certifié anonyme ».

## 4. Périmètre de la première version

### 4.1. Ouverture et lecture

- Ouvrir un PDF depuis le disque via un sélecteur de fichier.
- Afficher les pages, leur numéro et le nombre total de pages.
- Naviguer entre les pages ; zoomer ; ajuster la page à la fenêtre.
- Prendre en compte les rotations et les dimensions propres à chaque page.
- Afficher une erreur compréhensible en cas de fichier invalide ou non pris en charge.
- Ne pas exécuter les scripts ou actions intégrés au PDF ni ouvrir automatiquement des liens externes.

### 4.2. Sélection et substitution

- Dessiner une zone rectangulaire sur une page avec la souris.
- Déplacer, redimensionner ou supprimer une zone avant l'export.
- Associer à chaque zone un texte de remplacement, éventuellement vide pour un effacement simple.
- Proposer quelques valeurs fixes : « Toto », « John Doe », « Société Exemple », une adresse fictive et du texte libre.
- Permettre plusieurs substitutions par page et dans plusieurs pages du document.
- Réutiliser facilement le dernier texte saisi pendant la session.
- Utiliser un fond opaque et une police locale intégrée ou embarquée à l'export, avec prise en charge des accents français.
- Permettre un réglage simple de la taille du texte et de la couleur du fond pour les scans non blancs.
- Ne jamais tronquer silencieusement un remplacement : signaler qu'il ne tient pas et demander une correction avant l'export.
- Ne pas reformater les paragraphes ou déplacer le reste de la page.
- Autoriser le retour sur les substitutions avant l'export ; ne pas modifier le fichier source pendant l'édition.

La sélection doit englober toute l'information à retirer. Si un caractère ou un élément graphique traverse la limite, la suppression peut dépasser légèrement la zone ; ce comportement doit être documenté et visible dans l'aperçu.

### 4.3. Aperçu et contrôle utilisateur

- Distinguer clairement les zones d'édition du résultat final.
- Fournir un aperçu issu du PDF réellement transformé, et pas uniquement de rectangles superposés sur l'original.
- Présenter une liste des substitutions avec leur page et leur texte fictif.
- Permettre de revenir directement à une zone depuis cette liste.
- Avant l'enregistrement final, inviter l'utilisateur à contrôler toutes les pages et les identifiants indirects : signatures, photos, QR codes, codes-barres, coordonnées, références et numéros uniques.
- Ne pas présenter cette confirmation comme une preuve d'anonymisation exhaustive.

### 4.4. Export

- Enregistrer dans un nouveau fichier choisi par l'utilisateur ; refuser le chemin du document source.
- Proposer un nom neutre tel que `substidude-export.pdf`, sans recopier automatiquement un nom client présent dans le nom source.
- Demander confirmation avant de remplacer un fichier de destination existant.
- Appliquer les substitutions par suppression effective, puis insertion du contenu fictif.
- Réécrire le PDF intégralement, sans sauvegarde incrémentale conservant les anciennes versions d'objets.
- Éliminer les objets devenus inutilisés et les contenus auxiliaires décrits en section 6.
- Préserver autant que possible le nombre, l'ordre, les dimensions et la rotation des pages.
- Ne pas rasteriser systématiquement le document entier.
- Vérifier que le résultat se rouvre correctement avant de confirmer la réussite.
- Utiliser une écriture temporaire puis une finalisation sûre pour ne pas laisser un fichier final partiel en cas d'erreur. Préserver une destination existante si l'export échoue.

## 5. Traitement selon la nature du contenu

### PDF natif

Supprimer les objets textuels concernés avant d'ajouter le remplacement. Un fond opaque ou une annotation visuelle ne constitue pas une suppression.

### Page scannée

Supprimer ou remplacer réellement les pixels sensibles dans les images exportées. Il ne doit pas rester une image d'origine récupérable contenant les pixels effacés, même si une autre image ou un rectangle la recouvre.

### PDF avec couche OCR ou contenu mixte

Traiter ensemble les pixels visibles, le texte invisible et les autres objets concernés. Une même zone peut contenir du texte natif, des images et des éléments vectoriels.

### Exigences communes

- Gérer les images réutilisées entre plusieurs pages sans laisser leur version sensible récupérable dans le fichier final.
- Prendre en compte les masques, transparences, objets vectoriels et contenus masqués associés aux zones ciblées.
- Ne pas se limiter à rechercher une chaîne dans les octets du fichier : compression, encodage et images rendent cette vérification insuffisante.
- Si le moteur ne sait pas traiter sûrement un contenu, bloquer l'export avec une explication ; ne pas remplacer silencieusement la suppression par un masque visuel.
- La première version ne lance pas d'OCR : la sélection manuelle fonctionne sans reconnaissance de texte.

## 6. Nettoyage et confidentialité

### 6.1. Fonctionnement local

- Aucun envoi de document, extrait, image, texte ou nom de fichier à un service externe.
- Aucune télémétrie, publicité, police distante, ressource CDN ou vérification de mise à jour automatique pendant l'utilisation.
- Une fois installée, l'application fonctionne sans connexion Internet.
- Les téléchargements nécessaires à l'installation doivent être distingués du fonctionnement hors ligne.
- Aucune clé d'API ni aucun compte requis.
- Si une interface web locale est retenue, limiter le service à la boucle locale et protéger les routes contre les appels non autorisés depuis d'autres sites. Ne pas exposer le traitement sur le réseau local.

### 6.2. Contenu auxiliaire du PDF exporté

Par défaut, supprimer les métadonnées documentaires et XMP, commentaires, annotations, pièces jointes, champs de formulaire et leurs valeurs, scripts, actions, liens et miniatures intégrées. Les identifiants techniques du document doivent être régénérés ou retirés lorsque le format le permet.

Traiter également les couches optionnelles et les structures susceptibles de conserver du texte sensible, notamment les textes alternatifs, `ActualText` et structures d'accessibilité. Si leur nettoyage fiable n'est pas pris en charge, bloquer ce type d'export. Prévenir que le nettoyage peut retirer des fonctions interactives ou d'accessibilité du document.

Les contenus visibles nécessaires doivent être intégrés au rendu avant suppression de leur conteneur si cela est supporté de manière sûre ; sinon, refuser le document avec un motif explicite plutôt que perdre du contenu sans avertissement.

### 6.3. Données locales et erreurs

- Pas de base de données ni de copie persistante automatique des documents.
- Garder les opérations d'édition en mémoire pendant la session ; pas d'historique contenant les anciennes données dans le PDF final.
- Si des fichiers temporaires sont nécessaires, les placer dans un répertoire local dédié avec des droits limités à l'utilisateur et les nettoyer à la fermeture et après erreur.
- Prévoir le nettoyage des temporaires abandonnés après un arrêt brutal au démarrage suivant.
- Ne pas journaliser le contenu des documents, les données remplacées ou les chemins complets sensibles.
- Ne pas transmettre automatiquement les erreurs ou rapports de plantage.
- Ne pas promettre d'effacement forensique : fichiers source, sauvegardes, synchronisation de dossiers, mémoire virtuelle et stockage du système restent sous la responsabilité de l'environnement d'exécution.

## 7. Cas particuliers et limites initiales

- **PDF chiffré :** refus explicite dans la première version ; prise en charge par mot de passe à étudier ultérieurement. Aucun contournement de protection.
- **PDF signé :** avertir que la modification invalide la signature ; aucune promesse de conservation de sa validité. Refuser l'export si le nettoyage requis n'est pas maîtrisé.
- **PDF malformé ou fonctionnalité non supportée :** message clair, aucune sortie annoncée comme sûre.
- **Documents volumineux :** ne rendre que les pages nécessaires ; prévoir des limites de ressources et des erreurs maîtrisées. Les seuils chiffrés seront fixés après un prototype sur des fichiers représentatifs non confidentiels.
- **Sélections chevauchantes :** détecter le chevauchement et demander une correction avant export pour éviter qu'un remplacement efface un autre remplacement.
- **Sélection hors page ou de taille nulle :** empêcher sa validation.
- **Fermeture avec modifications non exportées :** demander confirmation avant de perdre le travail.

## 8. Ergonomie et accessibilité de l'application

- Parcours principal court : ouvrir → sélectionner → remplacer → vérifier → exporter.
- Interface centrée sur la page, sans fonctions générales d'édition PDF inutiles.
- Contrôles nommés, contraste suffisant, focus visible et navigation clavier pour les commandes principales.
- La couleur seule ne doit pas porter un état ou une erreur.
- Afficher les traitements en cours et empêcher les actions concurrentes pouvant altérer l'export.
- Fournir des messages d'erreur exploitables sans exposer de données confidentielles.

## 9. Hors périmètre initial

- Détection automatique de données personnelles, modèles IA ou LLM locaux.
- OCR intégré et reconstruction automatique de la mise en page.
- Recherche globale et remplacement automatique de toutes les occurrences.
- Traitement par lots, modèles de zones et réapplication automatique à plusieurs pages.
- Édition PDF généraliste, fusion, signature, conversion bureautique et réorganisation des pages.
- Collaboration, comptes utilisateurs, serveur partagé et stockage cloud.
- Sauvegarde de projets contenant les originaux ou les correspondances entre identités réelles et fictives.
- Génération de fausses identités réalistes ou préservation automatique de la cohérence entre montants, dates et totaux.

Ces fonctions ne seront ajoutées que si l'usage réel les justifie. Pour un test OCR nécessitant des données cohérentes, l'utilisateur choisit les valeurs de remplacement.

## 10. Orientation technique à valider

- Privilégier une application mono-utilisateur et un moteur PDF existant plutôt qu'un traitement maison du format.
- **Candidat : Python et PyMuPDF** pour le rendu, les coordonnées et la caviardisation, sous réserve d'un prototype validant la suppression réelle sur les différents contenus.
- Examiner la licence AGPL/commerciale de PyMuPDF avant de fixer le mode de distribution.
- Choisir pendant la planification entre interface de bureau et interface web strictement locale ; aucune infrastructure Laragon, base de données ou dépendance cloud n'est requise par le besoin.
- Utiliser le même moteur de transformation pour l'aperçu final et l'export afin d'éviter deux comportements divergents.
- Valider tôt la correspondance entre coordonnées écran et coordonnées PDF : zoom, rotation, recadrage, origine et dimensions de page.
- Ne promettre ni PDF/A, ni maintien de signature, ni reproduction exacte des polices d'origine.
- Maintenir les dépendances manipulant des PDF à jour : les fichiers ouverts sont des entrées non fiables.

## 11. Critères d'acceptation

Les essais utilisent exclusivement des documents synthétiques ou autorisés, avec des marqueurs sensibles connus. Aucun document client ne doit être ajouté au dépôt.

| Référence | Scénario | Résultat attendu |
| --- | --- | --- |
| A1 | Ouvrir un PDF natif multipage | Pages lisibles, navigation et zoom fonctionnels. |
| A2 | Remplacer un nom natif par « John Doe » | Le remplacement est visible ; l'ancien nom ciblé n'est plus extractible. |
| A3 | Remplacer une donnée dans un scan | Les pixels sensibles ont disparu des images récupérables du PDF exporté. |
| A4 | Remplacer une donnée sur un scan avec couche OCR | Ni les pixels ni le texte OCR ciblés ne subsistent. |
| A5 | Tester rotation, recadrage et plusieurs niveaux de zoom | La suppression correspond à la zone sélectionnée. |
| A6 | Traiter plusieurs pages et une image réutilisée | Aucun objet sensible résiduel provenant des zones traitées n'est récupérable. |
| A7 | Exporter un PDF contenant métadonnées et contenus auxiliaires | Les informations auxiliaires sont supprimées selon la section 6, ou l'export est explicitement refusé. |
| A8 | Contrôler une zone non modifiée | Pas de changement visuel inattendu ; toute différence structurelle reste compatible avec les limites annoncées. |
| A9 | Simuler une erreur d'export | Original intact ; pas de destination finale partielle ; erreur compréhensible. |
| A10 | Utiliser l'outil sans réseau | Ouverture, édition, aperçu et export fonctionnent sans appel externe. |
| A11 | Saisir un texte trop long ou des zones chevauchantes | Aucun export trompeur : correction demandée. |
| A12 | Ouvrir un format ou un contenu non supporté | Refus clair, sans affirmation de suppression sûre. |

### Validation minimale à automatiser

Conserver un petit contrôle de non-régression exécutable couvrant au moins un PDF natif et un scan avec couche OCR. Il doit exporter, rouvrir le résultat et vérifier la disparition des marqueurs ciblés dans le texte et les images ainsi que la présence du remplacement.

Compléter ce contrôle par une inspection avec un outil indépendant du moteur de génération, incluant les objets inutilisés, contenus masqués et révisions antérieures. Une simple vérification visuelle, une recherche textuelle brute ou l'absence du nom dans un seul extracteur ne suffit pas à prouver la suppression.

## 12. Décisions à prendre pendant la planification

1. Mode de distribution : usage interne uniquement ou diffusion à d'autres utilisateurs ; conséquences sur les licences.
2. Interface de bureau ou navigateur local ; procédure d'installation et de lancement sous Windows.
3. Validation du moteur sur textes, images, vecteurs, couches et structures auxiliaires avant construction de l'interface complète.
4. Liste exacte des contenus supportés et des refus de sécurité de la première version.
5. Corpus synthétique de validation et outil indépendant d'inspection.
6. Limites de taille, de mémoire et de durée à partir de mesures sur le prototype.

## 13. Définition de terminé pour la première version

- Le parcours manuel complet fonctionne sur les PDF natifs, scannés et mixtes du corpus pris en charge.
- Les critères d'acceptation sont vérifiés et les refus de prise en charge sont documentés.
- L'installation et le lancement local sous Windows sont documentés.
- Les limites de confidentialité, les effets sur la structure PDF et le contrôle humain avant partage sont clairement indiqués.
- Aucun service externe, compte ou stockage persistant de documents n'est nécessaire au fonctionnement.
