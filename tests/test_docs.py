"""
Tests for the docs: links between them resolve, and the iOS example behaves
the way its README says.

    python3 -m unittest discover tests
"""

import re
import subprocess
import unittest

from test_specloop import HERE

DOCS = [HERE / "README.md", *sorted((HERE / "docs").rglob("*.md")), *sorted((HERE / "examples").rglob("README.md"))]
LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?\s*\)")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


class LinkTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for doc in DOCS:
            for target in LINK.findall(CODE.sub("", doc.read_text())):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                path = (doc.parent / target.split("#")[0]).resolve()
                if not path.exists():
                    broken.append(f"{doc.relative_to(HERE)}: {target}")
        self.assertEqual(broken, [])


class ExampleTests(unittest.TestCase):
    def test_ios_example_coverage_is_as_documented(self):
        # examples/ios-swift/README.md: 4/6, and exits 1 because LVL-2 is required but untested.
        out = subprocess.run([str(HERE / "bin/specloop"), "coverage"], cwd=HERE / "examples/ios-swift",
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("4/6 spec IDs have at least one test.", out.stdout)
        self.assertIn("Required but uncovered: LVL-2", out.stdout)


if __name__ == "__main__":
    unittest.main()
