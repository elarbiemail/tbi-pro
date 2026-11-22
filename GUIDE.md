# TBI Pro : tableau blanc interactif à faible coût

TBI Pro transforme n'importe quelle projection (mur, tableau blanc, drap) en **tableau blanc interactif**, avec :

- un **vidéoprojecteur** et un **PC Windows** ;
- une **caméra**, au choix :
  - le **portable** (scan d'un QR code, aucune appli à installer),
  - une **webcam**, ou le portable utilisé comme webcam (DroidCam / Iriun),
  - une **caméra infrarouge**, pour plus de fiabilité en salle éclairée ;
- un ou plusieurs **stylets à LED** faits maison.

### Les trois modes

| Mode | Ce que fait le stylet |
|---|---|
| 🖱️ **Souris** | Pilote tout l'ordinateur : PowerPoint, PDF, navigateur, vidéos… Pointe appuyée = clic, glissée = glisser. |
| 🖊️ **Annoter** | Écrit **par-dessus n'importe quel logiciel** (diaporama, PDF, site web). L'écran peut être « figé » pour écrire sur une vidéo, et une capture peut être enregistrée. |
| 📋 **Tableau** | Tableau blanc plein écran : pages, fonds (blanc, quadrillage, **Seyès**, lignes, ardoise), stylo, surligneur, gomme, formes, images, annuler/rétablir, enregistrement et **export PDF**. |

**Sans stylet : le doigt.** En mode « Doigt », le pointeur suit le **bout de l'index**, reconnu par l'intelligence artificielle de détection de la main (MediaPipe). Pour cliquer, au choix :
- **pincer le pouce et l'index** : clic maintenu, pour écrire, dessiner ou glisser ;
- **garder le doigt immobile 1 seconde** : simple clic, pratique en mode souris et pour les boutons.

**Plusieurs stylets en même temps** (modes Annoter et Tableau) : chaque stylet est reconnu par la **couleur de sa LED** (blanc, rouge, vert, bleu). Chaque élève garde son propre outil, sa couleur et son épaisseur. Il suffit de toucher la barre d'outils avec son stylet pour régler *ce* stylet.

---

## 1. Fabriquer les stylets

### 1a. Stylet à LED visible (portable ou webcam)

| Pièce | Rôle |
|---|---|
| Feutre de tableau usagé, vidé | Corps |
| LED 5 mm haute luminosité : **verte, rouge, bleue ou blanche** (une couleur par stylet) | Point détecté |
| Micro-interrupteur (bouton 6×6 mm ou micro-switch à levier) | Allume la LED quand la pointe touche |
| Pile bouton CR2032 + support | Alimentation |
| Résistance 33 Ω (facultative) | Protège la LED |

```
 (+) CR2032 ──[33 Ω]──► LED (patte longue +) ── (patte courte −) ──[INTERRUPTEUR]── (−) CR2032

 ┌──────────────────────────── corps du feutre ────────────────────────────┐
 │ [pile]  ── fils ──  [interrupteur]  ◄── [LED] ◄─ pointe (recule de 1 mm) │
 └─────────────────────────────────────────────────────────────────────────┘
```

1. Percez le bouchon : la LED doit dépasser de 3-5 mm et pouvoir **reculer d'environ 1 mm** pour presser l'interrupteur.
2. Câblez selon le schéma et isolez les connexions.
3. Test : la LED s'allume quand on appuie la pointe sur une table, et s'éteint quand on relâche.
4. Poncez légèrement le sommet de la LED : la lumière se diffuse, et la caméra la voit même stylet incliné.

### 1b. Stylet infrarouge (caméra IR)

Même montage, avec une **LED infrarouge 850 nm** (la mieux vue par les caméras) ou 940 nm (totalement invisible, mais moins bien captée). Choisissez une LED IR « haute puissance » à large angle.
La lumière infrarouge est invisible à l'œil : pour vérifier qu'elle s'allume, regardez-la à travers la caméra d'un portable.

> Avec une caméra IR, toutes les LED ont la même « couleur ». Les stylets sont distingués par leur position : plusieurs élèves peuvent écrire en même temps, mais ils partagent les mêmes réglages d'outil.

### 1c. Pas de stylet : le doigt

Dans le panneau de contrôle, section **« 3. Pointeur »**, choisissez **« Doigt »**.
- La caméra doit filmer en **exposition normale** : la main doit être bien visible. La page du portable règle cela automatiquement.
- Le pointeur (cercle jaune) suit l'index. Le cercle se remplit quand vous pincez.
- **Calibrage au stylet en mode doigt** : placez l'index au centre de chaque cible et **pincez** une demi-seconde. Le calibrage auto fonctionne aussi.
- Le modèle de détection de la main est inclus dans l'exécutable. En version « code source », il est téléchargé une seule fois (7 Mo) au premier usage.
- Le mode doigt fonctionne avec le portable (QR code) et la webcam, pas avec la caméra infrarouge.
- Conseil : tenez-vous de côté pour que la caméra voie bien votre main, sans la cacher avec votre corps.
- **Précision** : après le calibrage, l'option « Zoomer sur la projection avant la détection » ne fait analyser que la zone utile de l'image, agrandie. Le pincement est mesuré en 3D (en centimètres réels), donc il reste fiable quelle que soit l'orientation de la main. Le réglage « Stabilisation du pointeur » supprime les tremblements à l'arrêt sans ralentir le tracé rapide.

---

## 2. Choisir et installer la caméra

### Option A : le portable par QR code (recommandé pour démarrer)

1. Dans TBI Pro, source **« Portable (QR code, sans appli) »**.
2. Le PC et le portable doivent être sur le **même réseau Wi-Fi** (un partage de connexion depuis le portable fonctionne aussi).
3. Scannez le QR code affiché dans le panneau de contrôle.
4. Un **avertissement de sécurité** apparaît, car le certificat est créé par votre PC : touchez **« Paramètres avancés » → « Continuer vers le site »**.
5. Touchez **« Démarrer la caméra »** et autorisez l'accès.
6. Ouvrez **« Réglages caméra »** en bas de l'écran du portable et **baissez l'exposition** : la projection doit devenir sombre, et seule la LED ressort.
7. « Écran noir » éteint l'affichage du portable : moins de batterie consommée et pas de lumière parasite. La caméra continue de fonctionner.

La détection se fait **sur le portable** et seules les positions sont envoyées au PC : la latence est faible, même en Wi-Fi.

> La 1re fois, Windows demande d'autoriser TBI Pro sur le réseau : cochez **« Réseaux privés »** et validez.
> Si le portable n'arrive pas à se connecter sur le réseau de l'établissement (Wi-Fi « invité » qui isole les appareils), utilisez le partage de connexion du portable, ou l'option B.

### Option B : webcam, DroidCam ou Iriun

- Source **« Webcam / DroidCam / Iriun »**, puis indiquez le numéro de caméra (`0` = webcam intégrée, `1` = souvent le portable) ou l'adresse DroidCam `http://ADRESSE_IP:4747/video`, et cliquez **Appliquer**.
- Baissez l'exposition dans l'appli DroidCam / Iriun.

### Option C : caméra infrarouge (pour plus tard)

La caméra IR ne voit que l'infrarouge : la projection devient invisible pour elle et seule la LED IR du stylet apparaît. C'est la solution **la plus fiable**, même avec des images très claires ou une salle éclairée.

Solutions possibles :
- une **caméra USB « sans filtre IR »** (vendue « 850 nm », « vision nocturne » ou « NoIR »), avec un **filtre passe-infrarouge** (850 nm) devant l'objectif ;
- une **webcam ordinaire modifiée** : retirer le petit filtre anti-IR derrière l'objectif et le remplacer par un filtre passe-IR. À défaut, un morceau de **négatif photo argentique développé** (partie noire) ou de disquette fait souvent l'affaire.

Dans TBI Pro : source **« Caméra infrarouge + stylet IR »**, puis numéro de caméra et **Appliquer**.
- Le **fond infrarouge** (soleil, lampes à incandescence, reflets) est appris automatiquement quand aucun stylet n'est visible, et soustrait de l'image.
- Si la caméra ou l'éclairage change, cliquez **« Réapprendre le fond infrarouge »**.
- Pour le calibrage, utilisez **« Calibrer au stylet »** : la caméra IR ne voit pas la projection, donc le calibrage automatique ne fonctionne pas avec elle.

### Placement de la caméra (toutes options)

- **Fixe** (trépied, support, plafond), **à côté du vidéoprojecteur** : votre corps ne doit pas cacher le tableau.
- Toute la projection doit être visible, avec un peu de marge.
- Si la caméra bouge, **recalibrez**.

---

## 3. Installer TBI Pro

**Version exécutable (recommandée)** : décompressez `TBI-Pro-Windows.zip` et lancez **`TBI Pro.exe`**. Aucune installation de Python n'est nécessaire. Le dossier peut être copié sur une clé USB et sur les autres PC.

**Depuis le code source** : installez Python 3.11 ou 3.12 (case « Add Python to PATH » cochée), puis double-cliquez sur **`lancer.bat`** (la 1re fois, il installe les bibliothèques).

**Créer l'exécutable vous-même** : deux possibilités.
- **Sur un PC Windows** : double-cliquez sur `build_exe.bat`. Le résultat est dans `dist\TBI Pro\`.
- **Sur GitHub** : déposez le dossier dans un dépôt. Le fichier `.github/workflows/build.yml` construit automatiquement le `.zip`, à récupérer dans l'onglet **Actions → Artifacts**. Créer un tag `v1.0.0` publie aussi une « Release ».

---

## 4. Première utilisation

1. Branchez le vidéoprojecteur et lancez TBI Pro. Le **panneau de contrôle** s'ouvre sur l'écran du PC.
2. **Caméra** : choisissez la source et connectez-la (étape 2).
3. **Écran projeté** : choisissez l'écran du vidéoprojecteur. En mode « Dupliquer », c'est le même écran que le PC.
4. **Calibrage** :
   - **🎯 Calibrer au stylet** : 4 cibles s'affichent sur la projection ; appuyez le stylet au centre de la cible jaune, maintenez une demi-seconde, relâchez. Recommencez pour les 4 cibles. C'est le plus précis.
   - **⚡ Calibrage auto** : la projection passe au noir puis au blanc, et la zone est trouvée seule. C'est plus rapide, mais impossible avec une caméra IR.
5. Réglez la **détection** en regardant la « Vue de la caméra » : chaque stylet allumé doit être entouré d'un cercle de sa couleur, et rien d'autre.
6. Choisissez un **mode**. En mode Souris, un bouton **✍️** reste en bas à droite de la projection : touchez-le avec le stylet pour passer en Annoter ou en Tableau.

Les réglages et le calibrage sont enregistrés : au prochain lancement, tout est prêt.

---

## 5. La barre latérale (Annoter et Tableau)

La barre se **masque toute seule** après quelques secondes sans être touchée : il reste un petit onglet **☰** au bord de l'écran. Touchez-le pour la faire revenir. **📌** épingle la barre (elle ne se masque plus), **⇆** la passe de l'autre côté, **«** la masque tout de suite.

**Barre principale (outils les plus utilisés)**

| Bouton | Action |
|---|---|
| 🖱️ 🖊️/📋 | Mode souris / annotation / tableau |
| ⋯ | Ouvre le panneau **Plus** (voir ci-dessous) |
| 🖐️ | **Sélection** : touchez un objet pour le sélectionner. Ensuite, glisser = déplacer, **coins** = agrandir / réduire, **⟳** = pivoter (aimanté tous les 15°). Barre d'actions sous l'objet : 🗑 supprimer, ⧉ dupliquer, ⬆ premier plan, ⬇ arrière-plan, ✏ modifier le texte, ◧ plein / vide. Toucher une couleur recolore l'objet sélectionné. Cela marche pour **tous les objets** : traits, formes, textes, images, cartes mentales, nuages de mots. |
| ✏️ 🖍️ 🧽 | Stylo, surligneur, gomme |
| ✍️ | **Écriture → texte** : écrivez à la main. Une seconde et demie après le dernier trait, l'écriture est reconnue (en français) et remplacée par du texte tapé, à la même taille. Nécessite Internet. |
| 🪄 | **Stylo de formes** : dessinez à main levée un cercle, une ellipse, un rectangle, un carré, un triangle, un polygone, une ligne ou une flèche, qui est remplacé par une forme nette. Fonctionne sans Internet. |
| 🔤 | Texte au clavier virtuel |
| ╱ ➚ ▭ ◯ △ ☆ | Ligne, flèche, rectangle, ellipse, triangle, étoile |
| Couleurs, 🎨 | 8 couleurs + **toutes les couleurs** (nuancier) |
| • ● ⬤, ◧ | Épaisseur ; formes **pleines** ou vides |
| ↶ ↷ 🗑️ | Annuler, rétablir, effacer la page |
| ▶ / 📸 | Page suivante (tableau) / capture d'écran (annotation) |

**Panneau « ⋯ Plus »**

| Rubrique | Contenu |
|---|---|
| Géométrie | 📏 règle, 📐 équerre, ◠ rapporteur, 🧭 compas |
| Présenter | 🔦 **projecteur** (tout l'écran est assombri sauf un disque, déplaçable ; ◉ change sa taille), 🎭 **rideau** (cache le haut de l'écran, glissez pour dévoiler progressivement), ⏱️ minuteur, 🎲 **tirage au sort** (liste d'élèves mémorisée, avec ou sans remise, et dé) |
| Ressources et activités | 🖼️ bibliothèque d'images, ☁️ nuage de mots, 🧠 carte mentale, ⚙️ panneau de contrôle |
| Pages | ◀ ▶ ➕, 🗂️ **gestion des pages** (aperçus, afficher, dupliquer, réordonner, supprimer), ▦ **fonds** : blanc, quadrillage, Seyès, lignes, points, **papier millimétré**, **repère orthonormé**, **portées musicales**, ardoise, noir |
| Fichiers | 💾 enregistrer, 📂 ouvrir, 📥 **importer un PDF** (chaque page devient une page du tableau sur laquelle on écrit ; pour un diaporama, exportez-le d'abord en PDF), 📄 exporter en PDF |

Le tableau est **sauvegardé automatiquement** toutes les 2 minutes dans `Documents\TBI Pro\Sauvegardes automatiques`.

### Outils de classe

| Bouton | Outil |
|---|---|
| 🔤 | **Texte** : touchez la page, puis écrivez avec le clavier virtuel (ou le clavier du PC). La taille suit l'épaisseur choisie. |
| 🧭 | **Compas** : appuyez au centre, glissez pour ouvrir le compas (le rayon s'affiche en cm), relâchez pour tracer le cercle. |
| 📏 📐 ◠ | **Règle, équerre, rapporteur** : un toucher les pose ou les retire. Glisser à l'intérieur pour les déplacer, poignée ⟳ pour les faire tourner (aimantation tous les 15°, angle affiché), × pour les retirer. **Tracez au stylo le long d'un bord** : le trait devient parfaitement droit. |
| 🖼️ | **Bibliothèque d'images** (voir ci-dessous) |
| ⏱️ | **Minuteur / chronomètre** : −1 / +1 / +5 minutes, ⏯️ démarrer/pause, ⟲ remise à zéro, ⏱️ changer de mode. Les 10 dernières secondes s'affichent en rouge, avec un signal sonore à la fin. |
| ☁️ | **Nuage de mots** : les élèves scannent le QR code affiché avec leur téléphone (même Wi-Fi), et leurs mots apparaissent en direct. Plus un mot est proposé, plus il est grand. Vous pouvez poser la question, ajouter des mots, fermer les réponses, puis **insérer le nuage dans le tableau**. |
| 🧠 | **Carte mentale** : écrivez un plan (1re ligne = idée centrale, une branche par ligne, « ⇥ Sous-idée » pour une sous-branche). L'aperçu se met à jour en direct, puis la carte est insérée dans le tableau, où elle se déplace avec ✋. |

### Bibliothèque d'images

- **Pictogrammes (hors ligne)** : plusieurs centaines de pictogrammes couleur classés par thèmes (école, animaux, nature, météo, aliments, corps et émotions, métiers, transports et lieux, sports et arts, sciences et symboles).
- **Banques libres en ligne** (le PC doit être connecté à Internet). Choisissez une banque, puis une **catégorie** (école, animaux, corps, émotions, aliments, nature, météo, transports, métiers, maison, sport, musique, sciences, géographie, histoire, famille, vêtements, lecture) ou tapez un mot :
  - **ARASAAC** : pictogrammes éducatifs, recherche en français (licence CC BY-NC-SA, usage non commercial) ;
  - **Icônes couleur** : OpenMoji, Noto, Twemoji, Fluent (recherche plutôt en anglais) ;
  - **Openverse** : illustrations et photos sous licence Creative Commons ou domaine public ;
  - **Wikimedia Commons** : photos, cartes, documents historiques ;
  - **Cartes et schémas** (Wikimedia) ;
  - **Œuvres d'art du domaine public** (Metropolitan Museum of Art) ;
  - **Icônes simples** monochromes (Material Design, Tabler, Phosphor, Carbon) ;
  - **Drapeaux du monde** (environ 180 pays, recherche par nom en français).
- **Mes ressources** : toutes les images déposées dans `Documents\TBI Pro\Ressources` (sous-dossiers compris), plus « Autre fichier… ».

Touchez une vignette : l'image est insérée au centre de la page. Déplacez-la ensuite avec l'outil ✋. Quand la licence l'exige, le **crédit de l'auteur** est ajouté automatiquement sous l'image.

---

## 6. Réglages de détection

| Réglage | Effet |
|---|---|
| **Seuil de luminosité** | Montez-le si des zones claires de la projection sont détectées ; baissez-le si la LED n'est pas vue. |
| **Taille mini / maxi du point** | Écarte les petits reflets et les grandes zones claires. |
| **Lissage du tracé** | Réduit les tremblements du trait (40-60 % convient pour écrire), au prix d'un léger retard. |
| **Distinguer les stylets par couleur** | Activé : chaque couleur de LED a ses propres réglages. Désactivé : tous les stylets sont identiques. |
| **Stylets simultanés** | Nombre maximal de stylets suivis en même temps. |
| **Pointeur laser** (mode souris) | Pour un pointeur laser : le curseur suit le point, et un point immobile pendant 1 s fait un clic. |

---

## 7. Dépannage

| Problème | Solution |
|---|---|
| Le portable ne charge pas la page | Même Wi-Fi ? Pare-feu Windows autorisé (réseaux privés) ? Essayez le partage de connexion du portable. |
| « Caméra refusée » sur le portable | Utilisez Chrome (Android) ou Safari (iPhone), et autorisez la caméra dans les réglages du site. |
| Le curseur saute partout | **Baissez l'exposition**, montez le seuil, vérifiez la vue caméra : seul le stylet doit être entouré. |
| Décalage entre stylet et trait | Recalibrez. Vérifiez que l'écran choisi est bien le projecteur. |
| Le calibrage auto échoue | La caméra doit voir toute la projection. Sinon, calibrez au stylet. |
| Mode doigt : rien ne se passe | Vérifiez que la main est bien éclairée et visible (cercle jaune dans la vue caméra). Remontez l'exposition sur le portable. Au premier usage depuis le code source, le PC doit être connecté à Internet pour télécharger le modèle. |
| Nuage de mots : les élèves n'accèdent pas à la page | Ils doivent être sur le même Wi-Fi que le PC, et le pare-feu Windows doit autoriser TBI Pro sur les réseaux privés. |
| Banques en ligne : « Connexion impossible » | Vérifiez Internet sur le PC. Le réseau de l'établissement bloque peut-être certains sites : essayez une autre banque. |
| Mode doigt : clics involontaires | Passez à « Garder le doigt immobile 1 s », ou pincez plus franchement. |
| Deux stylets de même couleur se mélangent | Utilisez des LED de couleurs différentes, ou espacez les élèves. |
| Caméra IR : taches parasites | « Réapprendre le fond infrarouge », fermez les rideaux côté soleil, montez le seuil. |
| Rien ne se passe | Consultez le journal `%APPDATA%\TBIPro\tbipro.log`. |

---

## 8. Pour les développeurs : ajouter un capteur

Le code est organisé en modules (`tbipro/`) :

| Fichier | Rôle |
|---|---|
| `sources.py` | Sources caméra et **registre `SOURCES`** |
| `vision.py` | Détection, couleur des LED, fond infrarouge, détection de la main (pincement), homographie, suivi multi-pointeurs |
| `handmodel.py` | Modèle de la main (inclus ou téléchargé au premier usage) |
| `phone/index.html` | Page du portable (caméra + détection en JavaScript) |
| `app.py` | Contrôleur : boucle principale, modes, distribution des événements |
| `ui/` | Panneau de contrôle, tableau blanc, calque d'annotation, barre d'outils, calibrage |

Pour brancher un nouveau capteur (Wiimote, caméra réseau, capteur de profondeur…) : créer une classe dérivée de `BaseSource` qui appelle `self._push([(x, y, surface, couleur[, appuyé]), …])` avec des coordonnées normalisées (0-1), puis l'ajouter au dictionnaire `SOURCES`. Calibrage, suivi, modes et interface fonctionnent alors sans autre modification.
