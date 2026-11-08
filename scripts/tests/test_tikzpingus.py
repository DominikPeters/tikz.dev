"""TikZpingus definitions, generated examples, and pinned implementation excerpts."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pingu_converter', ROOT / 'tikzpingus/convert.py')
pingu = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pingu
spec.loader.exec_module(pingu)


class TikZpingusTests(unittest.TestCase):
    def test_home_places_the_editor_between_compact_title_and_contents(self):
        ctx = SimpleNamespace(source=SimpleNamespace(parts=[], version='1.4', date='2026/02/27'),
                              intro=pingu.Page('motivation', 'index', None, ''))
        html = pingu.home_html(ctx, [])
        self.assertLess(html.index('pingu-title-block'), html.index('<!-- pingu-editor -->'))
        self.assertLess(html.index('<!-- /pingu-editor -->'), html.index('home-contents-title'))
        self.assertIn('Florian Sihler', html)
        self.assertIn('Dominik Peters', html)
        self.assertNotIn('home-showcase', html)
        self.assertNotIn('home-abstract', html)

    def test_editor_install_updates_only_its_home_page_sections(self):
        spec = importlib.util.spec_from_file_location('pingu_editor_build', ROOT / 'tikzpingus/editor/build.py')
        editor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(editor)
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'index.html'
            home.write_text('<html><head><title>Manual</title></head><body>Title'
                            '<!-- pingu-editor --><!-- /pingu-editor -->Contents</body></html>')
            editor.install(home, '<section id="pingu-editor">First</section>', 'first.css', 'first.js')
            editor.install(home, '<section id="pingu-editor">Updated</section>', 'next.css', 'next.js')
            soup = BeautifulSoup(home.read_text(), 'html.parser')
            self.assertEqual(len(soup.select('#pingu-editor')), 1)
            self.assertEqual(soup.select_one('#pingu-editor').text, 'Updated')
            self.assertEqual(soup.head.script['src'], 'editor/next.js')
            self.assertEqual(soup.head.link['href'], 'editor/next.css')
            self.assertNotIn('first.js', str(soup))
            self.assertTrue(soup.body.text.startswith('Title'))
            self.assertTrue(soup.body.text.endswith('Contents'))

    def test_editor_documentation_uses_real_key_index_targets(self):
        spec = importlib.util.spec_from_file_location('pingu_editor_build', ROOT / 'tikzpingus/editor/build.py')
        editor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(editor)
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            names = ['body type', 'eyes', 'left wing', 'right wing', 'bill', 'feet', 'hairstyle', 'cape', '\\pingu']
            (site / 'key-index.html').write_text(''.join(
                f'<a href="reference#entry-{i}"><kbd>{name}</kbd></a>' for i, name in enumerate(names)))
            (site / 'reference.html').write_text(''.join(f'<div id="entry-{i}"></div>' for i in range(len(names))))
            for page in ['overview', 'ref-glasses', 'ref-extras', 'clothes', 'usage-colors']:
                (site / (page + '.html')).write_text('<h1>Reference</h1>')
            catalog = {key: [] for key in ['bodies', 'eyes', 'wings', 'bills', 'feet', 'colors',
                                           'headwear', 'eyewear', 'neckwear', 'belly', 'items']}
            catalog['clothing'] = [{'tex': 'cape'}]
            docs = editor.documentation(site, catalog)
            self.assertEqual(docs['keys']['cape'], 'reference#entry-7')
            self.assertEqual(docs['keys']['\\pingu'], 'reference#entry-8')
            self.assertEqual(docs['groups']['clothing'], 'clothes')
            (site / 'reference.html').write_text('')
            with self.assertRaisesRegex(ValueError, 'Missing editor documentation target'):
                editor.documentation(site, catalog)

    def convert(self, text, values=None):
        ctx = pingu.Context()
        ctx.values = values or {}
        ctx.commit = 'a' * 40
        ctx.source = SimpleNamespace(selections={'leftwing': ['none', 'normal', 'wave']})
        chunk = pingu.Chunk('c1', 'example', 'guide', '1', 1, text)
        for n in (1, 2):
            ctx.pass_no = n
            page = pingu.Page(chunk.stem, chunk.slug, chunk.part, chunk.number)
            converter = pingu.PinguConverter(ctx, chunk, page)
            result = converter.render(converter.items(0, len(text)))
        return ctx, converter, BeautifulSoup(result, 'html5lib')

    def test_compact_subkey_keeps_executable_source_and_captures_output(self):
        ctx, converter, soup = self.convert(r'\subkeyline[eyes wink]{cup}{cup straw=blue}{color}{red}')
        self.assertIn('cup straw', ctx.known_keys)
        self.assertEqual(soup.select_one('.hl-default').get_text(), '(default: red)')
        self.assertIn('Requires cup.', soup.get_text())
        self.assertIn(r'\pingu[cup, eyes wink, cup straw=blue]', soup.select_one('.example-code').get_text())
        tex = pingu.instrument(converter.s, converter.captures)
        self.assertIn(r'\HTMLnext{c1-1}', tex)
        self.assertIn(r'\HTMLkeyvalue{c1-value-1}{cup}{cup straw}{red}', tex)
        self.assertTrue(tex.endswith(converter.s))

    def test_mixed_entry_syntax_preserves_nested_examples_and_command_arguments(self):
        text = r'''\keyexplain{cup}{color}{blue}
An extra.
\begin{tcblisting}{title={A cup},phantomlabel=cup-example}
\begin{tikzpicture}\pingu[cup]\end{tikzpicture}
\end{tcblisting}
\endkeyexplain
\begin{commandexplain}{pingu}{\opt{keys}}Draw a penguin.\end{commandexplain}
\cmdref{pingu}\keyref{cup}\nameref{cup-example}'''
        ctx, _, soup = self.convert(text)
        self.assertEqual(len(soup.select('.manualentry')), 2)
        self.assertEqual(len(soup.select('.example')), 1)
        self.assertIn('[keys]', soup.select('.entryheadline')[1].get_text())
        self.assertIn('pingu', ctx.known_commands)
        self.assertEqual(soup.find('a', string='A cup')['href'], '#cup-example')
        self.assertFalse(ctx.warnings)

    def test_aliases_and_shortcuts_have_distinct_searchable_targets(self):
        ctx, _, soup = self.convert(r'''\keyexplain{wings}{type}{}Both wings.\endkeyexplain
\keyalias{wing style}{wings}
\shortcuts{wings}{\@pingu@leftwing@}{wings}
\keyref{wings wave}''')
        self.assertEqual(len(soup.select('[id]')), len({node['id'] for node in soup.select('[id]')}))
        self.assertIn('wings wave', ctx.known_keys)
        self.assertEqual(soup.find_all('a')[-1]['href'], '#pk:/pingu/wings:wave')
        self.assertFalse(ctx.warnings)

    def test_inline_code_keeps_backslashes_and_metavariables(self):
        _, _, soup = self.convert(r'\lpingu{\\pingu@color@<name>}')
        self.assertEqual(soup.kbd.get_text(), r'\pingu@color@<name>')

    def test_code_defaults_keep_braces_and_link_inherited_colors(self):
        _, _, soup = self.convert(r'''\keyexplain{cup}{color}{}A cup.\endkeyexplain
\subkeyline{cup}{cup straw=blue}{code}{}''',
            {'c1-value-1': '', 'c1-value-2': r'{<pingu@block>{<@col>} \draw;}'})
        default = soup.select_one('.hl-default')
        self.assertEqual(default.get_text(), r'(default: {\pingu@block{⟨cup⟩} \draw;})')
        self.assertEqual(default.a['href'], '#pk:/pingu/cup')

    def test_html_requires_every_computed_default(self):
        ctx, converter, _ = self.convert('Text.')
        ctx.mode = 'html'
        with self.assertRaisesRegex(ValueError, 'Missing computed TeX value'):
            converter.value(0, 'red', 'cup')

    def test_visual_overview_references_have_names_without_partial_numbers(self):
        ctx = pingu.Context()
        chunk = pingu.Chunk('overview', 'overview', 'guide', '', 1,
                            r'\section{Visual overviews}\subsection{Gadgets}\label{Gadget-Overview}')
        page = pingu.Page(chunk.stem, chunk.slug, chunk.part, chunk.number)
        converter = pingu.PinguConverter(ctx, chunk, page)
        result = converter.render(converter.items(0, len(chunk.text)))
        self.assertEqual(ctx.labels['Gadget-Overview']['text'], 'Gadget overview')
        self.assertEqual(ctx.href('Gadget-Overview', 'usage'), 'overview#overview-gadgets')
        self.assertNotIn('sectionnumber', result)

    def test_chapter_groups_preserve_tex_scopes_without_changing_examples(self):
        text = r'''{\def\i{\textbackslash i}
\begin{tcblisting}{}
\section{An example heading} { unbalanced sample
\end{tcblisting}'''
        result = pingu.chapter_groups(text)
        self.assertTrue(result.startswith(r'\begingroup \def\i'))
        self.assertIn('{ unbalanced sample', result)
        self.assertEqual(pingu.chapter_groups('text }'), r'text \endgroup ')

    def test_implementation_chunks_resolve_relative_line_ranges(self):
        source = pingu.Source.__new__(pingu.Source)
        source.lines = ['% #region helpers', '% <draw>', 'line one', 'line two', 'line three',
                        '% <@draw>', '% #endregion']
        source.regions = source.read_regions()
        self.assertEqual(source.excerpt('draw'), (3, 5, 'line one\nline two\nline three'))
        self.assertEqual(source.excerpt('draw', 'from=2,to=3'), (4, 5, 'line two\nline three'))

    def test_color_defaults_link_to_keys_including_both_wings(self):
        source = pingu.Source.__new__(pingu.Source)
        source.code = r'''  cup straw/.code = \pingu@color{cup@straw}{#1},
  flag \@lr\space pole/.code = \pingu@color{flag\@lr @pole}{#1},'''
        colors = source.read_colorkeys()
        self.assertEqual(colors['pingu@color@cup@straw'], 'cup straw')
        self.assertEqual(colors['pingu@color@flagleft@pole'], 'flag left pole')
        self.assertEqual(colors['pingu@color@flagright@pole'], 'flag right pole')

    def test_reference_introductions_link_to_their_direct_child_pages(self):
        pages = [pingu.Page('intro', 'ref-extras', 'extras', 'A.3'),
                 pingu.Page('heart', 'ref-heart', 'extras', 'A.3.1'),
                 pingu.Page('tie', 'ref-tie', 'extras', 'A.3.2'),
                 pingu.Page('nested', 'ref-detail', 'extras', 'A.3.2.1')]
        pingu.append_child_contents(pages)
        soup = BeautifulSoup(pages[0].body, 'html5lib')
        self.assertEqual([a['href'] for a in soup.select('a')], ['ref-heart', 'ref-tie'])

    def test_heading_in_example_does_not_split_the_manual(self):
        source = pingu.Source.__new__(pingu.Source)
        source.overview = lambda: r'\section{Overview}'
        source.text = r'''\section{Introduction}Intro.
\begin{tcblisting}{}\section{A sample section}\end{tcblisting}
\section{Usage}Usage.
\subsection{A real subsection}Details.
\lstset{breakatwhitespace}'''
        chapters = source.read_chunks()
        self.assertEqual([c.slug for c in chapters], ['overview', 'introduction', 'usage', 'usage-a-real-subsection'])
        self.assertEqual(chapters[-1].number, '2.1')

    def test_guide_extras_and_wing_items_do_not_overwrite_reference_landing_pages(self):
        source = pingu.Source.__new__(pingu.Source)
        source.overview = lambda: r'\section{Overview}'
        source.text = r'''\section{Introduction}Intro.
\section{Usage}Usage.
\subsection{Extras}An example.
\subsection{Wing-Items}Another example.
\lstset{breakatwhitespace}'''
        chapters = source.read_chunks()
        self.assertEqual([c.slug for c in chapters[-2:]], ['usage-extras', 'usage-wing-items'])


if __name__ == '__main__':
    unittest.main()
