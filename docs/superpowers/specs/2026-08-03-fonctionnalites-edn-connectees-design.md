# Fonctionnalités EDN connectées — Design

Date : 3 août 2026  
Statut : design validé en conversation, à relire avant implémentation

## Objectif

Rendre réellement accessibles les fonctionnalités Flash-Zero, Sprint Countdown et Tuteur DP, puis relier les
résultats externes, les erreurs, les lacunes et la projection EDN dans une chaîne locale, explicable et exploitable
depuis le cockpit NiceGUI.

## Périmètre

Le chantier couvre :

- F2 : import initial de résultats EDNpro/Hypocampus depuis des fichiers CSV ou JSON ;
- F3 : indicateur consultatif de potentiel de gain ;
- F4 : profil personnel des erreurs ;
- F5 : projection de couverture et de maîtrise jusqu'à l'EDN ;
- F6 : suggestions automatiques de lacunes après erreurs répétées ;
- intégration cockpit du Flash-Zero comme tâche interne du matin ;
- intégration du Sprint Countdown dans le Dashboard ;
- intégration du Tuteur DP depuis l'historique de la vue Item.

Les connecteurs automatisés aux sites EDNpro/Hypocampus et l'export Google Calendar ne font pas partie de la
première tranche. Ils devront produire ou consommer les mêmes contrats que l'import fichier.

## Architecture et source de vérité

SQLite reste la source locale de vérité pour les résultats, les erreurs, les lacunes et les recommandations. Les
services métier restent indépendants du rendu NiceGUI ; les widgets et dialogues ne font qu'appeler ces services.

Les briques existantes sont réutilisées :

- `FlashZeroService` conserve sa banque locale et devient consommable par le cockpit ;
- `SprintCountdownService` conserve le calcul de phase et reçoit les agrégats de progression ;
- `PracticeService` génère les sessions Tuteur DP ;
- `local_store` conserve les sessions, tentatives, propositions et lacunes existantes.

Les recommandations sont consultatives : elles expliquent leurs preuves et ne modifient pas silencieusement la
maîtrise. Une maîtrise n'est enrichie par un résultat externe qu'après import valide et dédoublonné.

## Modèle de données

### Résultats externes

Une table `external_results` stocke un résultat normalisé : source, identifiant externe, date, item, type
d'activité, score, nombre total de questions, scores Rang A/B éventuels et métadonnées JSON. La clé logique
`(source, external_id)` rend l'import idempotent. Les colonnes inconnues du fichier sont conservées dans les
métadonnées ; les colonnes obligatoires manquantes produisent une erreur de ligne explicite.

Format minimal accepté :

```text
source, external_id, session_date, item_number, activity_type,
score_percent, total_questions, rank_a_percent, rank_b_percent
```

Le JSON accepte les mêmes champs sous forme d'objet ou de liste d'objets. Chaque import retourne un rapport avec
nombre de lignes acceptées, mises à jour, ignorées et erreurs détaillées.

### Signaux d'erreur

Une table `error_signals` relie une erreur à sa tentative ou à son résultat externe. Les catégories contrôlées sont
`oubli`, `raisonnement`, `piege_edn`, `rang_a`, `rang_b`, `inattention`, `temps` et `non_classe`. Le système conserve
la catégorie `non_classe` quand les données ne permettent pas une inférence fiable.

### Suggestions et tâches produit

Une table de recommandations ou un mécanisme équivalent conserve le type, l'item, les preuves, la date, le statut
(`proposée`, `acceptée`, `ignorée`, `résolue`) et une clé de déduplication. Cette clé empêche une nouvelle suggestion
identique tant qu'une lacune active existe pour le même motif.

## Règles métier

### F2 — Import

L'import vérifie les dates, les pourcentages, les identifiants et les items. Il ne rejette pas une ligne simplement
parce qu'une colonne facultative est absente. Un import répété du même résultat met à jour les métadonnées au lieu de
créer une nouvelle preuve.

