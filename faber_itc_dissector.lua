-- faber_itc.lua - Wireshark Lua dissector for Faber ITC protocol (Wireshark 4.6.x)
--
-- TCP Frame:
--   A1A2A3A4 00FA0002 [sender_id:4] [opcode:4] [payload...] FAFBFCFD
--
-- Default Payload schema (most messages):
--   Reserved/Session (8) | Length (1) | Data (Length)
--
-- SPECIAL CASE:
--   Control Request (Base Opcode 0x1040) uses a fixed 9-byte payload:
--   FF FF | Param_ID (2B BE) | 00 00 00 | Value (2B LE)
--
-- UDP Discovery (observed 48 bytes):
--   AA AA AA AA | FA BE FA BE | sender_id(4) | controller_ip(4) | discovery_seq32(4) | name(??) | FA BE FA BE

local faber   = Proto("faber_itc",      "Faber ITC")
local udpdisc = Proto("faber_itc_disc", "Faber ITC Discovery")

-- ===== TCP base fields =====
local f_magic_start = ProtoField.bytes("faber_itc.magic_start", "Magic Start", base.NONE)
local f_header      = ProtoField.bytes("faber_itc.header",      "Header",      base.NONE)
local f_sender      = ProtoField.uint32("faber_itc.sender",     "Sender-ID",   base.HEX)

local f_opcode      = ProtoField.uint32("faber_itc.opcode",     "Opcode",      base.HEX)
local f_is_resp     = ProtoField.bool("faber_itc.is_response",  "Is Response")
local f_base16      = ProtoField.uint16("faber_itc.base16",     "Base Opcode", base.HEX)
local f_optype      = ProtoField.string("faber_itc.op_type",    "Opcode Type")

local f_payload     = ProtoField.bytes("faber_itc.payload",     "Payload",     base.NONE)
local f_reserved    = ProtoField.bytes("faber_itc.reserved",    "Reserved/Session (8)", base.NONE)
local f_lenbyte     = ProtoField.uint8("faber_itc.length",      "Length (Data bytes)",  base.DEC)
local f_data        = ProtoField.bytes("faber_itc.data",        "Data",        base.NONE)
local f_ascii       = ProtoField.string("faber_itc.ascii",      "ASCII (best effort)")
local f_magic_end   = ProtoField.bytes("faber_itc.magic_end",   "Magic End",   base.NONE)

-- ===== Telemetry (1030) decoded fields =====
local f_tel_status  = ProtoField.uint8("faber_itc.telemetry.status", "Status", base.HEX)
local f_tel_flame_h = ProtoField.uint8("faber_itc.telemetry.flame_height", "Flame Height", base.HEX)
local f_tel_flame_w = ProtoField.uint8("faber_itc.telemetry.flame_width",  "Flame Width",  base.HEX)
local f_tel_temp_c  = ProtoField.float("faber_itc.telemetry.room_temp_c", "Room Temperature (°C)")

-- ===== Control (1040) decoded fields =====
local f_ctl_param   = ProtoField.uint16("faber_itc.control.param_id", "Param ID", base.HEX)
local f_ctl_value   = ProtoField.uint16("faber_itc.control.value",    "Value (Little Endian)", base.HEX)
local f_ctl_name    = ProtoField.string("faber_itc.control.name",     "Command")

-- ===== Device Info (1010 / 0410) decoded fields =====
local f_dev_model   = ProtoField.string("faber_itc.devinfo.model_name", "Model Name")
local f_dev_article = ProtoField.string("faber_itc.devinfo.article_no", "Article No")
local f_dev_variant = ProtoField.string("faber_itc.devinfo.variant",    "Variant")

local f_inst_name   = ProtoField.string("faber_itc.installer.name",    "Installer Name")
local f_inst_phone  = ProtoField.string("faber_itc.installer.phone",   "Installer Phone")
local f_inst_web    = ProtoField.string("faber_itc.installer.website", "Installer Website")
local f_inst_mail   = ProtoField.string("faber_itc.installer.email",   "Installer Email")

