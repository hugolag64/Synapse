# EDNpro, onglet Prépa et ressources liées aux items — spécification

Date : 2026-08-04

Statut : proposition approuvée pour spécification, en attente de relecture avant plan d’implémentation

## 1. Décisions validées

- EDNpro est une source tierce très fiable, mais ses corrections ne sont pas des corrections officielles.
- L’interface doit afficher explicitement cette provenance : `Correction EDNpro — source tierce fiable`.
- L’IA ne remplace pas la correction EDNpro. Elle sert à extraire, normaliser, relever les incohérences et classer les questions par item.
- Une connexion Google manuelle est nécessaire. Playwright ouvre une fenêtre visible ; l’utilisateur effectue lui-même la connexion et la double authentification éventuelle.
- Le mot de passe et les identifiants Google ne sont jamais stockés par Synapse. Une session locale persistante peut être réutilisée tant que les cookies restent valides.
- Les concours importés depuis EDNpro sont représentés comme des `EDN complets`, avec année, session, sous-partie et provenance conservées.
- Les vidéos ne sont pas téléchargées par défaut. Synapse conserve les liens et les métadonnées accessibles.

## 2. Objectifs

1. Collecter de manière relançable les annales EDNpro disponibles depuis 2023.
2. Importer les questions et leurs corrections EDNpro dans le lecteur QCM existant.
3. Garantir que le rattachement question → item est explicite, traçable et prudent.
4. Créer un onglet `Prépa` cohérent avec l’UI cockpit/Linear.
5. Exposer dans le cockpit d’un item les vidéos EDNpro réellement reliées à cet item.
6. Préparer l’ajout futur d’Hypocampus et d’EDNi sans créer une page spécifique par fournisseur.

## 3. Hors périmètre

- Contourner un contrôle d’accès, un CAPTCHA, une restriction d’abonnement ou une détection anti-automatisation.
- Copier ou redistribuer publiquement le contenu EDNpro.
- Télécharger et héberger les vidéos EDNpro.
- Affirmer automatiquement qu’une correction EDNpro est officielle.
- Rattacher une vidéo à un item uniquement parce que son titre contient un mot proche.
- Faire dépendre la réussite de l’import d’un appel IA unique et non relançable.

## 4. Architecture générale

Le système est organisé en trois couches :

```text
Source EDNpro
    │  Playwright + session Google locale
    ▼
Collecteur / artefacts bruts / manifest de progression
    ▼
Adaptateur vers le modèle d’examen canonique
    ▼
Correction EDNpro + vérification IA + classification question→item
    ▼
Annales / QCM / preuves de maîtrise / ressources Prépa
```

### 4.1 Adaptateurs de sources

Le collecteur EDNpro est un adaptateur de source, au même niveau conceptuel que le collecteur UNESS existant. Il ne doit pas dupliquer le lecteur QCM, la correction ou les mécanismes de déduplication.

L’adaptateur expose les mêmes informations canoniques :

- collection d’examen : année, titre, type, fournisseur, URL racine ;
- sous-partie/session : identifiant externe, titre, position ;
- question : identifiant externe, énoncé, propositions, réponse/correction, médias ;
- provenance : URL, date de collecte, statut de collecte, source de correction ;
- ressources : URL, titre, catégorie, item(s) éventuellement identifiés.

Dans une première livraison, les modèles UNESS existants peuvent rester la représentation interne compatible, mais la provenance doit devenir explicitement multi-source. La table de regroupement ne doit plus supposer silencieusement que toutes les lignes proviennent d’UNESS.

## 5. Authentification EDNpro

### Parcours utilisateur

1. Dans `Prépa`, cliquer sur `Connecter EDNpro`.
2. Synapse lance Chromium Playwright avec un profil dédié local.
3. L’utilisateur arrive sur `https://ednpro.app/auth`.
4. L’utilisateur clique sur `Continuer avec Google` et saisit lui-même ses informations.
5. La fenêtre reste visible pendant toute la connexion.
6. Synapse détecte le retour sur une page authentifiée et enregistre uniquement l’état du profil local.

### Contraintes

- Aucun champ de mot de passe EDNpro ou Google dans Synapse.
- Aucun secret dans les logs, manifests ou URL.
- Profil séparé du profil Chrome personnel pour éviter de mélanger les cookies.
- Bouton `Se déconnecter / réinitialiser la session` disponible dans les paramètres.
- Si la session expire, l’import passe en état `connexion requise` et attend une reconnexion manuelle.

## 6. Collecte et reprise

La collecte doit être idempotente et reprenable.

### Manifest local

Chaque exécution crée un dossier de collecte contenant :

- `manifest.json` ;
- les pages HTML ou réponses JSON brutes nécessaires ;
- les médias référencés utiles aux questions ;
- un identifiant de collecte et un identifiant externe par session/question.

Le manifest contient au minimum :

- source ;
- URL racine ;
- date de collecte ;
- statut global ;
- sessions découvertes ;
- sessions capturées, échouées ou à reprendre ;
- dernière erreur non sensible.

### Déduplication

La clé primaire logique est :

```text
(source, external_exam_id, external_session_id, external_question_id)
```

Un fingerprint de contenu est conservé comme filet de sécurité lorsque l’identifiant externe change entre deux visites.

### Mode aperçu

Avant l’import, l’utilisateur voit :

- nombre de sessions détectées ;
- nombre de questions ;
- nombre de corrections présentes ;
- nombre de questions avec item explicite ;
- nombre de questions nécessitant une classification IA ou une vérification manuelle ;
- nombre de doublons déjà connus.

L’import ne devient définitif qu’après validation de cet aperçu.

## 7. Correction et provenance

