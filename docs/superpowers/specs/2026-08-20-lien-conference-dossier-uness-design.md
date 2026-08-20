# Lien conférence DFASM ↔ dossier UNESS réalisé — conception

**Contexte source :** [`docs/NOTE_CONFÉRENCES_DFASM_UNESS.md`](../../NOTE_CONFÉRENCES_DFASM_UNESS.md),
section « Dossier UNESS après la conférence » ; case à cocher restée ouverte : « Associer chaque
dossier UNESS à la conférence correspondante ».

**Objectif :** relier une conférence DFASM1 déjà validée (`conferences.match_status = 'matched'`)
au dossier UNESS que l'utilisateur a réellement réalisé le même jour, en écrivant enfin
`conferences.uness_session_id` — colonne présente en base depuis la conception du planning
(20 août 2026) mais jamais renseignée. Ce lien est le prérequis attendu par la feuille de route
Batch conférences ([`2026-08-20-uness-conferences-gemini-batch.md`](../plans/2026-08-20-uness-conferences-gemini-batch.md),
§1.2) : l'analyse Batch d'une conférence a besoin de savoir quel dossier UNESS lui correspond.

**Hors périmètre de cette conception** (traité ailleurs ou plus tard) :

- Enregistrement audio, transcription, analyse IA de la conférence — feuille de route Batch,
  reprise séparément.
- Modification du dossier UNESS lui-même ou de ses questions — cette conception ne touche que la
  colonne `conferences.uness_session_id`.
- Correction d'un lien déjà confirmé (« délier », re-choisir un autre dossier) — non demandé,
  ajouté seulement si le besoin se présente réellement (YAGNI).
- Conférences DFASM2 (jeudi) — hors périmètre de l'utilisateur (DFASM1), comme pour l'import du
  planning.

---

## 1. Ce que `uness_session_id` référence

`uness_session_id` pointe vers `uness_annales.id` — le **dossier** UNESS tel qu'aspiré et importé
(titre, matière, date de collecte), pas vers une sous-partie individuelle
(`ai_practice_sessions.id`). C'est le niveau dont parle la note métier (« un dossier UNESS »), et
c'est aussi le niveau attendu par la feuille de route Batch (« un identifiant d'annale ou de
session UNESS déjà importé »). Un dossier composé de plusieurs sous-parties (`ai_practice_sessions`
liées par `annale_id`) reste rattaché dans son ensemble à la conférence.

## 2. Mécanisme de rapprochement

**Auto-suggestion par date, confirmation manuelle obligatoire** — même logique que le
rapprochement collège déjà en place pour les conférences (`matched` / `needs_validation` /
`skipped`), pas d'écriture silencieuse.

À l'affichage du panneau conférences, pour chaque conférence `matched` sans lien
(`uness_session_id IS NULL`), Synapse cherche les dossiers `uness_annales` dont la date de
collecte (`DATE(collected_at)`) tombe le même jour calendaire que la conférence. Une conférence
sans aucun candidat n'apparaît simplement pas encore dans la liste à confirmer — elle y entrera dès
qu'un dossier sera aspiré ce jour-là, sans action de récupération à prévoir.

Une conférence non encore validée côté collège (`needs_validation` ou `skipped`) n'est jamais
proposée : la validation du rapprochement collège reste un préalable.

## 3. Choix du candidat

Toujours un sélecteur, même à un seul candidat — uniformité plutôt qu'un raccourci à un seul choix
qui changerait de forme selon le nombre de dossiers du jour. Le libellé de chaque option combine le
titre et la matière du dossier (`"<titre> — <matiere>"`) pour permettre de distinguer deux dossiers
collectés le même jour.

## 4. Composants

- **`backend/core/reviews/local_store.py`** :
  - `list_uness_annales_by_date(date: str) -> list[dict]` — `SELECT * FROM uness_annales WHERE
    DATE(collected_at) = ? ORDER BY collected_at`.
  - `set_conference_uness_session(conference_id: int, annale_id: int) -> dict` — écrit
    `uness_session_id` et `updated_at`, lève si la conférence est introuvable (même contrat que
    `set_conference_match`).
