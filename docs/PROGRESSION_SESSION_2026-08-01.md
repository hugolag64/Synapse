# Progression Synapse — 1er août 2026

## Robustesse du pipeline UNESS (collecte → correction → import)

- `ui.notify`/mise à jour UI depuis la tâche de fond d'import corrigés : le
  pipeline entrait dans le slot NiceGUI explicitement au lieu de planter
  silencieusement (« slot stack empty »).
- `_bg_pipeline` (annales.py) enveloppé dans un try/except qui logue et
  notifie sur toute erreur inattendue au lieu de disparaître comme
  exception asyncio jamais récupérée.
- La correction Gemini (`correct_directory`) et l'import
  (`import_verified_directory`) ne s'arrêtent plus en bloc sur un
  quiz/examen imprévu : un mauvais fichier est isolé et logué, les autres
  continuent.
- Déduplication renforcée : réimporter une URL déjà importée est ignoré au
  lieu de dupliquer les sessions (Moodle donne un nouvel ID de tentative et
  Gemini reformule à chaque re-scrape, donc l'empreinte de contenu seule ne
  suffisait pas — dédoublonnage par (annale, titre de quiz) en plus).
- La boucle de retry automatique des corrections en échec importe
  désormais le résultat dès qu'une annale existante est concernée, au lieu
  de laisser le fichier corrigé moisir dans `UNESS/vérifiés/` sans que rien
  ne le signale.

## Import partiel malgré une question non vérifiable visuellement

- Une question dont l'image n'a pas pu être fournie à Gemini
  (`verification_status = "unsupported"`) ne bloque plus l'import de tout
  le quiz : son verdict IA est activement vidé (par le point d'entrée
  d'import lui-même, pas seulement par les producteurs internes) et
  l'import retombe sur la réponse officielle UNESS.
- Bandeau d'avertissement ambre dans la vue de correction pour signaler
  qu'une question n'a pas de vérification IA disponible.

## Nouveau : panneau Diagnostic UNESS (Paramètres)

- Nouveau module `backend/core/uness/diagnostics.py` : reconstruit, pour
  chaque annale UNESS déjà importée, l'état de chaque quiz (importé / en
  attente de retry / bloqué / jamais soumis à Gemini) en croisant les
  fichiers bridge sur disque avec la base SQLite.
- Nouvelle section « Diagnostic UNESS » dans Paramètres : ratio par
  annale, détail par quiz en échec avec message d'erreur, bouton
  « Relancer » par quiz, bouton « Rafraîchir » global. Les erreurs
  d'import qui ne peuvent être rattachées à aucune annale sont désormais
  affichées plutôt que silencieusement perdues.
- Garde-fou : une erreur dans le calcul du diagnostic n'empêche plus le
  reste de la page Paramètres de s'afficher.

## Vérification

- Développement en Subagent-Driven Development (7 tâches, chacune revue et
  corrigée avant la suivante) + review finale sur l'ensemble de la
  branche, qui a fait remonter 4 lacunes supplémentaires corrigées en une
  seule vague puis re-vérifiées.
- Vérification manuelle dans le navigateur sur l'application réelle
  (données réelles, pas seulement des fixtures).
- Suite complète : **956 tests passés**, 7 échecs préexistants sans
  rapport (routage IA, un test d'encodage console) inchangés.
- Poussé sur `origin/master`.