Chaque proposition doit conserver séparément :

- la réponse/correction issue d’EDNpro ;
- le verdict éventuel de l’IA ;
- l’explication EDNpro ;
- l’explication générée par l’IA ;
- les éventuels désaccords ;
- la confiance et la version du vérificateur.

Libellés UI attendus :

- `Correction EDNpro` ;
- `Source tierce fiable — non officielle` ;
- `Vérification IA` ;
- `À vérifier`.

Une correction EDNpro complète est importée même si l’IA échoue. L’échec IA ne doit pas supprimer la correction source.

## 8. Classification question → item

La classification au niveau de l’annale entière n’est pas suffisante pour un EDN complet. Le pipeline cible chaque question.

### Ordre de confiance

1. Numéro d’item explicitement fourni par EDNpro dans la page, le titre ou les métadonnées.
2. Correspondance déterministe avec une table locale validée.
3. Classifieur IA limité aux items candidats de la matière et du contexte.
4. Vérification manuelle pour les cas sans confiance suffisante.

Chaque liaison contient :

- numéro d’item ;
- confiance ;
- méthode (`source`, `mapping`, `ia`, `manual`) ;
- version du classifieur ;
- identifiant de la question et de la source.

Garde-fous :

- maximum deux items par question sauf validation explicite ;
- aucune liaison si le classifieur n’est pas confiant ;
- les questions non classées restent jouables mais ne nourrissent pas automatiquement la maîtrise d’un item ;
- les classifications larges au niveau session restent des suggestions, jamais une preuve questionnelle.

## 9. Onglet Prépa

### Structure

```text
Prépa
  Fournisseurs
    EDNpro       Connecté · Ouvrir
    Hypocampus   Raccourcis · Ouvrir
    EDNi         Bientôt

  Raccourcis EDNpro
    Annales       Iconographie       Vidéos ECG
    Physiologie   Anatomie/Sémiologie LCA

  Derniers accès
  Importations et synchronisation
```

### Principes UI

- surface blanche/grise légère ; bordures fines ; densité cockpit ;
- un seul CTA primaire par carte ;
- couleur fournisseur discrète, pas de grosses cartes décoratives ;
- états visibles : connecté, session expirée, jamais connecté, synchronisation en cours ;
- URLs et catégories stockées comme données configurables ;
- ajout futur de raccourcis personnalisés sans modifier le code de la page.

### Raccourcis initiaux EDNpro

- entraînement / tous les items ;
- annales ;
- iconographie ;
- vidéos ECG ;
- physiologie ;
- anatomie et sémiologie ;
- LCA.

Les URLs exactes sont confirmées lors de la première collecte ou saisies dans la configuration du fournisseur, plutôt que déduites uniquement d’un chemin supposé.

## 10. Ressources dans le cockpit item

Le panneau droit actuel contient déjà une section `Ressources`. Elle est étendue avec deux niveaux :

1. ressources globales de préparation, accessibles depuis `Prépa` ;
2. ressources reliées à l’item courant, affichées dans le cockpit.

Une ressource liée contient :

- fournisseur ;
- type (`video`, `annale`, `iconographie`, `lca`, etc.) ;
- titre ;
- URL ;
- numéro(s) d’item ;
- méthode de rattachement ;
- confiance ;
- date de dernière vérification.

Le cockpit n’affiche automatiquement que les ressources de confiance suffisante. Les ressources ambiguës apparaissent dans Prépa ou dans une file de vérification, pas directement comme recommandation personnalisée.

## 11. Erreurs et observabilité

États à prévoir :

- `non connecté` ;
- `connexion requise` ;
- `collecte en cours` ;
- `collecte partielle` ;
- `prêt pour aperçu` ;
- `importé` ;
- `à vérifier` ;
- `échec relançable`.

Les logs doivent identifier la source, la session et l’étape, sans contenu sensible ni cookie. Chaque erreur doit être relançable sans recréer les sessions déjà collectées.

## 12. Déploiement par phases

### Phase 1 — socle EDNpro

- profil Playwright et connexion Google manuelle ;
- découverte des annales depuis 2023 ;
- collecte d’un petit périmètre pilote ;
- aperçu et déduplication ;
- stockage de la provenance `EDNpro / non officielle`.

### Phase 2 — import QCM

- adaptation vers le modèle canonique ;
- import dans le lecteur existant ;
- conservation de la correction EDNpro ;
- vérification IA facultative ;
- type `EDN complet` visible dans Annales.

### Phase 3 — classification fine

- extraction des items explicites ;
- classification question par question ;
- file de vérification ;
- exclusion des questions non classées des preuves de maîtrise.

### Phase 4 — Prépa et ressources

- onglet Prépa ;
- raccourcis EDNpro/Hypocampus ;
- modèle de ressources ;
- liens vidéo par item lorsque le rattachement est fiable.

## 13. Critères d’acceptation

- Une première connexion Google peut être réalisée sans saisir de mot de passe dans Synapse.
- Une seconde collecte réutilise la session locale sans nouvelle connexion si elle est encore valide.
- Une collecte interrompue peut reprendre sans doublonner les sessions déjà terminées.
- Chaque question importée indique sa source de correction.
- L’interface ne présente jamais la correction EDNpro comme officielle.
- Une question peut être non classée sans bloquer l’import ni créer une fausse preuve de maîtrise.
- Un import EDN complet apparaît dans Annales avec année, session et provenance.
- L’onglet Prépa ouvre les raccourcis configurés dans un nouvel onglet.
- Le cockpit item affiche uniquement les vidéos dont le rattachement est traçable.
- Les tests existants restent verts et les nouvelles règles de provenance/classification sont couvertes par des tests unitaires.
