# Arène Brawl — Document de Design

Ce document résume la direction de jeu discutée, à faire évoluer au fur et à mesure.

## Concept général

Battle royale : **10 joueurs** apparaissent sur une même carte. La zone jouable
se rétrécit progressivement au fil du temps. **Dernier survivant gagne.**

Principe central : **le personnage n'a aucune statistique propre.** Toute la
puissance vient de l'**arme équipée**. Un même joueur peut être fort ou faible
selon l'arme qu'il porte, pas selon un "niveau de personnage" classique.

## Armes

- Chaque joueur peut porter **2 armes maximum**, mais une seule est
  **active/équipée** à la fois.
- Chaque arme a son **propre niveau et sa propre XP**, totalement indépendants
  l'un de l'autre. Changer d'arme active ne transfère rien automatiquement.
- Tuer un ennemi (joueur ou monstre) donne de l'XP à l'**arme actuellement
  équipée**.
- À chaque montée de niveau d'une arme, le joueur choisit **entre 2
  propositions** :
  - un bonus **passif** (statistique : dégâts, vitesse, PV, cadence de tir…)
  - ou un bonus **actif** (une capacité/compétence utilisable)
- Au fil de la progression, l'**apparence du personnage change
  progressivement** pour refléter la "classe" que l'arme est en train de
  devenir (évolution visuelle liée au build choisi).
- **Station de transfert** : un lieu spécifique sur la map permet de
  transférer l'XP investie d'une arme vers l'autre arme portée.
- **Mort d'un joueur** : son arme équipée **drop au sol** à l'endroit de sa
  mort, ramassable par n'importe quel autre joueur.

## Monstres

- Des monstres apparaissent aléatoirement sur la map.
- Ils ont un **délai de vie** : s'ils ne sont pas combattus/tués à temps, ils
  disparaissent d'eux-mêmes.
- Sous certaines conditions (à définir), un monstre peut **évoluer en boss**.

## Condition de victoire

- Dernier joueur en vie.
- Zone de jeu qui se referme progressivement (mécanique de zone/tempête,
  façon battle royale classique), pour forcer les affrontements.

## Points encore à trancher

Ces questions restent ouvertes et devront être précisées avant/pendant le
développement des mécaniques correspondantes :

1. **Monstres → boss** : quelle est la condition exacte de transformation
   (timer, nombre de monstres tués à proximité, ramassage d'un objet
   déclencheur, zone spécifique) ?
2. **Délai de vie des monstres** : combien de temps avant disparition ?
3. **Zone qui rétrécit** : sur quel intervalle de temps ? Dégâts infligés
   hors-zone ? Nombre de phases de rétrécissement ?
4. **Évolution visuelle du personnage** : à partir de combien de niveaux/choix
   le changement d'apparence se déclenche-t-il ? Combien de "classes"
   visuelles au total ?
5. **Station de transfert d'XP** : transfert total ou partiel ? Coût associé
   (temps, ressource) ou gratuit ?
6. **Apparition des armes sur la map** : fréquence, zones de spawn fixes ou
   aléatoires, rareté des armes de départ ?

## État actuel du projet technique

- Backend : Flask + Flask-SocketIO (temps réel, hébergé sur Railway)
- Frontend : Phaser.js (rendu, animations, sprites 4-directionnels)
- Personnages : sprites composés à partir du pack "Mana Seed" (Seliel the
  Shaper) — corps + tenue + cheveux, 4 directions, idle/marche/attaque
- Décor : fond de carte forestier (pack "Gentle Forest")
- Ce qui existe déjà et qu'il faudra faire évoluer vers ce design :
  - **Système de progression d'arme (XP/niveau, choix de bonus) — IMPLÉMENTÉ** (v1) :
    l'arme équipée gagne de l'XP en tuant (slimes/joueurs), monte de niveau, et
    propose un choix entre 2 bonus passifs à chaque palier (dégâts, cadence,
    portée, vitesse, PV max). Réinitialisé à chaque changement d'arme ou mort.
    Référence de style : *MO.CO* (Supercell) — XP liée à l'équipement, pas au
    personnage.
  - **Reste à faire** : bonus **actifs** (capacités, pas juste des stats) en
    plus des passifs ; slot de 2 armes simultanées ; station de transfert d'XP
    entre deux armes ; évolution visuelle du personnage selon la progression.
  - Combat par projectiles simple → conservé comme base, enrichi par les bonus
    de l'arme (dégâts/cadence/portée/vitesse modifiés dynamiquement)
  - Lobby de sélection de personnage → à transformer en sélection/apparition
    sur la map avec ramassage d'armes au sol

## Prochaine étape suggérée

Une fois les points ouverts tranchés, prochaines briques techniques à
construire dans cet ordre logique :
1. Système d'arme au sol (spawn, ramassage, drop à la mort)
2. Système d'XP/niveau par arme + écran de choix (passif vs actif)
3. Zone qui rétrécit + dégâts hors-zone
4. Spawn de monstres + logique de disparition par délai
5. Station de transfert d'XP
6. Évolution visuelle du personnage selon la progression
7. Boss (une fois la condition de déclenchement tranchée)
