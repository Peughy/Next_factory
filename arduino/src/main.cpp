#include <Arduino.h>

const int pinLumiere = A0;
const int pinBuzzer = 9;
const int pinLed = 10;

// Seuil de luminosité (0 = très lumineux, 1023 = obscurité totale sur la plupart des modules LDR)
const int seuilObscurite = 600; 
bool alarmeIncendie = false;

void setup() {
  Serial.begin(9600);
  pinMode(pinBuzzer, OUTPUT);
  pinMode(pinLed, OUTPUT);
}

void loop() {
  int valeurLumiere = analogRead(pinLumiere);
  Serial.print("L:");
  Serial.println(valeurLumiere);

  // Écoute des ordres prioritaires du Raspberry Pi
  if (Serial.available() > 0) {
    char ordre = Serial.read();
    if (ordre == 'A') {
      alarmeIncendie = true;
    } else if (ordre == 'N') {
      alarmeIncendie = false;
    }
  }

  // Gestion des actionneurs : priorité à l'alarme incendie, sinon éclairage automatique
  if (alarmeIncendie) {
    digitalWrite(pinLed, HIGH);
    tone(pinBuzzer, 1500);
  } else {
    noTone(pinBuzzer);
    if (valeurLumiere > seuilObscurite) {
      digitalWrite(pinLed, HIGH); // Allume l'éclairage s'il fait sombre
    } else {
      digitalWrite(pinLed, LOW);
    }
  }

  delay(100);
}