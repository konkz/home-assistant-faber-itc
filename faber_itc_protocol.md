# Faber ITC – Reverse Engineered Protokoll (Aspect Premium RD L / M4435200)

Stand: Dezember 2025  
Quelle: Mitschnitte einer Faber ITC App ↔ Kamin‑Kommunikation (Wireshark/RVI) & Unabhängige Analyse  
Gerät: Aspect Premium RD L, Article No M4435200, FAM ASG

---

## 1. Frame-Format (Allgemein)

Alle Nachrichten folgen einem festen Paket-Aufbau von mindestens 24 Bytes. Standardmäßig wird Port **58779** verwendet.

| Bereich | Länge | Wert / Beschreibung |
| :--- | :--- | :--- |
| **Magic Start** | 4 Bytes | `A1 A2 A3 A4` |
| **Protokoll-Header** | 4 Bytes | `00 FA 00 02` (Version & Konstante) |
| **Sender-ID** | 4 Bytes | Client: `00 00 7D ED`, Server: `FA C4 2C D8` |
| **Opcode** | 4 Bytes | Big-Endian (siehe Opcodes) |
| **Payload** | Variabel | Dateninhalt |
| **Magic End** | 4 Bytes | `FA FB FC FD` |

### 1.1 Opcode-Logik
Der Opcode ist ein 32-Bit-Wert.
- **Anfragen (Requests):** Bit 28 ist `0` (z.B. `00 00 10 30`).
- **Antworten (Responses):** Bit 28 ist `1` (z.B. `10 00 10 30`).
- **Basis-Opcode:** `opcode & 0x0FFFFFFF`.

---

## 2. Wichtige Opcodes

| Opcode (Base) | Funktion |
| :--- | :--- |
| `0x0020` | **Identify/Handshake**: Initialisierung der Verbindung. |
| `0x0410` / `0x1010` | **Device Info**: Liefert Modellname, Seriennummer etc. als ASCII. |
| `0x1030` | **Telemetry**: Kern-Status (Zustand, Flamme, Temp). |
| `0x1040` | **Control**: Senden von Steuerbefehlen. |
| `0x1080` | **Heartbeat**: Regelmäßige Bestätigung der Verbindung. |

---

## 3. Telemetrie (Status-Frame 1030)

Die Response auf `1030` enthält eine 41-Byte Payload. Die Werte liegen an festen Offsets:

| Offset (Payload) | Bedeutung | Werte / Kodierung |
| :--- | :--- | :--- |
| **11** | Kamin-Status | `00`: Aus, `01`: An, `04`: Zündvorgang, `05`: Aus-Vorgang |
| **15** | Flammenhöhe | `00`, `19` (1), `32` (2), `4B` (3), `64` (4) |
| **16** | Flammenbreite | `32`: Schmal, `64`: Breit |
| **21** | Raumtemperatur | Hex-Wert / 10 (z.B. `F3` = 243 = 24.3°C) |

---

## 4. Steuerung (Control-Frame 1040)

Anfragen zur Steuerung nutzen eine 9-Byte Payload mit folgendem Aufbau:
`FF FF` | `Param_ID (2B BE)` | `00 00 00` | `Value (2B LE)`

**Wichtig:** Der Wert (`Value`) wird im Gegensatz zu den IDs in **Little-Endian** übertragen.

| Aktion | Param_ID | Value (LE) |
| :--- | :--- | :--- |
| **Ausschalten** | `00 01` | `00 00` |
| **Zündung (Teil 1)** | `00 02` | `00 00` |
| **Zündung (Teil 2)** | `00 20` | `00 00` |
| **Schmaler Brenner** | `00 05` | `00 00` |
| **Breiter Brenner** | `00 06` | `00 00` |
| **Flammenhöhe setzen** | `00 09` | `19 00`, `32 00`, `4B 00`, `64 00` |

### 4.1 Zündsequenz (Power On)
Um den Kamin einzuschalten, müssen zwei Befehle kurz hintereinander gesendet werden:
1. `1040` mit Param `0x0002`
2. `1040` mit Param `0x0020`

---

## 5. Hinweise zur Implementierung
- **Endianness:** IDs und Opcodes sind Big-Endian, Stellwerte (Level) sind Little-Endian.
- **Keep-Alive:** Regelmäßiges Polling von `1030` oder Senden von `1080` wird empfohlen.
- **Socket:** Nur eine aktive TCP-Verbindung pro ITC-Modul zulässig.
