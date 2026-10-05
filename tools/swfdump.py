import struct, sys, os, re, collections, zlib

data = open(sys.argv[1], 'rb').read()
out = sys.argv[2]
os.makedirs(out, exist_ok=True)

# header: sig(3) ver(1) len(4) then RECT (variable bits), rate(2), count(2)
nbits = data[8] >> 3
rect_bytes = (5 + nbits * 4 + 7) // 8
def bits(buf, start, n):
    v = int.from_bytes(buf, 'big'); total = len(buf) * 8
    return (v >> (total - start - n)) & ((1 << n) - 1)
r = data[8:8 + rect_bytes]
xmax, ymax = bits(r, 5 + nbits, nbits), bits(r, 5 + 3 * nbits, nbits)
pos = 8 + rect_bytes
rate, frames = data[pos + 1], struct.unpack('<H', data[pos + 2:pos + 4])[0]
print(f'stage {xmax/20}x{ymax/20}px, {rate}fps, {frames} frames')
pos += 4

names = {6: 'DefineBits', 8: 'JPEGTables', 21: 'DefineBitsJPEG2', 35: 'DefineBitsJPEG3',
         20: 'DefineBitsLossless', 36: 'DefineBitsLossless2', 12: 'DoAction', 59: 'DoInitAction',
         37: 'DefineEditText', 11: 'DefineText', 33: 'DefineText2', 39: 'DefineSprite',
         7: 'DefineButton', 34: 'DefineButton2', 2: 'DefineShape', 22: 'DefineShape2', 32: 'DefineShape3',
         10: 'DefineFont', 48: 'DefineFont2', 14: 'DefineSound', 26: 'PlaceObject2', 1: 'ShowFrame', 43: 'FrameLabel'}
counts = collections.Counter()
texts = []

def walk(pos, end):
    while pos < end:
        code_len = struct.unpack('<H', data[pos:pos + 2])[0]; pos += 2
        code, ln = code_len >> 6, code_len & 0x3f
        if ln == 0x3f:
            ln = struct.unpack('<I', data[pos:pos + 4])[0]; pos += 4
        body = data[pos:pos + ln]
        counts[names.get(code, code)] += 1
        if code in (21, 35):
            cid = struct.unpack('<H', body[:2])[0]
            jpg = body[2:] if code == 21 else body[6:6 + struct.unpack('<I', body[2:6])[0]]
            jpg = jpg.replace(b'\xff\xd9\xff\xd8', b'')  # strip SWF's erroneous header pair
            open(f'{out}/img_{cid}.jpg', 'wb').write(jpg)
        if code in (20, 36):
            cid, fmt, w, h = struct.unpack('<HBHH', body[:7])
            open(f'{out}/lossless_{cid}_{fmt}_{w}x{h}.bin', 'wb').write(body)
        if code == 39:
            walk(pos + 4, pos + ln)
        if code in (12, 59, 37, 34, 7):
            for m in re.findall(rb'[\x20-\x7e\x80-\xfe]{4,}', body):
                try:
                    s = m.decode('cp949')
                except UnicodeDecodeError:
                    continue
                if re.search('[가-힣]', s) or code == 37:
                    texts.append((names[code], s))
        pos += ln
        if code == 0 and end == len(data):
            break

walk(pos, len(data))
print(dict(counts))
with open(f'{out}/texts.txt', 'w', encoding='utf-8') as f:
    for k, s in texts:
        f.write(f'[{k}] {s}\n')
print(len(texts), 'text strings')
