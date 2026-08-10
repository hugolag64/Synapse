# Recette du lot 1 — correctifs rapides (10 août 2026)

Branche `fix/lot1-correctifs-rapides`, partie de `main` à `0474ddc`.

Suite de tests complète : **1346 passed, 0 échec** (`./.venv/Scripts/python.exe -m pytest tests/ -q`).
Le plan annonçait des échecs préexistants dans deux modules dépréciés : ils ont disparu entre-temps,
la suite est intégralement verte.

Aucune capture d'écran n'accompagne ce compte rendu, contrairement à ce que prévoyait le plan : le
volet navigateur n'était pas affiché pendant la session, donc la capture d'image était indisponible.
Les vérifications visuelles ont été remplacées par des mesures de styles calculés dans la page, plus
robustes qu'une capture pour ce qui est jugé ici — fonds, bordures et ratios de contraste.

## B1 — Le mode sombre ne se sauvegardait pas

**Symptôme** : basculer en thème sombre, puis changer de page, ramenait le thème clair.

**Cause** : `toggle_dark_mode` ne modifiait que l'objet `ui.dark_mode()` de la page courante et n'écrivait
jamais la préférence. La coquille relit pourtant `data_store.preferences["dark_mode"]` à chaque rendu,
donc l'ancienne valeur écrasait le choix dès la navigation suivante.

**Correctif** : la fonction appelle désormais `data_store.set_preference("dark_mode", …)` avec la valeur
effective, comme le fait déjà le sélecteur de fuseau horaire.

**Recette** : bascule en sombre → `dark_mode: True` écrit dans `data/data_cache.json` → thème conservé
après navigation vers `/items` → **et conservé après un arrêt et un redémarrage complets de l'application**.

## B2 — Le panneau télémétrie avait un fond gris différent et illisible

**Symptôme** : l'expansion « Consommation, télémétrie & partiels importés » avait un fond gris qui ne
correspondait à aucune autre surface, et son contenu était difficile à lire.

**Cause** : le panneau portait `bg-slate-900/40` en dur, absent de l'expansion voisine. Plus largement,
tout son contenu était écrit en Tailwind figé sur une palette sombre — `bg-slate-800/50`, `text-slate-200`
à `text-slate-500`, `text-emerald-400`, `text-red-400` — donc indifférent au thème.

**Correctif, en deux temps.** D'abord la conversion de l'ensemble du bloc aux variables du design system,
via douze classes de rôle (`.se-tele-*`) et une classe partagée `.se-diag-expansion` appliquée aux deux
expansions de la section.

La recette a ensuite montré que la conversion ne suffisait pas : `--success`, `--warning` et `--danger`
sont déclarés « stables clair & sombre » dans `design_tokens.py` et calibrés pour un fond sombre.
En thème clair, les montants tombaient à 2,57 de contraste, les titres de section à 2,36 — sous le seuil
WCAG AA de 4,5. Un tour de correction a donc ajouté, de façon purement additive, `--success-text` et
`--danger-text`, définis une fois par thème, et fait passer les titres de section de `--text-dim` à
`--text-muted`. `--success`, `--warning` et `--danger` sont inchangés : rien d'autre dans l'application
n'est affecté.

**Recette** : les deux expansions ont un fond et une bordure strictement identiques dans les deux thèmes.
Ratios de contraste mesurés dans l'application, texte contre son fond effectif :

| Classe | Avant (clair) | Après (clair) | Après (sombre) |
|---|---|---|---|
| `.se-tele-value` | 2,57 | **4,81** | 6,77 |
| `.se-tele-cost` / `.se-tele-ok` | 2,57 | **4,81** | 6,77 |
| `.se-tele-err` | 3,75 | **6,26** | 4,65 |
| `.se-tele-section-title` | 2,36 | **4,79** | 5,14 |
| `.se-tele-muted` | 5,04 | 5,04 | 5,40 |
| `.se-tele-name` / `.se-tele-strong` | 18,31 | 18,31 | 16,55 |

Les huit classes franchissent le seuil AA dans les deux thèmes.

## B3 — Aucune barre de défilement dans « Couverture DP par item »

**Symptôme** : la liste des 367 items ne défilait pas dans son cadre ; aucune barre visible.

**Cause — les deux hypothèses du plan étaient fausses.** Le diagnostic mené dans le navigateur a montré
que la feuille de style est bien présente dans le document, et que `max-height:520px` comme
`overflow-y:scroll` sont appliqués et respectés sur `.dpc-scroll`.

La vraie cause : `.dpc-scroll` est une colonne flex et `.dpc-table` en est un enfant direct, donc un
élément flex avec `flex-shrink:1` par défaut. Il était comprimé de sa hauteur naturelle de 18508 px à
518 px pour tenir dans les 520 px du parent, et son propre `overflow:hidden` masquait les lignes.
`clientHeight` valait `scrollHeight` : rien ne débordait, donc aucune barre n'avait de raison d'exister.

