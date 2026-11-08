#!/usr/bin/env python3
"""Convert the pinned TikZpingus manual using shared/texhtml.

The custom key environments become searchable HTML definitions; tcblisting
and the compact keyline macros keep copyable source beside their native TeX
output. Source excerpts are read from the pinned .sty's region/chunk markers.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHARED = ROOT / 'shared'
sys.path.insert(0, str(SHARED))
from texhtml.core import (Context, Converter, Page, ParseError, code_block, esc,
                          find_env_end, footnotes_html, instrument, load_images, match_brace,
                          read_args, read_cs, skip_comment, skip_ws)
from texhtml.site import Manual, write_site
from home import contents

UPSTREAM = Path(os.environ.get('UPSTREAM', ROOT / '.upstream/tikzpingus'))
BUILD = HERE / 'build'
TEXDIR = BUILD / 'tex'
SITE = BUILD / 'site/tikzpingus'
IMGDIR = 'tikzpingus-images'
JOB = 'tikzpingus-html'


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def chapter_groups(text):
    """Represent groups crossing a page boundary with equivalent TeX commands.

    Braced arguments stay intact. Only unmatched grouping braces are changed;
    TeX retains their scope while the HTML parser can read each page alone.
    """
    stack, unmatched, i = [], [], 0
    while i < len(text):
        if text[i] == '%':
            i = skip_comment(text, i)
            continue
        if text.startswith(r'\begin{tcblisting}', i):
            i = find_env_end(text, i + len(r'\begin{tcblisting}'), 'tcblisting', True)[1]
            continue
        if text[i] == '\\':
            _, i = read_cs(text, i)
            continue
        if text[i] == '|':
            stop = text.find('|', i + 1)
            if stop != -1:
                i = stop + 1
                continue
        if text[i] == '{':
            stack.append(i)
        elif text[i] == '}':
            if stack:
                stack.pop()
            else:
                unmatched.append((i, r'\endgroup '))
        i += 1
    unmatched += [(i, r'\begingroup ') for i in stack]
    for pos, replacement in sorted(unmatched, reverse=True):
        text = text[:pos] + replacement + text[pos + 1:]
    return text


@dataclass
class Chunk:
    stem: str
    slug: str
    part: str
    number: str
    level: int
    text: str


class Source:
    def __init__(self, upstream=UPSTREAM):
        self.upstream = Path(upstream)
        self.text = (self.upstream / 'doc/tikzpingus-doc.tex').read_text()
        self.code = (self.upstream / 'tex/tikzpingus.sty').read_text()
        version = re.search(r'\[(\d{4}/\d{2}/\d{2}) version v([^ ]+)', self.code)
        self.date, self.version = version.groups()
        self.lines = self.code.splitlines()
        self.regions = self.read_regions()
        self.colorkeys = self.read_colorkeys()
        self.selection_keys = {'bodytype': 'body type', 'lefteye': 'eyes', 'leftwing': 'wings',
                               'leftfoot': 'feet', 'bill': 'bill', 'hairstyle': 'hairstyle'}
        helpers = {'bodytype': 'pingu@bodytype@add', 'lefteye': 'pingu@eyes@s',
                   'leftwing': '@pingu@wings@s', 'leftfoot': 'pingu@feet@s',
                   'bill': 'pingu@bill@s', 'hairstyle': 'pingu@hairstyle@add',
                   'wingitems': 'pingu@create@wing@extra'}
        self.selections = {}
        for name, helper in helpers.items():
            values = re.findall(r'^\\' + re.escape(helper) + r'\{([^#{}]+)\}', self.code, re.M)
            if not values:
                raise ValueError(f'No options found for {name}; review its source helper {helper}')
            self.selections[name] = list(dict.fromkeys(([] if name == 'wingitems' else ['none']) + values))
        for name in ('eye', 'wing', 'foot'):
            self.selections['right' + name] = self.selections['left' + name]
        self.gadgets = []
        for m in re.finditer(r'\\showkeyexplain\b', self.text):
            args, end = read_args(self.text, m.end(), 'ommm')
            key = self.text[slice(*args[1])]
            if '#' in key:  # the definition in the preamble
                continue
            end = skip_ws(self.text, end)
            value = ''
            if self.text[end:end + 1] == '(':
                stop = match_brace(self.text, end, '(', ')')
                value = self.text[end + 1:stop]
            self.gadgets.append((key, value))
        self.preamble = self.text[:self.text.index(r'\begin{document}')]
        start = self.text.index('For my slides')
        brace = self.text.rfind('{', 0, start)
        motivation = self.text[brace + 1:match_brace(self.text, brace)]
        footnote, _ = read_args(self.text, self.text.index(r'\footnotetext', start) + len(r'\footnotetext'), 'm')
        self.motivation = motivation.replace(r'\footnotemark', '\\footnote{' + self.text[slice(*footnote[0])] + '}')
        self.parts = [('guide', 'Getting started'), ('reference', 'Full reference'),
                      ('keys', 'Penguin keys'), ('styles', 'Drawing styles'),
                      ('extras', 'Extras'), ('wing-items', 'Wing items'),
                      ('clothes', 'Clothes'), ('implementation', 'Internals')]
        self.chunks = self.read_chunks()
        reserved = {name for name, _ in self.parts} | {'index', 'key-index'}
        collisions = reserved.intersection(c.slug for c in self.chunks)
        if collisions:
            raise ValueError('Chapter URLs collide with landing pages: ' + ', '.join(sorted(collisions)))

    def read_regions(self):
        entries, stack, chunks = [], [], {}
        for n, line in enumerate(self.lines, 1):
            m = re.fullmatch(r'\s*%\s*#region\s+(.+?)\s*', line)
            if m:
                entry = dict(name=m[1], start=n, end=None, depth=len(stack), kind='region')
                entries.append(entry)
                stack.append(entry)
            elif re.match(r'\s*%\s*#endregion', line):
                stack.pop()['end'] = n
            else:
                m = re.fullmatch(r'\s*%\s*<(@?)([^>]+)>\s*', line)
                if m:
                    if m[1]:
                        chunks[m[2]]['end'] = n
                    else:
                        entry = dict(name=m[2], start=n, end=None, depth=len(stack), kind='chunk')
                        entries.append(entry)
                        chunks[m[2]] = entry
        if stack or any(e['end'] is None for e in entries):
            raise ValueError('Unclosed source regions; review the upstream source map')
        return {e['name']: e for e in entries}

    def excerpt(self, name, options=''):
        entry = self.regions[name]
        first, last = entry['start'] + 1, entry['end'] - 1
        start = re.search(r'(?:^|,)\s*from\s*=\s*(\d+)', options)
        stop = re.search(r'(?:^|,)\s*to\s*=\s*(\d+)', options)
        if stop:
            last = first + int(stop[1]) - 1
        if start:
            first += int(start[1]) - 1
        return first, last, '\n'.join(self.lines[first - 1:last])

    def read_colorkeys(self):
        """Resolve the source scanner's color-macro markers to documented keys."""
        result = {}
        for match in re.finditer(r'^\s*([^%\n]+?)/\.code\s*=\s*(.*)', self.code, re.M):
            key, code = match.groups()
            color = re.search(r'\\pingu@color\{([^}]+)\}', code)
            if not color or '#' in key or '#' in color[1]:
                continue
            for side in ('left', 'right'):
                name = key.strip().replace(r'\@lr', side).replace(r'\space', ' ')
                macro = 'pingu@color@' + color[1].replace(r'\@lr', side)
                macro = re.sub(r'\s+', '', macro)
                if '\\' not in name and '\\' not in macro:
                    result.setdefault(macro, ' '.join(name.split()))
        return result

    def overview(self):
        lines = [r'\section{Visual overviews}']
        for name, key in self.selection_keys.items():
            lines += [f'\\subsection{{{key.capitalize()}}}\\label{{sec:overview-{key}}}',
                      f'Use \\lpingu{{{key}=<option>}} to select an option.', r'\begin{HTMLgallery}']
            lines += [f'\\HTMLselection{{{key}}}{{{v}}}' for v in self.selections[name]]
            lines.append(r'\end{HTMLgallery}')
        lines += [r'\subsection{Anchors}\label{sec:overview-anchors}',
                  r'\TypesetAnchors', r'\subsection{Gadgets}\label{Gadget-Overview}',
                  r'Select a penguin to read about its keys.', r'\begin{HTMLgallery}']
        lines += [f'\\HTMLgadget{{{k}}}{{{"=" + v if v else ""}}}' for k, v in self.gadgets]
        lines.append(r'\end{HTMLgallery}')
        return '\n'.join(lines)

    def read_chunks(self):
        # Only column-zero headings outside listings count as page boundaries.
        # In this manual examples are indented, but explicitly skip their bodies
        # as well so a future example containing a heading cannot split a page.
        begin = self.text.index(r'\section{Introduction}')
        end = self.text.index(r'\lstset{breakatwhitespace}', begin)
        body = self.text[begin:end]
        ignored = [(m.start(), find_env_end(body, m.end(), 'tcblisting', True)[1])
                   for m in re.finditer(r'\\begin\{tcblisting\}', body)]
        marks = [m for m in re.finditer(r'^\\(section|subsection|subsubsection)\{([^}]+)\}', body, re.M)
                 if not any(a <= m.start() < b for a, b in ignored)]
        chunks = [Chunk('overview', 'overview', 'guide', '', 1, self.overview())]
        section, subsection, subsubsection = 0, 0, 0
        part = 'guide'
        selected = []
        used = set()
        for m in marks:
            level = {'section': 1, 'subsection': 2, 'subsubsection': 3}[m[1]]
            if level == 1:
                section += 1
                subsection = subsubsection = 0
                part = 'reference' if section == 4 else 'implementation' if section == 6 else 'guide'
            elif level == 2:
                subsection += 1
                subsubsection = 0
                if section == 4:
                    part = {1: 'keys', 2: 'styles', 3: 'extras', 4: 'wing-items', 5: 'clothes'}[subsection]
            else:
                subsubsection += 1
            # The guide and internals split at subsections, reference at every
            # subsubsection (one gadget per page). Other sections stay together.
            if level > (3 if section == 4 else 2 if section in (2, 6) else 1):
                continue
            top = str(section) if section < 4 else chr(ord('A') + section - 4)
            number = '.'.join(map(str, [top] + ([subsection] if level >= 2 else []) +
                                      ([subsubsection] if level == 3 else [])))
            prefix = ('ref-' if section == 4 else 'internal-' if section == 6 else
                      'usage-' if section == 2 and level == 2 else '')
            name = prefix + slug(re.sub(r'^The ', '', m[2]))
            if name in used:
                name += '-' + part
            if name in used:
                raise ValueError('Repeated chapter title; assign a stable URL for ' + m[2])
            used.add(name)
            selected.append((m.start(), name, part, number, level))
        for n, (start, name, part, number, level) in enumerate(selected):
            stop = selected[n + 1][0] if n + 1 < len(selected) else len(body)
            text = body[start:stop]
            text = chapter_groups(text)
            text = text.replace(r'\expandafter\ipingu\expandafter{\@pingu@none}', r'\ipingu{!hide}')
            chunks.append(Chunk('c' + number.replace('.', '-'), name, part, number, level, text))
        return chunks


