# Projet 4, agent IA — Android

Portage Android de l'agent IA (app Windows `agent_screen/`) : même boucle
**capture d'écran → modèle de vision → actions JSON → exécution → vérification**,
mêmes fournisseurs, mêmes réglages.

## Architecture

| Composant | Rôle | Équivalent Python |
|---|---|---|
| `agent/ScreenCapture.kt` | MediaProjection + ImageReader, grille 0-1000 (lignes rouges, labels jaunes) | `display.py` |
| `agent/AgentAccessibilityService.kt` | Gestures (tap/swipe/scroll), saisie texte, dump de l'arbre UI | pyautogui + OCR |
| `agent/AgentService.kt` | Service foreground `mediaProjection`, boucle, notification, events | `agent.py` thread |
| `agent/AgentRun.kt` | Boucle agent, contrat JSON `thought/actions/done/summary` | `agent.py` |
| `agent/AppLauncher.kt` | Ouverture d'apps par nom/alias, URLs, recherche web | `open_app` |
| `agent/OverlayIndicator.kt` | Halo violet au point de tap (curseur visuel) | curseur overlay |
| `ai/AiClient.kt` | 8 fournisseurs, mêmes erreurs FR, retry, fallback clés | `ai_client.py` |
| `data/` | Réglages, mémoire, conversations, historique (JSON) | `settings.py`, `memory.py`, `conversations.py` |
| `ui/screens/` | Agent / Chat / Historique / Paramètres en Compose | `gui.py` |

## Actions de l'agent

`open_app`, `tap`, `double_tap`, `long_press`, `swipe`, `scroll`, `type_text`,
`press_enter`, `press_back`, `press_home`, `press_recents`,
`open_notifications`, `open_url`, `search_web`, `wait` — coordonnées
normalisées 0-1000 comme sur Windows. En bonus, le dump de l'arbre
d'accessibilité donne au modèle les nœuds cliquables/éditables (plus fiable
que la seule vision).

## Build

Prérequis : JDK 17, Android SDK (platform `android-34`, build-tools 34).

```bash
echo "sdk.dir=/chemin/android-sdk" > local.properties
gradle :app:assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk
```

`minSdk 26`, `targetSdk 34`. AGP 8.5.2, Kotlin 2.0.20, Compose BOM 2024.09.02.

## Installation & premiers pas

1. `adb install app-debug.apk` (ou transférer l'APK sur le téléphone).
2. Ouvrir l'app → activer le **service d'accessibilité** « Projet 4, agent IA »
   (bouton sur l'écran Agent, ou Paramètres Android → Accessibilité).
3. Optionnel : autoriser **Curseur visuel** (affichage par-dessus) et les
   notifications.
4. Onglet **Paramètres** : choisir le fournisseur, coller la/les clé(s) API
   (séparées par des virgules), vérifier le modèle, « Tester la connexion ».
5. Onglet **Agent** : décrire l'objectif → « Lancer l'agent » → accepter la
   capture d'écran (demandée à chaque mission, exigence Android).

L'agent tourne en service foreground : tu peux quitter l'app, la notification
montre la progression et permet d'arrêter. L'historique conserve les 100
dernières missions avec le journal complet.

## Fournisseurs

Gemini, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter — et **Ollama** /
**LM Studio** en local (127.0.0.1 ne fonctionne pas depuis le téléphone :
utiliser l'IP du PC sur le réseau, l'app le rappelle dans Paramètres).

Fallback multi-clés et multi-fournisseurs identique à la version Windows :
cooldown 90 s sur clé refusée, retry 5xx, jamais de repli local → cloud.
