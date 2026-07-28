# Synapse — Audit fonctionnel, reconnexion et évolution des algorithmes

> **Mise à jour — 28/07/2026 :** les éléments réalisés sont récapitulés en fin de document, sections 23 et 24.

## 1. Contexte

Une refonte graphique récente de Synapse a entraîné la disparition visuelle ou la déconnexion de certaines fonctions qui existaient auparavant.

L’objectif n’est donc **pas de tout recréer**, mais de demander à Codex de :

1. analyser complètement le code existant ;
2. identifier ce qui fonctionne encore en arrière-plan ;
3. retrouver les anciens composants, services, routes, modèles et algorithmes ;
4. reconnecter les fonctions perdues à la nouvelle interface ;
5. ne réécrire que ce qui est réellement absent, cassé ou devenu incompatible.

Synapse doit rester un système cohérent : les items, les QCM, les évaluations, les lacunes, Anki, Obsidian, le planning et Ollama doivent partager les mêmes données et les mêmes règles. Le but final est d'améliorer concrètement la préparation aux **EDN** et aux **ECOS**, et non d'accumuler des fonctionnalités isolées.

---

## 2. Principe général : auditer avant de développer

Avant toute modification importante, Codex doit produire une cartographie de l’existant.

### Éléments à rechercher

- pages et composants encore présents mais non utilisés ;
- routes ou boutons non reliés ;
- services métier existants ;
- anciens algorithmes de révision et de maîtrise ;
- modèles de données SQLite et migrations ;
- fonctions liées aux items, collèges, thèmes, OIC, QCM et lacunes ;
- intégrations déjà commencées avec Ollama, Obsidian, Anki ou le calendrier ;
- doublons créés pendant la refonte ;
- données affichées dans l’ancienne interface mais plus dans la nouvelle ;
- tests existants et comportements attendus.

### Livrable attendu avant reconstruction

Créer un document d’audit avec, pour chaque fonction :

| Fonction | État | Code existant | Interface actuelle | Action |
|---|---|---|---|---|
| Fonctionnelle et branchée | OK | Localisation | Vue concernée | Conserver |
| Fonctionnelle mais non branchée | Partiel | Localisation | Élément manquant | Reconnecter |
| Présente mais cassée | Cassé | Localisation | Erreur constatée | Corriger |
| Absente | Manquante | Aucun code fiable | Besoin identifié | Développer |

Aucune fonction importante ne doit être recréée avant d’avoir vérifié si une ancienne implémentation peut être récupérée.

---

## 3. Architecture fonctionnelle commune

Toutes les actions réalisées depuis le dashboard, le planning, la vue thème, la vue collège ou la vue item doivent appeler les **mêmes services métier**.

Exemple : terminer un item depuis le dashboard ou depuis sa fiche doit déclencher exactement le même workflow, enregistrer les mêmes données et mettre à jour toutes les vues.

### Source de vérité commune

Les modules doivent s’appuyer sur des entités partagées :

- `Item`
- `College`
- `Theme`
- `OIC`
- `ReviewTask`
- `Evaluation`
- `QCMSession`
- `QuestionResult`
- `KnowledgeGap`
- `AnkiReview`
- `VacationPeriod`
- `StudyPlanEvent`

Chaque action importante doit générer un événement métier, par exemple :

- `item_completed`
- `self_evaluation_recorded`
- `qcm_session_completed`
- `repeated_error_detected`
- `knowledge_gap_created`
- `review_scheduled`
- `vacation_period_started`
- `obsidian_note_requested`

Cela permettra de garder toutes les vues synchronisées et d’éviter que chaque page possède sa propre logique.

---

## 4. Workflow de fin de travail d’un item et auto-évaluation existante

La fonction d’**auto-évaluation existait avant la refonte graphique**. Elle ne doit pas être recréée sans audit préalable.

Codex doit d’abord :

- retrouver son ancien composant et son service métier ;
- identifier les données qu’elle enregistrait ;
- vérifier si l’algorithme associé fonctionne encore ;
- comprendre depuis quelles vues elle était appelée ;
- repérer ce qui a été perdu ou débranché pendant la refonte.

Ensuite, il faudra réfléchir à la manière de la rendre plus efficace, plus rapide à utiliser et plus pertinente pour l’apprentissage. L’objectif est de maximiser son potentiel sans transformer chaque fin de session en formulaire trop long.

### Point d’entrée souhaité

