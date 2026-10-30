"""
Tests for installing and updating specloop: the package, the thin files a
project keeps (shims, hook scripts, skill stubs, the CLAUDE.md block), the
minimum version, and `specloop update`.

    python3 -m unittest discover tests
"""

import subprocess
import sys

from test_specloop import HERE, Repo, SpecloopTestCase

sys.path.insert(0, str(HERE / "src"))

DATA = HERE / "src" / "specloop" / "data"


class VersionTests(SpecloopTestCase):
    def test_version(self):
        out = subprocess.run([str(HERE / "bin" / "specloop"), "--version"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "specloop 0.1.0")

    def test_package_data_present(self):
        for rel in ("skills/spec-sync/SKILL.md", "specloop-trigger", "claude-block.md", "templates/specloop.json"):
            self.assertTrue((DATA / rel).is_file(), rel)
