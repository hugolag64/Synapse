# Collecte locale UNESS — Gériatrie

Ce dossier documente le passage d'une annale UNESS ouverte par l'utilisateur vers un
artéfact local `RawUnessArtifact`, puis vers `normalize_artifact`. Il ne collecte pas
et ne stocke pas de données de session.

## Handoff avec l'utilisateur

1. L'utilisateur ouvre Chrome et se connecte lui-même à UNESS.
2. Il transmet l'URL exacte de l'annale, par exemple
   `https://entrainement.uness.fr/annales/course/view.php?id=29135`.
3. L'agent confirme avec lui le titre affiché, la faculté et le niveau avant toute
   collecte. En cas d'écart, il s'arrête et demande la bonne URL ou la bonne cible.
4. L'agent demande explicitement l'accord de l'utilisateur avant la première
   soumission finale d'une tentative blanche.

Ne jamais demander, lire, copier ou conserver de mot de passe, cookie, stockage local,
jeton de session, export de profil, ni capture contenant ces données. L'utilisateur
reste seul responsable de sa connexion dans Chrome.

## Parcours d'un contenu

Pour chaque contenu de l'annale :

1. Ouvrir le contenu depuis l'URL confirmée et relever son intitulé local.
2. Répondre à blanc, sans chercher à reproduire une réponse personnelle antérieure.
3. Juste avant la première soumission finale, demander l'accord annoncé ci-dessus.
4. Soumettre la tentative blanche, ouvrir la page de relecture/correction et relever
   uniquement le contenu visible : énoncé, propositions, correction, score, contexte,
   médias et éléments visuels pertinents.
5. Enregistrer le HTML de relecture et les médias utiles dans un répertoire local
   dédié à cette collecte; construire un `RawUnessArtifact` avec `source_url`,
   `html_by_content`, `media` et `artifact_root`.
6. Lancer `normalize_artifact(raw_artifact, metadata)` avec les métadonnées confirmées.
7. Après chaque contenu, vérifier que l'artéfact local et la sortie normalisée existent;
   consigner une erreur, revenir à la liste des contenus et continuer avec le suivant.

Les artéfacts restent locaux, sous le répertoire de collecte choisi (par défaut les
artéfacts UNESS locaux). Pour l'import QCM, placer uniquement le JSON vérifié dans le
répertoire d'import local configuré (`data/uness/imports` par défaut).

## Limites assumées

Les zones à pointer, hotspots, glisser-déposer et autres interactions graphiques ne
sont pas reconstruites. Préserver leur présence comme contexte visuel (`support_visuel_seul`)
et garder les médias associés localement; ne pas prétendre les rejouer ni en déduire une
réponse. En cas de changement du HTML UNESS, conserver l'instantané local et signaler
le contenu comme nécessitant une adaptation du normaliseur.

La checklist opérationnelle est dans
[geriatry_collect_checklist.md](geriatry_collect_checklist.md).