Lorsqu’un item est marqué comme terminé depuis le dashboard, le planning, la vue thème ou la fiche item, Synapse pourrait ouvrir un **wizard de fin de travail** fondé sur l’ancienne auto-évaluation reconnectée et améliorée.

Le contenu exact du wizard devra être discuté après analyse de l’existant. Il pourrait notamment intégrer :

1. la confirmation du travail effectué ;
2. une auto-évaluation courte ;
3. la capacité à restituer sans support ;
4. les résultats récents aux QCM ou autres évaluations ;
5. les erreurs et lacunes connues ;
6. une proposition de prochaine étape ;
7. une proposition de calendrier de révision.

### Questions à explorer

- Quels champs de l’ancienne auto-évaluation étaient réellement utiles ?
- Lesquels étaient redondants ou trop subjectifs ?
- Peut-on adapter le nombre de questions selon le type de travail réalisé ?
- Peut-on proposer une évaluation très courte par défaut et un mode approfondi facultatif ?
- Comment croiser l’auto-évaluation avec des données plus objectives sans alourdir le workflow ?
- Comment éviter qu’un utilisateur se surévalue ou se sous-évalue de manière répétée ?
- Comment utiliser l’historique pour améliorer progressivement les recommandations ?

### Suite de révision

Le planning peut conserver une base de type :

`J1 → J3 → J7 → J14 → J30`

Mais cette séquence ne doit pas être figée. Elle pourrait être raccourcie, maintenue, espacée ou réactivée selon les résultats. Les règles exactes dépendront de la réflexion sur l’algorithme de maîtrise et devront être validées avant implémentation.

---

## 5. Repenser l’algorithme de maîtrise avec une phase de réflexion dédiée

La refonte de l’algorithme de maîtrise est un chantier central qui nécessite une **réflexion approfondie avant toute modification du code**.

Il ne faut pas imposer immédiatement une formule, des coefficients ou un score définitif. Codex doit d’abord retrouver et documenter l’algorithme actuel ou ancien :

- variables utilisées ;
- règles de changement de statut ;
- données réellement disponibles ;
- comportements inattendus ;
- limites rencontrées ;
- éventuelles fonctions devenues inutilisées après la refonte.

### Travail de conception à mener

Une discussion spécifique devra ensuite être menée avec Hugo, avec l’aide de ChatGPT, pour comparer plusieurs modèles possibles. ChatGPT pourra proposer des pistes, leurs avantages, leurs limites et les risques de biais, mais **aucun modèle ne devra être implémenté avant validation commune**.

Les signaux à étudier pourraient comprendre :

- auto-évaluation ;
- résultats aux QCM ;
- résultats aux DP et KFP ;
- couverture des OIC de rang A et B ;
- fréquence et gravité des erreurs répétées ;
- révisions Anki ;
- restitution sans support ;
- stabilité des performances dans le temps ;
- ancienneté de la dernière validation ;
- contexte de stage, de cours ou d’échéance EDN ;
- distinction entre savoir théorique et capacité de raisonnement clinique.

### Questions structurantes

- Faut-il un score unique, plusieurs dimensions ou uniquement des statuts interprétables ?
- Comment pondérer les données subjectives et objectives ?
- Comment gérer un item réussi en QCM mais mal restitué oralement ?
- Comment différencier mémorisation récente et maîtrise durable ?
- Comment éviter qu’un gros volume de QCM masque des lacunes sur certains OIC ?
- Comment intégrer l’incertitude lorsque peu de données sont disponibles ?
- Comment adapter la maîtrise aux exigences différentes des EDN et des ECOS ?
- Faut-il calculer séparément une maîtrise théorique, une maîtrise clinique et une maîtrise globale ?

### Résultat attendu de cette phase

Avant le développement, produire une note de décision comprenant :

- plusieurs modèles candidats ;
- des exemples appliqués à de vrais items ;
- les données requises par chaque modèle ;
- les conséquences sur le planning ;
- les comportements en cas de données manquantes ;
- la proposition retenue après échange avec Hugo.

Les statuts visibles pourront rester simples — À préparer, À lire, En construction, À consolider, À entraîner, Fragile, Critique, Maîtrisé — mais leur logique devra être justifiable, testable et modifiable.

---

## 6. Rebrancher et optimiser l’évaluation des OIC avec Ollama

