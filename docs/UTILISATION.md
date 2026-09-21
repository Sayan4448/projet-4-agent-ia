# Utilisation

## Une tâche

1. Saisir une consigne concrète dans **Objectif de l’agent**.
2. Choisir **Bureau** ou **Navigateur uniquement**.
3. Régler les options, puis **Lancer l’agent**.
4. Lire les cartes d’activité : réflexion, commande, résultat, capture.
5. Utiliser **Consigne en direct** pour orienter l’étape suivante, ou **Stop**.

Un exemple sélectionné dans la liste démarre la tâche immédiatement.

## Curseur virtuel et bandeau

**Curseur IA visible** affiche une flèche violette avant les mouvements/clics de l’agent,
et un halo animé pour les clics. C’est une visualisation, pas une seconde souris physique.
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
