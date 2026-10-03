# Validation de la version 1.9.1

Vérifications réalisées sur Windows le 21 septembre 2026.

| Vérification | Résultat |
|---|---|
| Tous les fichiers `scripts/test_*.py` | 81 réussis |
| Dépendances Python (`pip check`) | Aucun conflit détecté |
| Interface native | Fenêtre principale, Chat et paramètres ouverts |
| Saisie bureau | Texte accentué de plus de 200 caractères saisi dans la fenêtre de test |
| Capture Windows | Fenêtre cible capturée et processus propriétaire identifié |
| Overlay | Styles Windows click-through et sans activation vérifiés |
| Navigateur dédié | Clics, saisie Unicode et capture redimensionnée vérifiés sur une page de test |
| Restrictions navigateur | Actions bureau et raccourcis système refusés dans les tests |
| Exécutable autonome | Interface ouverte ; diagnostic navigateur réussi avec pilote embarqué |
| MSI | Construction WiX réussie, extraction administrative réussie (code 0) |
| Exécutable extrait du MSI | Diagnostic navigateur réussi |

## Vérifications réelles du 3 octobre 2026 (branche IA locale / scroll / automatisations)

Faites sur un PC Windows 11, 32 Go de RAM, Radeon RX 5600 XT 6 Go, Ollama 0.33.3.

| Vérification | Résultat |
|---|---|
| Tous les fichiers `scripts/test_*.py` | 173 réussis, en local et sur GitHub Actions |
| Frappe et envoi sur une page Chromium (`smoke_typing.py`) | 7/7 : « salut » tapé une fois, confirmé, envoyé une fois. Le code précédent donnait « salutsalut » et annonçait un échec |
| Défilement sur de vraies fenêtres (`smoke_scroll.py`) | 9/9 : Tk et Chromium, virtuel et physique, vertical et horizontal ; un cran virtuel = un cran réel (133 px contre 134) |
| Ollama arrêté puis sélecteur de modèles | Serveur relancé seul, 11 modèles listés, vision en tête |
| Agent sur `gemma4:12b`, consignes complètes + capture | 1re étape 190 à 290 s (chargement compris), étapes suivantes 45 à 100 s ; run de 3 étapes sans erreur en 470 s |
| Lien Discord dans une automatisation | Discord réduit → ramené au premier plan et positionné sur la conversation du lien |
| Enregistrement « au démarrage de Windows » | Écriture, lecture et suppression vérifiées sur une clé de registre de test |
| Lancement avec `--startup` | Fenêtre ouverte réduite, sans erreur |

Non vérifié en réel : un vrai lien de groupe Discord (essai fait avec un identifiant
factice), l’entrée de démarrage réelle de Windows, LM Studio, le repli Gemini sur
quota 429 et les paramètres OpenAI (tests simulés uniquement).

Le diagnostic du binaire peut être relancé sur un PC disposant d’Edge ou Chrome :

```powershell
.\AgentScreen.exe --self-test-browser "$env:TEMP\projet4-check.json"
```

Ce mode ouvre seulement une session de test avec un profil temporaire, puis écrit
un rapport JSON. Il n’appelle aucune IA et ne navigue pas sur un site externe.

## Ce qui n’est pas validé par ces tests

- Ollama a été validé en réel depuis : serveur relancé automatiquement, modèle
  vision choisi automatiquement (`gemma4:12b`), réponse image correcte en ~9 s.
  LM Studio réel reste non validé : les formats des requêtes, listes de modèles
  et règles de fallback sont couverts par des tests simulés.
- La réussite de toutes les consignes possibles : elle dépend du modèle, des pages,
  du contenu de l’écran et des droits Windows.
- L’installation sur chaque version de Windows ou chaque configuration matérielle.
  L’extraction MSI et son exécutable ont été vérifiés ; pas une matrice de PC vierges.
- Les sites avec CAPTCHA, authentification spéciale ou protocoles externes.

Les workflows GitHub exécutent toute la suite `test_*.py` et reconstruisent la
distribution Windows ; leur résultat est visible dans l’onglet **Actions** du dépôt.