La fonction d’évaluation des OIC avec **Ollama en local est déjà présente dans le projet**. La priorité est de la retrouver, de comprendre son fonctionnement puis de la rebrancher à la nouvelle interface.

Avant la refonte, cette fonction était accessible par un **bouton raccourci directement placé dans une case d’item**. Codex doit rechercher :

- l’ancien bouton et son composant ;
- la fonction appelée ;
- le service Ollama utilisé ;
- le format des prompts et des réponses ;
- les données enregistrées après l’évaluation ;
- les liens avec les OIC, les items et les collèges ;
- les éventuelles raisons pour lesquelles le branchement a disparu.

### Réflexion sur la manière de l’appeler

Après reconnexion, il faudra comparer plusieurs points d’entrée possibles :

- bouton raccourci dans chaque case item, comme auparavant ;
- action dans le menu contextuel de l’item ;
- lancement depuis la fiche détaillée ;
- proposition automatique dans le wizard de fin d’item ;
- lancement depuis l’onglet Évaluation ;
- évaluation groupée de plusieurs items ou d’un collège.

Le choix final devra préserver un accès rapide sans surcharger l’interface. Plusieurs points d’entrée peuvent coexister s’ils appellent exactement le même service métier.

### Optimisations à étudier

- réduire la durée d’attente ;
- rendre le résultat plus structuré et plus facile à valider ;
- mieux distinguer les OIC de rang A et B ;
- éviter de réévaluer inutilement les mêmes OIC ;
- conserver l’historique des évaluations ;
- mesurer la confiance du modèle ;
- permettre une validation ou une correction humaine ;
- utiliser les résultats pour proposer une révision ou une lacune ;
- améliorer les prompts à partir des erreurs observées.

Ollama ne doit pas décider seul du statut final. Il doit fournir une aide structurée, traçable et révisable.

---

## 7. QCM, notation et erreurs répétées

Créer ou reconnecter un système commun de saisie des résultats pour :

- QCM unitaires ;
- séries de QCM ;
- DP ;
- KFP ;
- examens blancs ;
- évaluations générées par Ollama.

### Données à enregistrer

- matière, collège, thème et item ;
- OIC associé lorsque possible ;
- réponse donnée ;
- réponse correcte ;
- type d’erreur ;
- niveau de confiance de l’utilisateur ;
- date ;
- source du QCM ;
- correction validée ou non.

### Algorithme d’erreurs répétées

Lorsqu’une erreur similaire apparaît plusieurs fois :

1. normaliser le thème de l’erreur ;
2. rechercher les erreurs antérieures proches ;
3. calculer leur fréquence et leur récence ;
4. vérifier si elles concernent le même item ou le même OIC ;
5. proposer la création d’une lacune ;
6. laisser l’utilisateur confirmer, fusionner ou refuser.

Une lacune confirmée doit :

- être enregistrée dans Synapse ;
- être visible depuis l’item, le thème et l’onglet Évaluation ;
- pouvoir générer une note dans Obsidian ;
- créer des révisions ciblées ;
- être résolue uniquement après plusieurs validations réussies.

---

## 8. Onglet Évaluation

Créer un onglet central regroupant :

- auto-évaluations ;
- QCM ;
- DP ;
- KFP ;
- examens blancs ;
- validations OIC ;
- révisions Anki ;
- lacunes ;
- évolution de la maîtrise.

Cet onglet doit permettre de filtrer par :

- collège ;
- matière ;
- item ;
- période ;
- type d’évaluation ;
- source ;
- statut de la lacune.

Il ne doit pas devenir un module isolé : chaque résultat doit aussi être visible dans la fiche de l’item concerné.

---

## 9. Génération d’évaluations avec Ollama

Ajouter un mode d’évaluation non planifié permettant de tester les connaissances à tout moment.

### Modes possibles

- quelques QCM impromptus ;
- série ciblée sur un item ;
- série ciblée sur une matière ;
- contrôle de lacunes actives ;
- partiel blanc.

### Partiel blanc

L’utilisateur choisit notamment :

- matière ou collège ;
- nombre de questions ;
- difficulté ;
- types d’épreuves ;
- items inclus ou exclus.

Ollama peut ensuite proposer, par exemple :

- 20 QCM ;
- plusieurs DP ;
- un ou plusieurs KFP.

Chaque question doit être reliée autant que possible à un item et à un OIC. Les résultats doivent alimenter le même système de maîtrise et de lacunes que les autres évaluations.

---

