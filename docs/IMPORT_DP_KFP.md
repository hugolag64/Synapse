# Importer une banque QCM / DP / KFP dans Synapse

L'import est local : il ne déclenche aucun appel Gemini et ne coûte donc rien.
Il accepte aussi une discussion ChatGPT copiée ou exportée en `.txt`, `.md`, `.html`
ou JSON. Synapse extrait les blocs « Question / Réponse / Explication » et conserve
le texte intégral comme provenance.

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

`kind` vaut `qcm`, `dp` ou `kfp`. Les `item_numbers` explicites sont recommandés ; si
ils sont absents, Synapse tente de retrouver une mention du type `ITEM 115`
dans le titre ou l'énoncé. Un cas sans ITEM est placé dans la file « à vérifier ».

Les cas sont dédupliqués par empreinte du contenu. La source, les corrections,
les explications et les questions sont conservées dans SQLite. Une correction
générée par ChatGPT reste une proposition pédagogique : elle doit être relue
avant d'être considérée comme une référence médicale.

## Classement et entraînement

Les mentions `ITEM 115` sont proposées avec une case de confirmation. Plusieurs
ITEM peuvent être conservés pour un même cas. Une discussion sans ITEM est placée
en vérification et peut recevoir des numéros manuellement.

Depuis le Cockpit ITEM, un QCM, DP ou KFP importé peut être lancé comme session locale,
rejoué dans l'historique ou tiré aléatoirement. Une question peut être ajoutée
aux ancrages ; elle réapparaîtra alors dans les rappels volontaires. Ces usages
ne consomment pas d'API.
