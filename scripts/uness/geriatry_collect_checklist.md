# Checklist de collecte — Annale UNESS Gériatrie

## Avant de commencer

- [ ] L'utilisateur est connecté par lui-même dans Chrome.
- [ ] L'URL exacte de l'annale a été reçue et notée comme provenance.
- [ ] Le titre, la faculté et le niveau visibles ont été confirmés avec l'utilisateur.
- [ ] Aucune demande de mot de passe, cookies, stockage local ou jeton de session n'a été faite.
- [ ] Un répertoire local de collecte a été choisi pour le HTML et les médias.

## Pour chaque contenu

- [ ] Ouvrir le contenu depuis la collection confirmée.
- [ ] Faire une tentative blanche.
- [ ] Demander l'accord de l'utilisateur avant la première soumission finale.
- [ ] Soumettre et ouvrir la relecture/correction.
- [ ] Enregistrer localement le HTML de relecture, les médias et le nom du contenu.
- [ ] Relever énoncé, propositions, correction, score, contexte et médias visibles.
- [ ] Marquer les zones à pointer/hotspots comme non reconstruites et conserver leur contexte visuel.
- [ ] Construire ou compléter `RawUnessArtifact` sans aucune donnée de session.
- [ ] Vérifier la sauvegarde locale, revenir à la liste des contenus et poursuivre.

## Après la collecte

- [ ] Normaliser avec `normalize_artifact(raw_artifact, metadata)`.
- [ ] Vérifier que la provenance conserve l'URL exacte et la liste des contenus.
- [ ] Vérifier que les médias pointent vers des copies locales.
- [ ] Faire vérifier les propositions par l'IA avec du contexte pédagogique autorisé.
- [ ] Importer uniquement l'artéfact vérifié depuis le répertoire local d'import.
- [ ] Avant toute réponse finale manuelle, demander la validation explicite de l'utilisateur.
