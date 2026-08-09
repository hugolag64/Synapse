# Synapse — Feuille de route UX, reprise et algorithmes

> Document de référence validé avec Hugo le 9 août 2026.
> Cette feuille de route repart de l’état réel du dépôt et distingue ce qui doit être conservé,
> réparé, refondu ou réévalué.

## Objectif

Repartir sur une base saine pour la reprise d’étude du **20 août 2026**, sans perdre l’historique,
sans recréer une dette artificielle et sans refondre les vues qui fonctionnent déjà.

Synapse doit répondre rapidement à trois questions :

1. Que dois-je faire maintenant ?
2. Pourquoi cette action est-elle prioritaire ?
3. Quelle ressource ou quel entraînement dois-je ouvrir ?

## État d’exécution

**Étape actuelle : neutralisation métier, visibilité des échéances futures, validation hybride des
collèges, tri visuel des Items, harmonisations QCM/Prépa et annales implémentés — prochaines
tranches : refontes UI Linear restantes et audit des scores.**

Le premier plan détaillé est disponible dans
`docs/superpowers/plans/2026-08-09-sprint-reprise-preferences.md` pour le socle, puis
`docs/superpowers/plans/2026-08-09-neutralisation-dette-reprise.md` pour la règle métier. La
préférence est persistante, les paramètres proposent une sauvegarde explicite et un contrôle de
masquage/réaffichage du Sprint, et les flux actifs filtrent désormais les échéances antérieures au
20 août sans réécrire l’historique. Le détail item conserve le mode complet pour une action manuelle.
Planning couvre maintenant l’extrémité de la semaine affichée pour les consolidations futures, y
compris lors de la navigation vers la semaine suivante. La vue Collèges calcule maintenant un
rapport de preuve par collège : items couverts, cycle J3/J7/J14/J30 complet et état manuel. Elle
propose une confirmation automatique lorsque les preuves sont complètes et conserve une action de
validation manuelle lorsque ce n’est pas le cas.

## Décisions validées

### Périmètre visuel

La direction retenue est **Linear dominant** : listes denses, hiérarchie typographique claire,
états explicites, panneau contextuel lorsque nécessaire, peu de cartes et aucune décoration sans
fonction.

Les vues suivantes sont considérées comme visuellement satisfaisantes et ne seront pas refondues :

- Aujourd’hui ;
- Planning ;
- vue thème / vue Collèges, sous réserve des ajustements fonctionnels ;
- Révisions ;
- OEC ;
- Podcast ;
- Historique.

Elles ne changent que pour intégrer les règles transverses de reprise, de planning et de données.

### Reprise globale

La date de reprise est le **20 août 2026**.

- Les tâches échues avant cette date sont neutralisées de la dette active.
- Leur historique reste conservé et consultable.
- Aucun retard antérieur ne doit réapparaître dans Aujourd’hui, Planning ou Flash-Zero.
- Les échéances futures restent visibles.
- Aucune dette synthétique ne doit être créée automatiquement le 20 août.
- Un item sans échéance future reste accessible et peut être reprogrammé manuellement.
- Le Flash-Zero ne doit exploiter que les signaux postérieurs à la reprise pour ses nouvelles
  recommandations.

Cette règle doit être portée par le métier, pas implémentée séparément dans chaque page.

### Sprint EDN

- La date cible EDN est une préférence persistante unique.
- La modification doit afficher un état explicite « enregistré ».
- Un bouton « Masquer le Sprint » masque uniquement la carte et ne désactive pas les calculs.
- Un contrôle inverse dans Paramètres permet de réafficher la carte.
- Après Ctrl+R, la date et l’état masqué/visible doivent être restaurés exactement.
- Les valeurs par défaut ne doivent plus écraser une préférence existante.

### Collège validé

La validation est hybride.

Synapse propose automatiquement un collège comme validé lorsque :

- tous les items rattachés disposent d’une preuve d’étude ou d’une preuve historique reconnue ;
- le cycle J30 est terminé pour les items concernés ;
- les preuves nécessaires sont disponibles et cohérentes.

La proposition affiche ses preuves : items couverts, lectures manquantes, étapes J3/J7/J14/J30
manquantes et éventuelles ambiguïtés.

Hugo peut confirmer manuellement un collège même si la proposition automatique n’est pas complète.
Cette confirmation est une décision déclarative tracée ; elle ne modifie pas les preuves calculées.

