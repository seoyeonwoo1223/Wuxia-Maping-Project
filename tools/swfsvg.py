"""Render SWF display lists (shapes, sprites, buttons) to SVG. Text fields are skipped by default."""
from swflib import IDENTITY, mat_mul


def _color(c):
    return '#%02x%02x%02x' % tuple(c[:3])


def _alpha(c):
    return c[3] / 255 if len(c) > 3 else 1.0


def _cx(color, cx):
    """Apply a colour transform to [r,g,b,a]."""
    if not cx:
        return color
    c = list(color) + ([255] if len(color) == 3 else [])
    mult, add = cx.get('mult'), cx.get('add')
    out = []
    for i in range(4):
        v = c[i]
        if mult and i < len(mult):
            v = v * mult[i] / 256
        if add and i < len(add):
            v += add[i]
        out.append(max(0, min(255, round(v))))
    return out


def _mat(m):
    a, b, c, d, tx, ty = m
    return f'matrix({a:.5g} {b:.5g} {c:.5g} {d:.5g} {tx:.5g} {ty:.5g})'


def _combine_cx(outer, inner):
    """Compose colour transforms: apply inner first, then outer."""
    if not outer:
        return inner
    if not inner:
        return outer

    def norm(v, default):
        v = list(v or [])
        return v + [default] * (4 - len(v))

    om, oa = norm(outer.get('mult'), 256), norm(outer.get('add'), 0)
    im, ia = norm(inner.get('mult'), 256), norm(inner.get('add'), 0)
    return {'mult': [im[i] * om[i] / 256 for i in range(4)], 'add': [ia[i] * om[i] / 256 + oa[i] for i in range(4)]}


class Renderer:
    def __init__(self, swf, include_text=False, skip=None, path_filter=None):
        self.swf = swf
        self.path_filter = path_filter or (lambda m, path: True)
        self.include_text = include_text
        self.skip = skip or (lambda cid, place: False)
        self.defs = []
        self.grad_n = 0
        self.clip_n = 0
        self.bounds = None  # union of emitted path bounds (twips)

    def shape(self, cid, m, cx):
        s = self.swf.chars[cid][1]
        out = []
        for p in s['paths']:
            if not self.path_filter(m, p):
                continue
            if 'fill' in p:
                f = p['fill']
                if f['type'] == 'solid':
                    c = _cx(f['color'], cx)
                    a = _alpha(c)
                    attrs = f'fill="{_color(c)}"' + (f' fill-opacity="{a:.3g}"' if a < 1 else '')
                elif f['type'] in ('linear', 'radial'):
                    self.grad_n += 1
                    gid = f'g{self.grad_n}'
                    stops = ''.join(
                        f'<stop offset="{r / 255:.3g}" stop-color="{_color(_cx(c, cx))}"'
                        + (f' stop-opacity="{_alpha(_cx(c, cx)):.3g}"' if _alpha(_cx(c, cx)) < 1 else '') + '/>'
                        for r, c in f['stops'])
                    if f['type'] == 'linear':
                        self.defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="-16384" x2="16384" y1="0" y2="0" gradientTransform="{_mat(f["matrix"])}">{stops}</linearGradient>')
                    else:
                        self.defs.append(f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="16384" gradientTransform="{_mat(f["matrix"])}">{stops}</radialGradient>')
                    attrs = f'fill="url(#{gid})"'
                else:  # bitmap fill: not reproduced
                    continue
                out.append(f'<path {attrs} d="{p["d"]}"/>')
            else:
                ln = p['line']
                c = _cx(ln['color'], cx)
                a = _alpha(c)
                w = max(ln['width'], 20)
                out.append(f'<path fill="none" stroke="{_color(c)}" stroke-width="{w}"'
                           + (f' stroke-opacity="{a:.3g}"' if a < 1 else '')
                           + f' stroke-linecap="round" stroke-linejoin="round" d="{p["d"]}"/>')
        if not out:
            return ''
        for p in s['paths']:
            if self.path_filter(m, p) and ('line' in p or p['fill']['type'] != 'bitmap'):
                b = path_bounds(m, p)
                self.bounds = b if self.bounds is None else (
                    min(self.bounds[0], b[0]), min(self.bounds[1], b[1]),
                    max(self.bounds[2], b[2]), max(self.bounds[3], b[3]))
        return f'<g transform="{_mat(m)}">' + ''.join(out) + '</g>'

    def char(self, cid, m, cx, frame=0, place=None):
        kind, v = self.swf.chars.get(cid, (None, None))
        if kind == 'shape':
            return self.shape(cid, m, cx)
        if kind == 'sprite':
            f = v.frames[min(frame, len(v.frames) - 1)] if v.frames else {'display': {}}
            return self.display(f['display'], m, cx)
        if kind == 'button':
            parts = []
            for r in sorted(v['records'], key=lambda r: r['depth']):
                if r['states'] & 1:  # up state
                    parts.append(self.char(r['id'], mat_mul(m, r['matrix']), _combine_cx(cx, r['cxform'])))
            return ''.join(parts)
        if kind == 'text' and self.include_text:
            t = v
            x0, y0 = t['bounds'][0], t['bounds'][2]
            lines = t['text'].replace('\r\n', '\r').split('\r')
            h = t.get('height', 240)
            c = _color(_cx(t.get('color', [0, 0, 0, 255]), cx))
            spans = ''.join(f'<tspan x="{x0}" dy="{h * 1.2:.0f}">{_esc(l)}</tspan>' for l in lines)
            return f'<text transform="{_mat(m)}" y="{y0}" font-size="{h}" fill="{c}">{spans}</text>'
        return ''

    def display(self, display, m, cx):
        out = []
        clip_until, buf, clip_id = None, None, None
        for depth in sorted(display):
            p = display[depth]
            if 'id' not in p or self.skip(p['id'], p):
                continue
            if clip_until is not None and depth > clip_until:
                out.append(f'<g clip-path="url(#{clip_id})">' + ''.join(buf) + '</g>')
                clip_until = None
            pm = mat_mul(m, p.get('matrix', IDENTITY))
            pcx = _combine_cx(cx, p.get('cxform'))
            if 'clip' in p:
                self.clip_n += 1
                clip_id = f'c{self.clip_n}'
                self.defs.append(f'<clipPath id="{clip_id}">' + self.char(p['id'], pm, None) + '</clipPath>')
                clip_until, buf = p['clip'], []
                continue
            svg = self.char(p['id'], pm, pcx, place=p)
            (buf if clip_until is not None else out).append(svg)
        if clip_until is not None:
            out.append(f'<g clip-path="url(#{clip_id})">' + ''.join(buf) + '</g>')
        return ''.join(out)

    def document(self, body, viewbox):
        x, y, w, h = viewbox
        defs = '<defs>' + ''.join(self.defs) + '</defs>' if self.defs else ''
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.0f} {y:.0f} {w:.0f} {h:.0f}">'
                f'{defs}{body}</svg>\n')


def path_bounds(m, path):
    """Bounds of a shape path (control points included) under matrix m."""
    import re
    from swflib import mat_apply
    nums = list(map(float, re.findall(r'-?\d+(?:\.\d+)?', path['d'])))
    pts = [mat_apply(m, nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    return (min(x for x, y in pts), min(y for x, y in pts), max(x for x, y in pts), max(y for x, y in pts))


def _esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
