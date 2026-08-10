# Badges de fréquence EDNpro — Design

## Objectif

Afficher la priorité EDNpro de chaque item dans les trois vues où l’utilisateur
compare ses items : la vue Collèges, la fiche détaillée d’un item et la liste
générale des Items. Le badge doit rendre la priorité immédiatement lisible,
tandis que le nombre de sessions, de questions et les années restent
accessibles au survol.

## Décisions d’interface

Le badge partagé affiche exactement l’un des quatre libellés issus du snapshot
EDNpro :

- `INDISPENSABLE` — rouge, item tombé sur au moins 3 sessions ;
- `IMPORTANT` — ambre, item tombé sur 2 sessions ;
- `BASIQUE` — bleu/gris, item tombé sur 1 session ;
- `JAMAIS TOMBÉ` — gris neutre, item absent des annales.

Le style est compact, sobre et proche des badges de statut utilisés dans
l’application : texte court en capitales, fond légèrement teinté, bordure et
point colorés. Le survol affiche un tooltip du type :
`13 sessions · 31 questions · 2022, 2023, 2024, 2025`. Le contenu sera aussi
exposé via `aria-label` pour les utilisateurs de clavier et de lecteur d’écran.

## Architecture

Créer `frontend/components/ednpro_frequency_badge.py` avec :

- une table de présentation par priorité ;
- une fonction pure qui construit le libellé de tooltip ;
- une fonction `ednpro_frequency_badge(frequency, *, compact=False)` qui rend
  le badge NiceGUI et applique le tooltip accessible.

Ajouter à `backend/core/reviews/local_store.py` une lecture groupée de la table
`ednpro_item_frequency`, retournant un dictionnaire indexé par `item_number`.
Les trois pages chargent ce dictionnaire une seule fois et le transmettent à
leurs lignes, afin d’éviter une requête SQLite par item.

## Intégrations

### Vue Collèges

Dans le tableau détaillé d’un collège, ajouter la colonne `EDNpro` juste après
`QCM`. Le badge est compact et garde la largeur minimale de la grille. Les
items sans fréquence restent affichés comme `JAMAIS TOMBÉ` si le snapshot
contient l’item, et comme un badge neutre si aucune donnée n’est disponible.

### Vue item spécifique

Ajouter le badge dans la ligne de métadonnées de l’en-tête, après `QCM moyen`
quand cette information existe, ou comme dernière cellule de métadonnées dans
les autres cas. Le titre et les actions ne changent pas de comportement.

### Vue Items générale

Ajouter le badge dans la cellule du titre, à droite du numéro et du titre. La
colonne titre est réduite pour libérer l’espace, son contenu peut passer sur
deux lignes et l’ellipse est supprimée pour que le titre reste lisible. Le
badge ne doit pas agrandir la hauteur de façon excessive : taille compacte,
alignement au début et retour à la ligne du titre autorisé.

Corriger simultanément l’en-tête général pour qu’il reprenne exactement les
mêmes largeurs et le même alignement horizontal que les lignes, notamment après
l’ajout du badge.

## Données absentes et robustesse

- Une fréquence absente du dictionnaire ne doit pas provoquer d’exception ni
  masquer la ligne.
- Une fréquence présente mais à zéro session est rendue `JAMAIS TOMBÉ`.
- Les compteurs sont affichés au pluriel correctement (`1 session`,
  `2 sessions`, `1 question`, `31 questions`).
- Le composant ne recalcule pas la priorité : il utilise la valeur déjà
  normalisée du snapshot EDNpro.

## Vérification

- Tests unitaires du composant pour les quatre priorités, le tooltip et les
  pluriels.
- Tests de lecture groupée avec fréquence présente et absente.
- Tests d’inspection des trois pages confirmant l’appel au badge et la
  présence de la colonne `EDNpro` dans la vue Collèges.
- Vérification visuelle dans `/colleges`, `/items` et `/cours/<id>` sur un item
  connu (`247`) et un item jamais tombé.
