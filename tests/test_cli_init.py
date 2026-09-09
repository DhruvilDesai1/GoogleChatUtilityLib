import os

from chatnotify import cli


def test_init_writes_config_with_directory_name(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "payments-api"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    assert cli.main(["init"]) == 0
    content = (project_dir / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "[chatnotify]" in content
    assert "project = payments-api" in content
    assert "CHATNOTIFY_WEBHOOK_URL" in capsys.readouterr().out


def test_init_never_writes_a_webhook_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    content = (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "https://" not in content


def test_init_creates_gitignore_with_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_appends_dotenv_to_existing_gitignore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("target/\n", encoding="utf-8")
    cli.main(["init"])
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "target/" in content
    assert ".env" in content


def test_init_does_not_duplicate_dotenv_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    cli.main(["init"])
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content.count(".env") == 1


def test_init_refuses_to_overwrite_existing_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".chatnotify.ini").write_text("[chatnotify]\nproject = Keep Me\n", encoding="utf-8")
    assert cli.main(["init"]) == 1
    assert "Keep Me" in (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "already exists" in capsys.readouterr().err


def test_init_honours_project_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["init"])
    os.remove(str(tmp_path / ".chatnotify.ini"))
    parser = cli.build_parser()
    args = parser.parse_args(["init"])
    args.project = "Explicit Name"
    cli.init_command(args)
    content = (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "project = Explicit Name" in content


def test_init_warns_instead_of_lying_when_gitignore_update_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_ensure_gitignored", lambda path, entry: False)
    assert cli.main(["init"]) == 0
    captured = capsys.readouterr()
    assert "Added .env to .gitignore" not in captured.out
    assert "could not update .gitignore" in captured.err


# --- Fix 2: a mention is not an ignore rule ---


def _gitignore_pattern_lines(path):
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]


def test_ensure_gitignored_does_not_count_a_comment_as_a_match(tmp_path):
    target = str(tmp_path / ".gitignore")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("# remember to never commit .env\n")
    assert cli._ensure_gitignored(target, ".env") is True
    assert ".env" in _gitignore_pattern_lines(target)


def test_ensure_gitignored_does_not_count_a_negation_as_a_match(tmp_path):
    """`.env` followed by `!.env` leaves .env tracked - git's last match wins."""
    target = str(tmp_path / ".gitignore")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(".env\n!.env\n")
    assert cli._ensure_gitignored(target, ".env") is True
    assert _gitignore_pattern_lines(target)[-1] == ".env"


def test_ensure_gitignored_appends_after_a_leading_negation(tmp_path):
    target = str(tmp_path / ".gitignore")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("!.env\n")
    assert cli._ensure_gitignored(target, ".env") is True
    assert _gitignore_pattern_lines(target)[-1] == ".env"


def test_ensure_gitignored_treats_an_existing_pattern_line_as_present(tmp_path):
    target = str(tmp_path / ".gitignore")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("build/\n.env\ndist/\n")
    assert cli._ensure_gitignored(target, ".env") is True
    assert _gitignore_pattern_lines(target).count(".env") == 1


def test_ensure_gitignored_appends_to_a_file_without_the_entry(tmp_path):
    target = str(tmp_path / ".gitignore")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("build/\n")
    assert cli._ensure_gitignored(target, ".env") is True
    assert _gitignore_pattern_lines(target) == ["build/", ".env"]


def test_init_really_ignores_dotenv_when_gitignore_only_mentions_it(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(
        "# remember to never commit .env\n", encoding="utf-8"
    )
    assert cli.main(["init"]) == 0
    assert "Added .env to .gitignore" in capsys.readouterr().out
    assert ".env" in _gitignore_pattern_lines(str(tmp_path / ".gitignore"))


# --- Fix 5: init accepts the shared --project flag ---


def test_init_accepts_project_flag_on_the_command_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init", "--project", "My Thing"]) == 0
    content = (tmp_path / ".chatnotify.ini").read_text(encoding="utf-8")
    assert "project = My Thing" in content


# --- Fix 8: an unwritable directory gets a message, not a traceback ---


def test_init_reports_a_write_failure_instead_of_crashing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    real_open = open
    target = os.path.join(os.getcwd(), ".chatnotify.ini")

    def fake_open(path, *args, **kwargs):
        if os.path.abspath(str(path)) == os.path.abspath(target):
            raise PermissionError(13, "Permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    assert cli.main(["init"]) != 0
    monkeypatch.undo()
    captured = capsys.readouterr()
    assert "could not" in captured.err.lower()
    assert not os.path.exists(target)


def test_ensure_gitignored_reports_success(tmp_path):
    target = str(tmp_path / ".gitignore")
    assert cli._ensure_gitignored(target, ".env") is True
    assert cli._ensure_gitignored(target, ".env") is True
    with open(target, encoding="utf-8") as handle:
        assert handle.read().split().count(".env") == 1
