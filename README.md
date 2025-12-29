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

---

### 🎨 Dashboard (Empfehlung)
Für ein optimales Erlebnis mit der neuen **Tile Card** (HA 2023.6+), kannst du folgendes YAML in dein Dashboard kopieren.

> [!TIP]
> Die Entitäts-IDs (z.B. `switch.faber_fireplace_power`) hängen von dem Namen ab, den du bei der Einrichtung vergeben hast. Falls du den Kamin z.B. "Kamin" genannt hast, musst du die IDs im YAML entsprechend anpassen (z.B. `switch.kamin_power`).

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: switch.faber_fireplace_power
    name: Kamin
    icon: mdi:fire
    color: deep-orange
    tap_action: { action: toggle }
    state_content: [state, last_changed]

  - type: grid
    columns: 5
    square: false
    cards:
      - { type: tile, entity: switch.faber_flame_0, vertical: true, hide_state: true, color: disabled }
      - { type: tile, entity: switch.faber_flame_1, vertical: true, hide_state: true, color: yellow }
      - { type: tile, entity: switch.faber_flame_2, vertical: true, hide_state: true, color: amber }
      - { type: tile, entity: switch.faber_flame_3, vertical: true, hide_state: true, color: orange }
      - { type: tile, entity: switch.faber_flame_4, vertical: true, hide_state: true, color: red }

  - type: grid
    columns: 2
    square: false
    cards:
      - { type: tile, entity: switch.faber_mode_narrow, vertical: true, hide_state: true, color: blue }
      - { type: tile, entity: switch.faber_mode_wide, vertical: true, hide_state: true, color: indigo }

  - type: tile
    entity: sensor.faber_temperature
    color: blue-grey
    features:
      - type: trend-graph
        hours_to_show: 8
```

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

---

### 🎨 Dashboard (Recommended)
For the best experience using the **Tile Card** (HA 2023.6+), you can use this YAML in your dashboard.

> [!TIP]
> Entity IDs (e.g., `switch.faber_fireplace_power`) depend on the name you chose during setup. If you named it "Fireplace", you need to adjust the IDs in the YAML accordingly (e.g., `switch.fireplace_power`).

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: switch.faber_fireplace_power
    name: Fireplace
    icon: mdi:fire
    color: deep-orange
    tap_action: { action: toggle }
    state_content: [state, last_changed]

  - type: grid
    columns: 5
    square: false
    cards:
      - { type: tile, entity: switch.faber_flame_0, vertical: true, hide_state: true, color: disabled }
      - { type: tile, entity: switch.faber_flame_1, vertical: true, hide_state: true, color: yellow }
      - { type: tile, entity: switch.faber_flame_2, vertical: true, hide_state: true, color: amber }
      - { type: tile, entity: switch.faber_flame_3, vertical: true, hide_state: true, color: orange }
      - { type: tile, entity: switch.faber_flame_4, vertical: true, hide_state: true, color: red }

  - type: grid
    columns: 2
    square: false
    cards:
      - { type: tile, entity: switch.faber_mode_narrow, vertical: true, hide_state: true, color: blue }
      - { type: tile, entity: switch.faber_mode_wide, vertical: true, hide_state: true, color: indigo }

  - type: tile
    entity: sensor.faber_temperature
    color: blue-grey
    features:
      - type: trend-graph
        hours_to_show: 8
```
