# Chantier A — Correctifs & navigation

**Date** : 2026-08-07
**Statut** : design validé, prêt pour plan d'implémentation

## Contexte

Revue d'usage complète de Synapse (27 captures, dossier `ScreenTest`) ayant produit
~18 demandes hétérogènes. Elles ont été découpées en 4 chantiers indépendants :

| # | Chantier | Périmètre |
|---|---|---|
| **A** | **Correctifs & navigation** | **ce document** |
| B | Design system Linear | cards grises, wizards, largeurs, pages non centrées, animations |
| C | Fond pédagogique | Flash-Zero génératif, acquis antérieurs, fiches orphelines, Sprint EDN |
| D | Planning semaine | vue semaine + calendrier fac |

Le chantier A regroupe les défauts dont la cause racine a été identifiée dans le code
et dont la correction ne dépend d'aucune décision de design. Il passe en premier parce
qu'il débloque des irritants quotidiens sans préempter la refonte visuelle du chantier B.

## Objectif

Supprimer sept défauts fonctionnels confirmés, sans modifier l'apparence générale des
pages (réservée au chantier B) ni la logique pédagogique (réservée au chantier C).

## Périmètre

### A1 — Palette et raccourci de recherche unifiés

**Problème.** Deux palettes coexistent et se recouvrent :

- `frontend/components/command_palette.py` (`Ctrl+K`, `Ctrl+/`, touche `/` seule) —
  recherche de cours **plus** commandes texte `lacune` / `qcm` / `séance`. Stylée en
  Tailwind codé en dur (`bg-white dark:bg-slate-900`, `rounded-2xl`, `shadow-2xl`),
  donc hors design system.
- `frontend/components/item_search_palette.py` (`Ctrl+Alt+P`) — recherche de cours puis
  navigation vers `/cours/{id}`. Sous-ensemble fonctionnel de la précédente, mais
  correctement stylée aux tokens (`var(--bg)`, `var(--border)`, …).

La sidebar affiche par ailleurs `⌘K`, un raccourci macOS sur une application utilisée
sous Windows (`frontend/cockpit_shell.py:253`).

**Découvert pendant la rédaction du plan :** `register_keybindings()` n'est appelé nulle
part dans le dépôt. `Ctrl+K`, `Ctrl+/` et la touche `/` seule n'ont donc **jamais**
fonctionné — seuls le clic sur la barre de recherche et `Ctrl+Alt+P` sur la page Items sont
actifs aujourd'hui. Le chantier câble pour la première fois un raccourci global.

**Décision.** Une seule palette, un seul raccourci : **`Ctrl+Alt+P`**.

- Le squelette retenu est celui de `item_search_palette` (tokens de thème, navigation
  `↑` `↓`, `Entrée` pour ouvrir, `Échap` pour fermer, ligne de résultat
  `ITEM n° · titre · collège`).
- Les commandes texte de `command_palette` (`lacune <texte>`, `qcm <texte>`,
  `séance <texte>`) et son moteur de recherche (`search_index` avec repli sur filtrage
  local) y sont portés.
- `item_search_palette.py` est supprimé une fois la fusion faite.
- `Ctrl+K`, `Ctrl+/` **et la touche `/` seule** sont retirés. La touche `/` seule est un
  piège : elle ouvre la palette dès qu'un slash est saisi hors champ de texte.
- Le badge de la sidebar affiche `Ctrl Alt P`.
- `register_item_search_keybinding` devient redondant et disparaît : la page Items
  hérite du raccourci global.

**Critère d'acceptation.** `Ctrl+Alt+P` ouvre la même palette depuis n'importe quelle
page ; `Ctrl+K` et `/` n'ouvrent plus rien ; les trois commandes texte fonctionnent
depuis cette palette unique.

### A2 — Section « Récents » réellement alimentée

**Problème.** `frontend/cockpit_shell.py:262-264` affiche deux entrées écrites en dur
(« Item 221 · Athérome », « Item 330 · Prescription ») pointant toutes deux vers `/`.
Le commentaire du code les désigne comme un placeholder jamais câblé.

**Décision.** Historique de consultation réel.

- Nouvelle table SQLite `recent_courses(course_id TEXT PRIMARY KEY, opened_at TEXT NOT NULL)`
  dans `backend/core/reviews/local_store.py`, avec migration idempotente comme les
  autres tables du module.
- Écriture (`INSERT … ON CONFLICT DO UPDATE SET opened_at`) à chaque rendu de
  `/cours/{id}`.
- Lecture des 5 dernières entrées, ordonnées par `opened_at` décroissant, résolues en
  cours via `data_store`. Un `course_id` absent du store est ignoré silencieusement
  (cours supprimé côté Notion).
- Libellé : `ITEM {n} · {titre}` tronqué par la règle CSS existante `.lbl`, ou le titre
  seul si le cours n'a pas de numéro d'item. Lien vers `/cours/{id}`.
