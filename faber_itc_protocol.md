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
| **Payload** | Variabel | Dateninhalt (siehe unten) |
| **Magic End** | 4 Bytes | `FA FB FC FD` |

### 1.1 Payload-Struktur
Die Payload folgt standardmäßig diesem Schema:
`Reserved/Session (8 Bytes) | Length (1 Byte) | Data (Length Bytes)`

Das Byte an **Payload-Offset 8** gibt exakt an, wie viele Bytes im Data-Teil folgen (`Length = Total_Payload_Len - 9`).

**Ausnahme Control Request (0x1040):**
Hier wird ein fixes 9-Byte Format ohne das obige Schema verwendet (siehe Sektion 4).

### 1.2 Opcode-Logik
Der Opcode ist ein 32-Bit-Wert.
- **Anfragen (Requests):** Bit 28 ist `0` (z.B. `00 00 10 30`).
- **Antworten (Responses):** Bit 28 ist `1` (z.B. `10 00 10 30`).
- **Basis-Opcode:** `opcode & 0x0FFFFFFF`.

---

## 2. Wichtige Opcodes

| Opcode (Base) | Funktion |
| :--- | :--- |
| `0x0020` | **Identify/Handshake**: Initialisierung der Verbindung. |
| `0x1010` | **Device Info**: Liefert Modellname, Artikelnummer, Variante. |
| `0x0410` | **Installer Info**: Informationen zum Installateur. |
| `0x1030` | **Telemetry**: Kern-Status (Zustand, Flamme, Temp). |
| `0x1040` | **Control**: Senden von Steuerbefehlen. |
| `0x1080` | **Heartbeat**: Regelmäßige Bestätigung der Verbindung. |

---

## 3. Telemetrie (Status-Frame 1030)

Die Response auf `1030` enthält eine 41-Byte Payload (Längenbyte an Offset 8 ist `0x20` = 32).
Struktur des Data-Teils (ab Payload-Offset 9):

| Offset (Payload) | Offset (Data) | Bedeutung | Werte / Kodierung |
| :--- | :--- | :--- | :--- |
| **11** | **2** | Kamin-Status | `00`: Off, `01`: On, `04`: Ignition, `05`: Shutdown |
| **15** | **6** | Flammenhöhe | `00` (0), `19` (1), `32` (2), `4B` (3), `64` (4) |
| **16** | **7** | Flammenbreite | `32`: Schmal (Narrow), `64`: Breit (Wide) |
| **21** | **12** | Raumtemperatur | Hex-Wert / 10 (z.B. `F3` = 243 = 24.3°C) |

---

## 4. Steuerung (Control-Frame 1040)

Anfragen zur Steuerung nutzen eine 9-Byte Payload mit folgendem Aufbau:
`FF FF` | `Param_ID (2B BE)` | `00 00 00` | `Value (2B LE)`

**Wichtig:** Der Wert (`Value`) wird im Gegensatz zu den IDs in **Little-Endian** übertragen.

| Aktion | Param_ID | Value (LE) |
| :--- | :--- | :--- |
| **Power Off** | `00 01` | `00 00` |
| **Ignition (part 1)** | `00 02` | `00 00` |
| **Ignition (part 2)** | `00 20` | `00 00` |
| **Schmaler Brenner (Narrow)**| `00 05` | `00 00` |
| **Breiter Brenner (Wide)** | `00 06` | `00 00` |
| **Flammenhöhe setzen** | `00 09` | `00 00` (0), `19 00` (1), `32 00` (2), `4B 00` (3), `64 00` (4) |

### 4.1 Zündsequenz (Power On)
Um den Kamin einzuschalten, müssen zwei Befehle kurz hintereinander gesendet werden:
1. `1040` mit Param `0x0002`
2. `1040` mit Param `0x0020`

---

## 5. Hinweise zur Implementierung
- **Endianness:** IDs und Opcodes sind Big-Endian, Stellwerte (Level) sind Little-Endian.
- **Keep-Alive:** Regelmäßiges Polling von `1030` oder Senden von `1080` wird empfohlen.
- **Multi-Connection:** Mehrere parallele TCP-Verbindungen zum ITC-Modul sind möglich.

---

## 6. UDP Discovery (Broadcast)

Das ITC‑Modul sendet regelmäßig UDP Broadcasts, die von der App genutzt werden, um Geräte im lokalen Netz automatisch zu **discovern** (z.B. “found / discovered”).
In den bisherigen Mitschnitten wird UDP an **Port 59779** gesendet, während die eigentliche Steuerung über TCP auf **Port 58779** läuft.