**Correctif** : `flex:0 0 auto` sur `.dpc-table`. `overflow:hidden` est conservé — il arrondit les coins
par-dessus les lignes et ne rogne plus rien une fois l'élément à sa hauteur naturelle. `.dpc-scroll` est
inchangé, et aucune fonction d'injection de style n'a été ajoutée : elle aurait traité un problème qui
n'existe pas.

**Recette** : filtre « Tous », 367 lignes → `clientHeight` 520, `scrollHeight` 18510, défilement honoré.
Liste courte → le cadre se referme à 231 px sans laisser de vide.

## B4 — La liste « Récents » de la sidebar était trop longue

**Symptôme** : jusqu'à cinq fiches récentes alourdissaient la navigation latérale.

**Cause** : `_recent_nav_entries(limit=5)`.

**Correctif** : limite à 3. Baisser la valeur ne suffisait pas : la fonction écarte ensuite les cours
disparus du store, ce qui aurait souvent produit moins de trois entrées. Elle sur-échantillonne donc
l'historique puis tronque après filtrage.

**Recette** : après ouverture de quatre fiches différentes, exactement trois entrées sous « Récents ».

## B5 — La correction n'était pas proposée à la fin d'un Tuteur DP

**Symptôme** : après un Tuteur DP, aucune correction ne s'ouvrait ; il fallait aller la rechercher dans
l'historique QCM.

**Cause** : la fonction d'ouverture du Tuteur passait `on_complete=lambda _sid: None`, là où le flux
standard enchaîne vers la correction.

**Correctif** : le Tuteur réutilise `_open_answer_dialog`, la fonction du flux standard, au lieu de
dupliquer l'appel au lecteur. Aucun comportement perdu au passage : fermeture du dialogue, notification
et rafraîchissement sont conservés dans le même ordre.

**Recette — partiellement vérifié, à confirmer.** Le dialogue du Tuteur DP s'ouvre correctement et le
lecteur se lance sur la bonne session. En revanche, l'enchaînement final n'a pas pu être exercé de bout
en bout : piloter la dernière case à cocher du lecteur NiceGUI par clic synthétique n'a pas fonctionné,
et `_finish()` refuse — correctement — de finaliser une session dont une réponse est vide. C'est ce
garde-fou qui a bloqué la recette, pas un défaut.

**Seconde cause trouvée par la revue finale.** Le bug avait un deuxième volet que ni la recette ni les
revues de tâche n'avaient vu, parce qu'il ne se manifeste que depuis une des deux entrées.

`_open_session` appelait `refresh()` juste avant d'ouvrir le lecteur. Depuis `/cours/<id>` c'est sans
effet, l'appelant passant `refresh=lambda: None`. Mais depuis `/qcm`, `refresh` vaut `_render`, qui
descend jusqu'à `history_col.clear()` — or le bouton « Tuteur DP » qui a ouvert le dialogue vit dans
`history_col`. Le slot capturé par le lecteur était donc supprimé avant que celui-ci ne s'affiche : le
lecteur, puis la correction, étaient créés dans un slot mort, sans nœud parent côté navigateur.

L'appel `refresh()` anticipé a été supprimé, ce qui aligne le Tuteur sur le flux standard
`_open_generation_dialog`, lequel n'a jamais rafraîchi avant d'ouvrir. Le rafraîchissement n'est pas
perdu : la correction le rejoue dans son `on_back`. Un test verrouille l'absence de l'appel anticipé.

Le correctif est donc vérifié par deux tests dédiés et par trois revues de code indépendantes.
**À confirmer lors de la prochaine génération réelle d'un Tuteur DP, de préférence depuis `/qcm`.**

## Observations relevées en passant

Aucune n'a été traitée dans ce lot.

- **Le même défaut de contraste existe ailleurs.** `.se-label`, `.se-diag-ratio.full` et plusieurs
  libellés de statut de la page Réglages utilisent encore `var(--success)`, `var(--danger)` ou
  `var(--text-dim)` comme couleur de texte. Ils présentent probablement le même problème en thème clair,
  et sans doute pas seulement sur cette page. À verser à l'axe UI de l'audit.

- **Le Tuteur DP hérite d'un contexte hors sujet.** Sur l'item 230 « Douleur thoracique », le contexte
  pédagogique pré-rempli parlait de dyspnée et de classification NYHA, donc d'insuffisance cardiaque.
  C'est la confirmation directe du mécanisme de contamination décrit au chantier C1 de la spec :
  le contexte reprend les énoncés d'une session DP antérieure de l'item.

- **Une session DP a `item_number = 'DP'`** en base (session 220, modèle `exam-simulator`) au lieu d'un
  numéro d'item. À verser à l'axe intégrité des données de l'audit.

- **Le port de la configuration de lancement était faux.** `.claude/run_synapse.bat` force
  `SYNAPSE_ENV=prod`, ce qui fait écouter l'application sur le port 8000, alors que `.claude/launch.json`
  déclare 8082 : la prévisualisation ne pouvait pas s'attacher. Corrigé en ajoutant `SYNAPSE_PORT=8082`
  au script. C'est de l'outillage, pas du code applicatif.

- **Le serveur ne recharge pas à chaud.** En mode prod, `reload=False` : toute vérification d'un
  changement Python exige un redémarrage de la prévisualisation.
