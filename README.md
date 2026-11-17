# 🏭 Next Factory — Prototype Hybride (Raspberry Pi 4 + Arduino)

Ce dépôt contient le code et l'architecture matérielle du prototype de supervision centralisée (usine / maison connectée) avant l'intégration finale dans la maquette imprimée en 3D.

L'architecture repose sur un modèle hybride **Maître / Esclave** :
* **Raspberry Pi 4 (Maître - Ubuntu) :** Gère la logique centrale, l'affichage LCD, le contrôle d'accès RFID, la détection incendie, l'actionnement des portes (servos) et la température.
* **Arduino (Esclave - C++) :** Gère les lectures analogiques haute précision (luminosité) et les actionneurs nécessitant une puissance stable en 5V (Buzzer et LED d'alerte).

---

## ⚡ Architecture Électrique & Ségrégation des Tensions

Pour éviter les chutes de tension et protéger les broches logiques (3.3V max) du Raspberry Pi, l'alimentation est divisée en trois zones reliées par une **masse commune (GND)** :

1. **Zone Puissance 5V (Batterie 12V + Régulateur BEC 5V) :** Alimente le(s) servo-moteur(s), le capteur de fumée (K869051) et l'écran LCD.
2. **Zone Logique 3.3V (Raspberry Pi) :** Alimente le lecteur RFID (RC522) et le capteur DHT11.
3. **Zone Esclave 5V (Arduino via USB) :** Alimente le capteur de lumière (AO), la LED et le buzzer.

> ⚠️ **Sécurité matérielle :** La sortie numérique (`DO`) du capteur de fumée envoie un signal de 5V. Un **pont diviseur de tension** ($R_1 = 1\text{k}\Omega$, $R_2 = 2\text{k}\Omega$) est obligatoire pour abaisser ce signal à **3.33V** avant d'entrer dans le GPIO 27 du Raspberry Pi.

---

## 🔌 Tableau des Brochages (Pinout)

### Côté Raspberry Pi 4 (Numérotation BCM)

| Composant | Broche Module | BCM (Code) | Physique (Carte) | Bus / Type | Alimentation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RFID (RC522)** | **SDA (CS/CE)** | **GPIO 5** | **PHY 29** | SPI (CS logiciel) | 3.3V (Pi) |
| | MISO | GPIO 9 | PHY 21 | Bus SPI | 3.3V (Pi) |
| | MOSI | GPIO 10 | PHY 19 | Bus SPI | 3.3V (Pi) |
| | SCK | GPIO 11 | PHY 23 | Bus SPI | 3.3V (Pi) |
| | IRQ | GPIO 24 | PHY 18 | Interruption | 3.3V (Pi) |
| | RST | GPIO 25 | PHY 22 | Reset | 3.3V (Pi) |
| **Écran LCD** | SDA | GPIO 2 | PHY 3 | Bus I2C | 5V (BEC) |
| | SCL | GPIO 3 | PHY 5 | Bus I2C | 5V (BEC) |
| **Capteur DHT11** | DATA | GPIO 4 | PHY 7 | 1-Wire | 3.3V (Pi) |
| **Fumée K869051**| DO | GPIO 27 | PHY 13 | Numérique *(Pont div.)* | 5V (BEC) |
| **Servo-Moteur** | Signal | GPIO 12 | PHY 32 | PWM Matériel | 5V (BEC) |

### Côté Arduino (Uno / Mega)

| Composant | Broche Module | Broche Arduino | Type de Signal | Alimentation |
| :--- | :--- | :--- | :--- | :--- |
| **Capteur Lumière** | AO (Analog Out) | **A0** | Analogique (0 - 1023) | 5V (Arduino) |
| **Buzzer** | Signal (+) | **D9** | PWM (`tone()`) | 5V (Arduino) |
| **LED Alerte** | Anode (+) | **D10** | Numérique *(Résistance 220Ω)* | 5V (Arduino) |

---

## 📡 Bus de Communication & Protocole Série

### 1. Bus Internes (Capteurs ↔ Raspberry Pi)
* **Bus SPI (`/dev/spidev0.0`) :** Utilisé pour le transfert rapide des données avec le lecteur RFID RC522.
* **Bus I2C (`0x27`) :** Utilisé pour piloter l'écran LCD 16x2 via son module adaptateur `PCF8574` sur seulement deux fils (SDA/SCL).
* **Protocole 1-Wire :** Utilisé par la bibliothèque `adafruit_dht` sur le GPIO 4 pour lire la température et l'humidité.

### 2. Dialogue Série USB (`Arduino ↔ Raspberry Pi`)
Les deux cartes communiquent via liaison série USB (`/dev/ttyACM0` ou `/dev/ttyUSB0`) à **9600 bauds** selon un protocole asynchrone léger :
* **Arduino ➔ Raspberry Pi :** L'Arduino lit en continu le capteur analogique `A0` et envoie une trame formatée toutes les 100 ms :
  ```text
  L:742
  ```
* **Raspberry Pi ➔ Arduino :** Le Pi envoie un caractère unique de commande selon l'état du capteur de fumée :
  * `A` : Déclenche l'alarme (Allume la LED sur D10 et active le buzzer à 1500 Hz sur D9).
  * `N` : Retour à la normale (Éteint la LED et coupe le son).

---

## 🔍 Focus sur les Points Critiques du Code

### 1. Gestion du RFID (`pirc522` + `RPi.GPIO`)
Sous Ubuntu moderne (via `rpi-lgpio`), deux conflits matériels classiques surviennent lors de l'utilisation simultanée de plusieurs capteurs :
* **Conflit de mode (`ValueError`) :** `board` et `gpiozero` verrouillent la carte en mode `BCM`, tandis que `pirc522` tente d'utiliser le mode `BOARD` par défaut. Il est impératif de forcer `pin_mode=GPIO.BCM`.
* **Verrouillage SPI (`lgpio.error: 'GPIO not allocated'`) :** Le noyau Linux réserve exclusivement le **GPIO 8 (CE0)** lorsque le bus SPI est actif. Pour éviter le blocage, la broche **SDA (Chip Select)** du lecteur RFID est déportée sur le **GPIO 5 (PHY 29)** :
  ```python
  import RPi.GPIO as GPIO
  from pirc522 import RFID

  rdr = RFID(pin_mode=GPIO.BCM, pin_rst=25, pin_ce=5, pin_irq=24)
  ```
* **Lecture non-bloquante :** La boucle principale utilise `rdr.request()` (scrutation rapide) au lieu de `rdr.wait_for_tag()` afin de ne jamais figer la surveillance incendie en attendant un badge.

### 2. Lecture temporisée du DHT11
Le capteur DHT11 nécessite un délai minimum de 2 secondes entre chaque mesure et est sensible aux interruptions du système d'exploitation Linux. La lecture est donc encadrée par un chronomètre non-bloquant (`time.time()`) et un bloc `try...except RuntimeError:` pour ignorer les micro-coupures de lecture sans faire planter le script central.

---

## 🚀 Lancement du Test

1. Téléverser le sketch `.ino` dans l'Arduino via l'IDE Arduino.
2. Brancher l'Arduino en USB sur le Raspberry Pi et vérifier son port (`ls /dev/ttyACM* /dev/ttyUSB*`).
3. Alimenter le BEC 5V avec la batterie 12V (vérifier la masse commune avec le Pi).
4. Exécuter le script maître sur le Raspberry Pi :
   ```bash
   sudo python3 main.py
   ```