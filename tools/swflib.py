"""Minimal SWF (Flash 5) parser: characters, timelines, shapes, edit texts, buttons, actions.

Only the tags used by legacy/murim.swf are decoded. Coordinates stay in twips (1/20 px).
"""
import struct

TAG_NAMES = {
    0: 'End', 1: 'ShowFrame', 2: 'DefineShape', 6: 'DefineBits', 8: 'JPEGTables', 9: 'SetBackgroundColor',
    12: 'DoAction', 21: 'DefineBitsJPEG2', 22: 'DefineShape2', 26: 'PlaceObject2', 28: 'RemoveObject2',
    32: 'DefineShape3', 34: 'DefineButton2', 37: 'DefineEditText', 39: 'DefineSprite', 43: 'FrameLabel',
    46: 'DefineMorphShape', 48: 'DefineFont2',
}


class Bits:
    def __init__(self, data, pos=0):
        self.d, self.pos, self.bit = data, pos, 0

    def align(self):
        if self.bit:
            self.pos += 1
            self.bit = 0

    def ub(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.d[self.pos] >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit = 0
                self.pos += 1
        return v

    def sb(self, n):
        v = self.ub(n)
        if n and v & (1 << (n - 1)):
            v -= 1 << n
        return v

    def fb(self, n):
        return self.sb(n) / 65536.0

    def u8(self):
        self.align()
        v = self.d[self.pos]
        self.pos += 1
        return v

    def u16(self):
        self.align()
        v = struct.unpack_from('<H', self.d, self.pos)[0]
        self.pos += 2
        return v

    def s16(self):
        self.align()
        v = struct.unpack_from('<h', self.d, self.pos)[0]
        self.pos += 2
        return v

    def u32(self):
        self.align()
        v = struct.unpack_from('<I', self.d, self.pos)[0]
        self.pos += 4
        return v

    def cstr(self, enc='cp949'):
        self.align()
        e = self.d.index(b'\0', self.pos)
        s = self.d[self.pos:e]
        self.pos = e + 1
        return s.decode(enc, 'replace')

    def rect(self):
        self.align()
        n = self.ub(5)
        r = [self.sb(n) for _ in range(4)]  # xmin xmax ymin ymax
        self.align()
        return r

    def matrix(self):
        self.align()
        a = d = 1.0
        b = c = 0.0
        if self.ub(1):
            n = self.ub(5)
            a, d = self.fb(n), self.fb(n)
        if self.ub(1):
            n = self.ub(5)
            b, c = self.fb(n), self.fb(n)
        n = self.ub(5)
        tx, ty = self.sb(n), self.sb(n)
        self.align()
        return (a, b, c, d, tx, ty)  # x' = a*x + c*y + tx ; y' = b*x + d*y + ty

    def cxform(self, alpha):
        self.align()
        has_add, has_mult = self.ub(1), self.ub(1)
        n = self.ub(4)
        k = 4 if alpha else 3
        mult = [self.sb(n) for _ in range(k)] if has_mult else None
        add = [self.sb(n) for _ in range(k)] if has_add else None
        self.align()
        return {'mult': mult, 'add': add}

    def rgb(self, alpha=False):
        self.align()
        c = list(self.d[self.pos:self.pos + (4 if alpha else 3)])
        self.pos += 4 if alpha else 3
        return c


IDENTITY = (1.0, 0.0, 0.0, 1.0, 0, 0)


def mat_mul(m, n):
    """Return m∘n: apply n first, then m."""
    a, b, c, d, tx, ty = m
    a2, b2, c2, d2, tx2, ty2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * tx2 + c * ty2 + tx, b * tx2 + d * ty2 + ty)


def mat_apply(m, x, y):
    a, b, c, d, tx, ty = m
    return a * x + c * y + tx, b * x + d * y + ty


# ---------------------------------------------------------------- actions

