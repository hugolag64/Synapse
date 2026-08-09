# Remarques d'usage du 10 août 2026 — spécification

Onze remarques relevées en usage réel, traduites en trois lots. L'ordre est
imposé : les correctifs rapides d'abord, l'audit ensuite, les chantiers de fond
en dernier parce que l'audit doit les éclairer.

## 1. Deux questions tranchées

Ces deux points étaient des questions de compréhension, pas des chantiers. La
réponse est consignée ici parce qu'elle conditionne le chantier C4.

### 1.1 « Détail propositionnel EDN »

C'est la correction proposition par proposition (A, B, C…) et non question par
question. Pour chaque proposition, l'interface affiche : sélectionnée ou non,
attendue ou non, son rang (A/B), et sa discordance — `correct`, `omission` ou
`exces`. Le calcul vit dans `backend/core/practice/scoring.py:61`.

Cette grille alimente le barème officiel R2C, implémenté dans
`compute_question_score_edn` :

- 0 discordance = 1 pt ; 1 discordance = 0,5 pt ; 2 = 0,2 pt ; 3 ou plus = 0 pt
- pénalité absolue : proposition indispensable non cochée = 0 pt
- pénalité absolue : proposition inacceptable cochée = 0 pt
- QRU : tout ou rien

La note sur 20 en découle, avec validation Rang A à 14/20.

### 1.2 « Potentiel de gain »

Défini dans `backend/core/ednpro/frequency.py:146` :

```
gain = nb_sessions_EDNpro × (100 − maîtrise) × disponibilité_des_questions
```

où `disponibilité` vaut 0 si aucune question n'est importée, sinon
`min(1, questions_importées / questions_attendues)`.

Un item souvent tombé aux annales, mal maîtrisé, et dont les questions sont
effectivement disponibles localement obtient un score élevé. C'est un nombre
**relatif et sans unité** : ce n'est ni un nombre de points gagnés, ni une
prédiction de rang. Il est aujourd'hui affiché brut, sans échelle ni légende,
donc illisible. Le chantier C4 le rend interprétable.

## 2. LOT 1 — Correctifs rapides

Cinq bugs isolés, sans dépendance entre eux, sans risque de régression sur
d'autres surfaces.

### B1 — Le mode sombre ne se sauvegarde pas

`toggle_dark_mode` (`frontend/pages/settings_cockpit.py:49`) ne touche que
l'objet `ui.dark_mode()` de la page courante et n'écrit jamais la préférence.
Le shell relit pourtant `data_store.preferences["dark_mode"]` à chaque rendu de
page (`frontend/cockpit_shell.py:246`) : au premier changement de page,
l'ancienne valeur écrase le choix.

Correctif : `toggle_dark_mode` appelle `data_store.set_preference("dark_mode", …)`
avec la valeur effective, comme le fait déjà le sélecteur de fuseau horaire à la
ligne 197 du même fichier.

Critère de validation : basculer en sombre, naviguer vers une autre page, puis
redémarrer l'application — le thème sombre reste actif.

### B2 — Le panneau télémétrie a un fond gris différent des autres

L'expansion « CONSOMMATION, TÉLÉMÉTRIE & PARTIELS IMPORTÉS »
(`frontend/pages/settings_cockpit.py:462`) porte `bg-slate-900/40 text-sm
font-semibold` en dur, alors que l'expansion voisine « COUVERTURE DP PAR ITEM »
n'a que `border border-slate-700 rounded-lg mt-4`. La couleur est de surcroît
figée et ignore le thème, d'où l'illisibilité.

Correctif : supprimer les classes ad hoc et introduire une classe partagée
`.se-diag-expansion` dans le bloc `_CSS` de la page, en `var(--surface)` et
`var(--border)`, appliquée aux deux expansions de la section Diagnostics.

Critère de validation : les deux panneaux sont visuellement identiques, et
lisibles en thème clair comme en thème sombre.

### B3 — Pas de barre de défilement dans « Couverture DP par item »

