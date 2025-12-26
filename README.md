# Faber ITC Home Assistant Integration

Diese Integration ermöglicht die Steuerung von Faber Gaskaminen mit ITC-Modul (z.B. Aspect Premium RD L) über Home Assistant. Das Protokoll wurde per Reverse Engineering der lokalen TCP-Kommunikation zwischen der Faber ITC App und dem Kamin-Modul analysiert.

## Features

- **An/Aus Steuerung:** Schalten des Kamins über Home Assistant.
- **Flammenintensität:** Einstellung der Flammenhöhe in 5 Stufen (0%, 25%, 50%, 75%, 100%).
- **Brenner-Modus:** Umschalten zwischen 1-Brenner und 2-Brenner Profilen.
- **Status-Feedback:** Auslesen des aktuellen Zustands direkt vom Gerät.

## Installation

### HACS (Empfohlen)
1. Öffne HACS in Home Assistant.
2. Klicke auf die drei Punkte oben rechts und wähle "Custom repositories".
3. Füge die URL dieses Repositories hinzu und wähle die Kategorie "Integration".
4. Suche nach "Faber ITC" und installiere die Integration.
5. Starte Home Assistant neu.

### Manuell
1. Kopiere den Ordner `custom_components/faber_itc` in deinen `custom_components` Ordner.
2. Starte Home Assistant neu.

## Konfiguration

Die Einrichtung erfolgt bequem über die Benutzeroberfläche:
1. Navigiere zu **Einstellungen** -> **Geräte & Dienste**.
2. Klicke auf **Integration hinzufügen**.
3. Suche nach **Faber ITC**.
4. Gib die IP-Adresse deines Faber ITC Moduls ein (es wird empfohlen, eine feste IP im Router zu vergeben).

## Technische Details

Die Integration kommuniziert über den Port 58779 (TCP) direkt mit dem ITC-Modul im lokalen Netzwerk. Es wird kein Cloud-Zugang benötigt.

### Protokoll-Struktur
Das Protokoll verwendet binäre Frames mit folgendem Aufbau:
- **Start-Magic:** `A1A2A3A4`
- **End-Magic:** `FAFBFCFD`
- **Endianness:** Big Endian (32-Bit Wörter)

Weitere Details zum Protokoll findest du in der [faber_itc_protocol.md](faber_itc_protocol.md).

## Disclaimer

**Sicherheitshinweis:** Gasfeuerstellen sind sicherheitskritische Geräte. Diese Integration wurde durch Reverse Engineering erstellt und ist nicht offiziell vom Hersteller unterstützt. Die Nutzung erfolgt auf eigene Gefahr. Achte darauf, dass der Kamin jederzeit unter Aufsicht steht, wenn er betrieben wird.

---
Entwickelt auf Basis von Analysen eines *Aspect Premium RD L (M4435200)*.
