# Arène Brawl — mini Brawl Stars multijoueur

Jeu d'arène 2D en temps réel (top-down), inspiré de Brawl Stars : choisis un
combattant, déplace-toi au clavier, vise et tire à la souris, élimine les
autres joueurs connectés en direct.

- **Backend** : Flask + Flask-SocketIO (WebSockets, boucle de jeu serveur)
- **Frontend** : HTML5 Canvas + JavaScript, aucune dépendance à installer
- **Hébergement cible** : Railway (gratuit, supporte les WebSockets)

## Déploiement sur Railway

1. Va sur https://railway.app et crée un compte (gratuit, pas besoin de CB
   pour commencer).
2. Clique sur **New Project → Deploy from GitHub repo** (le plus simple est
   de pousser ce dossier dans un dépôt GitHub), ou utilise **Empty Project**
   puis l'onglet **Deploy** pour uploader directement ce zip décompressé.
3. Railway détecte automatiquement Python grâce à `requirements.txt` et lit
   la commande de démarrage dans `Procfile`. Aucune configuration
   supplémentaire n'est nécessaire.
4. Une fois le déploiement terminé, Railway te donne une URL publique
   (Settings → Networking → Generate Domain). C'est le lien à partager avec
   tes amis pour jouer ensemble.

### Si tu préfères la ligne de commande

```bash
npm install -g @railway/cli
railway login
railway init
railway up
railway domain
```

## Lancer en local pour tester avant de déployer

```bash
pip install -r requirements.txt
python app.py
```

Puis ouvre http://localhost:5000 dans plusieurs onglets pour simuler
plusieurs joueurs.

## Structure du projet

```
brawl-arena/
├── app.py                 # Serveur Flask + Socket.IO + boucle de jeu
├── requirements.txt        # Dépendances Python
├── Procfile                 # Commande de démarrage pour Railway
├── templates/
│   └── index.html          # Écran de sélection + zone de jeu
└── static/
    ├── css/style.css       # Interface
    └── js/game.js          # Rendu canvas + contrôles + Socket.IO
```

## Personnages

| Personnage    | PV  | Dégâts | Cadence | Portée |
|---------------|-----|--------|---------|--------|
| Rocailleux    | 180 | 12     | 1.67/s  | 260    |
| Vif-Argent    | 110 | 9      | 3.57/s  | 340    |
| Longue-Vue    | 85  | 26     | 1.00/s  | 560    |

## Pour aller plus loin

- Ajouter des salles (rooms) pour plusieurs parties simultanées
- Ajouter des obstacles/murs dans l'arène (buissons, murs destructibles)
- Ajouter un mode d'équipe (2v2, 3v3)
- Sauvegarder les scores dans une base de données (Railway propose
  PostgreSQL gratuit sur son plan de démarrage)
