# Historique

## 1.9.0

- Profil Montage vidéo pour Premiere Pro, CapCut et DaVinci Resolve.
- Reconnaissance et lancement déterministe des trois logiciels de montage.
- Observation de mouvement bornée à 6 secondes et 4 images au maximum.
- Enregistrement vidéo réel (record_video) : clip MP4 H.264 de 1 à 30 s, enregistré dans data/recordings.
- Analyse d’un fichier audio explicite avec Gemini, sans écoute permanente du micro.
- Champ de discussion dans le bandeau flottant de l’agent.
- Mode autonome borné en durée et en appels IA, avec veille et comparaison d’écran locales.
- Budget par défaut : 60 minutes, 20 appels IA, intervalle minimal de 30 secondes.
- Réponses de décision limitées à 900 tokens en mode éco et 1 600 sinon.

## 1.8.0

- Discussions du Chat enregistrées localement et restaurées après redémarrage.
- Barre latérale pour créer, ouvrir et supprimer une discussion.
- Discussions favorites épinglées en haut, sans appel IA supplémentaire.
- Titres créés localement à partir du premier message, sans coût API.
- Mode éco Chat activé par défaut : 6 messages précédents et réponses limitées à 700 tokens.
- Réglages du contexte et de la longueur maximale dans Paramètres.

## 1.7.0

- Nouveau nom affiché : **Projet 4, agent IA**.
- Interface native sombre/violette, choix des modes et commandes regroupées.
- Curseur IA transparent aux clics, halo animé et bandeau flottant Stop.
- Mode navigateur dédié Edge/Chrome, outils restreints aux pages.
- Limite activable de 1–12 actions par capture (automatique : 6).
- Mode éco : images 960 px, JPEG 60, historique court.
- Ollama et LM Studio : URL, modèles, Chat, vision et JSON, sans fallback cloud.
- Test de connexion limité au fournisseur sélectionné.
- Exécutable sans élévation obligatoire ; administrateur à la demande.
- Documentation d’installation, utilisation, développement, IA locale et publication MSI.

## 1.6.1

- Correction des coordonnées image/bureau et de la capture Windows 64 bits.
- Journal des actions, captures intermédiaires, Stop pendant l’attente IA.
- Sauvegarde atomique, conservation d’un fichier de configuration illisible.
- Saisie Unicode et texte long, conservation du MIME JPEG lors des retries.