## 10. Récupération de QCM depuis l’UNESS

Étudier la possibilité d’une connexion à l’UNESS :

- API officielle ;
- export autorisé ;
- format d’import ;
- autre méthode conforme aux conditions d’utilisation.

Codex doit d’abord vérifier :

- si une API existe ;
- si elle est accessible aux étudiants ;
- si une authentification est nécessaire ;
- quelles données peuvent légalement et techniquement être récupérées.

Prévoir une architecture avec plusieurs connecteurs de sources de QCM afin de ne pas dépendre d’une seule plateforme.

### Vérification des corrections

Ollama peut analyser les corrections importées pour :

- détecter une incohérence ;
- expliquer la réponse ;
- relier la question à un OIC ;
- signaler une correction douteuse.

Ollama ne doit pas remplacer automatiquement une correction officielle. En cas de conflit, Synapse doit afficher les deux versions et demander une validation.

---

## 11. Intégration d’Anki

Prévoir l’intégration d’un deck Anki pour renforcer la validation des connaissances.

### Objectifs

- relier les cartes aux items, thèmes et OIC ;
- récupérer les résultats de révision ;
- utiliser les performances Anki dans le score de maîtrise ;
- repérer les cartes souvent échouées ;
- proposer une lacune si une même notion échoue à répétition.

L’intégration doit éviter d’importer inutilement toutes les cartes dans Synapse. Il faut privilégier :

- les identifiants ;
- les statistiques utiles ;
- les liens vers les cartes ;
- les résultats agrégés.

---

## 12. Planning universitaire et création de notes Obsidian

Créer un système capable de lire le planning de la faculté et d’anticiper la préparation des notes dans Obsidian.

### Contraintes

- ne pas utiliser l’API Claude ;
- privilégier une utilisation locale ou semi-automatique de Claude Code/CLI ;
- utiliser des fichiers intermédiaires lisibles ;
- garder une validation humaine avant création définitive.

### Workflow possible

1. importer ou lire le planning universitaire ;
2. identifier les cours, dates, enseignants et matières ;
3. associer chaque cours à un collège, un item ou un thème ;
4. détecter les notes déjà présentes dans Obsidian ;
5. générer une file de demandes de création ;
6. produire un fichier de consignes pour Claude ;
7. lancer Claude localement ou manuellement ;
8. récupérer les notes créées ;
9. enregistrer leur lien dans Synapse.

Le système doit anticiper suffisamment tôt les cours à venir sans créer de doublons.

---

## 13. Programmation manuelle de révisions

Permettre de programmer une révision spécifique depuis n’importe quelle vue pertinente.

L’utilisateur doit pouvoir choisir :

- item ;
- date ;
- type de révision ;
- durée estimée ;
- niveau de priorité ;
- récurrence éventuelle ;
- contenu attendu : lecture, restitution, QCM, Anki, lacune, DP ou KFP.

Ces tâches doivent apparaître dans le même planning que les tâches automatiques.

---

## 14. Mode Vacances

Ajouter un mode Vacances configurable depuis un calendrier.

### Choix possibles

- pause complète ;
- réduction forte de la charge ;
- maintien minimal ;
- personnalisation manuelle.

La période peut concerner :

- une journée ;
- un week-end ;
- plusieurs semaines ;
- des dates non continues.

### Comportement de l’algorithme

Pendant la période :

- ne pas considérer automatiquement les tâches non faites comme des échecs ;
- reporter intelligemment les révisions ;
- protéger en priorité les rappels critiques ;
- éviter une accumulation irréaliste au retour.

Après les vacances :

1. détecter les items dont les révisions ont été interrompues ;
2. proposer une phase courte de reprise ;
3. augmenter temporairement les QCM diagnostiques ;
4. évaluer l’état réel des connaissances ;
5. reconstruire le planning selon les résultats.

La majoration des QCM doit être temporaire et ciblée sur les cours non revus pendant la période.

---

## 15. Algorithme global de planification

La planification doit combiner :

- échéances J1, J3, J7, J14, J30 ;
- priorité des stages et cours de faculté ;
- niveau de maîtrise ;
- lacunes actives ;
- résultats récents ;
- charge quotidienne maximale ;
- temps disponible ;
- mode Vacances ;
- révisions programmées manuellement.

### Priorité indicative

