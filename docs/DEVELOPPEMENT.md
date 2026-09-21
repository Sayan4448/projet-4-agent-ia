# Développement et compilation

## Ouvrir le projet

Cloner le dépôt ou télécharger **Code → Download ZIP**, extraire puis ouvrir le dossier
dans VS Code, PyCharm ou un autre éditeur. Python 3.11 x64 est la version de référence.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_app.py
```

Les versions directes validées sont dans `requirements-lock.txt` ; utiliser ce fichier
à la place de `requirements.txt` pour reproduire l’environnement de livraison.
Les bibliothèques Windows et Tk sont fournies par Python. Aucun service web n’est
nécessaire pour lancer l’interface native.

## Carte des fichiers

| Chemin | Rôle |
|---|---|
| `run_app.py` | Point d’entrée graphique et PyInstaller |
| `agent_screen/__main__.py` | Lancement par `python -m agent_screen` |
| `agent_screen/gui.py` | Interface native, événements, paramètres et Chat |
| `agent_screen/overlay.py` | Curseur transparent aux clics et bandeau d’activité |
| `agent_screen/agent.py` | Boucle IA, vocabulaire d’actions, Stop, lots et historique |
| `agent_screen/browser_mode.py` | Session navigateur dédiée, liste d’actions autorisées |
| `agent_screen/ai_client.py` | Huit fournisseurs, modèles, erreurs et fallback |
| `agent_screen/settings.py` | Valeurs par défaut, validation et sauvegarde atomique |
| `agent_screen/display.py` | Captures, géométrie, DPI et fenêtres Windows |
| `agent_screen/input_control.py` | Souris/clavier bureau, Unicode et PowerShell |
| `agent_screen/apps.py`, `app_catalog.py` | Résolution et lancement des applications |
| `agent_screen/paths.py` | Emplacements développement/installé |
| `agent_screen/server.py` | Interface HTTP historique, facultative, pas lancée par l’app |
| `scripts/test_*.py` | Tests unitaires/régression |
| `scripts/smoke_desktop.py` | Vérification interactive de l’UI et de la saisie |
| `scripts/measure_icons.py` | Mesure optionnelle utilisant un modèle réel et du quota |
| `scripts/make_icon.py`, `assets/app.ico` | Génération et ressource de l’icône |
| `scripts/build_windows.ps1` | Compilation Windows EXE/MSI et sommes SHA-256 |
| `scripts/build_msi.sh` | Ancien point d’entrée Git Bash |
| `AgentScreen.spec`, `installer/AgentScreen.wxs` | Définition PyInstaller et Windows Installer |
| `.github/workflows/` | Vérifications et livraison lors d’un tag |
| `.env.example` | Exemple sans secrets |

`data/`, `.venv/`, `build/`, `dist/`, outils téléchargés et profils navigateur sont
générés localement : ils ne font pas partie des sources publiques. Le MSI et l’EXE
sont distribués dans les Assets des Releases, pas dans l’historique Git.

## Modifier

- UI : `gui.py`, palette près de `BG`/`ACC` ; overlays dans `overlay.py`.
- Réglage : ajouter la valeur par défaut et sa validation dans `settings.py`, puis la
  passer explicitement à `AgentRun` depuis l’UI.
- Action bureau : table `ACTIONS`, `execute_action`, résumé et test de comportement.
- Action navigateur : liste `ALLOWED` et dispatcher de `BrowserSession` ; ne jamais
  appeler `input_control` depuis ce chemin.
- Fournisseur : `_call_provider_single`, `list_models`, réglages et libellés UI.

Tk reste sur le fil principal. Les workers déposent leurs événements dans une queue.
Le curseur transmet un accusé d’affichage avant l’exécution de l’action.
Playwright est créé/utilisé/fermé dans le même worker que le run.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
.\.venv\Scripts\python.exe -m scripts.smoke_desktop
.\.venv\Scripts\python.exe -m scripts.smoke_browser
.\.venv\Scripts\python.exe -m pip check
```

Les tests IA utilisent des réponses simulées ; ils ne prouvent pas la qualité d’un
modèle réel. La vérification interactive requiert un bureau déverrouillé et crée une
fenêtre de saisie propre au test. Ne pas utiliser le clavier pendant cette vérification.
`smoke_browser` vérifie le navigateur dédié avec une page de test locale, sans fournisseur IA.

## Construire EXE + MSI

Installer WiX 3.11, puis fournir son répertoire via `-WixBin` ou la variable `WIX`.
Si les outils sont déjà dans `tools/wix311`, ils sont détectés automatiquement.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -WixBin "C:\Program Files (x86)\WiX Toolset v3.11\bin"
```

Résultats : `dist/AgentScreen.exe`, `dist/Projet4-AgentIA-1.7.0.msi`,
`dist/SHA256SUMS.txt`. PyInstaller embarque Python, les bibliothèques et le pilote
Playwright. Les navigateurs système ne sont pas redistribués. La compilation nécessite
Windows ; le lancement de l’EXE ne nécessite pas l’environnement de compilation.

## Publier une version

1. Mettre à jour `agent_screen/__init__.py`, `installer/AgentScreen.wxs` et `CHANGELOG.md`.
2. Exécuter les tests et le build, vérifier les fichiers et la somme SHA-256.
3. Créer/pousser un tag `v1.7.0` (adapter à la version).
4. Le workflow Release reconstruit les binaires et les joint à la Release GitHub.
   Publication manuelle possible avec `gh release create` et les trois artefacts.

Ne jamais publier `data/config.json`, des profils navigateur, des captures personnelles,
des clés ou les environnements virtuels.
