"""Distribution contract; no runtime dependencies or assumed license."""
from pathlib import Path
import tomllib
import unittest


class PackagingTests(unittest.TestCase):
    def test_sdist_includes_public_safety_and_support_documents(self):
        path = Path(__file__).resolve().parents[1] / 'MANIFEST.in'
        self.assertTrue(path.is_file(), 'sdist must declare public documentation')
        self.assertIn('recursive-include docs *.md *.json', path.read_text().splitlines())

    def test_original_native_sources_are_package_data(self):
        path = Path(__file__).resolve().parents[1] / 'pyproject.toml'
        config = tomllib.loads(path.read_text())
        patterns = config['tool']['setuptools'].get('package-data', {}).get('things_workbench', [])
        self.assertEqual(set(patterns), {'native/*.m','native/*.h','native/*.swift','native/*.c','native/*.sb','native/*.json'})

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