- **Si la liste est vide, le libellé de groupe « Récents » n'est pas rendu du tout** —
  pas de section vide, et surtout pas de fausses données.

**Critère d'acceptation.** Ouvrir trois fiches item les fait apparaître dans « Récents »
dans l'ordre inverse de consultation ; une base neuve n'affiche aucune section
« Récents ».

### A3 — Report d'une révision relatif à aujourd'hui

**Problème.** Les deux implémentations de `_on_postpone`
(`frontend/pages/todo_cockpit.py:168` et `frontend/pages/dashboard/_cockpit_today.py:353`)
calculent `task.due_date + timedelta(days=days)`. Pour une tâche en retard de cinq jours,
la nouvelle date effective est donc située quatre jours dans le passé : la tâche reste
en retard et l'utilisateur doit cliquer cinq fois pour la repousser à demain.

**Décision.** La date de report devient `max(task.due_date, today) + days`.

- Helper partagé exposé par `backend/core/reviews/` (module de service, pas la page),
  appelé par les deux `_on_postpone`. Les deux callbacks restent dupliqués par ailleurs —
  leur déduplication complète est une dette déjà actée dans l'en-tête de
  `todo_cockpit.py`, hors périmètre ici.
- `postponed_count` continue de s'incrémenter comme aujourd'hui : la pénalité de maîtrise
  (`−5` par report, plafonnée à `−20`) et le bonus de priorité (`+3` par report) sont
  inchangés.

**Critère d'acceptation.** Reporter d'un jour une tâche en retard de cinq jours la place
à demain, et elle disparaît de la liste « en retard ».

### A4 — Tri et largeur de la vue Items

**Problème 1 — tri sans effet.** `frontend/pages/items.py:276` : `_select_sort` met à jour
`filt["sort"]` puis appelle `_draw_list(_all_rows["value"])`. Or `_all_rows["value"]` a été
trié une seule fois, par `_compute()`, au premier rendu. `_draw_list` ne trie jamais. Les
boutons « Item » et « Collège » changent donc uniquement l'état actif du chip.

**Problème 2 — espace mort à droite.** `frontend/pages/items.py:41` : `.it-wrap` est plafonné
à `max-width:1200px`, alors que les autres vues cockpit (`.rv-wrap` par exemple) sont en
`max-width:none` et laissent `.cockpit-main` porter la largeur utile. Sur un écran large,
le contenu s'arrête à 1200 px et laisse une bande vide.

**Décision.**

- `_draw_list` applique `_sort_item_rows(rows, filt["sort"])` avant de filtrer et rendre.
  `_compute()` peut cesser de trier, ou continuer sans conséquence — le tri de rendu fait
  autorité.
- `.it-wrap` passe en `max-width:none`, alignant Items sur les autres vues cockpit.

**Critère d'acceptation.** Basculer « Trier par : Collège » regroupe visiblement les lignes
par collège ; la liste occupe toute la largeur disponible sur écran large, sans changement
perceptible sur un écran de portable.

### A5 — Flash-Zero : croix de fermeture et lisibilité de la correction

**Problème 1 — croix invisible.** `frontend/components/flash_zero_cockpit.py:21` positionne
`.flash-zero-dismiss` en `position:absolute; top:8px; right:8px`, c'est-à-dire exactement
sous le bouton « Lancer » / « Rejouer » qui occupe la droite de la carte dans le flux flex.
La croix apparaît bien au survol mais est recouverte.

**Problème 2 — correction illisible.** `flash_zero_cockpit.py:123-124` empile
`Ta réponse : …` et `Réponse attendue : …` en deux `ui.label` consécutifs de même classe,
sans séparation. Les deux réponses se lisent comme un seul bloc.

**Décision.**

- La croix sort du positionnement absolu et rejoint le flux, **à gauche du bouton
  d'action**. Elle conserve son apparition au survol (`opacity` 0 → 1 sur
  `:hover` / `:focus-within` de la carte) et sa cible d'accessibilité.
- Le bloc correction rend « Ta réponse » et « Réponse attendue » comme deux lignes
  distinctes, chacune avec un libellé discret au-dessus de sa valeur, séparées par un
  espacement explicite. La réponse de l'utilisateur reste visuellement rattachée au
  verdict (`good` / `bad`).
- Suppression de `frontend/components/flash_zero_dialog.py` : ce fichier importe
  `streamlit`, framework abandonné au profit de NiceGUI. Il n'est référencé nulle part.

**Hors périmètre.** L'alignement complet de l'UI de question sur celle de QCM/Annale
(rectangle au survol, mise en page des choix) relève du chantier B. Le caractère figé de
la banque de questions relève du chantier C.

**Critère d'acceptation.** La croix est cliquable au survol sans chevaucher le bouton ;
la correction distingue au premier coup d'œil la réponse donnée de la réponse attendue.

