import json
from pathlib import Path

import pytest
from conftest import stored_bytes

from workshop import beam, generate, layers

REFERENCE_FILES = (
    "exercises/01-cantilever/reference.json",
    "exercises/02-gmsh-beam/reference.json",
    "exercises/04-cable-section/reference.json",
)


def test_the_renderers_cover_the_reference_files():
    assert set(REFERENCE_FILES) <= set(generate.RENDERERS)
    assert all("\\" not in path and not Path(path).is_absolute() for path in generate.RENDERERS)  # repo-relative POSIX


def test_render_all_renders_every_renderer_to_text_ending_in_one_newline():
    rendered = generate.render_all()
    assert set(rendered) == set(generate.RENDERERS)
    for path, text in rendered.items():
        assert text.endswith("\n") and not text.endswith("\n\n"), path
        assert "\r" not in text, path


def test_the_json_is_the_references_serialised(root):
    rendered = generate.render_all()
    assert rendered[REFERENCE_FILES[0]] == json.dumps(beam.cantilever_reference(), indent=2) + "\n"
    assert rendered[REFERENCE_FILES[1]] == json.dumps(beam.selfweight_reference(), indent=2) + "\n"
    assert rendered[REFERENCE_FILES[2]] == json.dumps(layers.cable_reference(), indent=2) + "\n"
    assert json.loads(rendered[REFERENCE_FILES[0]])["values"] == {"tip_displacement_y": -2.5, "support_reaction_y": 21.0}


def test_generated_files_are_current(root):
    assert generate.stale(root) == []


def test_what_git_stores_for_the_generated_files_is_current(root):
    # the index blob (or, before the first commit, the working-tree bytes), always LF
    for path, text in generate.render_all().items():
        assert stored_bytes(root, path) == text.encode("utf-8"), path


def test_write_all_writes_utf8_with_lf_and_reports_the_paths(tmp_path):
    written = generate.write_all(tmp_path)
    assert sorted(written) == sorted(generate.RENDERERS)
    for path in written:
        data = (tmp_path / path).read_bytes()
        assert b"\r" not in data
        data.decode("utf-8")
        assert data == generate.render_all()[path].encode("utf-8")
    assert generate.stale(tmp_path) == []


def test_stale_reports_a_missing_file(tmp_path):
    assert sorted(generate.stale(tmp_path)) == sorted(generate.RENDERERS)  # nothing written yet


def test_stale_reports_a_changed_file(tmp_path):
    generate.write_all(tmp_path)
    changed = REFERENCE_FILES[1]
    target = tmp_path / changed
    target.write_bytes(target.read_bytes().replace(b"30.8034", b"30.8035"))
    assert generate.stale(tmp_path) == [changed]
    generate.write_all(tmp_path)
    assert generate.stale(tmp_path) == []


def test_stale_reports_crlf(tmp_path):
    generate.write_all(tmp_path)
    target = tmp_path / REFERENCE_FILES[0]
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert generate.stale(tmp_path) == [REFERENCE_FILES[0]]


def test_main_check_exits_1_and_lists_stale_paths(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(generate, "ROOT", tmp_path)
    assert generate.main(["check"]) == 1
    out = capsys.readouterr()
    for path in REFERENCE_FILES:
        assert path in out.out + out.err
    assert generate.main([]) == 0  # write is the default
    capsys.readouterr()
    assert generate.main(["check"]) == 0
    assert generate.stale(tmp_path) == []


def test_main_rejects_an_unknown_command(capsys):
    with pytest.raises(SystemExit) as caught:
        generate.main(["publish"])
    assert caught.value.code == 2