1. tâches critiques ou très en retard ;
2. révisions JX des nouveaux items ;
3. préparation liée au stage ou au planning universitaire ;
4. lacunes actives ;
5. consolidation d’anciens collèges ;
6. QCM diagnostiques ;
7. entraînements facultatifs.

L’algorithme doit rester flexible pour les anciens collèges, mais plus strict pour les révisions JX des nouveaux items.

---

## 16. Interconnexion des vues

Une même action doit être disponible, lorsque cela est pertinent, depuis :

- dashboard ;
- planning ;
- vue collège ;
- vue thème ;
- vue item ;
- onglet Évaluation ;
- vue des lacunes.

Exemples :

- terminer un item ;
- lancer une auto-évaluation ;
- programmer une révision ;
- démarrer des QCM ;
- consulter les lacunes ;
- ouvrir la note Obsidian ;
- voir les résultats Anki.

Il ne faut pas dupliquer la logique dans chaque page. Les vues doivent seulement appeler les services communs.

---

## 17. Réflexion continue sur les fonctionnalités

La roadmap ne doit pas être considérée comme une liste figée de fonctions à implémenter. Pour chaque module existant ou futur, il faut prévoir une courte phase de réflexion afin de déterminer :

- le problème pédagogique réellement résolu ;
- la valeur ajoutée pour la préparation aux EDN ou aux ECOS ;
- les fonctions déjà présentes pouvant être améliorées ;
- les interactions avec les autres modules ;
- les données nécessaires ;
- les risques de complexité ou de surcharge ;
- la manière de mesurer si la fonction améliore réellement le travail.

Codex peut repérer des opportunités techniques, mais les choix pédagogiques et fonctionnels importants doivent être présentés à Hugo avant implémentation.

### Exemples de pistes à explorer

- recommandations quotidiennes mieux expliquées ;
- distinction entre révision de connaissances et entraînement au raisonnement ;
- détection des items négligés malgré un bon score global ;
- préparation ciblée selon les stages ;
- tableaux de bord orientés progression EDN ;
- suivi de la confiance et de la calibration ;
- révisions transversales par symptôme, porte d’entrée ou prise en charge ;
- génération de séances mixtes : rappel, QCM, cas clinique et restitution ;
- analyse des erreurs de raisonnement, et pas seulement des réponses fausses.

---

## 18. Objectif EDN et intégration progressive des ECOS

L’objectif prioritaire de Synapse est d’aider Hugo à arriver au meilleur niveau possible aux **EDN** et aux **ECOS**. Chaque nouvelle fonction doit donc être évaluée selon son utilité réelle pour ces deux formats.

### Axe EDN

Les fonctions déjà décrites peuvent contribuer aux EDN par :

- la couverture des OIC ;
- les QCM, DP et KFP ;
- la détection des lacunes répétées ;
- l’entraînement transversal ;
- les partiels blancs ;
- la planification adaptative ;
- la mesure de la stabilité des connaissances.

Il faudra réfléchir à des indicateurs plus directement liés à la préparation EDN : couverture du programme, maîtrise des rangs A/B, performance par type d’épreuve, progression temporelle et vulnérabilités prioritaires.

### Axe ECOS à concevoir

L’intégration des ECOS doit faire l’objet d’un chantier exploratoire spécifique. Il ne faut pas décider trop tôt d’une interface ou d’un algorithme sans définir le scénario d’usage.

Pistes à étudier :

- simulation de stations ECOS chronométrées ;
- génération d’un scénario patient et d’une consigne candidat ;
- interrogatoire interactif avec un patient simulé localement ;
- choix des examens cliniques pertinents ;
- annonce diagnostique ou explication thérapeutique ;
- communication avec un patient, un proche ou un professionnel ;
- grille d’évaluation structurée ;
- auto-évaluation après la station ;
- débriefing avec les éléments oubliés ;
- enregistrement des erreurs récurrentes ;
- création de lacunes cliniques ou communicationnelles ;
- répétition ciblée d’une compétence faible ;
- suivi séparé des compétences cliniques, relationnelles et organisationnelles.

### Questions à résoudre avant développement ECOS

- Quelle part peut être réalisée avec Ollama localement ?
- Faut-il un échange textuel, vocal ou les deux ?
- Comment créer des scénarios fiables et conformes aux attentes universitaires ?
- Quelle grille utiliser pour évaluer une station ?
- Comment gérer les actions physiques impossibles à simuler sur écran ?
- Comment chronométrer sans rendre l’expérience artificielle ?
- Comment relier une station aux items, OIC, symptômes et compétences ?
- Comment distinguer une erreur de connaissance, de raisonnement, de communication ou de gestion du temps ?
- Comment intégrer les résultats ECOS dans la maîtrise sans les confondre avec les QCM ?

