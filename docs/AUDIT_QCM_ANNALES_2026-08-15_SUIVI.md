# Suivi d'implémentation — audit QCM / annales

Ce document complète l'audit du 15 août 2026. L'audit décrit des constats et des
recommandations ; il ne constitue pas, à lui seul, une autorisation de modifier
le produit. Les choix ci-dessous sont ceux validés pendant la revue avec Hugo.

## Livré dans cette branche

### Notation et intégrité de la correction

- Le moteur distingue désormais QRU, QRM, QRP, QRP long, QZP, QROC et TCS.
- Les règles officielles UNESS sont prioritaires sur le verdict ou l'explication IA.
- Une correction officielle contenant une valeur inconnue (`null`) devient
  `not_noted` ; elle n'est ni incluse dans le dénominateur ni envoyée vers la maîtrise.
- Les QROC utilisent les listes officielles exactes / acceptables lorsqu'elles sont
  disponibles. Sans ces listes, elles restent conservées mais non notées.
- Les TCS utilisent le ratio entre le nombre de panélistes de la réponse et celui
  de la réponse modale ; sans grille de panel officielle, la question est non notée.
- Les réponses indispensables / inacceptables sont des pénalités déterministes et
  ne peuvent pas être inventées par Gemini.
- Le score de session conserve le dénominateur réel et expose les questions exclues.
  La validité Rang A ne porte que sur les Rang A des formats autorisés par le CNG.

Référence docimologique : [règles CNG/COSUI R2C](https://www.cng.sante.fr/sites/default/files/media/2024-10/r2c-docimologie-et-correction-valide-cosui-24-25.pdf).

### Formats, rang et provenance

- Le type canonique et le type source brut sont conservés ; `QRP/L` est normalisé
  en `QRP_LONG`, sans perdre le libellé d'origine.
- Le rang est une propriété de la question, avec source, confiance et éléments de
  preuve. Un rang explicitement présent dans le HTML est capturé comme officiel.
- Le contrat de résolution `backend/core/practice/rank_service.py` applique la
  priorité : source officielle, Gemini avec confiance `>= 0,85`, puis correction
  manuelle. Une contradiction manuelle avec une inférence fiable est conservée
  comme alternative et signalée.
- Le lecteur React affiche une pastille Rang A/B en pratique et au débrief, mais
  masque le rang pendant une composition d'épreuve.

### Images, import et sessions

- Une image présente peut être importée avec correction officielle ; l'explication
  visuelle reste identifiée comme en attente de revue humaine.
- Une image indispensable absente, ou un support interactif non exploitable,
  conserve la question mais la rend non notée.
- Le lecteur utilise un chronomètre global : 3 h EDN, 1 h 30 LCA par défaut,
  durée d'annale explicite prioritaire, et entraînement libre par défaut.
- À l'expiration, l'API enregistre les questions non répondues, verrouille la
  session et finalise le résultat.
- Les anciennes tentatives vides ne sont pas interprétées comme des réponses ; les
  tentatives `timed_out` le sont explicitement.
- Le catalogue affiche aussi les annales sans sous-partie et les signale comme
  nécessitant une collecte, au lieu de les masquer.

### Maîtrise et sécurité

- La preuve question → item est pondérée par `1 / nombre d'items liés`, afin qu'une
  question transverse ne pèse pas plusieurs fois.
- Les questions QCM/DP/KFP peuvent alimenter la maîtrise sans `course_id` ; les OIC
  conservent leur garde-fou de cours.
- Les erreurs Gemini sont déjà redacted côté client ; la boucle externe qui
  multipliait les tentatives réseau a été supprimée : le client porte la politique
  bornée de trois essais.
- Les anciennes routes NiceGUI de correction redirigent vers le lecteur React
  canonique avec le mode correction conservé.

## Reste explicitement à brancher

Ces éléments ne sont pas prétendus livrés dans cette branche :

1. Déclencher automatiquement l'inférence Gemini des rangs manquants pour les
   annales UNESS, avec OIC injectés, exécution asynchrone relançable et file
   d'administration question par question. Le contrat de résolution est prêt,
   mais l'orchestration et l'écran admin restent à connecter.
2. Versionner en base les résultats initial / final après arrivée tardive d'un rang
   ou d'une donnée officielle, au lieu d'ajouter seulement les métadonnées au
   résultat courant.
3. Composer une épreuve officielle complète à partir de blocs DP dans un parcours
   `/qcm` refondu, avec sélection gelée par seed et anti-biais limité à
   l'entraînement généré.
4. Ajouter les sauvegardes locales chiffrées, la copie sur second volume et le
   test mensuel de restauration.
5. Brancher les cinq indicateurs opérationnels de l'audit (sécurisation Rang A,
   discordance omission/excès, rythme par format, couverture × fréquence,
   courbe de reprise) à des décisions visibles dans le cockpit.

## Vérifications effectuées

- Backend ciblé : tests de scoring, import UNESS, images, API timeout/QROC et
  maîtrise passent.
- Frontend : `npm test -- --run` et `npm run build` passent.
- La suite complète doit être relue en séparant les échecs de données de référence
  déjà présents avant cette branche des éventuelles régressions introduites.