-- ===== UDP Discovery fields =====
local f_ud_magic1   = ProtoField.bytes("faber_itc_disc.magic1", "Magic 1", base.NONE)
local f_ud_magic2   = ProtoField.bytes("faber_itc_disc.magic2", "Magic 2", base.NONE)
local f_ud_sender   = ProtoField.uint32("faber_itc_disc.sender", "Sender-ID", base.HEX)
local f_ud_ip       = ProtoField.ipv4("faber_itc_disc.controller_ip", "Controller IP")
local f_ud_seq32    = ProtoField.uint32("faber_itc_disc.seq32", "Discovery Sequence (32-bit)", base.HEX)
local f_ud_name     = ProtoField.string("faber_itc_disc.name", "Device Name")
local f_ud_magicend = ProtoField.bytes("faber_itc_disc.magic_end", "Magic End", base.NONE)

faber.fields = {
  f_magic_start, f_header, f_sender,
  f_opcode, f_is_resp, f_base16, f_optype,
  f_payload, f_reserved, f_lenbyte, f_data, f_ascii, f_magic_end,
  f_tel_status, f_tel_flame_h, f_tel_flame_w, f_tel_temp_c,
  f_ctl_param, f_ctl_value, f_ctl_name,
  f_dev_model, f_dev_article, f_dev_variant,
  f_inst_name, f_inst_phone, f_inst_web, f_inst_mail
}

udpdisc.fields = { f_ud_magic1, f_ud_magic2, f_ud_sender, f_ud_ip, f_ud_seq32, f_ud_name, f_ud_magicend }

-- ===== Constants =====
local MAGIC_START_BA = ByteArray.new("A1A2A3A4")
local MAGIC_END_BA   = ByteArray.new("FAFBFCFD")

-- ===== Helpers =====
local function tvb_find_ba(tvb, ba, start_at)
  local plen = ba:len()
  local max = tvb:len() - plen
  for i = start_at, max do
    if tvb(i, plen):bytes() == ba then return i end
  end
  return -1
end

local function is_printable_ascii(b) return b >= 0x20 and b <= 0x7E end

