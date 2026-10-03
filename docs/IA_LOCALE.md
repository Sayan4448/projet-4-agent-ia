# Ollama et LM Studio

Le mode local n’exige pas de clé API. Une clé facultative peut être renseignée si
votre serveur est protégé. La liste des modèles provient du serveur réellement configuré.
L’application ne télécharge jamais de modèle sans votre intervention. En revanche,
pour éviter les faux départs : **Ollama est relancé automatiquement** si son
serveur est arrêté (`ollama serve`, sans fenêtre) et, si le champ modèle est
resté vide, **un modèle installé est choisi automatiquement** — toujours un modèle
vision compatible chat s’il y en a un (le Chat et l’Agent partagent ce choix, et
l’agent est aveugle sans vision), le plus léger d’abord. Le choix reste modifiable
dans le sélecteur, qui **liste tout seul les modèles installés** dès qu’un
fournisseur local est sélectionné (vision en tête, modèles d’embedding masqués).

## Ollama

1. Installer Ollama depuis son site officiel : <https://ollama.com>.
2. Télécharger un modèle compatible vision pour l’agent (ou textuel pour le Chat).
   Utiliser le nom exact de la bibliothèque Ollama, par exemple `ollama pull gemma3:4b`
   (léger), `ollama pull qwen2.5vl:7b` ou `ollama pull llama3.2-vision:11b`.
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
`response_format: json_object` pour les décisions (retiré automatiquement si le
serveur le refuse — LM Studio n’accepte que `json_schema`).

## Choisir un modèle

Un modèle texte peut répondre au test « OK » mais échouer dès qu’une capture est jointe.
La liste de modèles n’est pas une certification de leurs capacités. Vérifier vision,
JSON/instruction following, taille du contexte et mémoire requise dans la fiche du modèle.
La qualité de contrôle varie beaucoup selon le modèle et sa quantification.

## Confidentialité et erreurs

- Une session locale ne bascule pas vers les clés cloud enregistrées.
- Une adresse locale personnalisée peut pointer vers un autre PC : les captures seront
  alors envoyées à ce PC. Utiliser l’adresse souhaitée et un réseau approprié.
- **Connexion refusée** : Ollama est relancé automatiquement ; sinon démarrer le
  serveur, vérifier le port et le pare-feu.
- **Réponse vide** : les modèles « thinking » reçoivent `think: false`
  automatiquement ; si un modèle reste muet, en choisir un autre.
- **Délai dépassé** : le premier appel de l’agent paie le chargement du modèle
  puis la lecture de toutes ses consignes (~190 s mesurés avec un 12B sur une
  carte 6 Go) ; le plancher local est donc de 10 minutes. Les étapes suivantes
  réutilisent les consignes déjà lues par le serveur (~45 s au lieu de ~155 s).
- **Erreur 400/500** : le message affiché est celui du serveur local (mémoire
  insuffisante, modèle introuvable…), sans nouvelle tentative inutile.
- **Liste vide** : télécharger/charger un modèle et vérifier le serveur sélectionné.
- **Erreur image/vision** : sélectionner un modèle compatible images.
- **Trop lent / mémoire insuffisante** : modèle plus petit, quantification adaptée ou mode éco.
- Le délai HTTP est réglable (« Délai IA », plancher de 10 minutes en local) ;
  le bouton Stop reste disponible pendant l’attente.
- La fenêtre de contexte Ollama est fixée à 8192 jetons : les consignes de l’agent
  (~2800 jetons) plus sa réponse ne tiennent pas dans les 4096 par défaut.
