# Utilisation

## Une tâche

1. Saisir une consigne concrète dans **Objectif de l’agent**.
2. Choisir **Bureau** ou **Navigateur uniquement**.
3. Régler les options, puis **Lancer l’agent**.
4. Lire les cartes d’activité : réflexion, commande, résultat, capture.
5. Utiliser **Consigne en direct** pour orienter l’étape suivante, ou **Stop**.

Un exemple sélectionné dans la liste démarre la tâche immédiatement.

Après un lancement d’application, l’agent va au bout de la tâche : il attend la
fenêtre principale (jusqu’à 15 secondes pour les logiciels lourds), ferme les
fenêtres bloquantes — publicité, écran d’accueil, connexion, mise à jour — puis
vérifie à l’écran avant de déclarer l’objectif terminé. Le menu Démarrer ne
compte jamais comme « application ouverte ».

## Historique des sessions de l’agent

Le bouton **🗂 Historique** (barre supérieure) ouvre la liste des sessions du mode
Agent. Chaque run y est enregistré automatiquement : objectif, pensées, actions,
réponses, consignes, clips vidéo et résultat. Un clic affiche le déroulé complet ;
**Afficher dans l’activité** le rejoue sous forme de cartes dans le panneau
d’activité, et **Supprimer** le retire. Les captures d’écran ne sont pas
conservées : l’historique reste léger et privé (`data/agent_sessions.json`).

Les discussions du mode Chat restent dans l’onglet Chat ; celles du mode Agent
sont ici.

## Curseur virtuel et bandeau

**Curseur IA visible** affiche une flèche **bleue** avant les mouvements/clics de l’agent,
et un halo animé pour les clics. Après un clic, le marqueur bleu reste affiché à l’endroit
exact du clic pendant **5 secondes** par défaut ; la durée se règle de 0 à 30 s dans
Paramètres (« Durée du curseur IA bleu après un clic »). C’est une visualisation, pas une
seconde souris physique.
En mode Bureau, Windows possède toujours un seul pointeur réel.

L’overlay est transparent aux clics et ne prend pas le focus. Il est exclu des captures
sur les versions Windows compatibles. Le bandeau flottant affiche l’étape et l’action,
et comporte un bouton **Stop**. Il disparaît à la fin de la tâche.

## Mode navigateur

L’application ouvre Edge, ou Chrome si Edge n’est pas disponible, dans un profil dédié.
Les captures concernent le contenu de la page, pas le bureau. Les clics et la saisie
utilisent Playwright, sans appels aux commandes souris/clavier du bureau.

Les outils de terminal, lancement d’application, sélection d’une fenêtre, touches jeu,
glisser-déposer et raccourcis système sont refusés dans ce mode. La navigation explicite
accepte http(s). Les onglets ouverts par une page restent dans la même session.

La fenêtre dédiée se ferme à la fin de la tâche ; son profil est conservé. Le réglage
« Capture par fenêtre » et le mode jeu ne s’appliquent pas au mode navigateur.

## Actions par capture

- **Limite activée** : de 1 à 12 actions proposées sont exécutées avant une nouvelle
  capture envoyée au modèle. Si le modèle en propose davantage, le surplus est abandonné ;
  le prochain cycle repart de la nouvelle observation.
- **Limite désactivée** : limite automatique de 6 actions par cycle.
- **Maximum d’étapes par tâche**, dans Paramètres : limite du nombre de cycles IA,
  indépendante du nombre d’actions par capture.
- **Capture après chaque action** ajoute des captures d’aperçu ; elle ne provoque pas
  à elle seule un nouvel appel IA. Le modèle replanifie au cycle suivant.

Une petite limite favorise les vérifications fréquentes ; une plus grande limite
peut réduire les appels IA, mais les actions d’une séquence reposent sur la même observation.

## Mode éco