ACTION_NAMES = {
    0x04: 'NextFrame', 0x05: 'PrevFrame', 0x06: 'Play', 0x07: 'Stop', 0x08: 'ToggleQuality', 0x09: 'StopSounds',
    0x0A: 'Add', 0x0B: 'Subtract', 0x0C: 'Multiply', 0x0D: 'Divide', 0x0E: 'Equals', 0x0F: 'Less', 0x10: 'And',
    0x11: 'Or', 0x12: 'Not', 0x13: 'StringEquals', 0x14: 'StringLength', 0x15: 'StringExtract', 0x17: 'Pop',
    0x18: 'ToInteger', 0x1C: 'GetVariable', 0x1D: 'SetVariable', 0x20: 'SetTarget2', 0x21: 'StringAdd',
    0x22: 'GetProperty', 0x23: 'SetProperty', 0x24: 'CloneSprite', 0x25: 'RemoveSprite', 0x26: 'Trace',
    0x27: 'StartDrag', 0x28: 'EndDrag', 0x29: 'StringLess', 0x30: 'RandomNumber', 0x3C: 'DefineLocal',
    0x3D: 'CallFunction', 0x3E: 'Return', 0x40: 'NewObject', 0x41: 'DefineLocal2', 0x42: 'InitArray',
    0x43: 'InitObject', 0x44: 'TypeOf', 0x47: 'Add2', 0x48: 'Less2', 0x49: 'Equals2', 0x4C: 'PushDuplicate',
    0x4E: 'GetMember', 0x4F: 'SetMember', 0x50: 'Increment', 0x51: 'Decrement', 0x52: 'CallMethod',
    0x81: 'GotoFrame', 0x83: 'GetURL', 0x87: 'StoreRegister', 0x88: 'ConstantPool', 0x8A: 'WaitForFrame',
    0x8B: 'SetTarget', 0x8C: 'GotoLabel', 0x94: 'With', 0x96: 'Push', 0x99: 'Jump', 0x9A: 'GetURL2',
    0x9B: 'DefineFunction', 0x9D: 'If', 0x9E: 'Call', 0x9F: 'GotoFrame2',
}


def parse_actions(d, pos=0, end=None):
    end = len(d) if end is None else end
    out, pool = [], []
    while pos < end:
        code = d[pos]
        pos += 1
        if code == 0:
            break
        ln = 0
        if code >= 0x80:
            ln = struct.unpack_from('<H', d, pos)[0]
            pos += 2
        body = d[pos:pos + ln]
        pos += ln
        name = ACTION_NAMES.get(code, hex(code))
        args = []
        if code == 0x81:
            args = [struct.unpack_from('<H', body)[0]]
        elif code in (0x8C, 0x8B):
            args = [body.rstrip(b'\0').decode('cp949', 'replace')]
        elif code == 0x83:
            a, b = body.split(b'\0')[:2]
            args = [a.decode('cp949', 'replace'), b.decode('cp949', 'replace')]
        elif code == 0x88:
            n = struct.unpack_from('<H', body)[0]
            pool = [s.decode('cp949', 'replace') for s in body[2:].split(b'\0')[:n]]
            args = pool
        elif code == 0x96:
            p = 0
            while p < len(body):
                t = body[p]
                p += 1
                if t == 0:
                    e = body.index(b'\0', p)
                    args.append(body[p:e].decode('cp949', 'replace'))
                    p = e + 1
                elif t == 1:
                    args.append(struct.unpack_from('<f', body, p)[0]); p += 4
                elif t in (2, 3):
                    args.append(None)
                elif t == 4:
                    args.append(('reg', body[p])); p += 1
                elif t == 5:
                    args.append(bool(body[p])); p += 1
                elif t == 6:
                    hi, lo = struct.unpack_from('<II', body, p)
                    args.append(struct.unpack('<d', struct.pack('<II', lo, hi))[0]); p += 8
                elif t == 7:
                    args.append(struct.unpack_from('<i', body, p)[0]); p += 4
                elif t == 8:
                    args.append(pool[body[p]] if body[p] < len(pool) else ('c', body[p])); p += 1
                elif t == 9:
                    i = struct.unpack_from('<H', body, p)[0]
                    args.append(pool[i] if i < len(pool) else ('c', i)); p += 2
                else:
                    break
        elif code in (0x99, 0x9D):
            args = [struct.unpack_from('<h', body)[0]]
        elif code == 0x9F:
            args = [body[0]]
        out.append((name, args))
    return out