### A6 — Navigation

**A6.1 — Entités cliquables dans le Planning.** Dans `frontend/pages/planning_cockpit.py`,
les blocs rendus dans les cellules de jour par `_draw_day` (lignes 412-432) n'ont **aucun**
gestionnaire de clic. Ils doivent naviguer vers leur ressource :

| Bloc rendu | Cible |
|---|---|
| `plan.slots` de type révision/consolidation | `/cours/{slot.course_id}` |
| `plan.slots` de type `lacune` / `lacune_crit` | `/lacunes` |
| entrée planifiée manuellement | `/cours/{entry['course_id']}` |
| événement Google Calendar | aucune — bloc non navigable |

Correction par rapport à la première rédaction de ce document : le Flash-Zero **n'est pas
rendu** dans la grille du Planning — sa carte vit dans la vue Aujourd'hui, où son bouton
« Lancer » ouvre déjà le quiz. Rien à faire ici.

Les lignes de synthèse du bloc focus (`_draw_focus`, ligne 373), qui déclenchent
`_focus_action(kind)`, sont un composant distinct des cellules de jour et **restent
inchangées**.

**A6.2 — Lien collège depuis la fiche item.** `frontend/pages/course_detail_cockpit.py:400`
rend `ui.link(college, "/colleges")` : le nom du collège renvoie vers la liste générique de
tous les collèges, pas vers celui-ci. Il doit pointer vers `/items?college={college}`.
`items.py:159` consomme déjà ce paramètre de requête et applique le filtre initial, aucun
travail supplémentaire côté cible. C'est ce qui permet de circuler entre les items d'un
même collège.

**A6.3 — Retrait de Semestres de la navigation.** L'entrée `("◫", "Semestres", "/semestres", None)`
est retirée de `_NAV_GROUPS` dans `frontend/cockpit_shell.py`, ainsi que l'entrée
correspondante de `_TITLE_TO_NAV`. `_BOTTOM_NAV` ne la contient pas déjà. **La route,
`frontend/pages/semestres.py` et `frontend/pages/semestres_cockpit.py` sont conservés** et
restent accessibles par URL directe.

**Critère d'acceptation.** Cliquer une entité du planning ouvre sa cible ; cliquer le nom du
collège sur une fiche item affiche la liste des items de ce collège ; « Semestres » ne figure
plus dans la sidebar mais `/semestres` répond toujours.

## Hors périmètre du chantier A

Explicitement exclus, traités ailleurs :

- Cards grises → Linear (QCM, Annales, Examen blanc, Prépa), wizards à redessiner
  (validation de séance, palette, mnémo), pages non centrées (Points faibles, Revue hebdo,
  Statistiques), animation de déploiement des collèges, uniformisation des boutons et bentos
  de la vue item → **chantier B**.
- Banque Flash-Zero générative, marquage des acquis antérieurs à Synapse, fiches sans numéro
  d'item, logique du Sprint EDN → **chantier C**.
- Vue semaine du planning, branchement du calendrier fac → **chantier D**.

Également relevé pendant l'analyse mais non traité ici, car appartenant au socle de calcul
et non à l'interface : `backend/core/reviews/mastery.py:279` ajoute la raison « Socle Rang A
critique (<40%) » même lorsque c'est le score global qui a déclenché le niveau critique, sans
qu'aucune preuve de Rang A n'existe. Message trompeur, à corriger dans le chantier C avec le
reste de la logique pédagogique.

## Risques

- **A1** est le seul point à surface de régression notable : trois raccourcis disparaissent
  et deux composants fusionnent. Le risque est qu'une page appelle encore
  `open_item_search_palette` après suppression. À couvrir par une recherche exhaustive des
  appelants avant suppression.
- **A2** ajoute une écriture SQLite sur le chemin de rendu de `/cours/{id}`, page déjà
  identifiée comme lente lors de l'audit du 2 août (verrou SQLite). L'écriture doit rester
  une seule requête non bloquante, sans invalidation de cache.
- **A3** modifie un comportement que l'utilisateur a intégré. L'effet est voulu et
  souhaitable, mais change ce que fait un bouton existant.

## Tests

Chaque point porte un critère d'acceptation vérifiable manuellement, listé ci-dessus. Les
points suivants se prêtent à un test automatisé et doivent en recevoir un :

- `A3` — fonction pure de calcul de la date de report : tâche en retard, tâche du jour,
  tâche future, `days` > 1.
- `A4` — `_sort_item_rows` appliqué au rendu : vérifier que changer le mode de tri change
  l'ordre rendu, pas seulement l'état du chip.
- `A2` — écriture puis lecture des récents : ordre inverse de consultation, ré-ouverture
  d'un cours déjà présent (mise à jour et non doublon), `course_id` inconnu du store ignoré.