### 6.1 UDP Packet Format (Discovery)

Die UDP Payload ist (in den beobachteten Broadcasts) 48 Bytes lang und hat ein eigenes Magic‑Framing.
**Hinweis:** Dieses UDP Format ist *nicht* identisch mit dem TCP Frame-Format (`A1A2A3A4 … FAFBFCFD`).


| Field | Length | Value / Description |
| :-- | :--: | :-- |
| **Magic Start 1** | 4 | `AA AA AA AA` |
| **Magic Start 2** | 4 | `FA BE FA BE` |
| **Sender-ID** | 4 | Controller/ITC Sender-ID (z.B. `FA C4 2C D8`) |
| **Controller IP** | 4 | IPv4 des ITC‑Moduls (z.B. `AC 10 0A 45` = 172.16.10.69) |
| **Discovery Sequence** | 4 | 32‑bit Sequenzwert (z.B. `00 C6 8B 05`) – läuft kontinuierlich, nicht strikt „+1 pro Paket“ |
| **Device Name** | 24 | Null‑terminated ASCII, Rest mit `00` gepadded (z.B. `Aspect Premium RD L`) |
| **Magic End** | 4 | `FA BE FA BE` |

### 6.2 Discovery Sequence (Interpretation)

Die 4 Bytes “Discovery Sequence” verhalten sich wie ein laufender interner Counter (z.B. tick-/event‑basiert), der unabhängig von Paketpausen weiterläuft und daher beim Mitschnitt wie “Sprünge” wirken kann.
Der Wert ist bisher nicht als Zeitstempel verifiziert, eignet sich aber gut als “freshness / last-seen” Indikator im eigenen Discovery‑Scanner.

### 6.3 Relationship UDP ↔ TCP

Der UDP Broadcast enthält keine Information, die dem Client eine eigene TCP **Sender-ID** “zuweist”.
Für TCP Controls (`0x1040`) wird in der Praxis die Client Sender-ID `00 00 7D ED` benötigt; abweichende IDs werden vom Controller abgelehnt.

### 6.4 Building a Discovery Process (DIY)

Ein eigener Discovery‑Prozess kann so implementiert werden:

1. **Listen on UDP/59779** (oder allgemein auf UDP Broadcasts, wenn Port nicht sicher ist) und parse die UDP Payload anhand der Magic‑Bytes `AAAA AAAA` + `FA BE FA BE` … `FA BE FA BE`.
2. Extrahiere pro Broadcast mindestens:
    - `sender_id` (4B)
    - `controller_ip` (4B)
    - `device_name` (ASCII bis `00`)
    - optional `discovery_sequence` (4B) für “last update”/Monotoniechecks.
3. Pflege eine “device registry” in der App/CLI:
    - Key: `sender_id` oder `controller_ip`
    - Values: `device_name`, `last_seen_timestamp`, `discovery_sequence` (letzter Wert).
4. Wenn ein Gerät als “discovered” gilt (z.B. `last_seen < 5s`), kann eine TCP Verbindung auf `controller_ip:58779` aufgebaut werden und per `0x0020` ein Identify/Handshake gemacht werden.

### 6.5 Minimal UDP Parser (Pseudo)

- Validate:
    - Bytes[0..3] == `AA AA AA AA`
    - Bytes[4..7] == `FA BE FA BE`
    - Bytes[-4..-1] == `FA BE FA BE`
- Parse:
    - `sender_id = bytes[8..11]`
    - `controller_ip = bytes[12..15]`
    - `discovery_seq = bytes[16..19]` (big-endian Darstellung)
    - `device_name = bytes[20..43]` bis `0x00` (ASCII)

---

## 7. Info-Pakete Details

Die Info-Pakete (`0x1010` und `0x0410`) liefern in der Response mehrere Null-terminierte ASCII-Strings im `Data`-Teil.

### 7.1 Device Info (0x1010)
| String Index | Bedeutung |
| :--- | :--- |
| 1 | Modellname (z.B. `Aspect Premium RD L`) |
| 2 | Artikelnummer (z.B. `M4435200`) |
| 3 | Variante |

### 7.2 Installer Info (0x0410)
| String Index | Bedeutung |
| :--- | :--- |
| 1 | Name des Installateurs |
| 2 | Telefonnummer |
| 3 | Webseite |
| 4 | E-Mail Adresse |