Le CSS `.dpc-scroll` existe et déclare `max-height:520px; overflow-y:scroll`
(`frontend/components/dp_coverage_panel.py:28`), mais il est posé sur la colonne
qui *contient* `.dpc-table`, laquelle est en `overflow:hidden` (ligne 13). La
liste des items s'étale et c'est la page entière qui défile.

Le diagnostic doit être confirmé dans le navigateur avant correction : la cause
peut aussi être un parent flex qui neutralise le `max-height`. Correctif attendu
une fois confirmé : porter le conteneur de défilement au bon niveau, avec une
hauteur explicite plutôt qu'un `max-height` susceptible d'être écrasé.

Critère de validation : avec le filtre « Tous » (367 items), une barre de
défilement propre apparaît à l'intérieur du panneau et la page ne défile pas.

### B4 — La vue « Récents » de la sidebar est trop longue

`_recent_nav_entries(limit=5)` (`frontend/cockpit_shell.py:199`) : passer à 3.

Critère de validation : au plus trois entrées sous « Récents ».

### B5 — La correction du Tuteur DP est introuvable

`_open_session` dans `frontend/components/ai_practice_panel.py:275` ouvre la
session avec `on_complete=lambda _sid: None`. Le flux standard, lui, chaîne vers
la correction (`_open_answer_dialog`, ligne 134). Résultat : après un Tuteur DP,
aucune correction ne s'ouvre et il faut aller la rechercher à la main dans
l'historique QCM.

Correctif : chaîner `on_complete` vers `_open_correction_dialog`, comme le flux
standard, via `open_chained_dialog`.

Critère de validation : terminer un Tuteur DP ouvre directement sa correction.

## 3. LOT 2 — Audit complet

Un audit existe déjà (`docs/AUDIT_LOGIQUE_ALGORITHMES_IA_2026-08-09.md`), mais
il a été conduit surtout par lecture du code. Le nouvel audit est refait en
entier, confronté aux données réelles, et étendu à la chaîne IA.

**Livrable** : `docs/AUDIT_COMPLET_2026-08-10.md`, une section par axe précédée
d'une synthèse priorisée.

**Méthode** : quatre agents en parallèle, en lecture seule.

| Axe | Périmètre |
|---|---|
| Chaîne IA / API | Prompts, routing des modèles, garde-fous, retries, parsing, coût réel par tâche, qualité des sorties |
| Algorithmes pédagogiques | Maîtrise, SM-2, courbe d'oubli, potentiel de gain, scoring EDN, progression collège, confrontés à `data/synapse_local.db` |
| Intégrité des données | Schéma, associations item↔session↔cours, doublons, orphelins, cohérence Notion/Obsidian/UNESS, absence de sauvegarde |
| UI / parcours | Doublons de composants, code mort, chemins morts (Phase 5 jamais importée, façades F3/F4 vides) |

**Contrainte de coût** : aucun appel facturé à l'API Gemini sans accord préalable
explicite. Les agents lisent le code et la base ; ils ne génèrent pas.

## 4. LOT 3 — Chantiers de fond

### C1 — Ancrage des générations IA sur le bon item

**Cause racine identifiée.** `_prompt_for` (`backend/core/practice/service.py:29`)
écrit « Génère une session médicale fiable pour l'ITEM 233 » : le numéro seul,
jamais le titre. Le `course_title` est porté par la spec mais n'est jamais envoyé
au modèle. Pour le Tuteur DP, le bloc de contexte documentaire ne contient que
les erreurs et les lacunes — toujours pas l'intitulé.

Le modèle doit donc deviner de mémoire ce qu'est « l'item 233 », alors que la
numérotation EDN a changé entre versions du référentiel. Péricardite (233) et
fibrillation atriale (230/232) sont voisines : c'est exactement le profil du
symptôme observé.

Second effet, aggravant : quand une session DP existe déjà pour l'item,
`_render_dp_tutor` (`frontend/pages/course_detail_cockpit.py:937`) pré-remplit le
contexte avec les cinq premiers énoncés de cette session. Une session hors sujet
contamine donc toutes les générations suivantes.

