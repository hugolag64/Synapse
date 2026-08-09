# Neutralisation non destructive de la dette de reprise

> Spécification validée le 9 août 2026 pour préparer la reprise d’étude du 20 août.

## Objectif

À partir du 20 août 2026, Synapse ne doit plus présenter comme dette active les tâches dont
l’échéance est antérieure à la date de reprise. Cette neutralisation doit être purement métier :
l’historique SQLite, les dates théoriques Notion et les preuves d’étude restent inchangés.

La règle doit être unique et réutilisable par Aujourd’hui, Planning, la notification du matin,
la vue Collèges, la vue Items et Flash-Zero. La vue détail d’un item conserve un accès aux tâches
neutralisées afin de permettre une reprogrammation manuelle ultérieure.

## Règle métier

La préférence `study_resume_date` est la source de vérité. Elle est lue et validée par une petite
fonction de domaine, avec `2026-08-20` comme repli sûr.

Pour une tâche de révision ou de consolidation :

- une échéance effective strictement antérieure à la date de reprise est neutralisée des flux actifs ;
- une échéance égale ou postérieure à la date de reprise reste active ;
- aucune ligne `review_history` n’est créée, modifiée ou supprimée par cette opération ;
- une tâche neutralisée reste générable via un mode explicite réservé aux écrans de détail et aux
  actions manuelles ;
- une consolidation déjà protégée par un gate `not_before` conserve son comportement existant.

Pour Flash-Zero :

- les signaux antérieurs à la date de reprise ne servent pas à choisir les nouvelles priorités ni à
  générer de nouvelles questions ;
- les questions déjà générées et leur historique restent consultables ;
- les signaux postérieurs restent classés selon l’algorithme existant.

## Architecture retenue

### 1. Module de domaine de reprise

Créer `backend/core/reviews/reentry.py`, sans I/O, avec :

- `DEFAULT_STUDY_RESUME_DATE` ;
- `get_study_resume_date(preferences=None) -> date` ;
- `is_before_study_resume(value, resume_date=None) -> bool` ;
- `filter_active_review_tasks(tasks, resume_date=None) -> list` ;
- `filter_post_resume_signals(signals, resume_date=None) -> list`.

Les fonctions sont pures et testables avec des dates explicites. Elles ne connaissent ni NiceGUI,
ni SQLite, ni Notion.

### 2. Service de révision

Ajouter un paramètre explicite `active_only` à `ReviewService.generate_reviews()` et
`generate_all_reviews()`. Le mode par défaut reste rétrocompatible (`False`) pour préserver l’accès
aux données complètes et les usages manuels. Les flux actifs appellent le service avec
`active_only=True`, ce qui applique le filtre central après calcul des échéances effectives.

Les écrans concernés sont Aujourd’hui, Planning, notification du matin, lundi, Collèges, Items et
le shell de navigation. Le détail d’un item reste en mode complet.

### 3. Consolidation et planning

`get_due_consolidation_tasks()` applique le même filtre aux tâches non protégées par un gate. Une
consolidation gated à la date de reprise reste visible selon la logique de reprise historique
existante. `PlanningService` reste un service de composition : il reçoit déjà des tâches filtrées
et ne recrée pas une seconde règle de reprise.

### 4. Flash-Zero et gain items

`FlashZeroService` filtre les signaux avant la sélection de priorité, avant la génération IA et lors
de la sélection ciblée du quiz. Le dashboard filtre également les signaux transmis aux priorités de
gain afin que la carte Aujourd’hui ne réintroduise pas indirectement l’ancienne dette.

## Alternatives écartées

1. **Filtrer dans chaque page** : risque de divergences entre Aujourd’hui, Planning et Flash-Zero.
2. **Réécrire les dates ou créer des validations/ignores SQLite** : détruit la distinction entre
   historique et dette active et fabrique une dette synthétique.
3. **Décaler toutes les tâches anciennes au 20 août** : contraire à la règle « aucune dette
   synthétique » ; seules les consolidations explicitement gated conservent leur comportement.

## Tests et critères d’acceptation

- une tâche échue avant le 20 août est absente d’un flux `active_only` ;
- une tâche échéant le 20 août ou après reste visible ;
- le mode complet retourne les mêmes tâches qu’avant le filtre ;
- les lignes SQLite restent identiques après génération active ;
- les consolidations gated restent visibles à leur date de gate ;
- les signaux Flash-Zero antérieurs sont ignorés pour les nouvelles priorités ;
- la suite complète existante reste verte ;
- la feuille de route indique la tranche réalisée et la prochaine tranche.

## Hors périmètre

- reprogrammation manuelle avec nouvelle interface ;
- modification visuelle des vues Aujourd’hui, Planning ou thème ;
- refonte des algorithmes QCM, annales, maîtrise ou statistiques ;
- suppression ou migration de l’historique existant.
