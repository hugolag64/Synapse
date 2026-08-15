# Migration locale SQLite des Items et Collèges — conception

**Date** : 15 août 2026  
**Statut** : conception approuvée par l’utilisateur  
**Périmètre initial** : migration globale de la source runtime vers SQLite, avec corrections fonctionnelles des vues Items/Collèges.

## Objectif

Faire de `data/synapse_local.db` la source de vérité runtime de Synapse, migrer tous les écrans vers cette base sans changer leur comportement hors périmètre, puis corriger la cohérence des vues `/items`, `/colleges` et `/cours/{id}`.

Notion ne sera plus une source de vérité ni une cible d’écriture automatique. `data_cache.json` servira de snapshot d’import et de secours. Les imports futurs seront explicites, simulés, comparés et validés dans Paramètres.

## Décisions métier

- `/items` représente les 367 items EDN officiels, une ligne par item.
- `/colleges` représente le catalogue local consolidé, y compris les collèges vides.
- Un item multi-collèges apparaît dans chacun de ses collèges ; les KPI globaux dédupliquent les items.
- Un item officiel sans fiche locale reste visible avec l’état « fiche manquante ».
- Une fiche peut couvrir plusieurs collèges.
- Les ressources sont attachées aux fiches et peuvent concerner plusieurs collèges.
- Depuis un collège, le PDF spécifique est principal ; à défaut, une ressource partagée, puis la ressource principale manuelle. Depuis `/items`, les ressources sont toutes affichées groupées.
- Le référentiel officiel et les rattachements réellement présents sont conservés séparément.
- Les surcharges locales sont autorisées, prioritaires, justifiées et historisées.
- Les 125 cours hors collège/item sont archivés, masqués des vues actives et restaurables.

## Modèle de données local

SQLite étendra `data/synapse_local.db` au lieu de créer une seconde base.

### Entités principales

- `items` : UUID local stable, numéro EDN unique, titre officiel local, titre local optionnel, statut d’archivage, provenance et dates.
- `colleges` : UUID local stable, libellé local, statut actif/archivé, ordre d’affichage.
- `college_aliases` : noms officiels et historiques associés à un collège local.
- `course_fiches` : UUID local, référence externe Notion facultative, item parent, titre importé, données de ressource et statut d’archivage.
- `archived_courses` : cours historiques sans item/collège conservés hors du catalogue actif, avec payload d’origine et motif d’archivage.
- `fiche_colleges` : relation plusieurs-à-plusieurs entre fiches et collèges.
- `official_item_colleges` : rattachements du référentiel `data/nexternat_items.json`, traduits par `data/college_consolidation.json`.
- `local_item_college_overrides` : ajouts/retraits locaux, justification obligatoire, auteur local et provenance.
- `resources` : PDF, note Obsidian ou URL, statut de validité, date de contrôle et fiche propriétaire.
- `resource_colleges` : collèges concernés par une ressource.
- `audit_log` : opérations d’administration, valeur avant/après, provenance, justification et horodatage.
- `import_runs` et `import_changes` : simulation, diff, application, résultat et restauration.

Les historiques d’apprentissage, preuves, sessions, révisions, OIC, annales, IA et Anki restent dans la même base et seront reliés à l’UUID de l’item ou de la fiche selon leur granularité actuelle. Les identifiants externes Notion sont conservés uniquement pour la traçabilité et les imports.

## Autorité et provenance

L’ordre de priorité runtime est :

1. surcharge locale validée ;
2. valeur métier locale éditée ;
3. référentiel officiel importé ;
4. donnée importée brute.

Chaque valeur modifiable expose son origine, sa date de modification et, lorsqu’elle remplace le référentiel, une justification obligatoire.

Le référentiel officiel est chargé depuis `data/nexternat_items.json`. Les noms sont consolidés vers le catalogue local via `data/college_consolidation.json`. Une mise à jour du référentiel est importée dans une zone de proposition ; elle ne modifie rien avant validation champ par champ ou par lot.

## Maîtrise et planification

- Une maîtrise publique unique est calculée par item.
- Toutes les preuves locales sont agrégées entre les fiches : révisions, sessions, QCM, OIC, annales, sessions IA, Anki et évaluations manuelles.
- La fusion conserve l’algorithme actuel et corrige d’abord ses entrées, ses alias et ses périmètres.
- Une tâche de révision est unique par item.
- Une maîtrise déclarée est planifiable, mais porte toujours `Déclaré`.
- Une déclaration sans preuve ne peut pas être `Maîtrisé` ; elle peut devenir `Fragile` ou `Critique` avec sa provenance visible.
- Les statuts pédagogiques restent `À préparer`, `À lire`, `En construction`, `À consolider`, `Fragile`, `Critique`, `Maîtrisé`.
- Le cycle J3/J7/J14/J30 est une métrique secondaire de consolidation, jamais le verrou de validation automatique.

