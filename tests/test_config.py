import os

import pytest

from chatnotify import config


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


@pytest.fixture
def repo(tmp_path):
    return str(tmp_path)


def test_default_project_when_nothing_configured(repo):
    result = config.load(cwd=repo, env={})
    assert result.project == config.DEFAULT_PROJECT
    assert result.provenance["project"] == "default"


def test_flag_beats_every_other_layer(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    write(os.path.join(repo, ".env"), "CHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(
        flags={"project": "FromFlag"},
        cwd=repo,
        env={"CHATNOTIFY_PROJECT": "FromEnv"},
    )
    assert result.project == "FromFlag"
    assert result.provenance["project"] == "flag"


def test_env_beats_dotenv_and_ini(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    write(os.path.join(repo, ".env"), "CHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_PROJECT": "FromEnv"})
    assert result.project == "FromEnv"
    assert result.provenance["project"] == "env: CHATNOTIFY_PROJECT"


def test_dotenv_beats_ini(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    write(os.path.join(repo, ".env"), "CHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(cwd=repo, env={})
    assert result.project == "FromDotenv"
    assert result.provenance["project"] == ".env"


def test_repo_ini_is_used_when_no_higher_layer(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = FromIni\n")
    result = config.load(cwd=repo, env={})
    assert result.project == "FromIni"
    assert result.provenance["project"] == ".chatnotify.ini"


def test_dotenv_handles_quotes_comments_and_blanks(repo):
    write(
        os.path.join(repo, ".env"),
        '# a comment\n\nCHATNOTIFY_PROJECT="Quoted Name"\nCHATNOTIFY_ENV=\'staging\'\n',
    )
    result = config.load(cwd=repo, env={})
    assert result.project == "Quoted Name"
    assert result.environment == "staging"


def test_values_are_trimmed(repo):
    result = config.load(cwd=repo, env={"CHATNOTIFY_PROJECT": "  Padded  "})
    assert result.project == "Padded"


def test_legacy_java_env_names_still_work(repo):
    result = config.load(
        cwd=repo,
        env={
            "PROJECT_NAME": "Legacy App",
            "GOOGLE_CHAT_WEBHOOK_URL": "https://chat.example/legacy",
            "ENVIRONMENT": "beta",
            "MESSAGE_TYPE": "TEXT",
        },
    )
    assert result.project == "Legacy App"
    assert result.webhook_url == "https://chat.example/legacy"
    assert result.environment == "beta"
    assert result.message_type == "TEXT"


def test_named_webhook_resolves_from_env(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_WEBHOOK_QA_TEAM": "https://chat.example/qa"})
    assert result.webhook_url == "https://chat.example/qa"
    assert result.provenance["webhook_url"] == "env: CHATNOTIFY_WEBHOOK_QA_TEAM"


def test_plain_webhook_url_beats_named_lookup(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(
        cwd=repo,
        env={
            "CHATNOTIFY_WEBHOOK_URL": "https://chat.example/direct",
            "CHATNOTIFY_WEBHOOK_QA_TEAM": "https://chat.example/qa",
        },
    )
    assert result.webhook_url == "https://chat.example/direct"


def test_message_type_is_uppercased_and_validated(repo):
    assert config.load(cwd=repo, env={"CHATNOTIFY_MESSAGE_TYPE": "text"}).message_type == "TEXT"
    assert config.load(cwd=repo, env={"CHATNOTIFY_MESSAGE_TYPE": "TEXTT"}).message_type == "CARD"


def test_invalid_message_type_records_fallback_provenance(repo):
    result = config.load(cwd=repo, env={"CHATNOTIFY_MESSAGE_TYPE": "nonsense"})
    assert "invalid" in result.provenance["message_type"]


def test_disabled_by_default_when_not_in_ci(repo):
    result = config.load(cwd=repo, env={})
    assert result.enabled is False
    assert result.provenance["enabled"] == "default (local)"


def test_enabled_automatically_in_ci(repo):
    result = config.load(cwd=repo, env={"CI": "true"})
    assert result.enabled is True
    assert result.provenance["enabled"] == "CI detected"


def test_explicit_enable_opts_in_locally(repo):
    result = config.load(cwd=repo, env={"CHATNOTIFY_ENABLED": "1"})
    assert result.enabled is True


def test_disabled_beats_enabled_and_ci(repo):
    result = config.load(
        cwd=repo, env={"CI": "true", "CHATNOTIFY_ENABLED": "1", "CHATNOTIFY_DISABLED": "1"}
    )
    assert result.enabled is False
    assert result.provenance["enabled"] == "env: CHATNOTIFY_DISABLED"


def test_report_patterns_split_on_commas(repo):
    result = config.load(flags={"report": "a/*.xml, b/**/*.xml"}, cwd=repo, env={})
    assert result.report_patterns == ("a/*.xml", "b/**/*.xml")


def test_report_patterns_default_to_none(repo):
    assert config.load(cwd=repo, env={}).report_patterns is None


def test_boolean_flags_are_respected(repo):
    result = config.load(flags={"only_on_failure": True, "quiet": True}, cwd=repo, env={})
    assert result.only_on_failure is True
    assert result.quiet is True


def test_machine_config_supplies_webhook(tmp_path, repo):
    machine = tmp_path / "cfg" / "chatnotify" / "config.ini"
    write(str(machine), "[chatnotify]\nwebhook_url = https://chat.example/machine\n")
    result = config.load(
        cwd=repo, env={"APPDATA": str(tmp_path / "cfg"), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    )
    assert result.webhook_url == "https://chat.example/machine"
    assert result.provenance["webhook_url"] == "machine config"


def test_machine_config_named_webhooks_section(tmp_path, repo):
    machine = tmp_path / "cfg" / "chatnotify" / "config.ini"
    write(str(machine), "[webhooks]\nqa-team = https://chat.example/qa\n")
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(
        cwd=repo, env={"APPDATA": str(tmp_path / "cfg"), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    )
    assert result.webhook_url == "https://chat.example/qa"


def test_malformed_ini_is_ignored_not_raised(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "this is not ini at all {{{")
    result = config.load(cwd=repo, env={})
    assert result.project == config.DEFAULT_PROJECT


def test_machine_config_path_uses_appdata_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    path = config.machine_config_path({"APPDATA": r"C:\Users\A\AppData\Roaming"})
    assert path.endswith(os.path.join("chatnotify", "config.ini"))
    assert "Roaming" in path


def test_named_webhook_with_dot_resolves(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa.team\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_WEBHOOK_QA_TEAM": "https://chat.example/qa"})
    assert result.webhook_url == "https://chat.example/qa"
    assert result.provenance["webhook_url"] == "env: CHATNOTIFY_WEBHOOK_QA_TEAM"


def test_named_webhook_with_slash_resolves(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = team/prod\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_WEBHOOK_TEAM_PROD": "https://chat.example/p"})
    assert result.webhook_url == "https://chat.example/p"


def test_env_key_for_maps_all_punctuation_and_non_ascii():
    assert config._env_key_for("qa-team") == "CHATNOTIFY_WEBHOOK_QA_TEAM"
    assert config._env_key_for("qa.team") == "CHATNOTIFY_WEBHOOK_QA_TEAM"
    assert config._env_key_for("team/prod") == "CHATNOTIFY_WEBHOOK_TEAM_PROD"
    assert config._env_key_for("web:hooks") == "CHATNOTIFY_WEBHOOK_WEB_HOOKS"
    assert config._env_key_for("equipe1") == "CHATNOTIFY_WEBHOOK_EQUIPE1"
    assert config._env_key_for("\u00e9quipe") == "CHATNOTIFY_WEBHOOK__QUIPE"


# --- Fix 1: a UTF-8 BOM must not void file-based config ---------------------


def test_bom_prefixed_ini_is_read_correctly(repo):
    write(
        os.path.join(repo, ".chatnotify.ini"),
        "\ufeff[chatnotify]\nproject = FromIni\nmessage_type = TEXT\n",
    )
    result = config.load(cwd=repo, env={})
    assert result.project == "FromIni"
    assert result.provenance["project"] == ".chatnotify.ini"
    assert result.message_type == "TEXT"


def test_bom_prefixed_dotenv_is_read_correctly(repo):
    write(os.path.join(repo, ".env"), "\ufeffCHATNOTIFY_PROJECT=FromDotenv\n")
    result = config.load(cwd=repo, env={})
    assert result.project == "FromDotenv"
    assert result.provenance["project"] == ".env"


# --- Fix 2: a literal '%' in an ini value must survive, not be swallowed ----


def test_percent_in_ini_project_value_is_preserved(repo):
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nproject = Coverage 100% Suite\n")
    result = config.load(cwd=repo, env={})
    assert result.project == "Coverage 100% Suite"
    assert result.provenance["project"] == ".chatnotify.ini"


def test_percent_encoded_webhook_url_in_webhooks_section_is_preserved(tmp_path, repo):
    machine = tmp_path / "cfg" / "chatnotify" / "config.ini"
    write(str(machine), "[webhooks]\nqa-team = https://chat.example/qa?token=abc%3D%3D\n")
    write(os.path.join(repo, ".chatnotify.ini"), "[chatnotify]\nwebhook = qa-team\n")
    result = config.load(
        cwd=repo, env={"APPDATA": str(tmp_path / "cfg"), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    )
    assert result.webhook_url == "https://chat.example/qa?token=abc%3D%3D"


# --- Fix 3: .env must be able to set enablement, at the right rung ---------


def test_dotenv_can_enable_locally(repo):
    write(os.path.join(repo, ".env"), "CHATNOTIFY_ENABLED=1\n")
    result = config.load(cwd=repo, env={})
    assert result.enabled is True
    assert result.provenance["enabled"] == ".env: CHATNOTIFY_ENABLED"


def test_dotenv_can_disable_under_ci(repo):
    write(os.path.join(repo, ".env"), "CHATNOTIFY_DISABLED=1\n")
    result = config.load(cwd=repo, env={"CI": "true"})
    assert result.enabled is False
    assert result.provenance["enabled"] == ".env: CHATNOTIFY_DISABLED"


def test_real_env_disabled_beats_dotenv_enabled(repo):
    write(os.path.join(repo, ".env"), "CHATNOTIFY_ENABLED=1\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_DISABLED": "1"})
    assert result.enabled is False
    assert result.provenance["enabled"] == "env: CHATNOTIFY_DISABLED"


def test_dotenv_disabled_beats_real_env_enabled(repo):
    write(os.path.join(repo, ".env"), "CHATNOTIFY_DISABLED=1\n")
    result = config.load(cwd=repo, env={"CHATNOTIFY_ENABLED": "1"})
    assert result.enabled is False
    assert result.provenance["enabled"] == ".env: CHATNOTIFY_DISABLED"


def test_dotenv_enabled_beats_ci_detection(repo):
    write(os.path.join(repo, ".env"), "CHATNOTIFY_ENABLED=1\n")
    result = config.load(cwd=repo, env={"CI": "true"})
    assert result.enabled is True
    assert result.provenance["enabled"] == ".env: CHATNOTIFY_ENABLED"


# --- Fix 4: _truthy must strip quotes the same way _clean does -------------


def test_truthy_strips_quotes():
    assert config._truthy('"1"') is True
    assert config._truthy("'true'") is True
    assert config._truthy('"nope"') is False


def test_quoted_disabled_value_in_real_env_is_truthy(repo):
    result = config.load(cwd=repo, env={"CI": "true", "CHATNOTIFY_DISABLED": '"1"'})
    assert result.enabled is False
    assert result.provenance["enabled"] == "env: CHATNOTIFY_DISABLED"
