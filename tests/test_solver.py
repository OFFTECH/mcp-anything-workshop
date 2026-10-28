"""The instructor's run: every exercise deck through the real CalculiX and Gmsh, against the references.

Selected only with `-m solver` (pyproject.toml deselects it), inside the workshop dev container:

    uv run pytest -m solver        (or scripts/verify_decks.sh, which prints the whole table)

On a machine without ccx and gmsh this test FAILS: it is selected on purpose, and a missing solver must not pass.
"""

import pytest

from workshop import verify


@pytest.mark.solver
def test_every_deck_verifies():
    assert verify.main([]) == 0