Réduit la largeur des images à 960 px maximum et la qualité JPEG à 60, conserve deux
cycles d’historique au lieu de quatre, désactive les captures intermédiaires et applique
un délai minimum de 0,6 seconde. Les préférences originales ne sont pas écrasées.

Il ne change pas le modèle ni le fournisseur. L’économie réelle dépend de leur mode
de facturation et du nombre de cycles nécessaires ; aucun pourcentage n’est garanti.

## Arrêt

Le bouton Stop est présent dans l’app et le bandeau. En mode bureau, le coin supérieur
gauche déclenche aussi le failsafe PyAutoGUI. En mode navigateur, utiliser Stop.
Les attentes IA sont interrompues côté agent ; une requête HTTP déjà envoyée peut finir
en arrière-plan, sans exécuter sa réponse. Les navigations/commandes en cours ont un délai borné.

## Mode autonome et bandeau

Activer **Autonome** dans l’espace de travail puis démarrer un objectif, par exemple
« Occupe-toi de mon PC et traite les messages affichés ». Le bandeau contient un champ
pour parler à l’agent pendant son exécution. Les messages deviennent des consignes pour
la prochaine décision et réveillent la veille locale. Les réponses de l’agent
s’affichent dans le bandeau et dans le panneau d’activité.

Ce mode n’est pas illimité : par défaut 60 minutes, 20 appels IA et au moins 30 secondes
entre deux appels automatiques. En l’absence de message, l’app compare localement de
petites signatures de l’écran ; un écran inchangé ne consomme aucun appel IA. Stop reste
disponible. Les limites se règlent dans Paramètres (5–240 min, 2–80 appels, 15–300 s).

## Montage vidéo, mouvement et audio

Choisir le profil **Montage vidéo** pour utiliser Premiere Pro, CapCut ou DaVinci Resolve.
L’agent privilégie leurs raccourcis, sauvegarde régulièrement et vérifie timeline,
tête de lecture et export à l’écran. Le résultat dépend de l’interface/version du logiciel
et du modèle vision ; il ne remplace pas les API officielles de ces éditeurs.

L’action d’observation temporelle prend 2 à 4 captures chronologiques sur 1 à 6 secondes.
Elle est réservée aux animations et à la lecture vidéo, car plusieurs images coûtent plus
qu’une capture.

Pour enregistrer une vraie vidéo, l’agent peut utiliser `record_video(seconds, fps)` :
il enregistre l’écran en MP4 (H.264) et sauvegarde le fichier dans `data/recordings/`.
Durée bornée de 1 à 30 secondes, cadence de 2 à 15 images par seconde. Le clip peut être
ouvert directement dans Premiere Pro, CapCut ou DaVinci Resolve. L’encodage utilise un
ffmpeg embarqué dans l’application (aucune installation séparée).

Pour analyser un audio, écrivez son chemin exact dans l’objectif ou dans le bandeau.
Formats : MP3, WAV, M4A, AAC, OGG, FLAC, OPUS, 20 Mo maximum. L’analyse intégrée utilise
actuellement Gemini avec un modèle compatible audio. L’application n’écoute jamais le
microphone et n’envoie pas un fichier choisi uniquement par l’IA.

## Chat

Choisir l’onglet Chat. Cocher l’option de capture si l’on veut joindre le bureau au message.
La colonne **Discussions** permet de créer, rouvrir, supprimer et mettre une discussion
en favori. Les favoris sont épinglés en haut. Les titres sont produits localement depuis
le premier message, donc sans requête IA. Tout reste dans `conversations.json` sur le PC.

Le mode éco Chat est activé par défaut : seuls les 6 messages précédents sont renvoyés
au modèle et la réponse est limitée à 700 tokens. Paramètres permet de choisir 0 à 20
messages et 128 à 4096 tokens. Une petite valeur économise généralement les crédits,
mais peut faire oublier des informations anciennes. Une capture reste l’élément le plus
lourd : la joindre seulement lorsqu’elle est utile.