# ---------------------------------------------------------------- shapes

def parse_shape(body, version):
    """Return dict(bounds, paths=[{fill, line, d}]) with SVG path data in twips."""
    br = Bits(body)
    cid = br.u16()
    bounds = br.rect()
    alpha = version >= 3

    def styles():
        n = br.u8()
        if n == 0xFF:
            n = br.u16()
        fills = []
        for _ in range(n):
            t = br.u8()
            if t == 0x00:
                fills.append({'type': 'solid', 'color': br.rgb(alpha)})
            elif t in (0x10, 0x12, 0x13):
                m = br.matrix()
                br.align()
                k = br.u8() & 0x0F
                stops = [(br.u8(), br.rgb(alpha)) for _ in range(k)]
                if t == 0x13:
                    br.u16()
                fills.append({'type': 'linear' if t == 0x10 else 'radial', 'matrix': m, 'stops': stops})
            elif t in (0x40, 0x41, 0x42, 0x43):
                bid = br.u16()
                fills.append({'type': 'bitmap', 'bitmap': bid, 'matrix': br.matrix()})
            else:
                raise ValueError(f'fill type {t:#x}')
        n = br.u8()
        if n == 0xFF:
            n = br.u16()
        lines = [{'width': br.u16(), 'color': br.rgb(alpha)} for _ in range(n)]
        br.align()
        return fills, lines

    fills, lines = styles()
    nf, nl = br.ub(4), br.ub(4)
    groups = []  # list of (fills, lines, edges)
    edges = []   # (f0, f1, l, [x0,y0, ...segment])
    x = y = 0
    f0 = f1 = ln = 0
    while True:
        if br.ub(1):  # edge
            if br.ub(1):  # straight
                n = br.ub(4) + 2
                if br.ub(1):
                    dx, dy = br.sb(n), br.sb(n)
                elif br.ub(1):
                    dx, dy = 0, br.sb(n)
                else:
                    dx, dy = br.sb(n), 0
                edges.append((f0, f1, ln, (x, y), None, (x + dx, y + dy)))
                x, y = x + dx, y + dy
            else:
                n = br.ub(4) + 2
                cx, cy = x + br.sb(n), y + br.sb(n)
                ax, ay = cx + br.sb(n), cy + br.sb(n)
                edges.append((f0, f1, ln, (x, y), (cx, cy), (ax, ay)))
                x, y = ax, ay
        else:
            flags = br.ub(5)
            if flags == 0:
                break
            if flags & 1:
                n = br.ub(5)
                x, y = br.sb(n), br.sb(n)
            if flags & 2:
                f0 = br.ub(nf)
            if flags & 4:
                f1 = br.ub(nf)
            if flags & 8:
                ln = br.ub(nl)
            if flags & 16:
                groups.append((fills, lines, edges))
                edges = []
                fills, lines = styles()
                nf, nl = br.ub(4), br.ub(4)
                f0 = f1 = ln = 0
    groups.append((fills, lines, edges))

    paths = []
    for fills, lines, edges in groups:
        for fi in range(1, len(fills) + 1):
            segs = []
            for e in edges:
                if e[1] == fi:
                    segs.append((e[3], e[4], e[5]))
                if e[0] == fi:
                    segs.append((e[5], e[4], e[3]))
            if segs:
                paths.append({'fill': fills[fi - 1], 'd': _chain(segs)})
        for li in range(1, len(lines) + 1):
            segs = [(e[3], e[4], e[5]) for e in edges if e[2] == li]
            if segs:
                paths.append({'line': lines[li - 1], 'd': _chain(segs, closed=False)})
    return cid, {'bounds': bounds, 'paths': paths}


