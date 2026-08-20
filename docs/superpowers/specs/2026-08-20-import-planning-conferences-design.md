# Import du planning des conférences DFASM — conception

**Contexte source :** [`docs/NOTE_CONFÉRENCES_DFASM_UNESS.md`](../../NOTE_CONFÉRENCES_DFASM_UNESS.md),
section « Planning récurrent ».

**Objectif :** importer le calendrier annuel des conférences DFASM (fichier XLS fourni par la
fac) dans Synapse, afin que le planning affiche automatiquement chaque conférence et le créneau
de réalisation du dossier UNESS associé (17h30–19h), avec synchronisation Google Calendar.

**Périmètre :** utilisateur DFASM1 — seules les conférences du **mardi** (communes
DFASM1/DFASM2) sont pertinentes. Les conférences du jeudi (DFASM2 seul) ne sont pas importées.

**Hors périmètre de cette conception** (traité ailleurs ou plus tard) :

- Détection des semaines d'examen/révision codées par couleur de cellule dans le XLS — ignorée
  volontairement ; seules les cellules du mardi contenant un texte de thème produisent une
  conférence.
- Conférences du jeudi (DFASM2 uniquement).
- Enregistrement audio, analyse IA de la conférence, mise en relation avec le dossier UNESS
  réalisé le même jour — couvert par la feuille de route existante
  [`2026-08-20-uness-conferences-gemini-batch.md`](../plans/2026-08-20-uness-conferences-gemini-batch.md),
  à reprendre séparément.
- Lien effectif entre une conférence et un dossier UNESS réalisé (le champ existe en base mais
  n'est rempli par aucun flux dans cette conception).

---

## 1. Format source

Le fichier XLS (exemple analysé : `Calendrier Confs 26-27.xlsx`) n'est **pas un tableau plat**.
C'est une grille calendrier annuelle (Août → Juillet), organisée en 12 blocs de 4 colonnes (un
par mois) : `jour du mois | jour de semaine (Ma/Je/...) | thème abrégé | numéro de semaine ISO`.
Chaque ligne représente un jour du mois à la même position dans chaque bloc.

Une légende séparée (colonnes à droite du calendrier) associe des initiales à des noms
d'intervenants (ex. `JFD` → `Jean-François Delattre`). Certaines cellules de thème contiennent
ces initiales en suffixe (ex. `"Onco JFD"`).

Les semaines d'examen/révision sont indiquées par une couleur de remplissage de cellule dans le
fichier source, sans texte dédié — cette information n'est pas exploitée ici (voir Hors
périmètre).

## 2. Architecture

Nouveau module `backend/core/conferences/` :

- **`xlsx_parser.py`** — lit le classeur avec `zipfile` + `xml.etree.ElementTree` (stdlib
  uniquement, `openpyxl` n'étant pas une dépendance du projet). Localise dynamiquement les blocs
  de mois sur la ligne d'en-tête plutôt que de coder des indices de colonne en dur (le nombre de
  mois ou leur ordre peut varier d'une édition du fichier à l'autre). Ne retient que les lignes
  où la colonne « jour de semaine » vaut `Ma`. Sépare le thème brut des initiales d'intervenant
  quand un motif reconnaissable est présent en fin de libellé, et résout le nom complet via la
  légende si elle est trouvée dans le classeur. Retourne une liste de candidats
  `(date, theme_raw, speaker_initials, speaker_name)`.
- **`matcher.py`** — relie chaque `theme_raw` au référentiel collège UNESS déjà présent dans
  Synapse. Réutilise la normalisation/le fuzzy matching existants de
  [`backend/core/files.py`](../../../backend/core/files.py) (`fuzzy_word_in_text`,
  `PDF_COLLEGE_MAPPING`) plutôt que d'écrire une seconde implémentation. Retourne un statut
  `matched` (collège résolu avec confiance suffisante) ou `needs_validation` (ambigu, non
  reconnu, ou texte qui n'est pas un thème médical — ex. un jour férié capté par erreur si la
  cellule mardi contenait un nom de fête).
- **`service.py`** — orchestration bout en bout : parse → match → upsert SQLite → synchronisation
  Google Calendar. Point d'entrée unique appelé par l'UI d'import.

## 3. Modèle de données

Nouvelle table SQLite `conferences` :

