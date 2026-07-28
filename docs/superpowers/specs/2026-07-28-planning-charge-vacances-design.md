# Planning — charge quotidienne et mode vacances

## Objectif

Rendre le cockpit `/planning` plus lisible et cohérent avec le template Linear : le planning hebdomadaire reste l’élément principal, les réglages de charge sont regroupés dans un popover compact, et le mode vacances devient un réglage temporaire compréhensible.

## Décisions d’interface

- Supprimer les cartes inférieures « Pilotage de la période » et « À placer » du cockpit Planning.
- Centrer la grille du planning dans la largeur disponible, sans ajouter de résumé secondaire sous la grille.
- Remplacer le bouton actuel « Ma charge » (icône `tune` et style trop lourd) par une action discrète de type Linear : libellé court, bordure fine, hauteur compacte, état actif visible.
- L’action ouvre un popover guidé, variante B validée visuellement.

Le popover contient deux sections :

1. **Capacité quotidienne**
   - raccourcis : `3 h`, `6 h`, `9 h`, `12 h` ;
   - champ personnalisé borné entre 3 h et 12 h ;
   - la valeur persistée est en minutes pour rester compatible avec les services existants, mais l’interface n’expose plus les minutes.

2. **Vacances**
   - activation/désactivation ;
   - durée rapide : `1 jour`, `3 jours`, `5 jours` ;
   - option `Dates` avec calendrier pour une période personnalisée ;
   - stratégie : `Charge réduite` ou `Coupure complète`.

## Comportement métier

### Capacité quotidienne

La préférence Planning devient une capacité de travail journalière exprimée en heures dans l’UI et convertie en minutes pour `planning_service` et les recommandations. La plage autorisée est de 180 à 720 minutes. La valeur par défaut reste la valeur existante si elle est valide ; sinon 6 h est utilisée pour le nouveau réglage du cockpit.

Le planning utilise cette capacité pour borner la sélection des créneaux. Les urgences restent prioritaires. Les tâches non retenues ne sont pas supprimées et restent éligibles lors d’une prochaine génération.

### Mode vacances

Le mode vacances est temporaire et stocké dans une préférence structurée, par exemple :

```python
{
    "enabled": True,
    "start_date": "2026-07-30",
    "end_date": "2026-08-01",
    "strategy": "reduced",  # reduced | diagnostic_only
    "reduction_ratio": 0.5,
}
```

- **Charge réduite** : la capacité quotidienne est réduite de 50 % par défaut pendant la période ; elle ne descend pas sous 3 h. Le réglage reste explicite et réversible.
- **Coupure complète** : aucun créneau de travail ordinaire n’est planifié pendant la période. Au premier jour suivant la période, le planning propose un test diagnostique basé sur les connaissances attendues pendant cette période, afin de mesurer l’état des lieux au retour. Ce test est présenté comme un diagnostic, pas comme une validation automatique.
- Une période active est visible dans le popover et dans le sous-titre du planning, avec sa stratégie et sa date de fin.
- Les raccourcis 1/3/5 jours partent de la date du jour et remplacent la période active. `Dates` permet de la modifier précisément.

## Données et compatibilité

- Réutiliser `data_store.set_preference` et la préférence existante `planning_targets` autant que possible.
- Ajouter des clés dédiées seulement pour les informations qui ne peuvent pas être représentées par la structure existante : capacité en minutes et configuration vacances.
- Les anciennes valeurs en mode `minutes` doivent être migrées à la lecture vers une capacité en heures sans casser les autres écrans.
- Ne pas modifier les durées estimées des activités (`dur_revision`, `dur_qcm`, etc.) : elles restent des estimations de créneau, pas la capacité personnelle.

## Tests et vérification

- Tests unitaires des bornes 3–12 h, de la conversion heures/minutes et de la réduction vacances.
- Tests des raccourcis 1/3/5 jours et de la période personnalisée, y compris le cas d’une période expirée.
- Vérifier qu’une coupure complète ne supprime pas les tâches source et qu’un diagnostic est proposé au retour.
- Vérifier que le rendu ne crée plus les cartes inférieures et que la grille reste centrée sur les vues 1, 3 et 7 jours.
- Lancer la suite ciblée puis la suite complète et vérifier la compilation des modules modifiés.

## Hors périmètre

- Refonte générale de la navigation ou du design system.
- Modification des statistiques historiques de durée.
- Synchronisation de vacances avec Google Calendar.
- Drag-and-drop des créneaux.