### Première étape recommandée

Avant de développer un simulateur complet, concevoir avec Hugo un prototype limité à quelques types de stations. Tester son intérêt, la qualité du débriefing et la pertinence des données produites, puis décider de l’architecture définitive.

---

## 19. Ordre recommandé de réalisation

### Phase 1 — Audit et récupération

- cartographier le code ;
- retrouver les fonctions perdues ;
- identifier les services réutilisables ;
- vérifier la base de données ;
- reconnecter les éléments simples ;
- ajouter des tests de non-régression.

### Phase 2 — Socle métier commun

- unifier les services items, évaluations et planning ;
- créer les événements métier ;
- supprimer les logiques dupliquées dans les pages ;
- synchroniser les différentes vues.

### Phase 3 — Récupération du workflow de validation et conception de la maîtrise

- retrouver et rebrancher l’ancienne auto-évaluation ;
- analyser ses données et son efficacité ;
- proposer des améliorations du wizard de fin d’item ;
- mener la réflexion sur l’algorithme de maîtrise avec Hugo et ChatGPT ;
- ne développer le nouveau modèle qu’après validation.

### Phase 4 — Évaluations et lacunes

- saisie QCM, DP et KFP ;
- erreurs répétées ;
- création de lacunes ;
- onglet Évaluation.

### Phase 5 — Intégrations locales

- retrouver, rebrancher et optimiser l’évaluation OIC déjà présente avec Ollama ;
- Ollama pour QCM et examens blancs ;
- Anki ;
- Obsidian ;
- planning de la faculté ;
- workflow Claude sans API.

### Phase 6 — Sources externes, modes avancés et prototype ECOS

- étude de l’intégration UNESS ;
- connecteurs de QCM ;
- mode Vacances ;
- reprise diagnostique après interruption ;
- atelier de conception puis prototype limité de simulation ECOS.

---

## 20. Critères de réussite

Le travail sera considéré comme réussi si :

- aucune ancienne fonction utile n’a été recréée inutilement ;
- les fonctions perdues pendant la refonte ont été identifiées ;
- une action produit le même résultat depuis toutes les vues ;
- l’ancienne auto-évaluation a été retrouvée, reconnectée et améliorée sans duplication inutile ;
- le wizard de fin d’item met réellement à jour le statut et le planning ;
- les QCM, Anki, OIC et lacunes influencent le niveau de maîtrise ;
- les erreurs répétées peuvent générer une lacune validée ;
- les lacunes sont synchronisées avec Obsidian ;
- le mode Vacances ne crée pas une dette de travail irréaliste ;
- l’évaluation OIC existante avec Ollama a été retrouvée et rebranchée ;
- Ollama fonctionne localement et ses réponses restent vérifiables ;
- les évaluations sont regroupées sans devenir indépendantes des items ;
- les tests couvrent les principaux workflows métier ;
- les décisions importantes sur la maîtrise et les ECOS ont été discutées avec Hugo avant implémentation ;
- chaque nouvelle fonction démontre une utilité identifiable pour la préparation EDN ou ECOS.

---

## 21. Consigne finale pour Codex

Commencer par l’audit complet de l’existant. Ne pas lancer une refonte globale supplémentaire.

Pour chaque fonctionnalité demandée :

1. rechercher d’abord le code déjà présent ;
2. vérifier s’il peut être réparé ou reconnecté ;
3. identifier les données déjà enregistrées ;
4. centraliser la logique métier ;
5. ajouter des tests ;
6. seulement ensuite développer les éléments réellement manquants.

La priorité n’est pas d’ajouter une accumulation d’outils, mais de construire un système d’apprentissage unique dans lequel chaque action enrichit les autres modules et améliore concrètement la préparation aux EDN et aux ECOS.

Les choix pédagogiques majeurs — notamment l’algorithme de maîtrise, le contenu de l’auto-évaluation et le futur mode ECOS — doivent faire l’objet de propositions argumentées, puis être discutés avec Hugo avant développement.

---

## 22. Addendum — ergonomie, navigation et liaison des notes

Ces demandes s’inscrivent dans la phase d’audit et de reconnexion : elles ne doivent pas conduire à dupliquer les actions métier existantes dans les vues cockpit.

