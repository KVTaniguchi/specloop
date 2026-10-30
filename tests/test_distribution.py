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

from specloop import project  # noqa: E402

DATA = HERE / "src" / "specloop" / "data"


class VersionTests(SpecloopTestCase):
    def test_version(self):
        out = subprocess.run([str(HERE / "bin" / "specloop"), "--version"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "specloop 0.1.0")

    def test_package_data_present(self):
        for rel in ("skills/spec-sync/SKILL.md", "specloop-trigger", "claude-block.md", "templates/specloop.json"):
            self.assertTrue((DATA / rel).is_file(), rel)


class SkillTests(SpecloopTestCase):
    def test_skill_prints_versioned_text(self):
        out = self.repo().run("skill", "spec-sync")
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.startswith("<!-- specloop 0.1.0 -->\n"))
        self.assertIn("# Spec sync", out.stdout)

    def test_unknown_skill(self):
        self.assertEqual(self.repo().run("skill", "nope").returncode, 2)

    def test_stub_keeps_frontmatter_and_defers(self):
        stub = project.render_stub("spec-sync")
        full = (DATA / "skills" / "spec-sync" / "SKILL.md").read_text()
        self.assertTrue(stub.startswith(project.frontmatter(full)))
        self.assertIn("tools/specloop skill spec-sync", stub)
        self.assertIn(project.STUB_MARKER, stub)
