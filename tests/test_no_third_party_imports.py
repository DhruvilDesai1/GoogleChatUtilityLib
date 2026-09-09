"""Guard the project's defining constraint: zero runtime dependencies.

`chatnotify` is embedded in other people's repositories, so a third-party runtime
import could collide with whatever version that project already pins. That is the
exact failure the retired Java library suffered by depending on RestAssured, and
avoiding it is why this rewrite is stdlib-only.

`pyproject.toml` declares `dependencies = []`, but nothing stops someone adding an
import that happens to be installed in their own environment and only fails for a
consumer. This test checks the source itself.
"""

import ast
import pathlib
import sys

import pytest

SOURCE_DIR = pathlib.Path(__file__).resolve().parent.parent / "src" / "chatnotify"


def _imported_top_level_modules(path):
    """Every top-level module name imported by `path`, ignoring relative imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # `from . import x` - in-package, always fine
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_source_files_were_found():
    """Guard the guard: a wrong path would make the real test vacuously pass."""
    modules = list(SOURCE_DIR.glob("*.py"))
    assert len(modules) >= 9, "expected the package modules at %s, found %d" % (
        SOURCE_DIR,
        len(modules),
    )


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="sys.stdlib_module_names is 3.10+; the 3.10-3.13 CI cells enforce this",
)
def test_no_third_party_runtime_imports():
    offenders = []
    for path in sorted(SOURCE_DIR.glob("*.py")):
        for module in sorted(_imported_top_level_modules(path)):
            if module not in sys.stdlib_module_names:
                offenders.append("%s imports %r" % (path.name, module))
    assert not offenders, (
        "chatnotify must import only the standard library at runtime, but found:\n  "
        + "\n  ".join(offenders)
    )
