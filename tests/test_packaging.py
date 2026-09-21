"""Distribution contract; no runtime dependencies or assumed license."""
from pathlib import Path
import tomllib
import unittest


class PackagingTests(unittest.TestCase):
    def test_installable_cli_metadata(self):
        path = Path(__file__).resolve().parents[1] / 'pyproject.toml'
        self.assertTrue(path.is_file(), 'Missing package metadata')
        config = tomllib.loads(path.read_text())
        project = config['project']
        self.assertEqual(project['name'], 'things-workbench')
        self.assertEqual(project['requires-python'], '>=3.11')
        self.assertEqual(project.get('dependencies', []), [])
        self.assertEqual(project['scripts']['things-workbench'], 'things_workbench.cli:main')
        self.assertNotIn('license', project)