**Correctif — partie A, à la source.** Le prompt reçoit l'identité complète de
l'item : `ITEM 233 — Péricardite aiguë (Collège de Cardiologie)`, plus les
objectifs OIC de l'item déjà présents en base. Les données existent :
`item_title()` et `college_full()` dans `backend/core/qcm/items_mapping.py`,
`get_item_oics()` dans `backend/core/lisa/item_service.py:90`. Le correctif
s'applique à `_prompt_for`, donc à **toutes** les générations — QCM, OIC, DP,
KFP — et pas seulement au Tuteur DP.

**Correctif — partie B, sur l'existant.** Passer en revue les sessions DP déjà
enregistrées et produire la liste de celles dont le contenu ne correspond pas à
l'item déclaré. Puis nettoyer : reclasser vers le bon item quand il est
identifiable, marquer `suspect` sinon. Une session marquée `suspect` cesse
d'alimenter le contexte pré-rempli du Tuteur DP et sort de l'historique par
défaut de la vue item.

Critère de validation : générer un Tuteur DP sur l'item Péricardite produit un
dossier de péricardite ; le rapport de nettoyage est joint au commit.

### C2 — Lecteur QCM unifié en Node.js

Deux lecteurs coexistent aujourd'hui. Les annales (`frontend/pages/annale_detail.py:340`)
et le cockpit QCM (`frontend/pages/qcm_cockpit.py:452`) ouvrent le lecteur Node
via `open_node_qcm`. Les sessions IA de la vue item ouvrent le lecteur NiceGUI
`open_qcm_session` (`frontend/components/qcm_replay.py`). D'où l'incohérence
visuelle relevée.

**Cible** : toutes les entrées passent par `open_node_qcm` — sessions IA de la
vue item, Tuteur DP, banque locale DP/KFP, simulateur, annales. Le lecteur
NiceGUI devient mort et est supprimé (`qcm_replay.py`, environ 579 lignes), avec
ses tests.

**Vérification préalable, bloquante.** Le lecteur Node gère déjà les questions
ouvertes (QROC), le mode concours blanc, la correction propositionnelle, le
rejeu et la relance de suivi (`qcm_app/src/main.tsx`). Deux capacités doivent
être confirmées avant de basculer, et implémentées côté Node si elles manquent :

1. la reprise d'une session partiellement répondue ;
2. l'affichage de l'énoncé commun d'un dossier progressif.

Si l'une des deux manque, elle fait partie du chantier ; on ne supprime pas le
lecteur NiceGUI avant que le lecteur Node couvre l'ensemble.

**Cas du bundle absent.** `open_node_qcm` renvoie `False` si
`qcm_app/dist/index.html` n'existe pas. Une fois le lecteur NiceGUI supprimé, ce
cas doit produire un message d'erreur explicite invitant à reconstruire le
bundle, pas un clic sans effet.

Critère de validation : depuis chaque point d'entrée, le lecteur ouvert est le
même ; `qcm_replay.py` n'est plus importé nulle part.

### C3 — Enrichissement de la banque locale par les DP générés

Aujourd'hui les DP générés vont dans les tables de sessions IA, tandis que la
« Banque locale DP/KFP » lit `imported_practice_cases`, alimentée uniquement par
import manuel (`frontend/components/ai_practice_panel.py:509`).

**Cible** : un DP généré rejoint la banque locale **après** avoir été joué et
validé comme correct, pas à la génération. La banque ne contient donc que des
dossiers vérifiés, et un dossier hors sujet n'y entre jamais.

Le geste de validation se fait depuis la correction, à la fin de la session. Un
dossier versé garde une trace de son origine (généré, et par quel modèle) pour
le distinguer des imports manuels.

Critère de validation : un DP généré puis validé apparaît dans « Banque locale
DP/KFP » et peut être retiré au hasard ; un DP généré non validé n'y apparaît
pas.

### C4 — Aération de l'onglet Entraînement de la vue item

