# Guide des Plugins Claude Code

## 1. `superpowers` — Workflows avancés

Le plugin officiel Anthropic. Il ajoute des **workflows structurés** pour les tâches de développement complexes. Claude suit des protocoles stricts plutôt que d'improviser.

### Skills disponibles

| Commande | Usage |
|----------|-------|
| `/superpowers:brainstorming` | Explorer des idées ou architectures avant de coder |
| `/superpowers:writing-plans` | Rédiger un plan d'implémentation structuré |
| `/superpowers:executing-plans` | Exécuter un plan étape par étape |
| `/superpowers:systematic-debugging` | Débugger de façon méthodique (hypothèses → tests → fix) |
| `/superpowers:test-driven-development` | Workflow TDD (tests d'abord, puis implémentation) |
| `/superpowers:subagent-driven-development` | Déléguer du travail à des sous-agents parallèles |
| `/superpowers:dispatching-parallel-agents` | Lancer plusieurs agents en parallèle |
| `/superpowers:verification-before-completion` | Vérifier qu'un changement fonctionne vraiment avant de dire "c'est fait" |
| `/superpowers:finishing-a-development-branch` | Checklist de fin de branche (tests, review, commit) |
| `/superpowers:requesting-code-review` | Demander une revue de code structurée |
| `/superpowers:receiving-code-review` | Traiter et appliquer des retours de revue |
| `/superpowers:using-git-worktrees` | Travailler sur plusieurs branches simultanément |

### Quand l'utiliser
- Tâche complexe avec plusieurs étapes → `writing-plans` puis `executing-plans`
- Bug difficile à reproduire → `systematic-debugging`
- Avant de commit une feature → `verification-before-completion`

---

## 2. `sc` (SuperClaude) — Commandes slash enrichies

Plugin tiers qui ajoute des **commandes `/sc:*`** couvrant tout le cycle de développement. Chaque commande active un persona et des outils adaptés.

### Skills disponibles

| Commande | Usage |
|----------|-------|
| `/sc:implement` | Implémenter une feature (active les bons agents automatiquement) |
| `/sc:analyze` | Analyse complète : qualité, sécurité, perf, architecture |
| `/sc:design` | Concevoir une architecture, API, interface |
| `/sc:build` | Compiler/packager avec gestion d'erreurs intelligente |
| `/sc:test` | Générer ou lancer des tests |
| `/sc:improve` | Améliorer du code existant (qualité, perf, maintenabilité) |
| `/sc:cleanup` | Nettoyer le code mort, optimiser la structure |
| `/sc:document` | Générer de la documentation ciblée |
| `/sc:explain` | Expliquer du code ou un concept clairement |
| `/sc:research` | Recherche web approfondie avec plan adaptatif |
| `/sc:troubleshoot` | Diagnostiquer un problème |
| `/sc:git` | Opérations git avec messages de commit intelligents |
| `/sc:pm` | Orchestrateur projet (coordonne les autres agents) |
| `/sc:brainstorm` | Dialogue Socratique pour explorer les besoins |
| `/sc:estimate` | Estimer la durée/complexité d'une tâche |
| `/sc:task` | Gérer des tâches et sous-tâches |
| `/sc:workflow` | Orchestrer un workflow multi-étapes |
| `/sc:spawn` | Décomposer et déléguer une tâche complexe |
| `/sc:index` | Indexer et documenter le projet entier |
| `/sc:help` | Lister toutes les commandes disponibles |

### Quand l'utiliser
- Nouvelle feature complète → `/sc:implement`
- Code qui part dans tous les sens → `/sc:cleanup` ou `/sc:improve`
- Besoin de comprendre un module → `/sc:explain`
- Audit du projet → `/sc:analyze`

---

## 3. `pr-review-toolkit` — Revue de code spécialisée

Plugin qui ajoute des **agents de revue** très ciblés, chacun expert dans un domaine précis.

### Agents disponibles

| Agent | Usage |
|-------|-------|
| `code-reviewer` | Revue globale : guidelines, style, bonnes pratiques |
| `code-simplifier` | Cherche les simplifications possibles (DRY, lisibilité) |
| `comment-analyzer` | Vérifie que les commentaires sont justes et utiles |
| `pr-test-analyzer` | Analyse la couverture de tests d'une PR |
| `silent-failure-hunter` | Détecte les erreurs silencieuses et mauvais error handling |
| `type-design-analyzer` | Évalue la qualité des types/modèles de données |

### Commande principale
```
/pr-review-toolkit:review-pr
```

### Quand l'utiliser
- Avant de créer une PR → lancer `code-reviewer` sur le diff
- Après avoir ajouté des try/except → `silent-failure-hunter`
- Après avoir créé des modèles Pydantic/dataclasses → `type-design-analyzer`
- Pour vérifier les tests → `pr-test-analyzer`

---

## 4. `frontend-design` — Design UI intentionnel

Plugin qui guide les **choix visuels et esthétiques** pour éviter les interfaces trop génériques ou "template-like".

### Skill disponible
```
/frontend-design:frontend-design
```

### Ce qu'il apporte
- Direction esthétique et typographie
- Choix de couleurs non-génériques
- Cohérence visuelle entre composants
- Conseils sur l'expérience utilisateur

### Quand l'utiliser
- Créer une nouvelle interface NiceGUI
- Refondre le design d'un composant existant
- Quand l'UI "fait template" et manque de personnalité

---

## Combinaisons utiles pour Synapse

| Scénario | Workflow recommandé |
|----------|---------------------|
| Nouvelle feature complexe | `/superpowers:writing-plans` → `/sc:implement` → `/superpowers:verification-before-completion` |
| Bug difficile | `/superpowers:systematic-debugging` |
| Nouveau composant UI | `/frontend-design:frontend-design` → `/sc:implement` |
| Avant commit | `/pr-review-toolkit:review-pr` → `/superpowers:finishing-a-development-branch` |
| Audit du code | `/sc:analyze` + `silent-failure-hunter` |
