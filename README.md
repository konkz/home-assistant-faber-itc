# <img src="https://raw.githubusercontent.com/konkz/home-assistant-faber-itc/main/icon.png" width="32" height="32" align="center"> Faber ITC Integration for Home Assistant

Steuere deinen Faber Gaskamin mit ITC-Modul lokal über Home Assistant. Diese Integration nutzt das verifizierte TCP-Protokoll für eine schnelle und zuverlässige Steuerung ohne Cloud-Zwang.

---

### 🚀 Features
- **TCP Port:** Standardmäßig wird Port **58779** verwendet.
- **Power & Status:** Kamin an-/ausschalten inkl. Anzeige des Zündvorgangs.
- **Flammenhöhe:** Präzise Steuerung in 5 Stufen (Aus, 1-4).
- **Flammenbreite:** Umschalten zwischen schmalem und breitem Flammenbild (1 oder 2 Brenner).
- **Temperatur:** Auslesen der aktuellen Raumtemperatur direkt vom ITC-Modul.
- **Echtzeit-Updates:** Sofortige Statusrückmeldung via TCP-Polling.

---

### 📦 Installation

#### Über HACS (Empfohlen)
1. In HACS unter **Custom Repositories** diese URL hinzufügen: `https://github.com/konkz/home-assistant-faber-itc` (Kategorie: Integration).
2. Installieren und HA neu starten.

#### Manuell
1. Ordner `custom_components/faber_itc` in dein `custom_components` Verzeichnis kopieren.
2. HA neu starten.

---

### ⚙️ Konfiguration
1. Gehe zu **Einstellungen > Geräte & Dienste**.
2. Klicke auf **Integration hinzufügen** und suche nach **Faber ITC**.
3. Gib die IP-Adresse deines Kamins ein.

---

### 📱 App-Parallelität
**Wichtiger Hinweis:** Das ITC-Modul des Kamins erlaubt in der Regel nur **eine aktive TCP-Verbindung**. Wenn du die offizielle Faber ITC App auf deinem Smartphone öffnest, kann es sein, dass die Home Assistant Integration die Verbindung verliert oder Fehlermeldungen anzeigt. Für eine stabile Nutzung in Home Assistant sollte die Smartphone-App vollständig geschlossen sein.

### ⚠️ Disclaimer
**Sicherheitshinweis:** Gasgeräte sind sensibel. Diese Integration basiert auf Reverse Engineering und wird nicht offiziell vom Hersteller unterstützt. Die Nutzung erfolgt auf eigene Gefahr. Kamine sollten während des Betriebs stets beaufsichtigt werden.

---
*Getestet mit Aspect Premium RD L (M4435200)*