### Vue Collèges : déplier un collège et agir sur ses items

Depuis la vue Collèges, un clic sur un collège doit pouvoir le déplier dans la page pour afficher une vue simplifiée de ses items, sans imposer une navigation supplémentaire.

Pour chaque item affiché, prévoir au minimum :

- son numéro et son intitulé lisible ;
- son état de maîtrise/révision et sa prochaine action ;
- un accès à sa fiche détaillée ;
- une action de validation lorsque cela est pertinent.

La validation doit appeler exactement le même workflow métier que depuis le dashboard, le planning, la vue item et le mode Focus. Elle ne doit pas être une simple bascule visuelle propre à la vue Collèges.

Avant implémentation, auditer la différence entre : marquer une révision faite, terminer une première étude d’item et modifier un statut déclaratif. La vue dépliée doit rendre cette distinction compréhensible.

### Vue Items : lisibilité et tri par collège

La vue Items actuelle ressemble à un gros paquet d’items : les intitulés très longs provoquent un affichage horizontal difficile à lire et les doublons d’items appartenant à plusieurs collèges ne sont pas suffisamment explicités.

À auditer puis corriger :

- le bug d’affichage constaté sur la liste (largeur, débordement horizontal, hiérarchie des colonnes et troncature) ;
- un filtre et un tri explicites par collège ;
- la possibilité de grouper visuellement les items par collège, avec un état par défaut qui reste lisible ;
- la manière d’afficher un même item rattaché à plusieurs collèges, sans le confondre avec un doublon de données ;
- des tests de rendu et de navigation sur une liste contenant des intitulés longs et des items multi-collèges.

### Synchronisation Obsidian ↔ Synapse

Obsidian et Synapse n’ont pas le même modèle : Obsidian est le référentiel interconnecté de connaissance et doit normalement contenir une seule note canonique par item ; Synapse affiche ce même item dans un ou plusieurs collèges comme contextes de travail. Le lien entre une note Obsidian et l’item canonique Synapse est actuellement insuffisamment fiable. Exemple à utiliser comme test de caractérisation : l’item 75 « addiction au tabac » est signalé sans note dans Synapse alors que la note existe dans Obsidian.

Avant toute nouvelle fonctionnalité de note :

1. auditer la stratégie actuelle de rapprochement (identifiant, nom de fichier, frontmatter, numéro d’item, titre et collège) ;
2. comparer les données de l’item 75 avec le frontmatter et le chemin de sa note réelle ;
3. déterminer si le défaut vient de l’indexation, de la normalisation des titres, du mapping des collèges ou de la persistance du lien ;
4. définir une clé de liaison stable au niveau de l’item canonique (identifiant/numéro d’item dans le frontmatter), indépendante du collège d’affichage, avec des règles de repli explicites ;
5. ajouter des tests pour les accents, titres renommés, notes déjà existantes, items multi-collèges et absence réelle de note.

La synchronisation doit d’abord détecter et relier une note existante au niveau de l’item canonique. Une fiche Synapse doit afficher cette note même si elle est rangée dans le dossier Obsidian d’un autre collège. Elle ne doit jamais créer un doublon parce que le collège courant ou le nom de fichier diffère légèrement.

### Dashboard : séparateur Aujourd’hui / Contexte redimensionnable

Dans le dashboard cockpit, la séparation verticale grise entre les zones « Aujourd’hui » et « Contexte » doit pouvoir être déplacée par l’utilisateur afin d’adapter la largeur de chaque zone à son écran.

Contraintes :

- poignée de redimensionnement visible, accessible au clavier et utilisable à la souris/tactile ;
- largeurs minimale et maximale pour que les deux panneaux restent utilisables ;
- comportement correct sur petit écran (empilement ou valeur adaptée) ;
- préférence persistée localement et restaurée au prochain affichage ;
- aucune modification de la logique de recommandations ou des données affichées.

Ce changement est une amélioration de présentation : il doit rester séparé de la reconnexion des workflows métier.

---

## 23. Journal de session — 27/07/2026

### Réalisé

