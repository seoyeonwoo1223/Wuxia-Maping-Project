"""Re-encode a Flash 5 SWF's CP949 text fields to UTF-8 and bump it to SWF 6, so Ruffle shows Korean."""
import struct, sys

def u16(b, p): return struct.unpack('<H', b[p:p + 2])[0]

def tag(code, body):
    if len(body) < 0x3f and code not in (6, 21, 35, 20, 36):
        return struct.pack('<H', code << 6 | len(body)) + body
    return struct.pack('<HI', code << 6 | 0x3f, len(body)) + body

def edit_text(body):
    # DefineEditText: id(2) RECT flags(2) [font id+height] [color] [maxlen] [layout] varname\0 [text\0]
    nbits = body[2] >> 3
    p = 2 + (5 + nbits * 4 + 7) // 8
    f1, f2 = body[p], body[p + 1]; p += 2
    if f1 & 0x01: p += 4          # HasFont
    if f1 & 0x04: p += 4          # HasTextColor
    if f1 & 0x02: p += 2          # HasMaxLength
    if f2 & 0x20: p += 9          # HasLayout
    p = body.index(b'\0', p) + 1  # VariableName
    if not f1 & 0x80:             # HasText
        return body
    end = body.index(b'\0', p)
    return body[:p] + body[p:end].decode('cp949', 'replace').encode('utf-8') + body[end:]

def walk(b):
    out, p = bytearray(), 0
    while p < len(b):
        cl = u16(b, p); p += 2
        code, ln = cl >> 6, cl & 0x3f
        if ln == 0x3f:
            ln = struct.unpack('<I', b[p:p + 4])[0]; p += 4
        body = b[p:p + ln]; p += ln
        if code == 37:
            body = edit_text(body)
        elif code == 39:
            body = body[:4] + walk(body[4:])
        out += tag(code, body)
        if code == 0:
            break
    return bytes(out)

src, dst = sys.argv[1], sys.argv[2]
d = open(src, 'rb').read()
assert d[:3] == b'FWS' and d[3] == 5, 'expected uncompressed SWF 5'
nbits = d[8] >> 3
hdr_end = 8 + (5 + nbits * 4 + 7) // 8 + 4
body = d[8:hdr_end] + walk(d[hdr_end:])
open(dst, 'wb').write(b'FWS\x06' + struct.pack('<I', 8 + len(body)) + body)
