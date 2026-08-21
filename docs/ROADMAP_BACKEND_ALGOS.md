# Roadmap Backend & Algorithmes — état des lieux, prochaine feuille de route

> Document vivant, même esprit que `docs/UI_REFONTE_ETAT_DES_LIEUX.md` (désormais clos, chantiers
> A→D terminés le 9 août 2026). Celui-ci prend le relais pour le fil **backend/algorithmes**, distinct
> du fil UI. Ne pas confondre avec les rapports d'audit figés (`docs/AUDIT_2026-08-03.md`,
> `docs/AUDIT_2026-08-07.md`) : ce fichier consolide leurs items encore ouverts et se met à jour à
> chaque avancée, eux restent des instantanés historiques.

**Dernière mise à jour** : 2026-08-09. Aucun item ci-dessous n'a encore été repris — liste établie en
fin de session, à la demande de l'utilisateur, pour cadrer la prochaine reprise.

**⚠️ Avant d'agir sur un item** : ces constats viennent de mémoires/audits datés du 2 au 7 août 2026
(2 à 7 jours avant la rédaction de ce document). Revérifier l'état réel du code/de la base avant
d'implémenter quoi que ce soit — plusieurs statuts « fonctionne » se sont déjà révélés être des
façades vides lors de l'audit du 7 août.

---

## 1. Action immédiate en attente — chantier C5 (code déjà prêt, non exécuté)

Scripts écrits, testés et commités le 9 août mais jamais lancés contre les données réelles
(écriture sur données live volontairement laissée hors des plans automatisés) :

```bash
python scripts/reconcile_item_numbers.py            # dry-run, relire data/item_number_reconcile_report.json
python scripts/reconcile_item_numbers.py --apply
python scripts/heal_obsidian_item_frontmatter.py         # dry-run, relire data/obsidian_item_heal_report.json
python scripts/heal_obsidian_item_frontmatter.py --apply
```

Ordre strict : script 1 puis script 2 (le second dépend des données corrigées par le premier).

---

## 2. Chantiers backend/algorithmes ouverts

| # | Sujet | Constat (source) | Urgence / impact |
|---|---|---|---|
| **F2** | EDNpro/Hypocampus (ingestion) | Fetchers déjà complets (`network_capture/fetcher.py`, 834 lignes), atteignables seulement par CLI (`scripts/capture_qcm.py`). Question de légalité posée par l'utilisateur le 3 août, **jamais tranchée** (`project_audit_aug3_2026`) — usage personnel a priori peu risqué légalement, mais risque de suspension de compte côté Conditions d'Utilisation des plateformes. | **Bloquant** : aucune implémentation avant décision |
| **F3/F4** | Priorisation Flash-Zero / dashboard | `error_signals` et `edn_recommendations` ont **0 ligne** en base malgré un statut "✅ Fonctionne" affiché dans `docs/SYNAPSE_AI_CONTEXT.md` §9. `insert_error_signal()` jamais appelé. Le classement affiché au dashboard (`frontend/pages/dashboard/_cockpit_today.py:84-87`) utilise `edn_weight=0.7` codé en dur pour tous les items au lieu de `ednpro_item_frequency` (367 lignes jamais lues). 45% du poids de la formule F3 ne discrimine rien. (`project_audit_aug7_2026`) | Élevé — fonctionnalité visible mais façade vide |
| **Jumeau Rang A** | Niveau `fragile` de maîtrise | `mastery.py:279-282` (détermination du *niveau*, pas du score) réutilise `score_rang_a` sans revérifier `_has_rang_a_evidence` — dégénère en `score < 75 → "fragile"` avec motif trompeur "Sécurité Rang A non atteinte" pour 97,6% des cours sans couverture OIC réelle. **Distinct** du fix chantier C1 (9 août), qui ne corrigeait que le message du niveau `critique`, pas celui de `fragile`. À revérifier si toujours reproductible avant d'agir. (`project_audit_aug7_2026`) | Latent — se déclenchera dès qu'un score franchit le seuil 75 |
| **Gate §7.5** | Validation humaine obligatoire | "Validation humaine obligatoire" pour extraction de grille complexe (`requires_human_validation`) n'est lue nulle part en prod, seulement dans `tests/test_ai_tasks.py`. Le pipeline réel des corrections UNESS (`generate_uness_correction`) n'a aucun gate. (`project_audit_aug7_2026`) | Sécurité process IA |
| **Simulateur d'examen** | Barème Rang A forcé | `exam_simulator.py:160` force `"rank": "A"` sur **toutes** les propositions des cas SQLite → `compute_edn_score` annule à 0 au moindre oubli au lieu de 0,5. Notes d'entraînement structurellement faussées vers le bas. (`project_audit_aug3_2026`) | Fiabilité des notes affichées à l'utilisateur |
| **4 correctifs du 2 août** | Fiabilité générale | Préférences perdues après 12h (`store.py:262-266`), cache mastery jamais invalidé dans `complete_review`, aucun backup de la base SQLite, appels Notion sans retry. (`project_audit_aug3_2026`, hérité d'un audit du 2 août) | Fiabilité générale, silencieux tant que non déclenché |
| Tests cassés | Collecte pytest | À l'audit du 3 août : 2 modules en `ImportError` (`test_colleges_mastery_colors.py`, `test_todo_logic.py`), symboles supprimés par la purge cockpit. Probablement déjà réglé depuis (plusieurs refactors de fichiers `*_cockpit.py` depuis) — **à vérifier en premier**, coût de vérification quasi nul (`pytest --collect-only`). | À reclasser après vérification |

## 3. Items mineurs notés en passant (non priorisés)

- Anki : UI branchée (`anki_review_session.py` appelée, `mastery.py` pondère 25% dessus), mais
  AnkiConnect jamais lancé en pratique (0 ligne `anki_review_evidence`) — pas un bug, juste un usage
  non pris en main par l'utilisateur.
- Correction UNESS par image (Flash-Zero wizard) : 50% d'échec, jusqu'à 60s de latence, aucun retry
  synchrone (`gemini_client.py:73-86`).
- Dédup UNESS/EDNpro uniquement sur `source_url`, pas de clé matière/année/titre croisée.
- `obsidian/service.py` (`get_course_note_path`, `list_available_notes`) résout le collège avant
  l'item, viole partiellement la convention §8.9 ("item d'abord, collège ensuite").

## 4. Prochaine étape

Aucun item choisi pour l'instant. Au prochain lancement, commencer par demander à l'utilisateur
lequel de ces chantiers reprendre (ou lancer un mini-audit de revérification si l'écart avec l'état
réel du code semble trop grand après plusieurs jours d'inactivité sur ce fil).