## Vues et navigation

### `/items`

- 367 lignes maximum pour les items officiels actifs.
- Collèges affichés en liste compacte avec détail au survol.
- Fiches manquantes explicitement signalées.
- Filtres cumulables : collège, Fragile/Critique, En retard, recherche et tri.
- Provenance `Déclaré`/`Mesuré` visible à côté du score.
- Absence de maîtrise affichée comme `Non évaluée` ou `Aucune donnée`.
- Les anciennes URLs `/cours/{id}` continuent de fonctionner.

### `/colleges`

- Catalogue local consolidé, collèges vides inclus.
- Items officiels attendus comptés même si la fiche manque.
- « Sans PDF » mesure les rattachements item-collège sans ressource utilisable pour ce collège.
- KPI globaux dédupliqués au niveau item.
- Niveaux : `Non commencé`, `En cours`, `Parcouru`, `Consolidé`, `Validé`.
- Pourcentages visibles au survol des pastilles.
- Validation automatique : tous les items ont une preuve réelle et aucun n’est `Critique`.
- Validation manuelle possible avec justification ; une modification ultérieure produit un avertissement `À revalider`.

### Détail `/cours/{id}`

- Résolution vers l’item canonique selon le premier collège officiel présent, puis fallback déterministe.
- Ancienne URL de fiche conservée comme contexte de navigation.
- Une page item unique avec section « Collèges et ressources » groupée.
- Depuis un collège, sélection contextuelle du PDF principal.
- Détail des preuves : nombre, types et dates récentes.

## Administration dans Paramètres

L’administration locale sera mono-utilisateur, sans authentification.

Elle permettra :

- gestion des items, fiches, collèges, alias, titres, ressources et rattachements ;
- création rapide d’une fiche manquante préremplie ;
- recherche et formulaires guidés avec aperçu des impacts ;
- validation par lot des propositions de référentiel ;
- fusion contrôlée de doublons ;
- journal des changements et restauration de versions ;
- contrôle des ressources invalides (`À vérifier`/`Invalide`) ;
- import initial et imports futurs depuis `data_cache.json`, puis éventuellement Notion en lecture seule.

Chaque import suit : sauvegarde → simulation → diff → validation → application → vérification. Une sauvegarde nommée est conservée dans `data/backups/` jusqu’à suppression manuelle. Une migration échouée restaure automatiquement la sauvegarde et bloque explicitement le domaine concerné.

## Phases d’exécution

1. **Socle SQLite** : migrations versionnées, schéma métier, provenance, audit log et sauvegardes.
2. **Import initial** : simulation `data_cache.json`, rapprochement par identifiant, propositions ambiguës, archivage des 125 cours hors périmètre, import des 367 items officiels.
3. **Repositories runtime** : déplacer tous les écrans de `data_store.cours` vers SQLite sans modifier leur comportement fonctionnel.
4. **Maîtrise et planification** : agrégation item, API publique unique, tâches item-level et provenance.
5. **Items/Collèges** : déduplication, mapping multi-collèges, navigation, statuts, filtres, ressources et KPI.
6. **Paramètres** : assistant d’import, administration, fusion, overrides, journal et restauration.
7. **Performance et tests** : caches, index, rendu ciblé, tests unitaires et snapshot d’intégration anonymisé.

## Tests et critères d’acceptation

- Les migrations sont idempotentes et testées sur base vide et base existante.
- Un import simulé ne modifie aucune donnée.
- Un import appliqué puis annulé restitue exactement l’état précédent.
- Les rapprochements ambigus ne sont jamais fusionnés automatiquement.
- SQLite contient les 367 items officiels et les fiches importées conservées.
- `/items` contient une ligne par item, sans doublon.
- Les KPI globaux dédupliquent les items multi-collèges.
- La maîtrise est identique quelle que soit la fiche ouverte.
- Les preuves sont agrégées entre fiches.
- Les tâches sont uniques par item.
- Les fils d’Ariane aboutissent toujours à une liste contenant l’item ou à un état « fiche manquante » explicite.
- Chaque statut produit possède un libellé, une couleur et une classe CSS.
- Les filtres et dépliages n’exécutent pas de recalcul complet.
- Les tests d’intégration utilisent un snapshot anonymisé réaliste et couvrent SQLite, mapping, Items, Collèges, détail et planification.
