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

### Inférence Gemini des rangs manquants

- Les questions UNESS sans rang officiel sont détectées par un scan idempotent et
  placées dans une file SQLite persistante, question par question.
- Le worker de fond regroupe les questions par item, injecte les OIC LiSA
  disponibles et appelle Gemini sur un lot borné. Une question sans OIC passe en
  `needs_oic` sans appel IA.
- Les réponses sous le seuil de confiance `0,85`, ambiguës ou mal formées sont
  conservées pour validation admin ; elles ne modifient pas le rang courant.
- Les inférences fiables sont appliquées avec leur provenance, confiance, OIC et
  justification ; le rang officiel ne peut jamais être écrasé.
- La file est relançable après erreur et conserve les transitions dans un journal
  d’événements redacted.
- Le cockpit Paramètres expose les compteurs, filtres, preuves OIC et actions
  Accepter Gemini / Choisir A / Choisir B / Rejeter / Relancer.

### Versionnement des résultats

- Chaque évaluation `qcm_sessions` reçoit un snapshot `initial` immuable au
  moment de son enregistrement.
- Une arrivée tardive de donnée officielle peut produire une ou plusieurs
  révisions `final` append-only, avec provenance, motif, version du barème et
  métriques de rang conservés.
- Le résultat courant reste exposé par `qcm_sessions` pour la compatibilité des
  écrans, tandis que l'historique complet est disponible via
  `list_qcm_result_versions()`.

### Composition d’épreuve officielle

- Le composeur serveur propose les formats DP ×3, série isolée et mixte, sans
  appel IA pendant la sélection.
- La sélection combine fréquence EDNpro, signaux d’erreur et ancienneté, puis
  est tirée avec un seed persistant ; l’ordre et les identifiants sont figés
  dans `exam_compositions`.
- La page de configuration ouvre le lecteur React actif avec la durée du format
  et le mode examen ; le serveur refuse les tentatives hors ordre.

### Sauvegardes chiffrées

- Le script Ubuntu crée un snapshot SQLite cohérent, chiffre l’archive du volume
  `synapse-data`, la copie sur un second volume et conserve une rétention bornée.
- Un verrou `flock`, un manifeste SHA-256 et un test mensuel systemd de restauration
  vérifient qu’une sauvegarde est exploitable, jusqu’à `PRAGMA integrity_check`.

### Indicateurs opérationnels du cockpit

- Le cockpit QCM affiche désormais les cinq indicateurs de l’audit : sécurisation
  Rang A officiel, profil omission/excès, rythme par format, couverture × fréquence
  et courbe de reprise.
- Chaque carte indique la donnée utilisée, gère explicitement l’absence de signal
  et formule la décision associée ; les rangs inférés par Gemini restent exclus du
  verdict de sécurité Rang A.

## Reste explicitement à brancher

Ces éléments ne sont pas prétendus livrés dans cette branche :

Il n’y a plus d’élément de ce lot explicitement en attente. La validation distante
reste à faire dès que le home server `192.168.1.5` redevient joignable.

## Vérifications effectuées

- Backend ciblé : tests de scoring, import UNESS, images, API timeout/QROC et
  maîtrise passent.
- Inférence de rang : contrat, persistance, worker, boucle de fond, API admin et
  panneau de validation testés séparément.
- Frontend : `npm test -- --run` et `npm run build` passent.
- La suite complète doit être relue en séparant les échecs de données de référence
  déjà présents avant cette branche des éventuelles régressions introduites.
