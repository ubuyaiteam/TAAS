"""Guards against a library being used in the code but missing from requirements.txt."""

import ast  # read Python files without running them
import sys  # list of built-in module names
import unittest  # test tools
from pathlib import Path  # file paths

ROOT = Path(__file__).resolve().parent.parent  # the project folder
LOCAL = {"taas", "tests", "phase1_check", "phase23_check", "run_taas", "release", "make_icon"}  # our own modules
PACKAGE_OF = {"bs4": "beautifulsoup4", "dotenv": "python-dotenv", "PIL": "pillow"}  # import name -> package name


# Names of the libraries listed in requirements.txt
def required_packages():
    names = set()
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.add(line.split(">")[0].split("=")[0].split("<")[0].strip().lower())
    return names


# Tests that every outside library the code imports is in requirements.txt
class RequirementsTests(unittest.TestCase):
    def test_every_imported_library_is_listed(self):
        listed = required_packages()
        missing = {}
        for path in list(ROOT.glob("*.py")) + list(ROOT.glob("taas/**/*.py")) + list(ROOT.glob("tests/*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in sys.stdlib_module_names or name in LOCAL:
                        continue
                    if PACKAGE_OF.get(name, name).lower() not in listed:
                        missing.setdefault(name, path.name)
        self.assertEqual(missing, {}, "Add these libraries to requirements.txt")


if __name__ == "__main__":
    unittest.main()