**État au 9 août 2026 :** l’algorithme pur et la vue Collèges sont branchés. Chaque ligne expose
« À compléter », « Validation automatique proposée », « En cours » ou « Confirmé manuellement ».
La confirmation écrit uniquement le statut déclaratif existant et conserve l’historique des preuves.

### Items

**État au 9 août 2026 :** le tri par collège crée maintenant des séparateurs visuels et conserve un
seul affichage par item, y compris lorsqu’un item appartient à plusieurs collèges. Le tri par item
reste numérique et les filtres existants sont appliqués avant le rendu.

### Planning

La vue semaine doit réunir :

- les révisions J3/J7/J14/J30 ;
- les consolidations ;
- les tâches manuelles ;
- les événements Google Calendar.

**État au 9 août 2026 :** les révisions futures et les consolidations sont maintenant recherchées
jusqu’à la fin de la semaine affichée, y compris après navigation.

Les mêmes objets métiers doivent être ouvrables et validables depuis Aujourd’hui, Planning,
Collèges et le détail d’un item.

## Direction UI validée pour les écrans à refondre

### Évaluation : QCM et annales

**État au 9 août 2026 :** la vue QCM utilise maintenant une section principale pleine largeur,
une grille stable cours/barre/score et l’action primaire « Lancer un entraînement ». Les calculs
de score et les flux d’historique restent inchangés.

**Annales :** la liste des épreuves et le détail des sous-parties utilisent maintenant des lignes à
colonnes stables pour distinguer épreuve, progression, score officiel, statut et action. Le barème
et les données de maîtrise ne sont pas modifiés. Les groupes sans sous-partie importée (`0/0`) ne
sont plus affichés ; un nettoyage ciblé et réversible des artefacts de tests est disponible dans
`deploy/cleanup_test_annales.py`.

La largeur est maintenant réellement étendue à toute la zone disponible : les lignes de catalogue
sont étirées explicitement dans leur colonne flex, ce qui évite le retrait à une largeur intrinsèque
observé sur l’écran déployé.

QCM et annales partagent un cadre de lecture commun :

- bandeau de synthèse pleine largeur ;
- score, volume de sessions, récence et état ;
- listes lisibles plutôt que cartes imbriquées ;
- score et statut alignés dans des colonnes stables ;
- action primaire « Lancer un entraînement » ;
- distinction explicite entre QCM, DP, KFP et annale.

Une annale conserve son barème officiel et ne doit pas être présentée comme un simple QCM.

### Prépa

**État au 9 août 2026 :** Prépa est maintenant présentée comme une liste de sources pleine largeur :
source, objectif, dernière utilisation et action d’ouverture sont alignés sur chaque ligne. Les
catégories restent visibles sans empiler de cartes hétérogènes.

Prépa devient une liste de sources :

- EDN Pro ;
- Hippocampus ;
- EDN i ;
- autres sources réellement configurées.

Chaque ligne indique l’objectif de la source, la dernière utilisation et une action Ouvrir.
La vue ne doit plus empiler des cartes hétérogènes ou des blocs visuellement décalés.

### Points faibles, Revue hebdo et Statistiques

Ces écrans partagent un cadre d’analyse large et centré :

- bandeau de synthèse ;
- filtres temporels homogènes ;
- tableaux ou listes pleine largeur ;
- séparation nette entre activité, performance, maîtrise et lacunes ;
- aucune ancienne notion de « score de sévérité » affichée comme si elle était le score de maîtrise ;
- Revue hebdo : consolidés, régressions et focus de la semaine suivante ;
- Statistiques : temps, révisions, maîtrise moyenne, répartition par collège et activité récente.

Le libellé « taux de réussite » ne doit être utilisé que pour une proportion de sessions réussies,
pas pour une simple moyenne de pourcentages.

**État au 9 août 2026 — Revue hebdo :** le conteneur de la page étire maintenant ses enfants
directs sur toute la largeur disponible. Le bandeau, les métriques, les deux colonnes de transitions
et le focus hebdomadaire ne se rétractent plus chacun à leur largeur intrinsèque ; les données et les
comparaisons avant/après restent inchangées.

**État au 9 août 2026 — Statistiques :** le même correctif est appliqué au cadre principal et aux
sections internes. Le bandeau, les métriques, les temps par collège et les lignes d’activité utilisent
maintenant la largeur disponible, sans modifier les périodes, les agrégats ni le calcul de maîtrise.

