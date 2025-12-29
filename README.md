<p align="center">
  <a href="#english-description">English Description Below</a>
</p>

# <img src="https://raw.githubusercontent.com/konkz/home-assistant-faber-itc/main/icon.png" width="32" height="32" align="center"> Faber ITC for Home Assistant

Steuere deinen Faber Gaskamin lokal über Home Assistant. Diese Integration verbindet sich direkt mit dem Faber ITC Controller in deinem Netzwerk – schnell, zuverlässig und ohne Cloud.

---

### 🚀 Features
- **Power & Status:** Kamin an-/ausschalten inkl. Anzeige des Zündvorgangs.
- **Flammensteuerung:** Höhe in 5 Stufen regulieren und zwischen schmalem/breitem Brenner umschalten.
- **Temperatur:** Aktuelle Raumtemperatur direkt vom Controller auslesen.
- **Lokal:** Kommunikation erfolgt direkt über TCP (Port 58779).

---

### 📦 Installation

#### HACS (Empfohlen)
Füge diese URL als **Custom Repository** hinzu: `https://github.com/konkz/home-assistant-faber-itc` (Kategorie: Integration). Danach einfach installieren und HA neu starten.

#### Manuell
Kopiere den Ordner `custom_components/faber_itc` in dein HA-Verzeichnis und starte neu.

---

### ⚙️ Konfiguration
1. Gehe zu **Einstellungen > Geräte & Dienste**.
2. Suche nach **Faber ITC**.
3. Gib die IP-Adresse deines ITC Controllers ein – fertig!

---

### ⚠️ Disclaimer
**Sicherheit geht vor:** Gasgeräte sind sensibel. Diese Integration basiert auf Reverse Engineering und ist nicht offiziell. Die Nutzung erfolgt auf eigene Gefahr. Lass deinen Kamin nie unbeaufsichtigt brennen.

---
*Getestet mit Aspect Premium RD L (M4435200)*

<br>
<br>

<a name="english-description"></a>
# <img src="https://raw.githubusercontent.com/konkz/home-assistant-faber-itc/main/icon.png" width="32" height="32" align="center"> Faber ITC for Home Assistant

Control your Faber gas fireplace locally via Home Assistant. This integration connects directly to the Faber ITC controller in your network – fast, reliable, and cloud-free.

---

### 🚀 Features
- **Power & Status:** Turn fireplace on/off including ignition status.
- **Flame Control:** Adjust height in 5 levels and toggle between narrow/wide burners.
- **Temperature:** Read current room temperature directly from the controller.
- **Local:** Communication via direct TCP (Port 58779).

---

### 📦 Installation

#### HACS (Recommended)
Add this URL as a **Custom Repository**: `https://github.com/konkz/home-assistant-faber-itc` (Category: Integration). Then install and restart HA.

#### Manual
Copy the `custom_components/faber_itc` folder to your HA directory and restart.

---

### ⚙️ Configuration
1. Go to **Settings > Devices & Services**.
2. Search for **Faber ITC**.
3. Enter the IP address of your ITC controller – that's it!

---

### ⚠️ Disclaimer
**Safety first:** Gas appliances are sensitive. This integration is based on reverse engineering and is unofficial. Use at your own risk. Never leave your fireplace burning unattended.

---
*Tested with Aspect Premium RD L (M4435200)*