- **Vue Collèges** : clic sur un collège pour déplier ses items, avec affichage simplifié, accès à la fiche item et validation reliée au workflow métier commun.
- **Vue Items** : correction du débordement horizontal, tri par item ou collège et filtre explicite par collège.
- **Navigation depuis les listes** : clic sur un item pour ouvrir sa fiche ; double-clic depuis la file « Aujourd’hui » pour ouvrir directement l’écran détaillé.
- **Dashboard** : séparateur Aujourd’hui/Contexte redimensionnable, avec limites, adaptation aux petits écrans et persistance locale.
- **Synchronisation Obsidian** : recherche d’une note canonique au niveau de l’item, indépendante du collège dans lequel Synapse l’affiche.
- **OIC** : onglet OIC dans la fiche item, chargement à la demande et réutilisation du système d’évaluation existant.
- **Recherche Items** : palette dédiée avec animation, recherche par numéro/titre/collège, navigation clavier et ouverture directe de la fiche.
- **Raccourci recherche** : `Ctrl+Alt+P` (afin de ne pas interférer avec l’impression Chrome). La palette reprend désormais les tokens visuels Synapse.
- **Tests** : suite complète validée à **467 tests passés**, avec un avertissement de dépréciation préexistant.

### État de la feuille de route

Ces éléments sont considérés comme **implémentés et vérifiés**. Les chantiers de conception restant à traiter sont notamment l’algorithme de maîtrise, l’onglet Évaluation central, les intégrations QCM/Anki/UNESS, le mode Vacances et le prototype ECOS.

## 24. État consolidé — 28/07/2026

La section 23 conserve le journal historique de la session du 27/07. Depuis cette
session, plusieurs chantiers initialement indiqués comme restant à traiter ont
été implémentés et vérifiés dans le dépôt.

### Réalisé et vérifié

- reconnexion du cockpit, des vues Collèges et Items, du mode Focus et des
  principaux parcours de validation ;
- réutilisation du wizard commun de retour de séance, avec persistance de
  l’auto-évaluation ;
- façade métier commune `record_evaluation()` pour les résultats d’évaluation ;
- onglet OIC dans la fiche item, avec réutilisation du service LiSA/AnythingLLM
  existant ;
- QCM, propositions de lacunes et ancrage des lacunes récurrentes ;
- intégration technique Anki : client, mapping du paquet, déduplication des
  preuves, session de révision et bridge du scheduler natif ;
- maîtrise adaptative fondée sur des preuves datées et projection de rétention ;
- planning cockpit, planification manuelle, objectifs de charge et
  consolidations ;
- liaison canonique des notes Obsidian au niveau de l’item ;
- action explicite de première lecture et rappels J3/J7/J14/J30.

Validation actuelle : `pytest -q` donne **630 tests passés, 1 avertissement**.

La validation des workflows est compensatoire : si la transition métier échoue
après la création de session, la session est supprimée, ainsi que les
références de proposition de lacune qui la concernent. Cette garantie couvre
les parcours révision, consolidation et lacune. Une transaction SQLite native
reste à envisager pour couvrir les cas d’écriture partielle interne.

### Partiel ou à consolider

- l’architecture métier commune n’est pas encore appliquée à tous les parcours :
  certains chemins historiques conservent des écritures ou rafraîchissements
  spécifiques ;
- les QCM et lacunes disposent encore de plusieurs formats historiques ;
- l’onglet Évaluation central reste à structurer comme vue transverse complète ;
- le mode Vacances existe dans la conception et le planning, mais sa gestion
  complète des interruptions, reprises et reports doit encore être validée ;
- l’intégration Anki est couverte par les tests, mais nécessite une vérification
  manuelle avec AnkiConnect et un paquet réel ;
- l’évaluation OIC repose sur LiSA/AnythingLLM : elle n’est pas une intégration
  Ollama directe telle que formulée dans certaines parties historiques de cette
  feuille de route.

### Non commencé ou exploratoire

- récupération/import de QCM UNESS dans un cadre conforme ;
- connecteurs de sources QCM externes ;
- planning universitaire automatisé et génération semi-automatique de notes ;
- prototype et modèle de données ECOS ;
- validation pédagogique avec Hugo des dimensions finales de la maîtrise et
  des règles spécifiques EDN/ECOS.

### Prochain ordre de travail recommandé

1. mesurer et réduire les divergences restantes entre les points d’entrée ;
2. finaliser l’onglet Évaluation transverse ;
3. terminer la validation réelle du mode Vacances et d’Anki ;
4. décider explicitement du périmètre UNESS et du planning universitaire ;
5. concevoir un prototype ECOS limité avant toute intégration dans la maîtrise.
