# Installation Windows

## Configuration requise

- Windows 10 ou 11, 64 bits, bureau interactif déverrouillé.
- Internet pour les fournisseurs cloud et les pages web.
- Microsoft Edge (généralement inclus dans Windows) ou Google Chrome pour le mode navigateur.
- Pour l’IA locale : Ollama ou LM Studio, un modèle téléchargé, et assez de RAM/VRAM
  pour ce modèle. L’application elle-même n’impose pas de GPU.

## MSI (recommandé)

Dans la page **Releases** du dépôt, ouvrir la dernière version puis **Assets**.
Télécharger `Projet4-AgentIA-1.7.0.msi`, puis l’exécuter. L’assistant installe
l’application dans Program Files et crée des raccourcis Bureau et menu Démarrer.
L’installation machine peut demander l’autorisation administrateur.

Le MSI contient un exécutable autonome avec Python, Tk, Pillow, Requests, PyAutoGUI
et le pilote Playwright/Node. Il ne télécharge pas des dépendances Python à l’installation.
Il n’installe pas automatiquement des modèles IA ni Ollama/LM Studio. Edge/Chrome
sont détectés au lancement du mode navigateur ; un message indique leur absence.

## Portable

Télécharger `AgentScreen.exe` dans les mêmes Assets puis le lancer. Aucun Python
à installer. Le lancement normal ne demande pas les droits administrateur ; pour
piloter un jeu ou une fenêtre élevée, utiliser **Exécuter en tant qu’administrateur**.

## Première configuration

1. Ouvrir **Paramètres**.
2. Choisir un fournisseur cloud et renseigner sa clé, ou choisir Ollama/LM Studio.
3. Cliquer **Charger modèles**, sélectionner un modèle (vision pour l’agent).
4. **Enregistrer les paramètres**, puis **Tester la connexion**.

Le test vérifie le fournisseur sélectionné, sans masquer une erreur par une bascule
vers un autre fournisseur. Un test textuel réussi ne garantit pas la vision : choisir
un modèle explicitement compatible images.

## Mise à jour et désinstallation

Fermer l’application avant d’installer un MSI plus récent. Windows Installer remplace
la version précédente. Les réglages restent dans `%LOCALAPPDATA%\AgentScreen\data`.
Désinstaller via **Paramètres Windows → Applications → Projet 4, agent IA**.
Les données utilisateur ne sont pas supprimées automatiquement.

## Emplacements

| Données | Version installée / portable |
|---|---|
| Configuration et clés | `%LOCALAPPDATA%\AgentScreen\data\config.json` |
| Captures bureau | `%LOCALAPPDATA%\AgentScreen\data\shots\` |
| Profil du navigateur dédié | `%LOCALAPPDATA%\AgentScreen\data\browser-profile\` |
| Variables optionnelles | `%LOCALAPPDATA%\AgentScreen\.env` |

En développement, ces dossiers sont dans `data/` à la racine du projet. Les captures
ne sont pas purgées automatiquement ; on peut les supprimer lorsque l’agent est arrêté.

## Dépannage

- **429 / quota** : attendre le renouvellement, corriger la facturation ou choisir un autre fournisseur.
- **Modèle introuvable** : recharger la liste et vérifier les droits du compte.
- **Serveur local inaccessible** : [IA locale](IA_LOCALE.md).
- **Navigateur absent** : installer Edge ou Chrome ; aucun `playwright install` nécessaire.
- **Profil navigateur occupé** : fermer la session précédente et éviter plusieurs instances de l’app.
- **Clics sur une fenêtre réduite** : restaurer la fenêtre avant de lancer le mode bureau.
- **Configuration illisible** : conserver une copie du fichier signalé, puis corriger son JSON
  ou le renommer pour repartir avec les valeurs par défaut.