L'onglet empile aujourd'hui, sans hiérarchie : la carte Annales EDNpro avec ses
huit métriques sur fond ambre, les boutons d'action, puis jusqu'à trente
sessions en accordéons qui déversent chaque question, chaque correction, chaque
explication et chaque tentative (`_render_history`,
`frontend/components/ai_practice_panel.py:289`).

**Cible** : trois zones hiérarchisées.

1. **Agir** — générer une session, importer, s'entraîner sur les annales.
2. **Synthèse** — la carte Annales EDNpro compactée en une ligne, et le potentiel
   de gain rendu interprétable : une échelle lisible plutôt qu'un nombre brut, et
   une légende au survol expliquant la formule rappelée en section 1.2.
3. **Historique** — trois sessions au plus, en lignes compactes (date, type,
   score), avec « Voir tout l'historique ». Le détail d'une session n'est plus
   déversé dans la page : le clic renvoie vers le lecteur Node, ce qui est
   cohérent avec C2.

Critère de validation : l'onglet tient sans défilement excessif sur un item
chargé d'historique ; le détail reste accessible en un clic.

### C5 — Hypocampus : liens par item et fiches Martingale

Deux volets indépendants.

**C5a — Lien Hypocampus dans les Ressources de la vue item.** Le lien EDNpro est
construit en dur : `https://ednpro.app/fiches?tab=lisa2&item={n}`
(`frontend/pages/course_detail_cockpit.py:1325`). L'équivalent Hypocampus est
inconnu. Le chantier commence donc par une tâche d'investigation : inspecter une
page Hypocampus pour déterminer si un motif d'URL stable par item existe.

- Si oui : câbler le lien de la même façon, à côté de la Fiche EDNpro.
- Si non : ne pas inventer de lien. On s'appuie alors sur les fiches locales du
  volet C5b, et le lien pointe vers l'accueil.

**C5b — Compléter et indexer le dossier Martingale.** Le dossier de référence est
`G:\Mon Drive\Médecine\MARTINGALE`, déjà trié par collèges et partiellement
rempli. Trois fonctions attendues :

1. **Compléter** — télécharger uniquement les fiches manquantes, en respectant
   l'arborescence par collège existante.
2. **Indexer** — construire un index fiche → item EDN, persisté localement.
3. **Ouvrir depuis Synapse** — « Fiche Martingale » apparaît dans les Ressources
   de la vue item et ouvre le PDF local.

**Déduplication** : par identifiant Hypocampus de la fiche, stocké dans l'index
local, plus un hash du contenu du PDF. L'identifiant évite de retélécharger une
fiche renommée à la main ; le hash permet de repérer qu'une fiche a été mise à
jour à la source.

**Limite explicite sur le téléchargement automatisé.** Le téléchargement utilise
la session authentifiée existante, en séquentiel et espacé — ce qui est de toute
façon la bonne pratique pour ne pas marteler un serveur. En revanche, aucun
contournement de détection anti-robot ni résolution de CAPTCHA ne sera
implémenté. Si Hypocampus bloque explicitement l'accès automatisé, le chantier
bascule sur le mode semi-automatique : Synapse ouvre les pages une par une, le
déclenchement du téléchargement est manuel, le classement et l'indexation restent
automatiques.

Ce point comporte un risque assumé par l'utilisateur, déjà signalé lors de
l'audit du 3 août 2026 : l'accès automatisé à une plateforme de préparation peut
contrevenir à ses conditions d'utilisation et exposer à une suspension de compte.

Critère de validation : un second passage du téléchargement ne crée aucun
doublon ; « Fiche Martingale » ouvre le bon PDF depuis la vue item.

## 5. Découpage en plans d'implémentation

Le lot 1 forme un seul plan. Le lot 2 est une commande d'audit, pas un plan de
code. Chaque chantier du lot 3 forme un plan distinct, à écrire après l'audit,
qui peut réordonner ou requalifier C1 à C5.

Dépendance à respecter : C4 dépend de C2, puisque l'historique compacté renvoie
vers le lecteur unifié.
