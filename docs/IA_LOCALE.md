# Ollama et LM Studio

Le mode local n’exige pas de clé API. Une clé facultative peut être renseignée si
votre serveur est protégé. La liste des modèles provient du serveur réellement configuré.
L’application ne télécharge ni ne démarre des modèles sans votre intervention.

## Ollama

1. Installer Ollama depuis son site officiel : <https://ollama.com>.
2. Télécharger un modèle compatible vision pour l’agent (ou textuel pour le Chat).
   Utiliser le nom exact de la bibliothèque Ollama, par exemple `ollama pull <modele>`.
3. Lancer Ollama. Au besoin, utiliser `ollama serve` dans un terminal.
4. Dans Paramètres, choisir **Ollama (local)**.
5. Adresse par défaut : `http://127.0.0.1:11434`.
6. **Charger modèles**, choisir le modèle, **Enregistrer**, **Tester la connexion**.

API utilisées : `GET /api/tags`, `POST /api/chat`, messages non streamés, images base64,
sortie JSON demandée pour les décisions de l’agent.

## LM Studio

1. Installer LM Studio depuis <https://lmstudio.ai>.
2. Télécharger puis charger un modèle. Pour l’agent, choisir un modèle vision et
   charger les composants vision associés si LM Studio le demande.
3. Dans l’espace développeur, démarrer le **Local Server** compatible OpenAI.
4. Dans l’app, choisir **LM Studio (local)**.
5. Adresse par défaut : `http://127.0.0.1:1234/v1`.
6. Charger la liste, choisir le modèle chargé puis tester la connexion.

API utilisées : `GET /v1/models`, `POST /v1/chat/completions`, images en data URL et
`response_format: json_object` pour les décisions.

## Choisir un modèle

Un modèle texte peut répondre au test « OK » mais échouer dès qu’une capture est jointe.
La liste de modèles n’est pas une certification de leurs capacités. Vérifier vision,
JSON/instruction following, taille du contexte et mémoire requise dans la fiche du modèle.
La qualité de contrôle varie beaucoup selon le modèle et sa quantification.

## Confidentialité et erreurs

- Une session locale ne bascule pas vers les clés cloud enregistrées.
- Une adresse locale personnalisée peut pointer vers un autre PC : les captures seront
  alors envoyées à ce PC. Utiliser l’adresse souhaitée et un réseau approprié.
- **Connexion refusée** : démarrer le serveur, vérifier le port et le pare-feu.
- **Liste vide** : télécharger/charger un modèle et vérifier le serveur sélectionné.
- **Erreur image/vision** : sélectionner un modèle compatible images.
- **Trop lent / mémoire insuffisante** : modèle plus petit, quantification adaptée ou mode éco.
- Le délai HTTP actuel est de 90 secondes ; le bouton Stop reste disponible pendant l’attente.