| Colonne | Rôle |
|---|---|
| `id` | Identifiant local |
| `date` | Date de la conférence (unique — clé d'upsert) |
| `theme_raw` | Libellé brut extrait du XLS |
| `college_id` | Collège UNESS résolu, nullable |
| `match_status` | `matched`, `needs_validation`, `skipped` |
| `speaker_initials` | Initiales de l'intervenant, nullable |
| `speaker_name` | Nom résolu via la légende, nullable |
| `uness_session_id` | Lien vers un dossier UNESS réalisé, nullable — non renseigné par cette conception, réservé pour la suite |
| `google_event_id` | ID de l'événement Google Calendar de la conférence |
| `uness_slot_google_event_id` | ID de l'événement Google Calendar du créneau dossier UNESS |
| `source_file` | Nom du fichier importé |
| `created_at` / `updated_at` | Horodatage |

Index sur `(date)` (unique) et `(match_status)`.

`skipped` est le statut choisi manuellement par l'utilisateur pour une entrée `needs_validation`
qui ne correspond à aucune conférence réelle (jour férié, cellule mal renseignée) — elle reste en
base pour ne pas être réimportée à chaque fois, mais ne génère aucun événement Calendar ni
créneau UNESS.

## 4. Flux d'import

1. L'utilisateur saisit le chemin local du fichier XLS dans un champ de `settings_cockpit.py`
   (même pattern que le champ URL du collecteur UNESS existant) et déclenche l'import par bouton.
2. `xlsx_parser` produit la liste des candidats (mardis avec thème non vide).
3. `matcher` détermine le statut de chacun.
4. `service` fait l'upsert en base par `date` :
   - date absente → création, statut selon le matching.
   - date déjà présente et déjà validée manuellement (`matched` confirmé ou `skipped`) avec le
     même `theme_raw` → aucune modification (idempotent).
   - date déjà présente mais `theme_raw` différent → mise à jour du libellé et retour à
     `needs_validation`, même si l'ancien statut était déjà résolu (le thème a changé, l'ancienne
     résolution n'est plus fiable).
5. Pour chaque conférence en statut `matched` (auto ou validée manuellement) sans
   `google_event_id`, `service` crée deux événements via
   [`GoogleCalendarService.create_event`](../../../backend/core/google/calendar_service.py:75) :
   la conférence elle-même, et un second événement 17h30–19h intitulé
   `"Dossier UNESS — <theme>"`. Les IDs renvoyés sont stockés pour rendre les imports suivants
   idempotents (mise à jour de l'événement existant plutôt que doublon, si le thème ou la date a
   changé après création).
6. Un résumé est affiché à l'utilisateur : nombre importées, nombre déjà à jour, nombre à
   valider.

## 5. Validation manuelle

Panneau `settings_cockpit.py`, sur le modèle du panneau « RANGS UNESS — VALIDATION » déjà
existant : liste des conférences en `needs_validation` (thème brut, date), avec pour chacune un
sélecteur de collège UNESS ou un bouton « Non applicable » (→ `skipped`). Valider un
`needs_validation` en choisissant un collège déclenche la création des événements Google Calendar
correspondants (étape 5 ci-dessus) au moment de la validation, pas seulement au prochain import.

## 6. Gestion des erreurs

- Fichier XLS introuvable, format inattendu (pas de bloc de mois détecté) → message d'erreur
  explicite dans l'UI, aucun import partiel silencieux.
- Échec de création d'un événement Google Calendar (token expiré, quota, etc.) → la conférence
  reste en base avec `google_event_id` null ; le résumé d'import signale le nombre d'échecs de
  synchronisation Calendar séparément du nombre de conférences important en base. Un nouvel
  import ou une action de re-synchronisation retente uniquement les entrées sans
  `google_event_id`.
- Deux conférences UNESS ne doivent jamais partager le même `google_event_id` — un échec de
  synchronisation ne doit pas être retenté en dupliquant l'événement d'une autre date.

## 7. Tests

`tests/test_conferences_import.py` :

- Parsing de la grille : extraction correcte des mardis, cellules vides ignorées, détection des
  blocs de mois par en-tête plutôt que par indice fixe.
- Extraction des initiales d'intervenant et résolution via la légende, y compris quand la légende
  est absente.
- Matching : cas confiant → `matched`, cas ambigu/non reconnu (y compris un jour férié capté par
  erreur) → `needs_validation`.
- Upsert idempotent : deuxième import identique ne modifie rien ; import avec thème changé sur
  une date déjà validée repasse en `needs_validation` sans écraser `uness_session_id`.
- Synchronisation Calendar : création des deux événements pour une conférence `matched`, pas de
  duplication au réimport, gestion d'un échec de création (statut conservé, pas de crash).

## 8. Critères d'acceptation

- Importer le fichier `Calendrier Confs 26-27.xlsx` produit uniquement des conférences du mardi,
  avec le bon thème brut par date.
- Un thème reconnu avec confiance est lié au collège UNESS correct sans action manuelle.
- Un thème ambigu ou un jour férié capté par erreur n'écrase jamais un collège au hasard — il
  attend une validation humaine.
- Chaque conférence validée produit exactement un événement « conférence » et un événement
  « dossier UNESS » 17h30–19h dans Google Calendar, sans doublon lors d'un réimport.
- Un réimport avec un fichier mis à jour préserve les conférences déjà validées dont le thème n'a
  pas changé.