def _chain(segs, closed=True):
    """Link directed segments into contours; return SVG path data (twips)."""
    by_start = {}
    for i, s in enumerate(segs):
        by_start.setdefault(s[0], []).append(i)
    used = [False] * len(segs)
    out = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        start, c, end = segs[i]
        parts = [f'M{start[0]} {start[1]}', _seg(c, end)]
        cur = end
        while cur != start:
            nxt = next((j for j in by_start.get(cur, ()) if not used[j]), None)
            if nxt is None:
                break
            used[nxt] = True
            _, c, end = segs[nxt]
            parts.append(_seg(c, end))
            cur = end
        if closed and cur == start:
            parts.append('Z')
        out.append(''.join(parts))
    return ''.join(out)


def _seg(c, e):
    if c is None:
        return f'L{e[0]} {e[1]}'
    return f'Q{c[0]} {c[1]} {e[0]} {e[1]}'


# ---------------------------------------------------------------- other definitions

def parse_edit_text(body):
    br = Bits(body)
    cid = br.u16()
    bounds = br.rect()
    f1, f2 = br.u8(), br.u8()
    t = {'bounds': bounds, 'html': bool(f2 & 0x02), 'multiline': bool(f1 & 0x20), 'wordwrap': bool(f1 & 0x40)}
    if f1 & 0x01:
        t['font'] = br.u16()
        t['height'] = br.u16()
    if f1 & 0x04:
        t['color'] = br.rgb(True)
    if f1 & 0x02:
        br.u16()
    if f2 & 0x20:
        t['align'] = br.u8()
        br.u16(); br.u16(); br.u16(); br.s16()
    t['var'] = br.cstr()
    t['text'] = br.cstr() if f1 & 0x80 else ''
    return cid, t


def parse_font2(body):
    cid = struct.unpack_from('<H', body)[0]
    n = body[4]
    return cid, body[5:5 + n].decode('cp949', 'replace')


def parse_place2(body):
    br = Bits(body)
    fl = br.u8()
    p = {'depth': br.u16(), 'move': bool(fl & 1)}
    if fl & 0x02:
        p['id'] = br.u16()
    if fl & 0x04:
        p['matrix'] = br.matrix()
    if fl & 0x08:
        p['cxform'] = br.cxform(True)
    if fl & 0x10:
        p['ratio'] = br.u16()
    if fl & 0x20:
        p['name'] = br.cstr()
    if fl & 0x40:
        p['clip'] = br.u16()
    if fl & 0x80:  # SWF5 clip actions
        br.u16()
        br.u16()  # all event flags
        acts = []
        while True:
            ev = br.u16()
            if ev == 0:
                break
            ln = br.u32()
            acts.append((ev, parse_actions(body, br.pos, br.pos + ln)))
            br.pos += ln
        p['clipactions'] = acts
    return p


def parse_button2(body):
    br = Bits(body)
    cid = br.u16()
    br.u8()
    action_off = br.u16()
    off_pos = br.pos - 2
    recs = []
    while True:
        fl = br.u8()
        if fl == 0:
            break
        r = {'states': fl & 0x0F, 'id': br.u16(), 'depth': br.u16(), 'matrix': br.matrix()}
        r['cxform'] = br.cxform(True)
        recs.append(r)
    actions = []
    if action_off:
        pos = off_pos + action_off
        while True:
            size, cond = struct.unpack_from('<HH', body, pos)
            end = pos + size if size else len(body)
            actions.append({'cond': cond, 'actions': parse_actions(body, pos + 4, end)})
            if not size:
                break
            pos = end
    return cid, {'records': recs, 'actions': actions}


# ---------------------------------------------------------------- container

class Timeline:
    def __init__(self):
        self.frames = []  # each: {'label', 'actions', 'display': {depth: place}}


