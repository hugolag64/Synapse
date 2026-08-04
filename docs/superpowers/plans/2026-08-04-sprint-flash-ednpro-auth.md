# Sprint EDN, Flash-Zero et connexion EDNpro

## Objectif

Remettre les deux cartes du cockpit Aujourd'hui dans le langage visuel Linear
déjà utilisé par la file de travail, puis rendre la connexion Google EDNpro
robuste lorsque l'OAuth ouvre une nouvelle page.

## Décisions de conception

- Le Sprint EDN reste une carte d'information compacte : en-tête, métriques,
  barre de progression, scénarios et priorités de gain.
- Le Flash-Zero garde son action et son état existants. La fermeture est une
  action secondaire visible au survol ou au focus, positionnée dans la carte.
- Les données métier, le calcul du compte à rebours et le quiz ne changent pas.
- Le collecteur EDNpro utilise le profil Chromium persistant existant, attend
  les pages d'authentification/popup Google puis reprend sur une URL EDNpro
  authentifiée. Aucun cookie, token ou identifiant n'est lu ou exporté.

## Vérification

- Tests unitaires des modèles et du rendu source pour les cartes.
- Tests unitaires du flux Playwright avec une fausse page OAuth/popup.
- Suite ciblée puis suite complète avant commit.
