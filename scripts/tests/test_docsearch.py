"""Verify the search contract shared by the manual frontends."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared'))
from docsearch import add_docsearch
from assets import asset_url
from navbar import home_url, title_menu


def load_function(path, name, namespace):
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class DocSearchTests(unittest.TestCase):
    def check_assets(self, soup):
        scripts = soup.select('script[src="https://cdn.jsdelivr.net/npm/@docsearch/js@3"]')
        self.assertEqual(len(scripts), 1)
        self.assertTrue(scripts[0].has_attr('defer'))
        self.assertIs(scripts[0].parent, soup.head)
        self.assertEqual(len(soup.select('link[href="https://cdn.jsdelivr.net/npm/@docsearch/css@3"]')), 1)
        self.assertEqual(len(soup.select('header #search')), 1)

    def test_pgf_and_pgfplots_headers_use_shared_assets(self):
        for package in ['pgf', 'pgfplots']:
            with self.subTest(package=package):
                namespace = dict(BeautifulSoup=BeautifulSoup, add_docsearch=add_docsearch,
                                 home_url=home_url, title_menu=title_menu,
                                 asset_url=lambda name: asset_url(name, ROOT / 'shared'))
                add_header = load_function(ROOT / package / 'postprocessing.py', 'add_header', namespace)
                soup = BeautifulSoup('<html><head></head><body><div class="bodyandsidetoc"></div></body></html>', 'html5lib')
                add_header(soup)
                self.check_assets(soup)
                soup.head.append(soup.new_tag('link', href='style.css', rel='stylesheet'))
                soup.head.append(soup.new_tag('script', src='pgfmanual.js'))
                version_assets = load_function(ROOT / package / 'postprocessing.py',
                                               'add_version_to_css_js', namespace)
                version_assets(soup)
                self.assertEqual(soup.select_one('script[src^="pgfmanual.js"]')['src'],
                                 asset_url('pgfmanual.js', ROOT / 'shared'))

    def test_converted_manual_shell_uses_shared_assets(self):
        # the page shell of the manuals converted with shared/texhtml (tcolorbox, ...)
        from texhtml.site import Manual, page_shell
        manual = Manual(package='tcolorbox', title='tcolorbox Manual', name_html='tcolorbox',
                        parts=[], notice='notice', footer_links=[], build_dir='', site_dir='',
                        img_dir='images')
        result = page_shell(manual, [], None, 'Manual', '<p>Content</p>', [], is_home=True)
        soup = BeautifulSoup(result, 'html5lib')
        self.check_assets(soup)
        button = soup.find(id='hamburger-button')
        self.assertEqual(button.name, 'button')
        self.assertEqual(button['type'], 'button')
        self.assertEqual(button['aria-controls'], 'chapter-toc-container')
        self.assertEqual(button['aria-expanded'], 'false')

    def test_references_are_in_the_converted_manual_navigation(self):
        from texhtml.core import Page
        from texhtml.site import Manual, page_shell
        manual = Manual(package='tcolorbox', title='tcolorbox Manual', name_html='tcolorbox',
                        parts=[], notice='notice', footer_links=[], build_dir='', site_dir='',
                        img_dir='images', has_references=True)
        for slug in ['introduction', 'references']:
            with self.subTest(slug=slug):
                page = Page(slug, slug, None, '')
                result = page_shell(manual, [], page, slug, '', [])
                soup = BeautifulSoup(result, 'html5lib')
                link = soup.select_one('#chapter-toc-container a[href="references"]')
                self.assertIsNotNone(link)
                self.assertEqual('current' in link.parent.get('class', []), slug == 'references')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required to test browser configuration')
    def test_each_manual_searches_its_package_or_all_and_handles_missing_cdn(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const cases = [];
for (const packageName of ['pgf', 'pgfplots', 'tcolorbox', 'tikz-cd', 'pgf-pie', 'tikz-feynman', 'wheelchart', 'pgfgantt', 'tkz-euclide', 'chemfig', 'forest', 'nicematrix', 'tikzpingus', 'unknown']) {
  const calls = [];
  const sandbox = {
    document: {
      documentElement: {classList: ['pkg-' + packageName, 'pkg-pgf-contrib']},
      getElementById: () => ({}),
      addEventListener: () => {},
    },
    window: {docsearch: options => calls.push(options), addEventListener: () => {}},
  };
  vm.runInNewContext(source + '\ninitDocSearch();', sandbox);
  // The requests sent for this manual alone and for all manuals.
  const sent = {};
  if (calls.length) {
    const client = {search: (query) => {
      sent[sandbox.scope] = query.requests;
      return Promise.resolve({results: query.requests.map(() => ({hits: [], nbHits: 0}))});
    }};
    const search = calls[0].transformSearchClient(client).search;
    for (const scope of ['package', 'all']) {
      sandbox.scope = scope;
      vm.runInNewContext('searchScope = scope;', sandbox);
      search({requests: [{indexName: 'tikz', query: 'x'}]});
    }
  }
  // An unavailable CDN must not break navigation or the rest of the page.
  delete sandbox.window.docsearch;
  vm.runInNewContext('initDocSearch();', sandbox);
  cases.push({packageName, calls, sent});
}
process.stdout.write(JSON.stringify(cases));
'''
        result = subprocess.run(['node', '-e', script, str(ROOT / 'shared/pgfmanual.js')],
                                capture_output=True, text=True, check=True)
        for case in json.loads(result.stdout):
            package = case['packageName']
            if package == 'unknown':
                self.assertEqual(case['calls'], [])
                continue
            with self.subTest(package=package):
                self.assertEqual(len(case['calls']), 1)
                options = case['calls'][0]
                tag = 'tikz' if package == 'pgf' else package
                self.assertEqual([r['filters'] for r in case['sent']['package']], ['tags:' + tag])
                # All manuals use one unfiltered query, bounded to ten groups.
                self.assertEqual(len(case['sent']['all']), 1)
                self.assertNotIn('filters', case['sent']['all'][0])
                for scope in ['package', 'all']:
                    request = case['sent'][scope][0]
                    self.assertEqual((request['distinct'], request['hitsPerPage']), (2, 10))
                    self.assertIn('manual', request['attributesToRetrieve'])
                self.assertEqual((options['appId'], options['indexName'], options['container']),
                                 ('JS6V5VZSDB', 'tikz', '#search'))

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required to test browser configuration')
    def test_global_search_preserves_ranking_cached_hits_and_scope(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const sandbox = {
  document: {documentElement: {classList: ['pkg-pgfplots']}, addEventListener: () => {}},
  window: {addEventListener: () => {}}, URL,
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
(async () => {
  const hits = [
    {url: 'https://tikz.dev/tcolorbox/option-keys', manual: 'tcolorbox',
     hierarchy: {lvl0: 'Core'}, _highlightResult: {hierarchy: {lvl0: {value: '<mark>Core</mark>'}}}},
    {url: 'https://tikz.dev/pgfplots/reference-markers', hierarchy: {lvl0: 'Reference'}},
    {url: 'https://tikz.dev/tikz-shapes', hierarchy: {lvl0: 'TikZ'}},
  ];
  const cached = {results: [{hits, nbHits: 30, nbPages: 3, queryID: 'original'}]};
  const sent = [];
  sandbox.client = {search: query => {sent.push(query); return Promise.resolve(cached);}};
  sandbox.query = {requests: [{indexName: 'tikz', query: 'node', attributesToRetrieve: ['url', 'hierarchy']}]};
  vm.runInNewContext('searchScope = "all";', sandbox);
  const pending = vm.runInNewContext('scopedSearch(client, query)', sandbox);
  vm.runInNewContext('searchScope = "package";', sandbox);
  const result = await pending;
  assert.equal(sent[0].requests.length, 1);
  assert.equal(result.results[0].nbHits, 30);
  assert.equal(result.results[0].queryID, 'original');
  assert.deepEqual(Array.from(result.results[0].hits, hit => hit.hierarchy.lvl0),
    ['tcolorbox › Core', 'PGFplots › Reference', 'PGF/TikZ › TikZ']);
  assert.equal(result.results[0].hits[0]._highlightResult.hierarchy.lvl0.value, 'tcolorbox › <mark>Core</mark>');
  assert.equal(hits[0].hierarchy.lvl0, 'Core');
  assert.equal(hits[0]._highlightResult.hierarchy.lvl0.value, '<mark>Core</mark>');
  assert.equal(sandbox.query.requests[0].attributesToRetrieve.length, 2);
  assert.ok(!('filters' in sandbox.query.requests[0]));
  sandbox.query.requests[0].filters = 'lang:en-US';
  assert.equal(await vm.runInNewContext('scopedSearch(client, query)', sandbox), cached);
  assert.equal(sent[1].requests[0].filters, '(lang:en-US) AND tags:pgfplots');
  vm.runInNewContext('searchScope = "all";', sandbox);
  await vm.runInNewContext('scopedSearch(client, query)', sandbox);
  assert.equal(sent[2].requests[0].filters, 'lang:en-US');
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
        subprocess.run(['node', '-e', script, str(ROOT / 'shared/pgfmanual.js')], check=True)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required to test symbol searches')
    def test_symbol_queries_use_exact_filters_and_preserve_scope(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const sent = [];
const sandbox = {
  document: {documentElement: {classList: ['pkg-pgf']}, addEventListener: () => {}},
  window: {addEventListener: () => {}}, URL,
  client: {search: query => {sent.push(query); return Promise.resolve({results: [{hits: []}]});}},
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
for (const [query, token] of [['--', '2d_2d'], ['-|', '2d_7c'], ['|-', '7c_2d'],
  ['++', '2b_2b'], ['..', '2e_2e'], ['<->', '3c_2d_3e'], [':', '3a'],
  ['\\', '5c'], ['"', '22'], ['∥', '2225'], ['§§', 'a7_a7'], [' -- ', '2d_2d']]) {
  sandbox.request = {query, filters: 'lang:en-US', facetFilters: [['type:lvl4', 'type:content']], optionalFilters: 'tags:tikz'};
  vm.runInNewContext('searchScope = "package"; scopedSearch(client, {requests: [request]});', sandbox);
  const batch = sent.at(-1);
  assert.equal(batch.requests.length, 1);
  const actual = batch.requests[0];
  assert.equal(actual.query, '');
  assert.equal(actual.filters, '(lang:en-US) AND tags:tikz');
  assert.equal(actual.facetFilters[1], 'symbol_tokens:' + token);
  assert.equal(actual.facetFilters[0], sandbox.request.facetFilters[0]);
  assert.equal(actual.optionalFilters[0], 'tags:tikz');
  assert.equal(actual.optionalFilters[1], 'defined_symbol_tokens:' + token);
  assert.equal(actual.distinct, 2);
  assert.equal(sandbox.request.query, query);
  assert.equal(sandbox.request.facetFilters.length, 1);
  vm.runInNewContext('searchScope = "all"; scopedSearch(client, {requests: [request]});', sandbox);
  assert.equal(sent.at(-1).requests[0].filters, 'lang:en-US');
}
for (const query of ['node', 'line-to', '\\draw', 'a+b', '-- line', '"exact phrase"', '', '   ']) {
  sandbox.request = {query};
  vm.runInNewContext('scopedSearch(client, {requests: [request]});', sandbox);
  const actual = sent.at(-1).requests[0];
  assert.equal(actual.query, query);
  assert.ok(!('facetFilters' in actual));
  assert.ok(!('optionalFilters' in actual));
}
'''
        subprocess.run(['node', '-e', script, str(ROOT / 'shared/pgfmanual.js')], check=True)


if __name__ == '__main__':
    unittest.main()