### F4 — Profil d'erreurs

Le profil regroupe les signaux par catégorie, item et période. Il expose fréquence, récence, score moyen associé et
part des erreurs Rang A/B. Il ne fabrique pas de catégorie à partir d'un simple score global.

### F6 — Lacunes automatiques

Une suggestion apparaît après au moins deux signaux comparables sur le même item ou thème dans les 30 derniers
jours. Elle affiche les preuves déclenchantes et reste révisable avant création. L'acceptation appelle le mécanisme
existant `add_weak_point_full` ; l'ignorance est tracée et ne supprime pas l'historique.

### Flash-Zero

Le quiz sélectionne en priorité les erreurs récentes et répétées, puis complète avec la banque EDN locale. Une seule
tâche Flash-Zero est créée par jour et par fuseau métier. Elle est interne à Synapse, dure cinq à dix minutes et ne
crée pas automatiquement d'événement Google Calendar.

### Tuteur DP

Depuis l'onglet Historique de la vue Item, chaque DP ou évaluation compatible expose une action « Ouvrir le Tuteur
DP ». Le service reçoit le contexte du dossier, l'item, les erreurs et les lacunes associées, puis crée une session
`PracticeKind.DP` via `PracticeService`. La session générée reste consultable dans l'historique.

### Sprint Countdown et F5

Le Dashboard affiche le compte à rebours, la date cible, la phase, les items étudiés, la maîtrise moyenne, les
révisions restantes et le retard. F5 calcule une projection hebdomadaire en trois scénarios : prudent, central et
ambitieux, à partir du rythme réel des 28 derniers jours, de la capacité quotidienne et de la charge restante.

### F3 — Potentiel de gain

F3 produit un indicateur consultatif par item, calculé avec l'importance EDN, l'écart de maîtrise, la fréquence des
erreurs, la disponibilité d'entraînement et le coût estimé en minutes. L'interface le présente comme une priorité
relative, jamais comme une garantie de classement.

## Parcours utilisateur

1. Un fichier EDNpro/Hypocampus est importé depuis le cockpit et son rapport est affiché.
2. Les erreurs sont regroupées dans le profil personnel.
3. Les répétitions déclenchent des suggestions dans l'écran Lacunes, avec preuves et actions Créer/Ignorer.
4. Le Dashboard propose le Flash-Zero du matin et affiche le Sprint Countdown enrichi.
5. Depuis un Item, l'onglet Historique permet d'ouvrir le Tuteur DP sur le dossier sélectionné.
6. La projection et le potentiel de gain utilisent les données importées et locales disponibles.

## Tolérance aux erreurs

Les imports mal formés sont isolés par ligne et n'empêchent pas l'import des lignes valides. Une panne IA ne bloque
ni le planning ni les révisions ; le Flash-Zero fonctionne avec la banque locale. Une panne de synchronisation
externe ne supprime aucune donnée déjà importée. Les recommandations peuvent rester absentes ou obsolètes sans
altérer les scores existants.

## Vérification

Les tests couvriront :

- validation et idempotence CSV/JSON ;
- regroupement et récence des catégories d'erreurs ;
- seuil de deux signaux et déduplication F6 ;
- sélection Flash-Zero et unicité quotidienne par fuseau ;
- calcul des trois scénarios F5 et du classement relatif F3 ;
- création d'une session Tuteur DP avec contexte Item/Historique ;
- rendu des cartes Dashboard, Item Historique et Lacunes ;
- non-régression de la suite complète et fonctionnement sans service externe.

## Découpage d'implémentation

L'ordre d'implémentation est :

1. contrats SQLite et import F2 ;
2. profil F4 et suggestions F6 ;
3. intégration Flash-Zero dans le cockpit et la routine du matin ;
4. Tuteur DP dans l'onglet Historique Item ;
5. Sprint Countdown enrichi et projection F5 ;
6. indicateur F3 et documentation des formats d'import ;
7. vérification complète et mise à jour de l'audit.
