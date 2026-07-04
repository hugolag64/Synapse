# Synapse — Contexte système QCM

> Ce document décrit le système QCM de l'application Synapse. Lis-le en entier avant de générer des QCM ou des fichiers d'import.

---

## 1. Qui suis-je et pourquoi je fais des QCM

Je suis un externe en médecine qui prépare l'**EDN** (Examen Dématérialisé National), l'examen classant français de fin de 6e année de médecine. J'utilise **Synapse**, une application personnelle de gestion des révisions, pour suivre ma progression par cours, gérer mes lacunes et planifier mes révisions espacées.

Les QCM que je fais servent à évaluer ma maîtrise d'un item ou d'une matière. Synapse enregistre chaque session, identifie mes erreurs récurrentes, et génère des alertes sur le dashboard ("à retravailler").

---

## 2. Structure des cours EDN

L'EDN est organisé en **items numérotés** (environ 368 items au total), regroupés par **collèges** (spécialités médicales) :

- Chaque item correspond à une pathologie, situation clinique, ou thème transversal
- Ex : Item 154 = Pneumonie aiguë communautaire, Item 219 = Douleur thoracique aiguë
- Les items sont notés **ITEM XXX** suivi du titre exact du cours

Quand tu génères des QCM, tu dois préciser à quelle item/cours correspond chaque question, car Synapse mappe automatiquement les résultats vers le bon cours dans la base de données.

---

## 3. Types de sessions QCM dans Synapse

| Type | Description | Usage |
|------|-------------|-------|
| `QCM` | Questions à Choix Multiples simples | Session sur 1 item ou thème |
| `DP` | Dossier Progressif | Cas clinique avec questions séquentielles |
| `KFP` | Key Feature Problem | Problème à réponse construite courte |
| `Annales` | Annales officielles EDN/iECN | Sujets tombés aux épreuves précédentes |

---

## 4. Format QCM EDN

Les QCM EDN ont des particularités importantes à respecter :

- **Plusieurs réponses possibles** (pas de "une seule bonne réponse")
- **Réponses couplées** : une mauvaise réponse peut annuler une bonne (selon la plateforme)
- Le score est exprimé en **X/Y** ou **%** (ex : "14/20" ou "70%")
- Le **seuil de validation** dans Synapse est **70%** (en dessous → "raté")
- La zone limite est **60-70%** (flagué comme "limite")

---

## 5. Types d'erreurs reconnus par Synapse

Synapse catégorise les erreurs QCM en **4 types** :

| Type | Description |
|------|-------------|
| `connaissance` | La notion n'était pas connue ou mal mémorisée |
| `raisonnement` | La notion était connue mais le raisonnement était faux |
| `inattention` | Erreur de lecture, piège de formulation, réponse cochée par inadvertance |
| `stratégie EDN` | Mauvaise stratégie de réponse (trop/pas assez large, piège classique EDN) |

---

## 6. Catégories de lacunes

Quand tu identifies des points faibles, classe-les dans l'une de ces catégories :

| Catégorie | Exemples |
|-----------|----------|
| `Diagnostic` | Critères diagnostiques, DDx, examens pour confirmer |
| `Clinique` | Sémiologie, examen physique, signes cliniques |
| `Examens complémentaires` | Bilan biologique, imagerie, indication des examens |
| `Traitement` | Molécules, posologies, durées, indications chirurgicales |
| `Complications` | Complications aigues/chroniques, pronostic |
| `Physiopathologie` | Mécanismes, physiopath sous-jacente |
| `Urgence` | Situations d'urgence, conduite à tenir immédiate |
| `Contre-indication` | CI médicamenteuses, absolues/relatives |
| `Piège EDN` | Formulations trompeuses, pièges classiques de l'examen |
| `Valeur chiffrée` | Seuils, doses, durées à mémoriser exactement |
| `Raisonnement` | Logique clinique, démarche diagnostique |
| `Inattention` | Erreur de lecture ou de compréhension de l'énoncé |
| `Autre` | Tout ce qui ne rentre pas dans les catégories ci-dessus |

---

## 7. Sévérité des lacunes (1 à 5)

| Niveau | Label | Quand l'utiliser |
|--------|-------|-----------------|
| `1` | Mineur | Détail accessoire, peu susceptible de tomber à l'examen |
| `2` | Modéré | Notion importante mais non fondamentale |
| `3` | Important | Notion fréquente en QCM, à revoir en priorité |
| `4` | Critique | Notion fondamentale, souvent discriminante à l'EDN |
| `5` | Critique+ | Erreur grave (urgence vitale, contre-indication majeure) |

Règle pratique : score < 50% → sévérité 4, score 50-60% → sévérité 3, score 60-70% → sévérité 2.

---

## 8. Format du fichier d'import Synapse

À la fin d'une session, génère un fichier avec ce format **exact** (le bloc JSON doit commencer dès la première ligne) :