class PinguConverter(Converter):
    verbatim_envs = Converter.verbatim_envs | {'tcblisting'}
    transparent_envs = Converter.transparent_envs | {'HTMLgallery'}
    ignored = dict(Converter.ignored, **{'tcbset': 'm', 'lstset': 'm', 'appendix': '',
                   'newsavebox': 'm', 'newif': 'm', 'savebox': 'moom',
                   '@toggle@showcase': '', 'percenttargetreductionpengus': '',
                   'indexprologue': 'm', 'printindex': 'o'})
    img_dir = IMGDIR

    def __init__(self, ctx, chunk, page):
        super().__init__(ctx, chunk.text, chunk.slug, chunk.stem, page)
        self.chunk = chunk
        self.value_count = 0
        self.anchors = set()

    def add_anchor(self, label, text='', kind='key'):
        anchor = label.replace(' ', ':')
        anchor = re.sub(r'[^A-Za-z0-9_:./=!-]', '-', anchor)
        if anchor in self.anchors:
            return ''
        self.anchors.add(anchor)
        self.ctx.add_label(label, slug=self.slug, anchor=anchor, text=text, kind=kind)
        return anchor

    def definition(self, name, path='/pingu/', command=False):
        name = ' '.join(name.split())
        label = 'pk:' + path + ('_' if command else '') + name
        anchor = self.add_anchor(label, ('\\' if command else '') + name, 'command' if command else 'key')
        if self.ctx.pass_no == 1:
            (self.ctx.known_commands if command else self.ctx.known_keys).setdefault(name, label)
        return anchor

    def linked(self, label, text):
        label = ' '.join(label.split())
        href = self.ctx.href(label, self.slug)
        if href:
            return f'<a href="{esc(href)}">{text}</a>'
        if self.ctx.pass_no == 2:
            self.ctx.warn('unresolved reference ' + label)
        return text

    def value(self, pos, expression, key=None, parent=''):
        self.value_count += 1
        ident = f'{self.stem}-value-{self.value_count}'
        tex = (f'\\HTMLkeyvalue{{{ident}}}{{{parent}}}{{{key}}}{{{expression}}}' if key is not None else
               f'\\HTMLvalue{{{ident}}}{{{expression}}}')
        self.captures.append((pos, None, tex + '%\n', 'raw'))
        if getattr(self.ctx, 'mode', 'tex') == 'html' and ident not in self.ctx.values:
            raise ValueError('Missing computed TeX value ' + ident)
        value = self.ctx.values.get(ident, expression)
        if ident not in self.ctx.values and '\\' in value:
            return ''  # resolved by the forthcoming native TeX run
        def placeholder(match):
            name = match[1]
            if name == '@col':
                words = (key or '').split()[:-1]
                target = parent or next((' '.join(words[:n]) for n in range(len(words), 0, -1)
                                         if ' '.join(words[:n]) in self.ctx.known_keys), '')
                label = self.linked('pk:/pingu/' + target, esc(target)) if target else 'color'
            else:
                target = (self.ctx.values.get('colorkey:' + name) or
                          getattr(self.ctx.source, 'colorkeys', {}).get(name))
                if target and 'pk:/pingu/' + target not in self.ctx.labels:
                    target = None
                if not target:
                    # The source scanner uses angle markers around macros,
                    # including macros inside code-valued defaults. Keep their
                    # braces and backslashes verbatim, just as the PDF does.
                    label = 'pk:/pingu/_' + name
                    return self.linked(label, esc('\\' + name)) if label in self.ctx.labels else esc('\\' + name)
                label = self.linked('pk:/pingu/' + target, esc(target))
            return '<span class="angle">⟨</span><i>' + label + '</i><span class="angle">⟩</span>'
        parts = re.split(r'(<@col>|<@?pingu@[A-Za-z@]+>)', value)
        output = []
        for part in parts:
            match = re.fullmatch(r'<(@col|@?pingu@[A-Za-z@]+)>', part)
            output.append(placeholder(match) if match else esc(part))
        return ''.join(output)

    def entry_html(self, anchor, name, typ, default, body, command=False, parent=''):
        signature = f'<kbd>{esc(("" if command else "/pingu/") + name)}</kbd>'
        if typ:
            signature += f' = <span class="angle">⟨</span><i>{typ}</i><span class="angle">⟩</span>'
        syntax = '<span class="hl-def">' + signature + '</span>'
        if default:
            syntax += f'<span class="hl-default">(default: {default})</span>'
        requirement = f'<p class="pingu-requires">Requires {parent}.</p>' if parent else ''
        ident = f' id="{esc(anchor)}"' if anchor else ''
        permalink = f'<a class="anchor-link" href="#{esc(anchor)}">&para;</a>' if anchor else ''
        return (f'<div class="manualentry"><div class="entryheadline"{ident}><p>{syntax}{permalink}</p></div>'
                f'<div class="entrybody">{requirement}{body}</div></div>')

    def entry(self, k, e, out, env, command=False, sub=False, show=False):
        spec = ('o' + 'm' * (3 if sub else 2)) if command else ('o' + 'm' * (4 if sub else 3))
        args, start = read_args(self.s, e, spec)
        raw = [self.raw(a) for a in args]
        parent = raw[1] if sub else ''
        name = raw[2] if sub else raw[1]
        path = raw[0] or '/pingu/'
        if show and self.s[skip_ws(self.s, start):].startswith('('):
            start = match_brace(self.s, skip_ws(self.s, start), '(', ')') + 1
        if self.s.startswith(r'\begin{' + env + '}', k):
            stop, after = find_env_end(self.s, start, env)
        else:
            m = re.search(r'\\end' + env + r'\b', self.s[start:])
            if not m:
                raise ParseError('missing end' + env)
            stop, after = start + m.start(), start + m.end()
        anchor = self.definition(name, path, command)
        default = '' if command else self.value(k, raw[-1], name, parent)
        typ = self.inline(args[-1] if command else args[-2])
        if command:
            display = '\\' + name
            syntax = f'<kbd>{esc(display)}</kbd>{typ}'
            typ = ''
        else:
            display, syntax = name, None
        body = self.render(self.items(start, stop))
        requires = self.linked('pk:/pingu/' + ('_' if command else '') + parent,
                               '<kbd>' + esc(('\\' if command else '') + parent) + '</kbd>') if parent else ''
        output = self.entry_html(anchor, display, typ, default, body, command, requires)
        if syntax:
            output = output.replace(f'<kbd>{esc(display)}</kbd>', syntax, 1)
        out.append(('b', output))
        return after

    def cmd_keyexplain(self, k, e, out):
        return self.entry(k, e, out, 'keyexplain')

    def cmd_subkeyexplain(self, k, e, out):
        return self.entry(k, e, out, 'subkeyexplain', sub=True)

    def cmd_showkeyexplain(self, k, e, out):
        return self.entry(k, e, out, 'showkeyexplain', show=True)

    def environment(self, k, e, b, out):
        args, end = read_args(self.s, e, 'm')
        name = self.raw(args[0])
        if name in ('keyexplain', 'subkeyexplain', 'showkeyexplain', 'commandexplain', 'subcommandexplain'):
            return self.entry(k, end, out, name, command='command' in name,
                              sub=name.startswith('sub'), show=name.startswith('show'))
        return super().environment(k, e, b, out)

    def keyline(self, k, e, out, sub):
        args, end = read_args(self.s, e, 'ommmm' if sub else 'ommm')
        raw = [self.raw(a) for a in args]
        parent = raw[1] if sub else ''
        setting = raw[2] if sub else raw[1]
        name = setting.split('=', 1)[0].strip()
        anchor = self.definition(name)
        default = self.value(k, raw[-1], name, parent)
        typ = self.inline(args[-2])
        keys = ', '.join(x for x in (parent, raw[0], setting) if x)
        code = '\\begin{tikzpicture}\n  \\pingu[' + keys + ']\n\\end{tikzpicture}'
        image = self.new_image(k, None, 'example')
        example = self.example(code, image)
        requires = self.linked('pk:/pingu/' + parent, '<kbd>' + esc(parent) + '</kbd>') if parent else ''
        out.append(('b', self.entry_html(anchor, name, typ, default, example, parent=requires)))
        return end

    def cmd_keyline(self, k, e, out):
        return self.keyline(k, e, out, False)

    def cmd_subkeyline(self, k, e, out):
        return self.keyline(k, e, out, True)

    def example(self, code, image, title=''):
        return (f'<figure class="example"><div class="example-image"><p>{self.img_html(image)}</p></div>'
                + code_block(code, self.ctx, self.slug, title or None) + '</figure>')

    def env_tcblisting(self, k, a, b, after, out):
        args, start = read_args(self.s, a, 'm')
        opts = self.kv_dict(args[0])
        title = self.inline(opts.get('title'))
        image = self.new_image(k, None, 'example')
        label = self.raw(opts.get('label') or opts.get('phantomlabel'))
        if label:
            anchor = self.add_anchor(label, self.plain(opts.get('nameref')) or title, 'example')
            out.append(('b', f'<a id="{esc(anchor)}"></a>'))
        out.append(('b', self.example(self.s[start:b], image, title)))

    def env_center(self, k, a, b, after, out):
        if r'\percenttargetreductionpengus' in self.s[a:b]:
            return  # a print-only explanation of the PDF's example scaling
        if re.search(r'\\(?:resizebox|parbox|begin\{tikzpicture\})', self.s[a:b]):
            image = self.new_image(k, after, 'block')
            out.append(('b', f'<div class="figure">{self.img_html(image)}</div>'))
        else:
            out.extend(self.items(a, b))

    def env_HTMLgallery(self, k, a, b, after, out):
        out.append(('b', '<div class="pingu-gallery">' + self.render(self.items(a, b)) + '</div>'))

    def gallery_item(self, k, e, out, gadget):
        args, end = read_args(self.s, e, 'mm')
        name, val = map(self.raw, args)
        image = self.new_image(k, end, 'inline')
        label = 'pk:/pingu/' + name if gadget else 'expl-list:' + next(
            key for key, value in self.ctx.source.selection_keys.items() if value == name)
        caption = name if gadget else val
        card = f'<figure>{self.img_html(image, alt=caption)}<figcaption><kbd>{esc(caption)}</kbd></figcaption></figure>'
        out.append(('b', self.linked(label, card)))
        return end

    def cmd_HTMLgadget(self, k, e, out):
        return self.gallery_item(k, e, out, True)

    def cmd_HTMLselection(self, k, e, out):
        return self.gallery_item(k, e, out, False)

    def cmd_TypesetAnchors(self, k, e, out):
        image = self.new_image(k, e, 'inline')
        out.append(('b', '<div class="figure">' + self.img_html(image, alt='Penguin anchors') + '</div>'))
        return e

    def cmd_typesetselection(self, k, e, out):
        args, end = read_args(self.s, e, 'om')
        name = self.raw(args[1])
        anchor = self.add_anchor('expl-list:' + name, name, 'selection')
        out.append(('i', f'<span id="{esc(anchor)}">' + ', '.join(
            f'<i>{esc(v)}</i>' for v in self.ctx.source.selections[name]) + '</span>'))
        return end

    def cmd_keyref(self, k, e, out, short=False):
        args, end = read_args(self.s, e, 'om')
        path, name = self.raw(args[0]) or '/pingu/', self.raw(args[1])
        out.append(('i', self.linked('pk:' + path + name, '<kbd>' + esc(('' if short else path) + name) + '</kbd>')))
        return end

    def cmd_dkeyref(self, k, e, out):
        return self.cmd_keyref(k, e, out, True)

    def cmd_cmdref(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        name = self.raw(args[0])
        out.append(('i', self.linked('pk:/pingu/_' + name, '<kbd>\\' + esc(name) + '</kbd>')))
        return end

    def cmd_cmddef(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        name = self.raw(args[0])
        anchor = self.definition(name, command=True)
        out.append(('i', f'<kbd id="{esc(anchor)}">\\{esc(name)}</kbd>' if anchor else '<kbd>\\' + esc(name) + '</kbd>'))
        return end

    def cmd_cmdcoldef(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        name = 'pingu@color@' + self.raw(args[0])
        anchor = self.definition(name, command=True)
        out.append(('i', f'<kbd id="{esc(anchor)}">\\{esc(name)}</kbd>'))
        return end

    def cmd_subcmddef(self, k, e, out):
        args, end = read_args(self.s, e, '*mm')
        name = self.raw(args[2])
        anchor = self.definition(name, command=True)
        out.append(('i', f'<a id="{esc(anchor)}"></a>' if args[0] else f'<kbd id="{esc(anchor)}">\\{esc(name)}</kbd>'))
        return end

    def alias(self, k, e, out, sub):
        args, end = read_args(self.s, e, 'ommm' if sub else 'omm')
        path, name, target = self.raw(args[0]) or '/pingu/', self.raw(args[1]), self.raw(args[2])
        anchor = self.definition(name, path)
        out.append(('b', f'<p class="pingu-alias" id="{esc(anchor)}"><kbd>{esc(name)}</kbd>: alias of ' +
                    self.linked('pk:' + path + target, '<kbd>' + esc(target) + '</kbd>') + '.</p>'))
        return end

    def cmd_keyalias(self, k, e, out):
        return self.alias(k, e, out, False)

    def cmd_subkeyalias(self, k, e, out):
        return self.alias(k, e, out, True)

    def cmd_sourcecode(self, k, e, out):
        args, end = read_args(self.s, e, 'om')
        name = self.raw(args[1])
        first, last, code = self.ctx.source.excerpt(name, self.raw(args[0]))
        anchor = self.add_anchor('src:' + name, f'lines {first}–{last}', 'source')
        url = self.source_url(first, last)
        title = f'<a href="{url}">tikzpingus.sty, lines {first}–{last}</a>'
        out.append(('b', (f'<a id="{esc(anchor)}"></a>' if anchor else '') + code_block(code, self.ctx, self.slug, title)))
        return end

    def source_url(self, first, last):
        return f'https://github.com/EagleoutIce/tikzpingus/blob/{self.ctx.commit}/tex/tikzpingus.sty#L{first}-L{last}'

    def cmd_implref(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        name = self.raw(args[0])
        first, last, _ = self.ctx.source.excerpt(name)
        text = f'implementation (lines {first}–{last})'
        href = self.ctx.href('src:' + name, self.slug) or self.source_url(first, last)
        out.append(('i', f'<a href="{esc(href)}">{text}</a>'))
        return end

    def cmd_SourceMap(self, k, e, out):
        rows = []
        for name, entry in self.ctx.source.regions.items():
            href = self.ctx.href('src:' + name, self.slug) or self.source_url(entry['start'], entry['end'])
            rows.append(f'<li style="margin-left:{entry["depth"]}em"><a href="{esc(href)}">{esc(name)}</a>'
                        f' <span class="pingu-lines">{entry["start"]}–{entry["end"]}</span></li>')
        out.append(('b', '<ul class="pingu-source-map">' + ''.join(rows) + '</ul>'))
        return e

    def cmd_shortcuts(self, k, e, out):
        args, end = read_args(self.s, e, 'ommm')
        path, name, selection, target = [self.raw(a) for a in args]
        path = path or '/pingu/'
        family = re.search(r'@pingu@([^@]+)@', selection)
        if not family:
            raise ValueError('Unknown shortcut selection ' + selection)
        links = []
        for val in self.ctx.source.selections[family[1]]:
            shortcut = name + ' ' + val
            anchor = self.definition(shortcut, path)
            links.append(f'<kbd id="{esc(anchor)}">{esc(shortcut)}</kbd>')
        out.append(('b', '<p>Shortcuts for ' + self.linked('pk:' + path + name, '<kbd>' + esc(name) + '</kbd>') +
                    ': ' + ', '.join(links) + '. The color is passed to ' +
                    self.linked('pk:' + path + target, '<kbd>' + esc(target) + '</kbd>') + '.</p>'))
        return end

    def cmd_BlockString(self, k, e, out):
        _, end = read_args(self.s, e, 'om')
        return end

    def cmd_ValueAnchor(self, k, e, out):
        args, end = read_args(self.s, e, 'mmm')
        anchor = self.add_anchor(self.raw(args[0]), self.raw(args[2]), 'value')
        out.append(('i', f'<a id="{esc(anchor)}"></a>'))
        return end

    def cmd_lpingu(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        text = self.raw(args[0]).replace('\\\\', '\\')
        out.append(('i', '<kbd>' + esc(text) + '</kbd>'))
        return end

    cmd_ipingu = cmd_ltex = cmd_lpingu
    cmd_cmd = Converter.cmd_cs
    cmd_say = Converter.cmd_enquote
    cmd_mand = Converter.cmd_marg

    def cmd_opt(self, k, e, out):
        args, end = read_args(self.s, e, 'om')
        default = self.inline(args[0])
        out.append(('i', '[<i>' + self.inline(args[1]) + '</i>' + ('=' + default if default else '') + ']'))
        return end

    def cmd_autoref(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        label = self.raw(args[0])
        info = self.ctx.labels.get(label, {})
        text = info.get('text', label)
        if info.get('kind') in ('section', 'subsection', 'subsubsection', 'label'):
            text = 'Section ' + text
        out.append(('i', self.linked(label, esc(text))))
        return end

    def cmd_nameref(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        label = self.raw(args[0])
        out.append(('i', self.linked(label, esc(self.ctx.labels.get(label, {}).get('text', label)))))
        return end

    def cmd_hyperref(self, k, e, out):
        args, end = read_args(self.s, e, 'om')
        out.append(('i', self.linked(self.raw(args[0]), self.inline(args[1]))))
        return end

    def cmd_textcopyright(self, k, e, out):
        out.append(('i', '©'))
        return e

    def cmd_def(self, k, e, out):
        # The manual also defines macros with delimited parameters, for
        # example \\def\\parseRGB#1,#2,#3;{...}.
        name, end = read_cs(self.s, skip_ws(self.s, e))
        brace = self.s.index('{', end)
        params = self.s[end:brace]
        self.user_macros[name] = 'm' * len(re.findall(r'#\d', params))
        return match_brace(self.s, brace) + 1

    cmd_gdef = cmd_edef = cmd_xdef = cmd_def

    def env_multicols(self, k, a, b, after, out):
        if r'\foreach \tx/\s' in self.s[a:b]:
            # This print-only two-column layout consists of captions and small
            # pictures. Keep the native illustration as a single faithful figure.
            image = self.new_image(k, after, 'block')
            out.append(('b', '<div class="figure">' + self.img_html(image) + '</div>'))
            return
        if r'\foreach \col' not in self.s[a:b]:
            _, start = read_args(self.s, a, 'm')
            out.extend(self.items(start, b))
            return
        colors = re.findall(r'\\@pingu@color@\{([^}]+)\}\{RGB\}\(([^)]+)\)', self.ctx.source.code)
        items = []
        for name, rgb in colors:
            anchor = self.add_anchor('pv:pingu@' + name, 'pingu@' + name, 'value')
            items.append(f'<li id="{esc(anchor)}"><span class="pingu-swatch" style="background:rgb({rgb})"></span>'
                         f'<kbd>pingu@{esc(name)}</kbd> <small>RGB {esc(rgb)}</small></li>')
        out.append(('b', '<ul class="pingu-colors">' + ''.join(items) + '</ul>'))

    def cmd_TikZ(self, k, e, out):
        out.append(('i', 'Ti<i>k</i>Z'))
        return e

    def cmd_important(self, k, e, out):
        out.append(('b', '<p><strong>Important:</strong></p>'))
        return e

    def cmd_paragraph(self, k, e, out):
        args, end = read_args(self.s, e, 'm')
        title = self.inline(args[0])
        anchor = 'paragraph-' + slug(self.plain(args[0]))
        out.append(('b', f'<h6 id="{anchor}">{title}<a class="anchor-link" href="#{anchor}">&para;</a></h6>'))
        return end

    def heading(self, k, e, out, level, title=None):
        if self.stem == 'overview':
            args, end = read_args(self.s, e, '*om')
            title = self.inline(args[2])
            name = self.plain(args[2])
            anchor = 'overview-' + slug(name)
            end = skip_ws(self.s, end)
            while (match := re.match(r'\\label\{([^}]*)\}', self.s[end:])):
                text = 'Gadget overview' if name == 'Gadgets' else name + ' overview'
                self.ctx.add_label(match[1], slug=self.slug, anchor=anchor, text=text, kind='overview')
                end = skip_ws(self.s, end + match.end())
            tag = 'h4' if level == 1 else 'h5'
            out.append(('b', f'<{tag} id="{anchor}">{title}<a class="anchor-link" href="#{anchor}">&para;</a></{tag}>'))
            if level == 1:
                self.page.title = self.page.title_html = title
            else:
                self.page.toc.append(('tocsubsection', anchor, title))
            return end
        return super().heading(k, e, out, max(1, level - self.chunk.level + 1), title)

    def command(self, k, b, out):
        name, end = read_cs(self.s, k)
        # Native saveboxes and dimension assignments are needed by later
        # pictures, but have no text of their own in the HTML.
        if name == 'setbox':
            brace = self.s.index('{', end)
            return match_brace(self.s, brace) + 1
        if name == 'the':
            _, stop = read_cs(self.s, skip_ws(self.s, end))
            out.append(('i', self.value(k, self.s[k:stop])))
            return stop
        if name == 'basicfeetbend':
            out.append(('i', self.value(k, self.s[k:end])))
            return end
        if name == '@pingu@none':
            out.append(('i', self.value(k, self.s[k:end])))
            return end
        return super().command(k, b, out)


def convert_all(ctx):
    pages = []
    for chunk in ctx.source.chunks:
        page = Page(chunk.stem, chunk.slug, chunk.part, chunk.number)
        conv = PinguConverter(ctx, chunk, page)
        page.body = conv.render(conv.items(0, len(chunk.text)))
        page.captures = conv.captures
        pages.append(page)
    intro = Chunk('motivation', 'index', 'guide', '', 1, ctx.source.motivation)
    ctx.intro = Page(intro.stem, intro.slug, None, '')
    conv = PinguConverter(ctx, intro, ctx.intro)
    ctx.intro.body = conv.render(conv.items(0, len(intro.text)))
    ctx.intro.captures = conv.captures
    append_child_contents(pages)
    return pages


def append_child_contents(pages):
    """Keep reference introductions useful when their children get own pages."""
    for page in pages:
        if not page.section_number:
            continue
        prefix = page.section_number + '.'
        children = [p for p in pages if p.section_number.startswith(prefix) and
                    p.section_number.count('.') == prefix.count('.')]
        if children:
            links = ''.join(f'<li><a href="{p.slug}">{p.section_number}&ensp;{p.title_html}</a></li>'
                            for p in children)
            page.body += '<div class="part-toc"><ul>' + links + '</ul></div>'


def write_tex(ctx, pages):
    TEXDIR.mkdir(parents=True, exist_ok=True)
    # Give both the package loader and implementation scanner a private copy
    # of the pinned .sty, adapting their original relative paths below.
    native = TEXDIR / 'tex'
    native.mkdir(exist_ok=True)
    shutil.copy(ctx.source.upstream / 'tex/tikzpingus.sty', native)
    for src in [SHARED / 'texhtml/tikzdev-capture.sty', HERE / 'pinguhtml.sty']:
        shutil.copy(src, TEXDIR)
    preamble = ctx.source.preamble.replace('../tex/', 'tex/').replace('../tex/tikzpingus', 'tex/tikzpingus')
    # The HTML renderer supplies highlighting and links, so the PDF capture
    # build needs only standard listings, with no documentation submodule.
    preamble = preamble.replace(r'\usepackage[style=plain,hlnumbers=false]{xlistings/xlistings}',
                                r'\usepackage{listings}\lst@Key{add to literate}{}{}')
    body = instrument(ctx.source.motivation, ctx.intro.captures) + '\n'
    body += '\n'.join(instrument(chunk.text, page.captures) for chunk, page in zip(ctx.source.chunks, pages))
    body = body.replace(r'\the\dimexpr\pagegoal-\pagetotal-2\baselineskip\relax', '9cm')
    source = (r'\def\pinguDocLinks{0}' + '\n' + preamble + '\n' +
              r'\usepackage{pinguhtml}\begin{document}' + '\n' + body + '\n' + r'\end{document}')
    (TEXDIR / (JOB + '.tex')).write_text(source)
    print(f'Wrote {len(pages)} instrumented chapters with {sum(len(p.captures) for p in pages)} captures/values')


def manual(source):
    return Manual(package='tikzpingus', title='TikZpingus Manual',
                  name_html='The <span class="tikzname">TikZ</span>pingus package', parts=source.parts,
                  notice='''TikZpingus documentation: Copyright 2026 Florian Sihler.
Distributed under the LaTeX Project Public License, version 1.3 or later.
HTML adaptations: Copyright 2026 Dominik Peters.''',
                  footer_links=[('CTAN', 'https://ctan.org/pkg/tikzpingus'),
                                ('Official PDF version', 'https://mirrors.ctan.org/graphics/pgf/contrib/tikzpingus/tikzpingus-doc.pdf'),
                                ('Source and license', 'https://github.com/EagleoutIce/tikzpingus')],
                  build_dir=str(BUILD), site_dir=str(SITE), img_dir=IMGDIR,
                  home_title='TikZpingus Manual — Penguins with TikZ')


def home_html(ctx, pages):
    box = ('<div class="manual-title-block home-box pingu-title-block">'
           '<h2 class="manual-title">The <span class="tikzname">TikZ</span>pingus package</h2>'
           f'<div class="manual-version">Version {esc(ctx.source.version)} ({esc(ctx.source.date)}) · Florian Sihler</div>'
           '<p class="manual-html-explanation">Unofficial HTML version by Dominik Peters · '
           '<a href="https://github.com/EagleoutIce/tikzpingus">Package source</a></p></div>')
    groups = []
    for part, title in ctx.source.parts:
        items = [(p.section_number, p.title_html, p.slug) for p in pages if p.part == part]
        groups.append((title, part, '', items))
    return (box + '<!-- pingu-editor --><!-- /pingu-editor -->' + contents(groups) +
            '<h2 class="home-contents-title">Motivation</h2>' + ctx.intro.body + footnotes_html(ctx.intro))


def key_index(ctx):
    page = Page('key-index', 'key-index', 'reference', '')
    page.title = page.title_html = 'Key and command index'
    body = ['<h4 id="key-index">Key and command index</h4><ul class="pingu-key-index" data-nosnippet>']
    names = [(name, label) for name, label in ctx.known_keys.items()]
    names += [('\\' + name, label) for name, label in ctx.known_commands.items()]
    for name, label in sorted(names, key=lambda item: item[0].casefold()):
        body.append(f'<li><a href="{esc(ctx.href(label, page.slug))}"><kbd>{esc(name)}</kbd></a></li>')
    body.append('</ul>')
    page.body = ''.join(body)
    return page


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'html'
    if mode not in ('tex', 'html'):
        sys.exit('Usage: convert.py [tex|html]')
    ctx = Context()
    ctx.mode = mode
    ctx.source = Source()
    ctx.commit = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    ctx.values = {}
    if mode == 'html':
        load_images(ctx, str(BUILD / 'images'))
        for line in (TEXDIR / (JOB + '.htmlvalues')).read_text().splitlines():
            ident, _, value = line.partition(' ')
            ctx.values[ident] = value
    convert_all(ctx)
    ctx.pass_no = 2
    ctx.warnings.clear()
    pages = convert_all(ctx)
    if mode == 'tex':
        write_tex(ctx, pages)
    else:
        expected = {image for p in pages for _, _, image, kind in p.captures if kind != 'raw'}
        missing = expected - ctx.images.keys()
        if missing:
            raise SystemExit('Missing compiled illustrations: ' + ', '.join(sorted(missing)))
        pages.append(key_index(ctx))
        shutil.rmtree(SITE, ignore_errors=True)
        write_site(manual(ctx.source), ctx, pages, home_html)
        subprocess.run([sys.executable, str(HERE / 'editor/build.py'), '--output', str(SITE / 'editor')], check=True)
        print(f'Wrote {len(pages)} chapters to {SITE}')
    for message, count in ctx.warnings.most_common():
        print(f'warning ({count}x): {message}')
    if mode == 'html' and ctx.warnings:
        raise SystemExit('Conversion warnings must be resolved before publishing')


if __name__ == '__main__':
    main()