- **`backend/core/conferences/service.py`** :
  - `list_pending_uness_links() -> list[dict]` — pour chaque conférence `matched` sans lien,
    calcule ses candidats du jour ; ne renvoie que celles qui en ont au moins un. Forme de chaque
    élément : `{"conference": <row conferences>, "candidates": [<row uness_annales>, ...]}`.
  - `link_conference_to_uness_session(conference_id: int, annale_id: int) -> dict` — vérifie que
    le dossier existe (`local_store.get_uness_annale`), sinon `ValueError`, puis délègue à
    `set_conference_uness_session`.
- **`frontend/components/conferences_admin.py`** — nouvelle section « Dossier UNESS à confirmer »
  sous la section existante des collèges en attente, même patron de rendu
  (`_render_pending_uness_link`, appelée depuis `_render_body`). Pour chaque entrée : date + thème
  de la conférence, sélecteur des dossiers candidats, bouton « Lier ». Après confirmation,
  `_render_body()` est rappelé comme pour la validation collège — la ligne disparaît puisque
  `uness_session_id` n'est plus `NULL`.

## 5. Flux de données

```
Import XLS → conférence matched                    (existant, inchangé)
Aspiration UNESS → uness_annales                    (existant, inchangé)
Rendu du panneau → list_pending_uness_links()        (nouveau : jointure par date)
Choix utilisateur → link_conference_to_uness_session (nouveau : écrit uness_session_id)
```

Aucune écriture vers Google Calendar ni vers `uness_annales` — le flux se limite à
`conferences.uness_session_id`.

## 6. Gestion des erreurs

- Dossier sélectionné supprimé entre le rendu et la confirmation (course rare mais possible si un
  dossier est retiré depuis `/annales` pendant que le panneau est ouvert) → `ValueError` remontée
  en notification, pas de lien écrit, `_render_body()` rappelé pour rafraîchir la liste de
  candidats.
- Aucune sélection faite avant de cliquer « Lier » → notification d'avertissement, pas d'appel
  service — même pattern que la validation collège sans collège choisi.

## 7. Tests

`tests/test_conferences_store.py` :

- `list_uness_annales_by_date` retrouve un dossier collecté le même jour calendaire, même avec une
  heure de collecte tardive ; ne retrouve rien pour une date différente.
- `set_conference_uness_session` écrit l'identifiant et `updated_at` ; lève sur une conférence
  inconnue.

`tests/test_conferences_service.py` :

- `list_pending_uness_links` ne renvoie que les conférences `matched` sans lien et avec au moins un
  candidat ; une conférence `needs_validation` ou déjà liée n'apparaît pas ; plusieurs dossiers le
  même jour donnent plusieurs candidats pour une seule conférence.
- `link_conference_to_uness_session` écrit le lien puis fait disparaître l'entrée de
  `list_pending_uness_links` ; lève sur un `annale_id` inexistant sans écrire.

`tests/test_conferences_admin_ui.py` :

- La section « Dossier UNESS à confirmer » n'apparaît que s'il y a au moins une entrée en attente.
- Sélection d'un candidat puis clic « Lier » fait disparaître la ligne du panneau rendu.
- Clic « Lier » sans sélection déclenche une notification d'avertissement, aucun appel service.

## 8. Critères d'acceptation

- Une conférence validée sans dossier lié, avec un dossier UNESS collecté le même jour, apparaît
  dans la section à confirmer du panneau conférences.
- Confirmer le lien écrit `uness_session_id` sur la conférence et la retire de la liste à
  confirmer, sans toucher au dossier UNESS, à Google Calendar ni au rapprochement collège.
- Une conférence sans dossier collecté ce jour-là n'apparaît dans aucune liste — ni erreur ni faux
  positif.
- Deux dossiers collectés le même jour qu'une conférence donnent deux candidats distincts dans le
  sélecteur.
