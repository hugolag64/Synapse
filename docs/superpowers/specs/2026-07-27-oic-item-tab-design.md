# Onglet OIC dans la fiche item — spécification de conception

## Objectif

Rendre les OIC accessibles depuis la fiche item cockpit, dans un véritable onglet `OIC`, en réutilisant le système LiSA + AnythingLLM existant. La V1 vise la parité fonctionnelle avec l’ancien dialogue : liste des OIC par rang A/B, progression, validation manuelle, évaluation interactive, score, niveau et historique.

## Décisions de périmètre

- La source OIC reste LiSA/UNESS via le scraper et le cache SQLite existants.
- L’évaluation interactive reste locale via AnythingLLM ; aucun appel Ollama n’est ajouté dans cette tranche.
- La source de vérité fonctionnelle des OIC est l’item canonique, pas le collège. La V1 doit agréger les `course_id` Synapse qui représentent le même item, dédupliquer par `oic_code` et présenter une maîtrise/tentatives partagées. Une migration progressive depuis les lignes historiques par `course_id` est autorisée, sans perte d’historique.
- Le nouvel onglet et l’ancien dialogue partagent le même renderer et les mêmes opérations métier. Aucune logique de liste, de score ou de persistance ne doit être recopiée.
- Le chargement LiSA est paresseux : afficher immédiatement le cache si disponible, puis charger/scraper à l’activation de l’onglet. Un bouton de rafraîchissement explicite permet de forcer la synchronisation.
- Un rafraîchissement LiSA ne doit pas supprimer l’historique `oic_attempts` ni perdre les niveaux/validations déjà enregistrés.

## Expérience utilisateur

La fiche item contient les onglets actuels et un nouvel onglet `OIC`, placé à côté de `QCM`/`Lacunes`.

Le panneau affiche :

1. un état de chargement ou une indication « cache disponible » ;
2. une synthèse : nombre total d’OIC, progression Rang A/B, nombre maîtrisé ;
3. deux groupes repliables ou visuellement séparés : `Rang A` puis `Rang B` ;
4. une ligne par OIC avec code, intitulé, rubrique, statut/niveau et action ;
5. une action de validation manuelle identique à l’ancien dialogue ;
6. une action `Évaluer` qui ouvre le dialogue d’évaluation existant pour cet OIC ;
7. un bouton `Actualiser LiSA` et des états d’erreur/retry explicites.

L’évaluation interactive reste un dialogue secondaire : le panneau OIC ne réimplémente ni le quiz, ni la correction IA, ni le calcul de niveau. À la fermeture du dialogue, le panneau recharge les données agrégées du même item canonique.

## Architecture et flux de données

### Renderer partagé

Extraire de `frontend/components/lisa_dialog.py` un renderer de panneau réutilisable, recevant le cours, un conteneur NiceGUI et un callback de rafraîchissement. Le wrapper `open_lisa_dialog` conserve son en-tête et son cycle de vie, mais délègue la liste/progression au renderer. La fiche cockpit utilise le même renderer dans le panneau `OIC`.

### Chargement

À l’activation de l’onglet :

1. résoudre tous les `course_id` Synapse correspondant au même identifiant/numéro d’item canonique ;
2. charger les caches OIC de ces cours et fusionner les lignes par `oic_code` ;
3. si un cache est disponible, afficher immédiatement la vue agrégée (y compris la liste vide qui signifie « déjà interrogé, aucun OIC ») ;
4. si aucun cache exploitable n’existe, lancer le scraper LiSA en tâche asynchrone avec le contexte de collège le plus pertinent ;
5. persister le résultat dans la représentation canonique en conservant niveaux, validations et tentatives historiques provenant des alias ;
6. afficher le résultat ou un message d’erreur avec possibilité de retry/authentification.

Le chargement ne doit pas se produire pour chaque rendu de la fiche : l’activation et le bouton d’actualisation sont les seuls déclencheurs.

### Évaluation

Le bouton d’une ligne appelle `open_oic_eval_dialog(oic, course, refresh_fn)`. Le flux existant reste la référence : résolution du workspace, génération de 3–5 questions, correction QCM locale/ouvertes via AnythingLLM, agrégation, `save_oic_attempt`, mise à jour du niveau, puis refresh du panneau.

### Persistance

Le contrat SQLite existant doit être adapté progressivement : `lisa_oic`/`oic_attempts` restent lisibles pour les données historiques par `course_id`, mais l’accès de l’onglet passe par une couche d’agrégation canonique par item. La réconciliation LiSA doit éviter le `DELETE` global qui déclenche la cascade des tentatives ; les OIC supprimés de LiSA doivent être traités explicitement sans effacer silencieusement l’historique. Une validation ou un niveau affiché depuis un collège doit être visible depuis tous les alias du même item.

## États et erreurs

- Cache absent : panneau vide avec chargement LiSA.
- Cache présent : panneau utilisable immédiatement, indicateur de date de synchronisation.
- LiSA indisponible : conserver le cache affiché, expliquer l’échec, proposer retry/authentification.
- AnythingLLM indisponible : le panneau et les validations manuelles restent utilisables ; seule l’évaluation IA affiche l’erreur.
- OIC sans tentative : niveau initial clairement indiqué, sans le présenter comme maîtrisé.
- Rechargement forcé : aucune perte d’historique ou de statut ; résultat nouveau fusionné par code OIC.

## Tests de conception

Les tests doivent vérifier les seams publiques suivantes :

- chargement cache `None` vs liste vide vs lignes existantes ;
- agrégation de plusieurs `course_id` du même item avec déduplication par `oic_code` et partage du niveau/statut ;
- rendu/agrégation de progression A/B à partir des lignes OIC ;
- réconciliation LiSA qui conserve `mastered`, `oic_level` et `oic_attempts` ;
- évaluation qui persiste une tentative et rafraîchit le panneau ;
- erreur LiSA avec cache conservé et retry possible ;
- ouverture de la fiche cockpit avec onglet OIC sans charger LiSA avant activation ;
- parité du renderer entre dialogue classic et onglet cockpit.

Les tests existants de logique pure (`tests/test_oic_evaluator.py`) sont conservés. Les tests LiSA/API devront être réalignés sur le contrat MediaWiki actuel avant de déclarer le workflow OIC vert.

## Hors périmètre V1

- nouveau modèle de maîtrise global ;
- refonte complète du modèle de données au-delà de la couche d’agrégation nécessaire à la vue item ;
- génération d’examens blancs ou de QCM génériques ;
- remplacement d’AnythingLLM par Ollama ;
- refonte complète de la fiche item ou du dialogue d’évaluation.
