# Historique

## 1.9.5

- Souris virtuelle Windows par défaut : événements envoyés à la fenêtre cible sans
  déplacer le pointeur physique ni le garer dans un coin. Double-clic, molette,
  coordonnées multi-écrans et saisie Unicode corrigés. Aucun repli automatique vers
  un clic physique si une application ignore les messages Windows. Le clavier et
  le focus restent partagés ; le mode jeu utilise toujours les entrées physiques.
- Isolation du navigateur rétablie : ses actions ne passent jamais par la souris virtuelle Windows.
- Capture du bureau entier par défaut, limite stricte de 1 à 3 actions ; nouvelle
  observation après un clic ou une navigation, et arrêt du lot après une erreur.
  Les clics identiques sans effet ne sont plus réautorisés après deux refus.
- Discussion réduite pendant les missions et bandeau masqué avant captures/actions.
  Mode discret par défaut, affichage pendant l’analyse optionnel. Arrêt global : Ctrl + Maj + F12.
- L’agent autonome poursuit une tâche active sans attendre un changement extérieur
  de l’écran. Les limites de temps et d’appels restent appliquées ; un blocage n’est
  pas annoncé comme un succès. Correction de l’échantillonnage local de l’écran.
- Historique commun Chat/Agent avec recherche, filtres, résultats des actions et
  sauvegarde des événements pendant la mission. Les longues discussions et les
  réponses arrivant après une nouvelle discussion sont conservées.
- Mémoire locale de préférences explicites (« retiens que… », « je préfère… »,
  « j’utilise… »), sans requête IA supplémentaire : consultation, ajout, suppression
  et désactivation dans les paramètres. La mémoire activée est envoyée au fournisseur
  choisi avec le contexte ; désactivée, elle n’est ni injectée ni enrichie automatiquement.
- Couleur d’accent et taille du texte Chat réglables, espacement des échanges amélioré.

## 1.9.1

- Enregistrement vidéo réel (`record_video`) : clip MP4 H.264 de 1 à 30 s,
  enregistré dans `data/recordings`, via un ffmpeg embarqué (imageio-ffmpeg).
- Curseur IA **bleu** : le marqueur de clic reste affiché là où l’IA a cliqué,
  5 secondes par défaut et réglable de 0 à 30 s dans Paramètres.
- Captures d’écran nettement plus rapides : redimensionnement BILINEAR, JPEG sans
  optimisation, nettoyage du dossier des captures différé (~45 % plus rapide).
- Historique des sessions du mode Agent (bouton 🗂 Historique) : chaque run est
  enregistré (objectif, pensées, actions, réponses, consignes, résultat) et peut
  être relu dans l’activité ou supprimé. Les réponses de l’agent en mode autonome
  sont désormais affichées dans l’activité et le bandeau flottant.
- Tâches menées jusqu’au bout : après un lancement, l’agent attend la fenêtre
  principale (15 s max), ferme les fenêtres bloquantes (pub, accueil, connexion…) et
  **doit vérifier la fenêtre avant de terminer** — terminer juste après avoir ouvert le
  menu Démarrer ou un écran de chargement est refusé. Le menu Démarrer ne compte plus
  comme « application ouverte », et l’agent ne doit plus ouvrir le menu Démarrer lui-même.
- Mode autonome réparé : les réglages du dialogue Paramètres (Autonome, Éco, curseur,
  limites) sont recopiés dans l’onglet Agent au lieu d’être annulés par une case
  restée à son ancienne valeur.
- Veille autonome allégée : un échantillon d’écran minuscule remplace la capture
  complète + écriture disque toutes les 3 secondes ; la capture réelle n’a lieu
  qu’au réveil (message ou changement d’écran).
- Souris : le curseur est garé au-dessus de la barre des tâches (l’ancien coin
  bas-droite déclenchait l’aperçu Aero et faussait la capture suivante), et
  `mouse_scroll` accepte des coordonnées x,y pour défiler au bon endroit.
- Clics plus précis : grille étiquetée tous les 100 px au lieu de 200, et consigne de
  viser le **milieu de la ligne** cliquable plutôt que son texte, avec un ré-essai
  légèrement décalé quand un clic n’a aucun effet visible.
- Correction du nombre maximal d’étapes par défaut (12 → 20) dans le code,
  l’interface et le test de régression.

## 1.9.0

- Profil Montage vidéo pour Premiere Pro, CapCut et DaVinci Resolve.
- Reconnaissance et lancement déterministe des trois logiciels de montage.
- Observation de mouvement bornée à 6 secondes et 4 images au maximum.
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
