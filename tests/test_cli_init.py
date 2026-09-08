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
