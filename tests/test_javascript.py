from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = Path(__file__).parent / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_javascript_form_state_tests_pass() -> None:
    """Run the JavaScript unit tests for the form's data handling.

    The browser form is rendered by JavaScript from a widget tree, and every bug
    found while building it lived in the path arithmetic rather than in the DOM code.
    Those tests therefore live with the JavaScript, but they are run from here so
    that one command covers the whole project.
    """
    test_files = sorted(str(path) for path in JS_TESTS.glob("*.test.js"))
    assert test_files, "no JavaScript tests found"
    result = subprocess.run(
        ["node", "--test", *test_files],
        capture_output=True,
        text=True,
        cwd=JS_TESTS.parent,
        check=False,
    )
    assert result.returncode == 0, f"JavaScript tests failed:\n{result.stdout}\n{result.stderr}"
