"""Synthetic CLI isolation: help must never build or discover a database."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import unittest
from things_workbench.cli import main

class CopyCLITests(unittest.TestCase):
    def test_copy_commands_have_explicit_help(self):
        for args in (['copies','--help'],['wording','--help'],['native','--help']):
            out=StringIO(); err=StringIO()
            with redirect_stdout(out),redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught: main(args)
            self.assertEqual(caught.exception.code,0,err.getvalue())
            self.assertIn('copy',out.getvalue().lower())