local function bytes_to_ascii(tvb_range)
  local b = tvb_range:bytes()
  local s = {}
  for i = 0, b:len()-1 do
    local v = b:get_index(i)
    if v == 0 then break end
    if is_printable_ascii(v) then s[#s+1] = string.char(v) else s[#s+1] = "." end
  end
  local out = table.concat(s)
  if #out == 0 then return nil end
  return out
end

local function extract_null_terminated_ascii_strings(tvb_range, min_len)
  min_len = min_len or 3
  local b = tvb_range:bytes()
  local out, cur = {}, {}

  local function flush()
    if #cur >= min_len then out[#out+1] = table.concat(cur) end
    cur = {}
  end

  for i = 0, b:len()-1 do
    local v = b:get_index(i)
    if v == 0 then
      flush()
    else
      if is_printable_ascii(v) then
        cur[#cur+1] = string.char(v)
      else
        flush()
      end
    end
  end
  flush()
  return out
end

local function opcode_type_name(base16)
  if base16 == 0x0020 then return "Identify/Handshake" end
  if base16 == 0x0410 or base16 == 0x1010 then return "Device Info" end
  if base16 == 0x1030 then return "Telemetry" end
  if base16 == 0x1040 then return "Control" end
  if base16 == 0x1080 then return "Heartbeat" end
  return "Unknown"
end

local function status_name(v)
  if v == 0x00 then return "Off" end
  if v == 0x01 then return "On" end
  if v == 0x04 then return "Ignition" end
  if v == 0x05 then return "Shutdown" end
  return "Unknown"
end

local function flame_height_name(v)
  if v == 0x00 then return "0" end
  if v == 0x19 then return "1" end
  if v == 0x32 then return "2" end
  if v == 0x4B then return "3" end
  if v == 0x64 then return "4" end
  return "?"
end

local function flame_width_name(v)
  if v == 0x32 then return "Narrow" end
  if v == 0x64 then return "Wide" end
  return "?"
end

local function control_name(param_id, value_le_u16)
  if param_id == 0x0001 then return "Power Off" end
  if param_id == 0x0002 then return "Ignition (part 1)" end
  if param_id == 0x0020 then return "Ignition (part 2)" end
  if param_id == 0x0005 then return "Burner Narrow" end
  if param_id == 0x0006 then return "Burner Wide" end
  if param_id == 0x0009 then
    if value_le_u16 == 0x0000 then return "Set Flame Level = 0" end
    if value_le_u16 == 0x0019 then return "Set Flame Level = 1" end
    if value_le_u16 == 0x0032 then return "Set Flame Level = 2" end
    if value_le_u16 == 0x004B then return "Set Flame Level = 3" end
    if value_le_u16 == 0x0064 then return "Set Flame Level = 4" end
    return string.format("Set Flame Level = 0x%04X", value_le_u16)
  end
  return string.format("Param 0x%04X (Value 0x%04X)", param_id, value_le_u16)
end

local function decode_device_info(subtree, base16, is_resp, data_range)
  if not is_resp then return end
  local strings = extract_null_terminated_ascii_strings(data_range, 3)

  if base16 == 0x1010 then
    local t = subtree:add("Device Info (decoded)")
    if strings[1] then t:add(f_dev_model,   data_range, strings[1]) end
    if strings[2] then t:add(f_dev_article, data_range, strings[2]) end
    if strings[3] then t:add(f_dev_variant, data_range, strings[3]) end
    return
  end

  if base16 == 0x0410 then
    local t = subtree:add("Installer Info (decoded)")
    if strings[1] then t:add(f_inst_name,  data_range, strings[1]) end
    if strings[2] then t:add(f_inst_phone, data_range, strings[2]) end
    if strings[3] then t:add(f_inst_web,   data_range, strings[3]) end
    if strings[4] then t:add(f_inst_mail,  data_range, strings[4]) end
    return
  end
end

-- Control decode from PAYLOAD (special case) or from Data (fallback)
local function decode_control(subtree, payload_range, data_range, is_resp)
  if is_resp then return end

  -- Prefer payload_range if it looks like FF FF .... .... .... .... ....
  if payload_range and payload_range:len() == 9 then
    local b0 = payload_range(0,1):uint()
    local b1 = payload_range(1,1):uint()
    if b0 == 0xFF and b1 == 0xFF then
      local t = subtree:add("Control (decoded)")

      local param_id = payload_range(2,2):uint()      -- BE
      local value_le = payload_range(7,2):le_uint()   -- LE

      t:add(f_ctl_param, payload_range(2,2), param_id)
      t:add(f_ctl_value, payload_range(7,2), value_le)
      t:add(f_ctl_name,  payload_range, control_name(param_id, value_le))
      return
    end
  end

  -- Fallback: older assumption (if some firmware uses normal schema)
  if data_range and data_range:len() >= 9 then
    local t = subtree:add("Control (decoded) [fallback]")

    local param_id = data_range(2,2):uint()
    local value_le = data_range(7,2):le_uint()

    t:add(f_ctl_param, data_range(2,2), param_id)
    t:add(f_ctl_value, data_range(7,2), value_le)
    t:add(f_ctl_name,  data_range, control_name(param_id, value_le))
  end
end

local function decode_data(subtree, base16, is_resp, payload_range, data_range)
  -- Telemetry 1030 (response)
  if base16 == 0x1030 and is_resp and data_range and data_range:len() >= 13 then
    local t = subtree:add("Telemetry (decoded)")

    local st = data_range(2,1):uint()
    t:add(f_tel_status, data_range(2,1)):append_text(" (" .. status_name(st) .. ")")

    local fh = data_range(6,1):uint()
    t:add(f_tel_flame_h, data_range(6,1)):append_text(" (level " .. flame_height_name(fh) .. ")")

    local fw = data_range(7,1):uint()
    t:add(f_tel_flame_w, data_range(7,1)):append_text(" (" .. flame_width_name(fw) .. ")")

    local temp_raw = data_range(12,1):uint()
    t:add(f_tel_temp_c, data_range(12,1), temp_raw / 10.0)
    return
  end

  -- Control 1040 (request) - special-cased payload
  if base16 == 0x1040 then
    decode_control(subtree, payload_range, data_range, is_resp)
    return
  end

  -- Device info (0410/1010) parsed fields
  if (base16 == 0x0410 or base16 == 0x1010) and is_resp and data_range then
    decode_device_info(subtree, base16, is_resp, data_range)
    return
  end
end

-- ===== TCP dissector =====
function faber.dissector(tvb, pinfo, tree)
  local pktlen = tvb:len()
  if pktlen < 24 then return 0 end

  local offset = 0
  local any = false

  while offset < pktlen do
    local start = tvb_find_ba(tvb, MAGIC_START_BA, offset)
    if start < 0 then break end
    if start + 20 > pktlen then break end

    local endpos = tvb_find_ba(tvb, MAGIC_END_BA, start + 16)
    if endpos < 0 then break end

    local framelen = (endpos + 4) - start
    if framelen < 24 then
      offset = start + 4
    else
      any = true
      local subtree = tree:add(faber, tvb(start, framelen), "Faber ITC Frame")

      subtree:add(f_magic_start, tvb(start, 4))
      subtree:add(f_header,      tvb(start+4, 4))

      local sender = tvb(start+8, 4):uint()
      local opcode = tvb(start+12, 4):uint()

      subtree:add(f_sender, tvb(start+8, 4))
      subtree:add(f_opcode, tvb(start+12, 4))

      local is_resp = bit.band(opcode, 0x10000000) ~= 0
      subtree:add(f_is_resp, tvb(start+12, 4), is_resp)

      local base = bit.band(opcode, 0x0FFFFFFF)
      local base16 = bit.band(base, 0xFFFF)
      subtree:add(f_base16, tvb(start+14, 2), base16)

      local opname = opcode_type_name(base16)
      subtree:add(f_optype, tvb(start+12, 4), opname)

      local payload_len = framelen - 20
      local payload_range = tvb(start+16, payload_len)
      subtree:add(f_payload, payload_range)

      -- Special case: Control request payload is fixed 9 bytes (no default schema)
      if base16 == 0x1040 and (not is_resp) and payload_len == 9 then
        decode_data(subtree, base16, is_resp, payload_range, nil)
      else
        -- Default schema parsing
        if payload_len >= 9 then
          subtree:add(f_reserved, tvb(start+16, 8))
          local lenbyte = tvb(start+24, 1):uint()
          subtree:add(f_lenbyte, tvb(start+24, 1))

          local data_len = payload_len - 9
          local data_range = nil
          if data_len > 0 then
            data_range = tvb(start+25, data_len)
            subtree:add(f_data, data_range)

            local ascii = bytes_to_ascii(data_range)
            if ascii ~= nil and #ascii >= 4 then
              subtree:add(f_ascii, data_range, ascii)
            end
          end

          decode_data(subtree, base16, is_resp, payload_range, data_range)

          if lenbyte ~= data_len then
            subtree:append_text(string.format(" [lenbyte=%d, actual_data=%d]", lenbyte, data_len))
          end
        end
      end

      subtree:add(f_magic_end, tvb(endpos, 4))

      pinfo.cols.protocol = "FABER-ITC"
      local dir = is_resp and "RESP" or "REQ"
      pinfo.cols.info:append(string.format(" | %s %s base=%04X sender=%08X", dir, opname, base16, sender))

      offset = start + framelen
    end
  end

  if any then return pktlen end
  return 0
end

-- ===== UDP Discovery dissector =====
function udpdisc.dissector(tvb, pinfo, tree)
  local pktlen = tvb:len()
  if pktlen < 28 then return 0 end

  local t = tree:add(udpdisc, tvb(), "Faber ITC Discovery")

  t:add(f_ud_magic1,  tvb(0,4))
  t:add(f_ud_magic2,  tvb(4,4))
  t:add(f_ud_sender,  tvb(8,4))
  t:add(f_ud_ip,      tvb(12,4))
  t:add(f_ud_seq32,   tvb(16,4))

  local name_range_len = pktlen - 24 -- start at 20, exclude trailing 4 bytes
  if name_range_len > 0 then
    local name_range = tvb(20, name_range_len)
    local name = bytes_to_ascii(name_range)
    if name ~= nil then
      t:add(f_ud_name, name_range, name)
    end
  end

  t:add(f_ud_magicend, tvb(pktlen-4, 4))

  pinfo.cols.protocol = "FABER-ITC"
  pinfo.cols.info:append(string.format(" | DISC sender=%08X seq=%08X", tvb(8,4):uint(), tvb(16,4):uint()))
  return pktlen
end

-- ===== Register dissectors on known ports =====
DissectorTable.get("tcp.port"):add(58779, faber)
DissectorTable.get("udp.port"):add(59779, udpdisc)