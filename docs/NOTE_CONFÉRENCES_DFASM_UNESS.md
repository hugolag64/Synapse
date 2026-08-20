# Besoin métier — conférences DFASM et dossiers UNESS

## Planning récurrent

- **DFASM1** : conférences le mardi.
- **DFASM2** : conférences le mardi et le jeudi.
- Ajouter ces créneaux au planning de Synapse dès que le planning détaillé sera fourni.
- Le planning détaillé devra permettre d’associer à chaque conférence sa date, son niveau
  (DFASM1 ou DFASM2), son thème et, si disponible, la matière ou le collège concerné.

**Statut (20 août 2026) — fait pour DFASM1 :** l'import se fait depuis le fichier XLS annuel
fourni par la fac (grille calendrier, un thème par mardi), pas depuis une saisie manuelle.
Chaque conférence du mardi est rattachée au collège UNESS (automatiquement ou après validation
manuelle), synchronisée dans Google Calendar, avec création automatique du créneau dossier
UNESS 17 h 30–19 h le même jour. Import depuis Réglages → PLANNING CONFÉRENCES. DFASM2 (jeudi)
n'est pas importé — hors périmètre puisque l'utilisateur est en DFASM1. Détails : conception
[`docs/superpowers/specs/2026-08-20-import-planning-conferences-design.md`](superpowers/specs/2026-08-20-import-planning-conferences-design.md)
et plan [`docs/superpowers/plans/2026-08-20-import-planning-conferences.md`](superpowers/plans/2026-08-20-import-planning-conferences.md).

## Dossier UNESS après la conférence

- Prévoir un créneau de **17 h 30 à 19 h** pour réaliser un dossier UNESS.
- Ce créneau correspond au travail sur le QCM et au **début de la correction**.
- Pendant la réalisation du QCM, aspirer localement les données utiles de l’UNESS afin de
  conserver les questions, les propositions, les réponses, les corrections et les éléments
  de provenance nécessaires à la suite du traitement.

## Enregistrement et analyse de la conférence

- Enregistrer la conférence lorsque cela est possible et autorisé.
- Faire analyser l’enregistrement par l’IA (transcription, notions importantes, explications,
  mises en garde et liens avec le programme).
- Mettre en relation l’analyse de la conférence avec les questions du dossier UNESS réalisé
  le même jour.
- Utiliser cette mise en relation pour approfondir les réponses et enrichir la correction,
  tout en distinguant clairement les informations issues de la conférence, de l’UNESS et de
  l’IA.

## Alimentation de la base QCM

Les questions réalisées sur l’UNESS doivent alimenter la base de données de QCM de Synapse,
avec au minimum :

- l’énoncé et les propositions ;
- la réponse de l’étudiant et la correction disponible ;
- la source et la provenance UNESS ;
- l’**item** EDN canonique associé ;
- le **rang** de la question (notamment Rang A/B), avec sa source et son niveau de confiance
  lorsqu’il est inféré ;
- le lien vers la conférence et son analyse, lorsque ce lien est disponible.

Les questions doivent rester réutilisables dans les sessions QCM et être dédupliquées sans
perdre leur provenance d’origine.

## Décision d’exécution Gemini

- Les analyses liées à l’**import d’une annale UNESS** doivent utiliser l’API Batch afin de
  réduire le coût : correction, analyse des captures, résolution des items manquants et
  inférence des rangs manquants.
- L’analyse d’une **conférence associée à une annale UNESS** doit également utiliser Batch,
  avec l’audio, les captures disponibles et le snapshot des QCM concernés.
- La **création interactive de QCM** ne doit pas utiliser Batch : elle doit rester traitée par
  `generateContent` standard afin de fournir une réponse immédiate.
- Les données officielles aspirées depuis UNESS restent prioritaires et ne doivent jamais être
  remplacées par une sortie Gemini.

La fiche de route détaillée est dans
[`docs/superpowers/plans/2026-08-20-uness-conferences-gemini-batch.md`](superpowers/plans/2026-08-20-uness-conferences-gemini-batch.md).

## À compléter à la réception du planning

- [x] Importer les dates exactes des conférences DFASM1 (mardi), depuis le XLS de la fac.
- [ ] Importer les dates des conférences DFASM2 (jeudi) — hors périmètre actuel (utilisateur DFASM1).
- [x] Renseigner les thèmes et matières/collèges (auto-matching + file de validation manuelle).
- [x] Associer chaque dossier UNESS à la conférence correspondante — suggestion automatique par
      date dans Réglages → PLANNING CONFÉRENCES (section « Dossier UNESS à confirmer »),
      confirmation manuelle obligatoire. `uness_session_id` référence `uness_annales.id`.
- [ ] Définir le format de stockage des enregistrements et transcriptions.
- [ ] Vérifier le flux d’aspiration UNESS et la persistance des questions dans la BDD QCM.
