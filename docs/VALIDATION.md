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
