# Ein Standard-Command-Frame (15 Wörter) basierend auf deinen Aufzeichnungen
# Index 3: Status, Index 5: Intensity, Index 11: Burner-Mask
BASE_COMMAND_FRAME = [
    0xA1A2A3A4, 0x00FA0002, 0x00007DED, # Header + Device-ID
    0x00001040,                         # [3] STATUS_MAIN
    0xFFFF0009,                         # [4] FLAGS
    0x00000000,                         # [5] INTENSITY
    0x00FAFBFC, 0xFDA1A2A3, 0xA400FA00, # Sub-Header
    0x02FAC42C, 0xD8100010,             # Sub-Header
    0x40000000,                         # [11] BURNER_MASK
    0x00000000,                         # [12] Padding
    0x0000FAFB, 0xFCFD0000              # [13, 14] Trailer (FCFD als Magic End)
]