### Détail item

- supprimer le bouton Obsidian doublonné près de Mnemo/Image ;
- conserver un seul lien Obsidian dans l’en-tête ou la zone de ressources ;
- remplacer « + Mnemo Image » par « Ajouter un mnémo » ;
- rendre Entraînement clairement visible comme action principale secondaire ;
- regrouper Réviser, Entraînement, Note et Obsidian dans une hiérarchie courte ;
- ne pas empiler plusieurs boutons équivalents dans des bentos séparés.

## Cartographie de l’existant

### Interfaces

| Domaine | Fichiers principaux | Orientation |
|---|---|---|
| Sprint / Paramètres | `frontend/pages/settings_cockpit.py`, `backend/state/store.py` | persistance et masquage |
| Aujourd’hui | `frontend/pages/dashboard/` | conserver visuellement, appliquer reprise |
| Planning | `frontend/pages/planning_cockpit.py`, `backend/core/planning/` | ajouter toutes les échéances futures |
| Collèges | `frontend/pages/colleges_cockpit.py`, `frontend/pages/triage.py` | validation hybride |
| Items | `frontend/pages/items.py` | conserver la logique, vérifier tri/groupement |
| Détail item | `frontend/pages/course_detail_cockpit.py`, `frontend/components/` | nettoyer les actions |
| QCM | `frontend/pages/qcm_cockpit.py`, `backend/core/qcm/` | unifier rendu et métriques |
| Annales | `frontend/pages/annales.py`, `frontend/pages/annale_detail.py`, `backend/core/uness/` | séparer barème et maîtrise |
| Prépa | `frontend/pages/prepa.py` | liste de sources |
| Points faibles | `frontend/pages/weak_points_cockpit.py`, `frontend/components/weak_point_row.py` | nouvelle hiérarchie |
| Revue hebdo | `frontend/pages/revue.py`, `backend/core/analytics/weekly_report.py` | brancher et clarifier |
| Statistiques | `frontend/pages/stats.py`, `frontend/pages/stats_cockpit.py` | recentrer les données |

### Données et services

- SQLite local : `backend/core/reviews/local_store.py` ;
- tâches de révision : `backend/core/reviews/service.py` ;
- SM-2 : `backend/core/reviews/sm2.py` ;
- maîtrise : `backend/core/reviews/mastery.py` ;
- rétention : `backend/core/knowledge/retention.py` ;
- planning : `backend/core/planning/service.py` ;
- compte à rebours : `backend/core/planning/sprint_countdown.py` ;
- Flash-Zero : `backend/core/practice/flash_zero_service.py` ;
- priorisation EDN : `backend/core/edn/trajectory.py` ;
- QCM : `backend/core/qcm/service.py` et `backend/core/ai_qcm/` ;
- annales / barème : `backend/core/uness/exam_simulator.py` ;
- rapport hebdomadaire : `backend/core/analytics/weekly_report.py`.

## Algorithmes actuels expliqués

### 1. Génération des révisions J3/J7/J14/J30

`ReviewService` génère des tâches virtuelles à partir des dates Notion ou de la date de première
lecture. Les cycles sont : J3, J7, J14 et J30. Les tâches terminées, ignorées ou annulées sont
masquées ; les tâches reportées utilisent leur date effective pour l’affichage tout en conservant
la date théorique dans l’identifiant.

Le moteur utilise un horizon futur de 30 jours et un cache par contexte/date.

Évolution prévue : ajouter une règle métier de neutralisation avant le 20 août sans supprimer ni
réécrire `review_history`. Le filtre doit être commun à Aujourd’hui, Planning, Révisions et aux
recommandations.

### 2. SM-2 hybride

Le grade utilisateur 1–5 est converti en grade SM-2 0–4.

- confiance 1 ou 2 : échec ; intervalle de 1 jour si piège critique, sinon 3 jours ; facteur de
  facilité diminué de 0,2 ;
- confiance 3 à 5 : réussite ; le facteur de facilité est ajusté selon la formule SM-2 ;
- première répétition réussie : 3 jours ;
- deuxième répétition réussie : 7 jours ;
- répétitions suivantes : intervalle courant × facteur de facilité ;
- piège critique : intervalle plafonné à 7 jours ;
- piège récurrent : pénalité supplémentaire de 0,15 sur le facteur de facilité ;
- facteur de facilité minimal : 1,3 ; valeur initiale : 2,5.

