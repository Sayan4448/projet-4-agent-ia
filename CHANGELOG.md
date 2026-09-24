# Historique

> **Renumérotation bêta** : le projet reste en bêta — les anciennes versions
> `1.x` ont été renumérotées `0.1x` (1.0 → 0.10, 1.9.5 → 0.19.5, 2.0 → 0.20).

## 0.50.1 (bêta)

- **Ollama réparé de bout en bout** : le serveur est relancé automatiquement
  quand il est arrêté (`ollama serve`, sans fenêtre), un modèle installé est
  choisi automatiquement quand le champ est vide (vision + chat de préférence,
  le plus léger d'abord — les modèles « caption » comme moondream et les
  proxies distants sont écartés), `think: false` évite les réponses vides des
  modèles à raisonnement, et le délai local passe à 120 s pour couvrir le
  chargement à froid (~90 s pour un 12B). Validé en réel : réponse image
  correcte en ~9 s via `gemma4:12b`.
- **Erreurs locales honnêtes** : un délai dépassé (« modèle trop lent,
  augmente Délai IA ») n'est plus rapporté comme « serveur inaccessible »,
  et inversement.

## 0.50.0 (bêta)

- **Correctif « tapé mais jamais envoyé »** : chaque Entrée virtuelle portait le
  bit « touche étendue », donc Chromium/Electron lisait `NumpadEnter`
  (`event.code='NumpadEnter'`) et les handlers d'envoi qui vérifient le code
  ignoraient l'appui. L'Entrée principale est maintenant postée sans ce bit,
  et le keydown/keyup respecte une durée d'appui réaliste (~40 ms).
- **Envoi vérifié** : l'Entrée qui suit une frappe confirmée est vérifiée par
  empreinte d'écran (champ vidé, message apparu), retentée une fois en cas
  d'échec silencieux, puis échoue honnêtement au lieu de prétendre que le
  message est parti. Harnais de reproduction : `scripts/smoke_enter.py`
  (fenêtre native instrumentée — 100/100 envois, 0 Entrée étendue).

- **Interface réactive pendant les missions** : la file d'événements est
  drainée toutes les 25 ms (au lieu de 80) et la miniature de capture est
  décodée dans un thread séparé — le décodage 1280 px sur le thread UI
  gelait tous les boutons 100–300 ms à chaque étape. En mode rapide la
  miniature est carrément désactivée.
- **Profil « Vitesse »** (Prudent / Normal / Rapide) dans les Paramètres :
  pilote ensemble le délai entre étapes (0,8 / 0,4 / 0,15 s), les actions
  par capture (1 / 2 / 3) et l'attente post-frappe. Chaque réglage reste
  ajustable finement après avoir choisi un profil.
- **Zone morte anti-spam** : deux clics inefficaces dans une même zone
  (~50 px) refusent le troisième — l'agent doit changer de méthode (raccourci
  clavier, sélecteur rapide, recherche) au lieu de re-viser autour d'une
  cible morte. Un clic efficace vide la zone.

- **Nouveau style « Simple » par défaut** : interface claire et arrondie —
  boutons pilule, champ d'objectif et champ de chat arrondis, cartes d'activité
  à coins arrondis, palette claire. Les réglages fins (profil, éco, autonome,
  limites, capture par fenêtre, journal de session) sont repliés sous
  « Options avancées » : rien n'est supprimé, tout reste modifiable.
- **Bascule d'interface dans les Paramètres** : « Style d'interface » permet de
  revenir à la présentation « Complète » (sombre et dense). Le changement
  redémarre l'interface proprement.
- **Fiabilité de l'affichage** : un événement défectueux ne peut plus figer
  l'interface pendant une mission — chaque message est isolé et la boucle
  d'événements se replanifie toujours (le bouton restait mort auparavant).
- **Masquage instantané** : quand la fenêtre est déjà réduite et le panneau
  déjà caché, l'agent n'attend plus ~180 ms avant chaque action/capture.
- **Timeout IA configurable** (10–180 s, défaut 45 s au lieu de 90 s figé) :
  une requête qui pend ne peut plus immobiliser une étape pendant 4 minutes.
- **Mesures de performance intégrées** : chaque étape enregistre dans le
  journal et l'historique le temps de capture, d'appel IA et d'actions —
  les lenteurs deviennent mesurables au lieu d'être devinées.
