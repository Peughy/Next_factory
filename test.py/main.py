import time
import serial
import RPi.GPIO as GPIO
from pirc522 import RFID
import board
import adafruit_dht
from RPLCD.i2c import CharLCD
from gpiozero import DigitalInputDevice, Servo

def affichage_lcd(ecran_lcd, ligne1, ligne2):
    ecran_lcd.clear()
    ecran_lcd.cursor_pos = (0, 0)
    ecran_lcd.write_string(ligne1)
    ecran_lcd.cursor_pos = (1, 0)
    ecran_lcd.write_string(ligne2)

# Initialisation du RFID en premier pour éviter le conflit de mode BCM/BOARD
rdr = RFID(pin_mode=GPIO.BCM, pin_rst=25, pin_ce=5, pin_irq=24)

# Initialisation des capteurs et actionneurs sur le Pi
lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)
dht_sensor = adafruit_dht.DHT11(board.D4)
capteur_fumee = DigitalInputDevice(27, pull_up=False)
porte = Servo(12)

# Connexion série USB avec l'Arduino
try:
    arduino = serial.Serial('/dev/ttyUSB0', 9600, timeout=0.1)
    time.sleep(2)
    arduino.flush()
    print("✅ Arduino connecté.")
except Exception as e:
    print(f"❌ Erreur Arduino : {e}")
    exit()

dernier_temps_dht = 0
delai_dht = 3.0
alarme_active = False
lumiere_actuelle = "N/A"

affichage_lcd(lcd, 'USINE CONNECTEE', 'SYSTEME ACTIF')
porte.min()
arduino.write(b'N')

print("🟢 USINE EN LIGNE")

try:
    while True:
        temps_actuel = time.time()

        # 1. Lecture de la luminosité envoyée par l'Arduino
        if arduino.in_waiting > 0:
            ligne = arduino.readline().decode('utf-8', errors='ignore').rstrip()
            print(f"[{time.strftime('%H:%M:%S')}] DEBUG LIGNE ARDUINO: {ligne}")
            if ligne.startswith("L:"):
                lumiere_actuelle = ligne.split(":")[1]

        # 2. Sécurité incendie (prioritaire)
        if capteur_fumee.is_active and not alarme_active:
            alarme_active = True
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ ALERTE INCENDIE")
            arduino.write(b'A')
            affichage_lcd(lcd, '!! ALARME !!', 'EVACUATION')
            porte.max()

        elif not capteur_fumee.is_active and alarme_active:
            alarme_active = False
            print(f"[{time.strftime('%H:%M:%S')}] 🟢 Fin d'alerte")
            arduino.write(b'N')
            affichage_lcd(lcd, 'USINE CONNECTEE', 'SYSTEME ACTIF')
            porte.min()

        # 3. Lecture température/humidité toutes les 3 secondes
        if temps_actuel - dernier_temps_dht > delai_dht:
            try:
                temp = dht_sensor.temperature
                hum = dht_sensor.humidity
                print(f"[{time.strftime('%H:%M:%S')}] 🌡️ {temp}°C | 💧 {hum}% | 💡 {lumiere_actuelle}")
                dernier_temps_dht = temps_actuel
            except RuntimeError:
                pass

        # 4. Contrôle d'accès RFID (scrutation non-bloquante)
        if not alarme_active:
            (error, tag_type) = rdr.request()
            if not error:
                (error, uid) = rdr.anticoll()
                if not error:
                    uid_str = "-".join([str(x) for x in uid])
                    print(f">>> BADGE LU : {uid_str}")
                    
                    affichage_lcd(lcd, 'ACCES AUTORISE', 'BIENVENUE')
                    porte.max()
                    time.sleep(3)
                    porte.min()
                    
                    affichage_lcd(lcd, 'USINE CONNECTEE', 'SYSTEME ACTIF')
                    dernier_temps_dht = time.time()

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nArrêt du système.")
finally:
    arduino.write(b'N')
    arduino.close()
    rdr.cleanup()
    dht_sensor.exit()
    lcd.clear()
    porte.detach()