# Intégration UNESS — collecte, vérification IA et banque d’épreuves

## Objectif

Permettre à Synapse de constituer une banque personnelle d’épreuves UNESS provenant de plusieurs facultés et niveaux (DFGSM2/3, DFASM1/2/3), puis de les rejouer en mode examen ou révision.

Le système doit conserver la correction officielle UNESS, demander à une IA une vérification indépendante et une explication de chaque proposition, puis afficher les désaccords sans écraser silencieusement la source officielle.

Le périmètre est personnel et local : l’utilisateur importe uniquement des épreuves auxquelles il a légitimement accès. Aucun scraping de comptes, contournement d’authentification ou partage de la banque n’est prévu.

## Découpage fonctionnel

### 1. Collecteur navigateur UNESS

Le collecteur est piloté depuis une session Chrome déjà authentifiée. Il parcourt une catégorie sélectionnée par l’utilisateur, ouvre les épreuves et leurs contenus, lance une tentative vide, envoie et termine la tentative, puis ouvre la relecture corrigée.

Le collecteur extrait le DOM visible et les médias associés, sans lire les mots de passe, cookies ou stockage de session. Une confirmation est requise avant la première soumission irréversible ; les soumissions suivantes peuvent être autorisées par une option explicite.

Chaque épreuve produit un artefact brut conservant : URL, titre, faculté, catégorie, niveau, date, type d’épreuve, contenu HTML nettoyé, captures ou images référencées et état de collecte. Les erreurs de navigation sont journalisées et permettent une reprise à l’épreuve ou au contenu suivant.

### 2. Normaliseur

Le normaliseur convertit l’artefact brut en JSON canonique. Il gère en V1 les QRM, QRU, QRP/L, DP et contenus avec images classiques. Les zones à pointer et autres interactions complexes sont conservées comme support visuel et marquées non reconstruites ; leur scoring interactif est reporté à une V2.

Le modèle distingue l’énoncé général d’un dossier, les questions, les propositions, la correction officielle et les médias. Il conserve les textes originaux et ne déduit pas la correction officielle quand elle n’est pas visible.

### 3. Vérification IA

Une analyse IA est lancée question par question, avec le contexte de l’épreuve et, lorsque disponible, les sources pédagogiques de Synapse (cours EDN/Notion, items LiSA et références fournies). Pour chaque proposition, l’IA retourne :

- un verdict vrai/faux/indéterminé ;
- une explication même lorsque la proposition est vraie ;
- l’explication de l’erreur et la formulation correcte lorsque la proposition est fausse ;
- les références utilisées ;
- un niveau de confiance et un éventuel commentaire de désaccord.

La correction UNESS et le verdict IA restent deux champs distincts. Le statut calculé est `concordant`, `desaccord`, `incertain` ou `valide_manuellement`. Par défaut, Synapse affiche l’avis IA en correction principale, avec une bulle ou un panneau « Correction UNESS » et un avertissement visible en cas de divergence. La correction finale peut être validée manuellement.

L’IA ne doit pas produire une explication médicale sans signaler l’absence de source ou une incertitude importante. Une divergence n’est jamais résolue silencieusement.

### 4. Import Synapse et usages

Après vérification, l’épreuve est importée comme banque de questions avec son rattachement faculté/niveau/matière/année et ses liens vers les items EDN.

Deux usages sont prévus :

- **Mode examen** : sélection d’une épreuve ou d’un sous-ensemble, chronomètre, correction masquée, soumission locale, puis correction IA avec comparaison UNESS ;
- **Mode révision** : correction à la question, affichage des explications, filtres par faculté, année, item et type d’erreur.

Les tentatives stockent les réponses de l’étudiant, le temps, le score calculé avec la correction finale choisie, les erreurs et les divergences rencontrées. Elles alimentent les lacunes et la planification existantes.

## Modèle JSON canonique

```json
{
  "faculte": "Université de La Réunion",
  "niveau": "DFGSM2",
  "matiere": "Cardiologie",
  "type_epreuve": "partiel",
  "annee": 2024,
  "titre": "UE cardiovasculaire - session 2024",
  "source_url": "https://...",
  "collecte": {"date": "2026-07-30T...", "statut": "complete"},
  "questions": [
    {
      "numero": 1,
      "type": "QRM",
      "enonce": "...",
      "contexte": "...",
      "images": [{"fichier": "q1-img1.png", "role": "support_diagnostic"}],
      "propositions": [
        {
          "texte": "...",
          "reponse_uness": true,
          "verdict_ia": true,
          "reponse_finale": null,
          "explication_ia": "...",
          "sources_ia": ["cours/..."] ,
          "confiance_ia": 0.91,
          "statut": "concordant"
        }
      ],
      "items_edn": ["221"],
      "interaction": {"type": "standard", "support_visuel_seul": false}
    }
  ]
}
```

Les corrections sont versionnées : `officielle_uness`, `ia`, puis `validee`. `reponse_finale` reste nulle tant qu’aucune validation n’a été nécessaire ou effectuée ; le produit peut alors utiliser le verdict IA par défaut tout en gardant la correction officielle visible.

## Images et interactions

Les images classiques sont téléchargées avec un nom stable, reliées à la question et présentées à l’IA comme contexte visuel. Les supports médicaux (ECG, radiographie, schéma) peuvent être expliqués mais restent accompagnés d’un avertissement de confiance.

Pour une zone à pointer, le collecteur tente de récupérer les coordonnées et la géométrie exposées par la page. Si elles ne sont pas accessibles, il conserve une capture et marque `support_visuel_seul: true`. L’image reste consultable, mais la question n’est pas annoncée comme équivalente à l’interaction UNESS.

## Sécurité, fiabilité et droits

- Ne jamais demander ou stocker les identifiants UNESS.
- Ne jamais contourner un contrôle d’accès ni interroger directement une API privée sans autorisation.
- Traiter les fichiers et réponses comme des données personnelles et conserver les artefacts localement.
- Respecter les conditions d’utilisation et ne pas distribuer la banque ou les corrections.
- Afficher la provenance et la date de collecte de chaque correction.
- Prévoir un avertissement général : une explication IA est une aide pédagogique, pas une autorité médicale.

## Tests et critères d’acceptation

Le premier prototype est validé sur une seule épreuve DFASM/DFGSM comportant plusieurs contenus et au moins une image simple.

Les tests doivent vérifier :

1. collecte complète d’une épreuve et reprise après échec d’un contenu ;
2. extraction exacte du texte, des propositions et des couleurs de correction ;
3. conservation d’une image et de son lien avec la question ;
4. génération JSON conforme au schéma ;
5. analyse IA présente pour chaque proposition, vraie ou fausse ;
6. désaccord affiché sans perte de la correction UNESS ;
7. import dans Synapse et lancement d’un mode examen local ;
8. marquage explicite des zones à pointer non reconstruites.

Le prototype ne traite pas encore l’automatisation de toutes les facultés ni les interactions de pointage complexes. Il doit d’abord démontrer une chaîne fiable sur une catégorie limitée avant extension.
