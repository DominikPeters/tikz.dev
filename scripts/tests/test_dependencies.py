"""A shared module rebuilds only the manuals that use it."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from dependencies import affected, packages

CONVERTED = {'chemfig', 'forest', 'nicematrix', 'tcolorbox', 'tkz-euclide', 'tikzpingus'}
CONTRIBUTED = {'pgf-pie', 'pgfgantt', 'tikz-cd', 'tikz-feynman', 'wheelchart'}


class DependencyTests(unittest.TestCase):
    def test_shared_modules(self):
        self.assertEqual(set(affected(['shared/texhtml/core.py'])), CONVERTED)
        self.assertEqual(set(affected(['shared/pgf_contrib_site.py'])), CONTRIBUTED)
        self.assertEqual(set(affected(['shared/home.py'])), CONVERTED | CONTRIBUTED)
        self.assertEqual(affected(['shared/navbar.py']), packages())

    def test_other_files(self):
        self.assertEqual(affected(['shared/style.css']), packages())
        self.assertEqual(affected(['scripts/prepare.py']), packages())
        self.assertEqual(affected(['wheelchart/preprocess.py', 'docs/building.md']), ['wheelchart'])
        self.assertEqual(affected(['README.md']), [])


if __name__ == '__main__':
    unittest.main()