Ce moteur est utile pour le calendrier, mais son comportement doit être testé sur des séries
longues : réussite répétée, échec après long intervalle, piège récurrent et reprise après absence.

### 3. Score QCM

Le score est normalisé depuis `14/20`, `70 %`, `70` ou `0,7`.

- 70 % ou plus : réussi ;
- 60 % à moins de 70 % : limite ;
- moins de 60 % : raté ;
- score inférieur à 50 % : sévérité suggérée plus élevée pour une lacune.

Le score actuel est un résultat d’évaluation, pas encore une mesure complète de maîtrise. Une
moyenne de scores ne suffit pas à distinguer une amélioration récente d’une ancienne réussite.

Évolution prévue : conserver le score brut, ajouter la taille de l’échantillon, la récence, les
erreurs par proposition, les erreurs Rang A et une moyenne pondérée par récence. Les seuils ne seront
pas modifiés sans comparaison sur les données historiques.

### 4. Barème des annales / épreuves EDN

Pour chaque question, le moteur compte les discordances entre les réponses choisies et les réponses
correctes : oublis et faux positifs.

- 0 discordance : 1,0 point ;
- 1 discordance : 0,5 point ;
- 2 discordances : 0,2 point ;
- 3 discordances ou plus : 0 point ;
- oubli d’une proposition Rang A vitale : annulation à 0 point.

Problème identifié : lors de la conversion de certains cas SQLite, les propositions sont marquées
Rang A par défaut. Cela peut annuler artificiellement une question. La priorité est de préserver le
rang réel, de distinguer omission/faux positif et de stocker le détail de l’erreur.

Le score officiel de l’annale doit rester séparé de la maîtrise Synapse. Une annale réussie est une
preuve forte, mais elle ne doit pas écraser à elle seule l’historique de rétention.

### 5. Score de maîtrise

Le score actuel commence généralement à 50 puis applique des ajustements :

- première lecture : -5 ; deux lectures : +5 ; trois lectures ou plus : +10 ;
- QCM manquant après plusieurs lectures : -4 ;
- report : -5 par report, plafonné à -20 ;
- confiance moyenne basse : -15 ; confiance moyenne haute : +10 ;
- session déclarée difficile : -10 ;
- QCM raté : -15 ; plusieurs QCM réussis : +10 ;
- QCM récent sous 50 % avec au moins 10 questions : -15 ;
- moyenne d’annales >=80 % : +15 ; moyenne <50 % : -15 ;
- graine d’un niveau déclaré : fusion progressive avec les preuves réelles ;
- Anki : 75 % du score Synapse + 25 % du score Anki lorsqu’une preuve existe ;
- projection de rétention finale avec un plancher de 25 et une stabilité dépendant de la source et
  de la qualité de la preuve.

Les niveaux sont ensuite déduits du score : critique sous 40, fragile sous 60, puis consolidation ou
maîtrise selon le score et la présence d’un QCM. Une preuve Rang A ne doit influencer le niveau que
si une couverture Rang A existe réellement.

Évolution prévue : séparer quatre dimensions :

1. score continu ;
2. niveau lisible ;
3. stabilité / rétention projetée ;
4. suffisance des preuves.

Un score élevé avec trop peu de preuves doit être affiché comme insuffisamment confirmé, et non comme
une maîtrise certaine.

### 6. Rétention

Chaque preuve possède une date, une source et une qualité. Les sources ont une stabilité de base :
lecture, auto-évaluation, QCM, DP, KFP, OIC, Anki et annale ne sont pas équivalents.

La stabilité augmente après une preuve de qualité suffisante et se contracte après une preuve faible.
La rétention projetée suit une décroissance exponentielle vers un plancher de 25, plafonnée à 730 jours
de stabilité.

Ce modèle est une bonne base explicable. Il doit recevoir les preuves d’erreurs de manière fiable,
notamment les erreurs QCM et annales, sinon la projection est optimiste par défaut.

### 7. Priorisation

La formule actuelle combine :

- poids EDN ;
- écart de maîtrise ;
- récurrence des erreurs ;
- disponibilité de questions ;
- fréquence EDN lorsqu’elle est disponible ;
- effort estimé.