```
---json
{
  "synapse_version": 1,
  "date": "YYYY-MM-DD",
  "platform": "ChatGPT",
  "session_type": "QCM",
  "sessions": [
    {
      "course_title": "Titre exact du cours EDN",
      "item_number": "154",
      "score_raw": "14/20",
      "score_percent": 70.0,
      "total_questions": 20,
      "correct_answers": 14,
      "wrong_answers": 6,
      "difficulty": "moyen",
      "error_types": ["connaissance", "inattention"],
      "weak_points": [
        {
          "category": "Traitement",
          "detail": "Description précise et actionnable de l'erreur ou du concept à revoir",
          "severity": 3
        }
      ],
      "comments": "Commentaire synthétique sur la session (optionnel)"
    }
  ],
  "notes": "Remarques globales sur l'ensemble de la session (optionnel)"
}
---
```

### Règles importantes pour le JSON

- `date` : date d'aujourd'hui, format `YYYY-MM-DD`
- `platform` : `"ChatGPT"` ou `"Gemini"` (selon où tu es)
- `session_type` : l'une des valeurs de la section 3 (`"QCM"`, `"DP"`, `"KFP"`, `"Annales"`)
- `item_number` : uniquement le numéro, sans le mot "Item" (ex : `"154"` et non `"Item 154"`)
- `score_percent` : float entre 0.0 et 100.0 (ex : `70.0`)
- `difficulty` : `"facile"`, `"moyen"`, ou `"difficile"`
- `error_types` : liste (peut être vide `[]`), valeurs de la section 5
- `category` des lacunes : exactement l'une des valeurs de la section 6
- `severity` : entier de 1 à 5 (section 7)
- `detail` des lacunes : phrase courte, précise, actionnable (max ~120 caractères)
- Si plusieurs items dans une même session (DP, annale), crée une entrée par item dans `sessions`
- Les champs `total_questions`, `correct_answers`, `wrong_answers` sont optionnels mais utiles

### Ce que Synapse fait avec le fichier

1. Mappe `item_number` ou `course_title` vers le cours dans sa base de données
2. Enregistre le score dans l'historique QCM du cours
3. Crée les lacunes listées dans `weak_points`
4. Si score < 70% sans `weak_points` explicites → crée une lacune automatique
5. Met à jour le score de maîtrise du cours
6. Le cours apparaît en "à retravailler" sur le Dashboard si le dernier score < 70%

---

## 9. Bonnes pratiques pour générer les QCM

- Respecte le style des QCM EDN : propositions A, B, C, D, E — plusieurs bonnes réponses possibles
- Inclus des **pièges classiques EDN** (formulations proches, exceptions, contre-indications)
- Mets des questions sur les **valeurs chiffrées** (seuils biologiques, posologies, délais)
- Varie les niveaux : 30% facile, 50% intermédiaire, 20% difficile
- À la fin, fais un **récap des erreurs** avec explications avant de générer le fichier
- Le `detail` de chaque lacune doit être une phrase mémorisable, pas une description vague :
  - ✓ `"Amoxicilline PAC légère : 1g × 3/j pendant 5 jours (et non 7j)"`
  - ✗ `"Erreur sur l'antibiothérapie"`

---

## 10. Exemple complet

**Scenario :** Session QCM de 15 questions sur l'Item 154 (Pneumonie aiguë communautaire), score 10/15.

```
---json
{
  "synapse_version": 1,
  "date": "2026-06-20",
  "platform": "ChatGPT",
  "session_type": "QCM",
  "sessions": [
    {
      "course_title": "Pneumonie aiguë communautaire",
      "item_number": "154",
      "score_raw": "10/15",
      "score_percent": 66.7,
      "total_questions": 15,
      "correct_answers": 10,
      "wrong_answers": 5,
      "difficulty": "moyen",
      "error_types": ["connaissance", "stratégie EDN"],
      "weak_points": [
        {
          "category": "Traitement",
          "detail": "PAC légère ambulatoire : amoxicilline 1g × 3/j (pas 2g × 2/j) — durée 5j",
          "severity": 3
        },
        {
          "category": "Diagnostic",
          "detail": "CRB65 score : C=confusion, R=FR≥30, B=PAS<90 ou PAD≤60, 65=âge≥65 — 0 = ambulatoire",
          "severity": 4
        },
        {
          "category": "Piège EDN",
          "detail": "Légionellose : pas de macrolide en 1re intention si critères de gravité — β-lactamine IV",
          "severity": 3
        }
      ],
      "comments": "Erreurs concentrées sur les critères de gravité et les posologies ATB"
    }
  ],
  "notes": "Revoir les arbres décisionnels PAC avant la prochaine session"
}
---

# Analyse — Item 154 : Pneumonie aiguë communautaire

Score : 10/15 (66,7%) — En dessous du seuil de 70%, à retravailler.

## Erreurs principales

1. **Posologie amoxicilline** : confusion 1g×3/j vs 2g×2/j
2. **Score CRB65** : critères mal mémorisés → hospitalisation à tort
3. **Légionellose sévère** : piège classique sur l'antibiothérapie

## À revoir

- Arbres PAC : ambulatoire / hospitalisation standard / réanimation
- Posologies ATB par situation (légère, modérée, grave)
- Spécificités légionellose (antigénurie, traitement)
```
