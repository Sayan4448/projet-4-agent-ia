<div align="center">

# ✦ Projet 4, agent IA

### Votre objectif. Son prochain mouvement.

**Application Windows native · Bureau & navigateur · IA cloud & locale**

![Windows](https://img.shields.io/badge/Windows_10%2F11-x64-8b5cf6)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab)
![Version](https://img.shields.io/badge/version-1.7.0-a78bfa)

[Installation](docs/INSTALLATION.md) · [Utilisation](docs/UTILISATION.md) · [IA locale](docs/IA_LOCALE.md) · [Développement](docs/DEVELOPPEMENT.md)

</div>

Un assistant qui observe, agit et vous montre ce qu’il fait. Décrivez votre objectif,
choisissez **Bureau** ou **Navigateur uniquement**, puis suivez ses actions dans une
interface sombre à accents violets. Un curseur IA avec halo indique les clics ; un
bandeau flottant garde l’état d’exécution et le bouton **Stop** à portée de main.

Projet indépendant, avec une direction visuelle inspirée des assistants de bureau
comme Neural Agent ; aucune affiliation ni reprise de leur marque.

![Interface native de Projet 4, agent IA](docs/interface.png)

## Fonctionnalités

| | Ce que vous pouvez faire |
|---|---|
| **Bureau Windows** | Ouvrir des applications, cliquer, écrire, utiliser le clavier et PowerShell. |
| **Navigateur uniquement** | Piloter une session Edge/Chrome dédiée, sans injection de souris/clavier sur le bureau. |
| **Curseur virtuel** | Flèche violette, halo animé, aperçu avant clic, indicateur d’activité flottant. |
| **Actions par capture** | Limite activable de **1 à 12** actions avant la prochaine observation ; automatique = 6 maximum. |
| **Mode éco** | Images limitées à 960 px, JPEG 60, historique réduit, captures intermédiaires désactivées. |
| **IA cloud** | Gemini, OpenAI, Anthropic, Groq, DeepSeek et OpenRouter ; rotation des clés en cas d’échec. |
| **IA locale** | Ollama et LM Studio, adresse configurable, liste des modèles et test de connexion. |
| **Chat** | Conversation et analyse de captures jointes. |

## Installation rapide

1. Ouvrir les [**Releases**](https://github.com/Sayan4448/projet-4-agent-ia/releases/latest) et télécharger `Projet4-AgentIA-1.7.0.msi`.
2. Lancer le MSI puis ouvrir **Projet 4, agent IA** depuis le Bureau ou le menu Démarrer.
3. Dans **Paramètres**, choisir un fournisseur, charger les modèles, sélectionner un
   modèle puis **Tester la connexion**. Pour les captures, il faut un modèle avec vision.
4. Écrire un objectif et cliquer sur **Lancer l’agent**.

**Python et les bibliothèques de l’application sont embarqués** : aucune installation
de Python, pip ou Playwright à faire pour utiliser le MSI. Le mode navigateur utilise
Microsoft Edge ou Google Chrome installé sur le PC. Ollama/LM Studio et leurs modèles
restent optionnels et se configurent séparément : [guide IA locale](docs/IA_LOCALE.md).

Une version portable `AgentScreen.exe` est aussi produite. Le nom de fichier interne
est conservé pour les mises à jour ; l’application porte bien le nom **Projet 4, agent IA**.

## Exemples

- **Bureau** : « Ouvre le Bloc-notes et écris Bonjour. »
- **Navigateur** : « Recherche la météo à Lyon et résume les prévisions. »
- **Chat** : « Explique-moi ce message d’erreur » avec une capture jointe.

Le mode navigateur utilise son propre profil, distinct de vos profils personnels.
Il ouvre une fenêtre dédiée et la ferme à la fin de la tâche. Les connexions conservées
dans son profil peuvent être réutilisées lors d’une prochaine session.

## Lancer et modifier les sources

Dans PowerShell, depuis le dossier du projet :

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_app.py
```

```powershell
# Tests hors API externe
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
# Test interactif de l’interface Windows et de la saisie
.\.venv\Scripts\python.exe -m scripts.smoke_desktop
# Création de l’exécutable et du MSI
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Voir [Développement](docs/DEVELOPPEMENT.md) pour la structure complète, les dépendances,
les tests, la compilation, l’ajout d’actions et la publication des versions.

## Données et limites

- Les clés et captures restent dans le dossier de données local, jamais dans le dépôt.
  Avec une IA cloud, le prompt et les captures jointes sont envoyés à ce fournisseur.
- Une session **Ollama/LM Studio ne bascule jamais vers une IA cloud**. L’adresse du
  serveur peut toutefois être distante si vous la changez.
- Le mode navigateur restreint les **outils de l’agent** à la page. Ce n’est pas un
  environnement sandbox de sécurité pour exécuter des pages malveillantes.
- La reconnaissance et la précision dépendent du modèle choisi. Les erreurs de quota
  (429) et un serveur local arrêté doivent être résolus côté fournisseur/serveur.
- Stop interrompt l’attente de l’IA et les pauses. Une commande système ou une navigation
  déjà en cours se termine ou atteint son délai avant l’arrêt complet.
- Une seule tâche par processus ; ne lancez pas deux instances pour piloter le même bureau.
- Le binaire n’est pas signé : Windows peut afficher une demande de confirmation.

[Historique des versions](CHANGELOG.md) · [Vérifications réalisées](docs/VALIDATION.md) · [Contribuer](CONTRIBUTING.md)
