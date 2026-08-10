# Inférence des rangs EDNpro avant les statistiques

## Objectif

Compléter les rangs A/B absents des questions QCM EDNpro avant la création des statistiques Synapse, sans remplacer un rang officiellement affiché par EDNpro et en limitant les appels Gemini.

## Règles métier

1. Un rang A/B extrait du DOM EDNpro est officiel et prioritaire.
2. Une question sans rang officiel peut être enrichie à partir des OIC de son item.
3. Les OIC sont fournis une seule fois par couple session/item, puis toutes les questions sans rang de cet item sont analysées dans le même appel.
4. Une inférence Gemini n'alimente les statistiques que si :
   - le résultat est `A` ou `B` ;
   - la confiance est strictement supérieure à `0.85`.
5. Une inférence insuffisamment confiante reste non classée et ne compte ni dans le dénominateur A ni dans le dénominateur B.
6. Une question déjà présente en base n'est pas recréée ; une nouvelle tentative peut toutefois recevoir une inférence mise en cache.

## Contexte transmis à Gemini

Pour chaque item concerné, la requête contient :

- le numéro d'item ;
- les questions sans rang officiel de la session ;
- les propositions, réponses, scores et explications déjà observés ;
- la liste dédupliquée des OIC actifs de l'item, avec code, intitulé et rang A/B.

La réponse attendue est un JSON strict contenant, pour chaque question, son identifiant, `rank`, `confidence`, les codes OIC retenus et une justification courte.

## Résolution des OIC

Les OIC locaux sont lus depuis le cache SQLite `lisa_oic`. Comme un item peut être représenté par plusieurs cours Synapse, la résolution regroupe les OIC de tous les cours portant le même numéro d'item et déduplique par code OIC.

Si aucun OIC local n'est disponible, l'enrichissement Gemini est ignoré pour cette question et l'import continue sans bloquer la session.

## Provenance et persistance

Les rangs enrichis doivent conserver leur provenance :

- `ednpro` pour un rang extrait de la page ;
- `oic` pour une résolution déterministe éventuelle ;
- `gemini` pour une inférence validée par le seuil ;
- `unknown` lorsque le rang reste absent.

La question et la tentative conservent également la confiance et les codes OIC justificatifs. Les statistiques par item exposent séparément les résultats A, B et non classés.

## Flux d'import

1. Capturer et normaliser les corrections EDNpro.
2. Regrouper les observations par item.
3. Conserver les rangs EDNpro existants.
4. Enrichir en une requête Gemini maximum par item et par session lorsque nécessaire.
5. Persister questions et tentatives avec provenance.
6. Créer les évaluations QCM par item avec les résultats A/B enrichis.

Une erreur réseau, une réponse Gemini invalide ou l'absence de clé ne doit jamais empêcher l'import des questions ni des scores bruts.

## Coût et cache

Les questions déjà classées ne sont jamais renvoyées. Les OIC sont mutualisés dans chaque requête groupée. Une empreinte du contenu question/OIC permet d'éviter une nouvelle analyse lors d'une tentative ultérieure.

## Vérification

Les tests couvriront :

- priorité du rang EDNpro ;
- groupement des questions par item ;
- déduplication des OIC multi-collèges ;
- acceptation uniquement au-dessus de 85 % ;
- conservation des rangs vides en cas d'échec Gemini ;
- alimentation des statistiques A/B sans modifier les données officielles.