Dans le fallback, les poids sont 0,35 / 0,35 / 0,20 / 0,10. Avec une fréquence EDN disponible,
la formule devient multiplicative et amplifie l’écart de maîtrise.

Le problème principal n’est pas la vitesse de calcul, mais la fiabilité des entrées : certaines
valeurs sont encore codées en dur dans le dashboard et les tables `error_signals` /
`edn_recommendations` peuvent être vides.

Évolution prévue : afficher la contribution de chaque facteur, alimenter réellement les signaux,
mesurer les décisions produites et seulement ensuite calibrer les poids.

### 8. Sprint EDN

Le moteur actuel choisit une phase selon le nombre de jours avant la date cible :

- plus de 120 jours : apprentissage profond, ratios 50/35/15, cible 4 items ;
- 31 à 120 jours : consolidation, ratios 25/45/30, cible 6 items ;
- 30 jours ou moins : Sprint Flash, ratios 5/35/60, cible 8 items.

Ces ratios sont des recommandations, pas encore une preuve de performance. La carte doit expliquer
qu’il s’agit d’un conseil de rythme et pouvoir être masquée sans désactiver le moteur.

### 9. Flash-Zero

Le service combine une banque canonique et un pool de questions générées par IA. La priorisation
devrait utiliser les erreurs récentes et répétées. L’audit montre que l’alimentation des signaux
d’erreur doit être vérifiée : si `error_signals` reste vide, le caractère adaptatif est une façade.

À partir du 20 août, les anciennes erreurs ne doivent pas déclencher une nouvelle génération. Les
questions canoniques restent disponibles ; les questions IA doivent conserver leur source et leur
statut de vérification.

### 10. Projection vers l’EDN

La projection utilise une fenêtre récente d’environ quatre semaines, une cadence d’items, une charge
quotidienne et trois scénarios prudent/central/ambitieux. La maîtrise projetée augmente selon la
couverture projetée, avec une confiance indicative.

Cette projection doit être présentée comme une estimation, jamais comme une prédiction certaine. Elle
doit intégrer la date de reprise pour ne pas interpréter la neutralisation de dette comme une baisse
de rythme.

### 11. Revue hebdomadaire et statistiques

Le rapport compare des snapshots hebdomadaires de maîtrise et agrège séances, durée, lacunes,
confiance et résultats QCM.

Points à corriger :

- `qcm_pass_rate` correspond actuellement à une moyenne de scores, pas à un taux de sessions réussies ;
- les deltas doivent afficher les scores avant/après ;
- les catégories de lacunes doivent être reliées à la période analysée lorsqu’elles sont présentées
  comme un focus hebdomadaire ;
- une semaine sans snapshot de comparaison doit être affichée comme « comparaison indisponible »,
  pas comme une absence de progression.

## Feuille de route en quatre chantiers

### Chantier 1 — Socle de reprise et fiabilité

Objectif : rendre la reprise du 20 août déterministe depuis toutes les vues.

**État au 9 août 2026 :** le modèle de préférences persiste la date cible EDN, la date de reprise
`2026-08-20` et la visibilité du Sprint, avec validation des dates et écriture groupée. Les flux
Aujourd’hui, Planning, notification du matin, lundi, Collèges, Items et le shell utilisent le mode
actif centralisé. Les consolidations non gated antérieures à la reprise et les signaux Flash-Zero
antérieurs sont neutralisés sans suppression d’historique ; les consolidations explicitement gated
conservent leur date de démarrage.

Vérification de la tranche : tests ciblés reprise précédents **66/66**, tests ciblés collèges
**13/13**, tests ciblés Items **8/8**, tests ciblés QCM **33/33**, tests ciblés Prépa **9/9**, tests
ciblés Annales et nettoyage **23/23**, Revue hebdo / largeurs **5/5**, Statistiques / largeurs **6/6**,
suite complète **à relancer
après cette correction**, compilation
Python de `backend` et `frontend` réussie. La vérification manuelle de l’application reste à faire
quand le serveur Synapse sera ouvert dans l’onglet local.

Livrables :

- préférence globale de reprise ;
- neutralisation non destructive de la dette antérieure ;
- persistance robuste de la date cible EDN ;
- masquage/réaffichage du Sprint ;
- statut hybride de collège validé ;
- agrégation des tâches futures dans le planning ;
- tests de redémarrage et Ctrl+R simulé.

