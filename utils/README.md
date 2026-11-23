# Stockage hybride (SQLite / PostgreSQL) et traitement des données

**Responsable :** NOUIRA Ismail — 4A Robotique & Instrumentation (Polytech Dijon)

Ce dossier regroupe la couche de persistance PostgreSQL, le basculement automatique entre SQLite et PostgreSQL, la synchronisation des données locales et le pipeline de détection d'anomalies.

## Organisation des fichiers

* `database_pg.py` : gestionnaire PostgreSQL (`GestionnaireBDPostgreSQL`) avec pool de connexions thread-safe et indexation SQL.
* `db_factory.py` : point d'entrée unique (`obtenir_gestionnaire_bd`) qui choisit le moteur selon `.env` et bascule sur SQLite en mode dégradé si PostgreSQL est injoignable.
* `sync_sqlite_to_pg.py` : rapatriement incrémental des enregistrements de `data/usine.db` vers PostgreSQL.
* `traitement_donnees.py` : filtrage des mesures capteurs, détection d'anomalies (seuils fixes + Z-score) et génération des commandes matérielles.
* `create_db.py` *(branche `cyborg`)* : gestionnaire SQLite local, laissé intact pour éviter tout conflit avec le reste de l'équipe.

## Choix techniques et problèmes réglés

* **Faire cohabiter SQLite et PostgreSQL sans casser le code des collègues :** SQLite est pratique pour les tests embarqués sur Raspberry Pi sans serveur, mais supporte mal les accès concurrents quand plusieurs scripts (acquisition capteurs, nœuds ROS, interface Flask) écrivent en même temps. Plutôt que de remplacer `create_db.py`, `GestionnaireBDPostgreSQL` reprend exactement les 6 tables, les mêmes signatures de méthodes, le même format de dates (`YYYY-MM-DD HH:MM:SS`) et le même hachage de mots de passe (`PBKDF2-HMAC-SHA256`, `sel:hash`). L'équipe peut passer d'une base à l'autre en changeant une seule ligne dans `.env`.
* **Éviter les collisions d'identifiants lors de la synchronisation :** Si SQLite et PostgreSQL tournent séparément, forcer les mêmes `id` numériques provoque des erreurs de clé primaire. `sync_sqlite_to_pg.py` s'appuie donc sur les clés métier (`nom_utilisateur`, `uid` RFID) et ne transfère que les mesures et événements postérieurs au dernier horodatage déjà présent dans PostgreSQL.
* **Fiabiliser les chemins relatifs :** Le gestionnaire SQLite initial pointe sur `../data/usine.db`, ce qui échoue si on lance Python depuis la racine du dépôt. `db_factory.py` et `sync_sqlite_to_pg.py` résolvent le chemin dynamiquement à partir de la racine du projet via `pathlib.Path`, sans modifier `create_db.py`.
* **Gérer les cas limites des capteurs réels :**
  * Le DHT11 renvoie parfois des lectures corrompues ou nulles : toute valeur hors plage physique (`[-20 ; 100] °C` ou `[0 ; 100] %`) est rejetée avant insertion en base.
  * L'Arduino renvoie la luminosité sous forme de chaîne (`"742"`) ou `"N/A"` au démarrage, avec une polarité inversée (`> 600` = obscurité). `traitement_donnees.py` normalise ces valeurs (`int` ou `None`) et produit directement l'ordre série attendu par l'Arduino (`b"A"` ou `b"N"`).
  * En plus des seuils fixes (fumée, température `> 45 °C`, humidité `> 80 %`), un calcul de **Z-score** sur fenêtre glissante (`N = 20`) repère les dérives thermiques brutales avant le seuil critique, avec un *cooldown* de 30 s pour ne pas saturer la table `evenements_systeme`.
* **Tester sans matériel ni serveur actif :** La suite `tests/test_storage_processing.py` utilise un double en mémoire respectant le contrat commun des deux gestionnaires, avec un fichier `pytest.ini` à la racine pour que `pytest -v` résolve les imports `utils.*` directement.

## Mise en route rapide

1. Copier le modèle de variables d'environnement à la racine du dépôt :
   ```bash
   cp .env.example .env