- **Frappe réellement livrée à la fenêtre cliquée** : la saisie virtuelle
  ciblait la fenêtre « au premier plan » — or Windows refuse souvent à un
  processus en arrière-plan de changer ce premier plan, donc le texte partait
  dans le mauvais champ ou nulle part (le bug « il n'écrit pas »). Texte et
  touches vont désormais à la fenêtre du dernier clic virtuel ; les touches
  système (Win, volume…) gardent le chemin physique.
- **Frappe vérifiée, pas aveugle** : une empreinte d'écran avant/après chaque
  saisie détecte les champs qui avalent les caractères (Discord/Electron) —
  un essai physique discret suit si activé, sinon l'échec est honnête et le
  lot d'actions s'arrête au lieu d'enchaîner Entrée dans le vide.
- **Noms épelés compris** : quand l'utilisateur dicte « L-E-S-G-A-Z-O »,
  l'agent tape le mot assemblé (LESGAZO / la forme visible à l'écran) au lieu
  des tirets littéraux.
- **Repli de modèle Gemini** : un 503 « forte demande » est un problème du
  modèle, pas de la clé — la même clé est retentée sur un modèle Gemini sain
  (2.5-flash…) avant de déclarer l'échec, au lieu de tuer le run à l'étape 0.
- **Discord sans visée pixel** : pour ouvrir un salon/contact, l'agent privilégie
  le sélecteur rapide (Ctrl+K) + frappe vérifiée plutôt que de cliquer une ligne
  de la barre latérale.
- **Lancement d'app plus tolérant** : si le processus tourne sans fenêtre
  (démarrage réduit en zone de notification, typique de Discord), l'exe est
  relancé une fois pour restaurer la fenêtre, et l'attente passe à 20 s.

## 0.19.6

- Coordonnées normalisées 0–1000 pour toutes les actions souris : les modèles
  (Gemini en particulier) émettent nativement des positions sur une grille
  normalisée, pas des pixels d'image. Les traiter comme des pixels plaçait les
  clics systématiquement trop bas/à droite — proportionnellement à la position,
  ce qui faisait cliquer ~3 lignes sous la cible (bug Discord). La grille de la
  capture est désormais étiquetée en unités 0–1000 et la conversion applique la
  taille réelle de la capture + l'origine de la fenêtre. Les petites sorties de
  plage du modèle sont bornées au lieu d'être rejouées décalées.
- Panneau d'activité en bas à droite (style Neural Agents) : journal horodaté
  des pensées/actions/erreurs, miniature de la dernière capture et champ de
  discussion avec l'agent. Il se masque pendant chaque capture et chaque clic,
  puis réapparaît pendant que l'agent travaille (modes auto/toujours/caché).
  Il est exclu des captures et l'agent ne peut pas cliquer dessus.
- Le champ de discussion du panneau accepte vraiment le focus clavier (la
  fenêtre n'est plus « non activable » pour l'utilisateur).
- Correction du mode HUD « auto » qui ne réaffichait jamais le bandeau.

## 0.19.5

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

## 0.19.1

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

## 0.19.0

- Profil Montage vidéo pour Premiere Pro, CapCut et DaVinci Resolve.
- Reconnaissance et lancement déterministe des trois logiciels de montage.
- Observation de mouvement bornée à 6 secondes et 4 images au maximum.
- Analyse d’un fichier audio explicite avec Gemini, sans écoute permanente du micro.
- Champ de discussion dans le bandeau flottant de l’agent.
- Mode autonome borné en durée et en appels IA, avec veille et comparaison d’écran locales.
- Budget par défaut : 60 minutes, 20 appels IA, intervalle minimal de 30 secondes.
- Réponses de décision limitées à 900 tokens en mode éco et 1 600 sinon.

## 0.18.0

- Discussions du Chat enregistrées localement et restaurées après redémarrage.
- Barre latérale pour créer, ouvrir et supprimer une discussion.
- Discussions favorites épinglées en haut, sans appel IA supplémentaire.
- Titres créés localement à partir du premier message, sans coût API.
- Mode éco Chat activé par défaut : 6 messages précédents et réponses limitées à 700 tokens.
- Réglages du contexte et de la longueur maximale dans Paramètres.

## 0.17.0

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

## 0.16.1

- Correction des coordonnées image/bureau et de la capture Windows 64 bits.
- Journal des actions, captures intermédiaires, Stop pendant l’attente IA.
- Sauvegarde atomique, conservation d’un fichier de configuration illisible.
- Saisie Unicode et texte long, conservation du MIME JPEG lors des retries.