### Chantier 2 — Refonte UI ciblée

Objectif : corriger les écrans signalés sans toucher visuellement aux vues conservées.

Livrables :

- cadre commun Évaluation pour QCM et annales ;
- liste de sources pour Prépa ;
- analyse pleine largeur pour Points faibles, Revue hebdo et Statistiques ;
- détail item avec actions Mnemo/Obsidian/Entraînement nettoyées ;
- états vides, chargements, erreurs et responsive homogènes ;
- tests de présence des actions et tests de rendu ciblés.

### Chantier 3 — Audit et évolution des algorithmes

Objectif : rendre les scores pédagogiquement explicables et techniquement mesurables.

Ordre :

1. rapport de référence sur les données actuelles ;
2. correction des biais avérés sans changer les seuils par défaut ;
3. alimentation des preuves et signaux manquants ;
4. séparation score QCM / score annale / maîtrise ;
5. validation de la maîtrise et de la rétention ;
6. calibration de la priorisation ;
7. comparaison avant/après sur des cas représentatifs.

### Chantier 4 — Validation et documentation

Objectif : empêcher une nouvelle divergence entre code, interface et documentation.

Livrables :

- matrice de tests métier ;
- rapport de scores avant/après ;
- vérification visuelle des écrans refondus ;
- explication de chaque formule dans la documentation ;
- mise à jour de cette feuille de route à chaque chantier terminé.

## Matrice de validation

### Reprise

- une tâche due le 19 août reste dans l’historique mais disparaît de la dette active ;
- une tâche due le 21 août reste visible dans Planning ;
- le Flash-Zero ne reprend pas une erreur antérieure comme nouveau signal ;
- une nouvelle erreur à partir du 20 août peut alimenter la priorisation ;
- un redémarrage conserve la date et les préférences.

### Collèges

- collège avec toutes les premières lectures et J30 terminés : proposition validée ;
- collège avec un item manquant : proposition non validée et preuve affichée ;
- confirmation manuelle : statut déclaré conservé sans modifier les preuves ;
- item multi-collèges : une preuve canonique ne crée pas de doublon.

### Algorithmes

- item jamais étudié ;
- item déclaré ancien sans preuve récente ;
- QCM faible récent ;
- QCM réussi ancien ;
- annale avec 0, 1, 2 ou 3 discordances ;
- oubli d’un Rang A réel ;
- donnée Rang A absente ;
- lacune critique et lacune récurrente ;
- série SM-2 longue avec échec puis reprise ;
- comparaison hebdomadaire sans snapshot précédent.

### Interface

- largeur desktop complète ;
- fenêtre intermédiaire ;
- mobile ;
- état vide ;
- erreur de chargement ;
- boutons principaux accessibles au clavier ;
- aucun bouton Obsidian doublonné ;
- aucune mention « + Mnemo Image » résiduelle.

## Hors périmètre immédiat

- refonte visuelle globale d’Aujourd’hui, Planning ou de la vue thème ;
- remplacement immédiat du moteur de maîtrise par une formule non mesurée ;
- ajout de nouvelles sources externes avant stabilisation des sources existantes ;
- création d’un simulateur ECOS dans cette feuille de route ;
- suppression de l’historique SQLite ou Notion ;
- exécution automatique contre les données live sans rapport dry-run lorsque l’opération peut
  modifier Notion ou le vault Obsidian.

## État des captures et références visuelles

Le dossier fourni `design_handoff_synapse_refonte` contient actuellement le README et le handoff
de conception, mais pas encore les screenshots annoncés. Ils seront ajoutés aux sections concernées
dès réception, sans changer les décisions déjà validées.

## Critère de réussite global

La feuille de route sera considérée comme réalisée lorsque :

- la reprise du 20 août est propre et non destructive ;
- le Sprint est persistant et masquable ;
- un collège peut être confirmé automatiquement selon ses preuves ou manuellement ;
- le planning affiche les révisions et consolidations futures ;
- les écrans signalés comme moches suivent une grammaire Linear cohérente ;
- QCM, annales, maîtrise et priorisation ont des rôles séparés et expliqués ;
- les biais connus sont corrigés ou explicitement documentés ;
- les tests et rapports avant/après empêchent de déclarer un algorithme amélioré sans preuve.
