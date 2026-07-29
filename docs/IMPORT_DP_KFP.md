# Importer une banque DP/KFP dans Synapse

L'import est local : il ne déclenche aucun appel Gemini et ne coûte donc rien.

## Format JSON version 1

```json
{
  "version": 1,
  "source": "ChatGPT · DP item 115",
  "cases": [
    {
      "id": "dp-115-001",
      "kind": "dp",
      "title": "Dyspnée aiguë",
      "item_numbers": ["115"],
      "stem": "Un patient consulte pour dyspnée...",
      "questions": [
        {
          "prompt": "Quelle est la première décision ?",
          "choices": ["A", "B", "C"],
          "answer": "A",
          "explanation": "La priorité est..."
        }
      ]
    }
  ]
}
```

`kind` vaut `dp` ou `kfp`. Les `item_numbers` explicites sont recommandés ; si
ils sont absents, Synapse tente de retrouver une mention du type `ITEM 115`
dans le titre ou l'énoncé. Un cas sans ITEM est placé dans la file « à vérifier ».

Les cas sont dédupliqués par empreinte du contenu. La source, les corrections,
les explications et les questions sont conservées dans SQLite. Une correction
générée par ChatGPT reste une proposition pédagogique : elle doit être relue
avant d'être considérée comme une référence médicale.