class SWF:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        d = self.data
        assert d[:3] == b'FWS', 'uncompressed SWF expected'
        self.version = d[3]
        br = Bits(d, 8)
        self.stage = br.rect()
        self.rate = d[br.pos + 1]
        self.frame_count = struct.unpack_from('<H', d, br.pos + 2)[0]
        self.chars = {}      # id -> (kind, data)
        self.jpegs = {}      # id -> bytes
        self.root = self._timeline(br.pos + 4, len(d))

    def _tags(self, pos, end):
        d = self.data
        while pos < end:
            cl = struct.unpack_from('<H', d, pos)[0]
            pos += 2
            code, ln = cl >> 6, cl & 0x3F
            if ln == 0x3F:
                ln = struct.unpack_from('<I', d, pos)[0]
                pos += 4
            yield code, pos, ln
            pos += ln
            if code == 0:
                return

    def _timeline(self, pos, end):
        tl = Timeline()
        display, label, actions = {}, None, []
        d = self.data
        for code, p, ln in self._tags(pos, end):
            body = d[p:p + ln]
            if code in (2, 22, 32):
                cid, s = parse_shape(body, {2: 1, 22: 2, 32: 3}[code])
                self.chars[cid] = ('shape', s)
            elif code == 46:
                self.chars[struct.unpack_from('<H', body)[0]] = ('morph', None)
            elif code == 37:
                cid, t = parse_edit_text(body)
                self.chars[cid] = ('text', t)
            elif code == 48:
                cid, name = parse_font2(body)
                self.chars[cid] = ('font', name)
            elif code == 34:
                cid, b = parse_button2(body)
                self.chars[cid] = ('button', b)
            elif code == 39:
                cid = struct.unpack_from('<H', body)[0]
                self.chars[cid] = ('sprite', self._timeline(p + 4, p + ln))
            elif code in (6, 21):
                cid = struct.unpack_from('<H', body)[0]
                self.jpegs[cid] = body[2:]
                self.chars[cid] = ('bitmap', None)
            elif code == 26:
                pl = parse_place2(body)
                if pl['move']:
                    old = dict(display.get(pl['depth'], {}))
                    if 'id' in pl and pl.get('id') != old.get('id'):
                        old = {}
                    old.update({k: v for k, v in pl.items() if k != 'move'})
                    display[pl['depth']] = old
                else:
                    display[pl['depth']] = {k: v for k, v in pl.items() if k != 'move'}
            elif code == 28:
                display.pop(struct.unpack_from('<H', body)[0], None)
            elif code == 43:
                label = body.split(b'\0')[0].decode('cp949', 'replace')
            elif code == 12:
                actions.append(parse_actions(body))
            elif code == 1:
                tl.frames.append({'label': label, 'actions': actions, 'display': dict(display)})
                label, actions = None, []
        return tl

    def frame_index(self, tl, label):
        for i, f in enumerate(tl.frames):
            if f['label'] == label:
                return i
        return None


def char_bounds(swf, cid, m=IDENTITY, frame=0):
    """Axis-aligned bounds (xmin, ymin, xmax, ymax) of a character under matrix m, or None."""
    kind, v = swf.chars.get(cid, (None, None))
    if kind in ('shape', 'text'):
        b = v['bounds']
        pts = [mat_apply(m, x, y) for x in (b[0], b[1]) for y in (b[2], b[3])]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    if kind == 'sprite':
        if not v.frames:
            return None
        items = [(p['id'], mat_mul(m, p.get('matrix', IDENTITY)))
                 for p in v.frames[min(frame, len(v.frames) - 1)]['display'].values() if 'id' in p]
    elif kind == 'button':
        items = [(r['id'], mat_mul(m, r['matrix'])) for r in v['records'] if r['states'] & 8 or r['states'] & 1]
    else:
        return None
    bs = [b for b in (char_bounds(swf, c, mm) for c, mm in items) if b]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def button_gotos(swf, cid):
    """Frame targets of a button's release actions: list of ('frame', n) / ('label', s) / ('url', u)."""
    out = []
    for ba in swf.chars[cid][1]['actions']:
        for name, args in ba['actions']:
            if name == 'GotoFrame':
                out.append(('frame', args[0]))
            elif name == 'GotoLabel':
                out.append(('label', args[0]))
            elif name == 'GetURL':
                out.append(('url', args[0]))
    return out
