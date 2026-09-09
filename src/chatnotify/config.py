"""Six-layer configuration cascade. Every value records where it came from."""

import configparser
import os
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

from .models import CARD, TEXT

DEFAULT_PROJECT = "Unknown Project"
VALID_MESSAGE_TYPES = (CARD, TEXT)
_TRUTHY = ("1", "true", "yes", "on")

_ENV_KEYS = {
    "project": ("CHATNOTIFY_PROJECT", "PROJECT_NAME"),
    "environment": ("CHATNOTIFY_ENV", "ENVIRONMENT"),
    "webhook_url": ("CHATNOTIFY_WEBHOOK_URL", "GOOGLE_CHAT_WEBHOOK_URL"),
    "message_type": ("CHATNOTIFY_MESSAGE_TYPE", "MESSAGE_TYPE"),
}

_INI_KEYS = {
    "project": "project",
    "environment": "environment",
    "webhook_url": "webhook_url",
    "message_type": "message_type",
}


@dataclass(frozen=True)
class Config:
    project: str
    environment: Optional[str]
    webhook_url: Optional[str]
    message_type: str
    enabled: bool
    only_on_failure: bool
    quiet: bool
    report_patterns: Optional[Tuple[str, ...]]
    provenance: Dict[str, str] = field(default_factory=dict)


def _clean(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().strip('"').strip("'").strip()
    return text or None


def _truthy(value) -> bool:
    cleaned = _clean(value)
    return cleaned is not None and cleaned.lower() in _TRUTHY


def _env_key_for(name: str) -> str:
    """Build a shell-usable env var name from a webhook name.

    Any character outside A-Z and 0-9 becomes an underscore, so a name like
    "qa.team" or "team/prod" still yields a key a user can actually export.
    """
    safe = "".join(
        char if ("A" <= char <= "Z" or "0" <= char <= "9") else "_"
        for char in name.upper()
    )
    return "CHATNOTIFY_WEBHOOK_" + safe


def machine_config_path(env: Optional[Mapping[str, str]] = None) -> str:
    env = os.environ if env is None else env
    if os.name == "nt":
        base = env.get("APPDATA") or os.path.expanduser("~")
    else:
        base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "chatnotify", "config.ini")


def _read_ini(path: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return configparser.ConfigParser(interpolation=None)
    return parser


def _ini_get(parser: configparser.ConfigParser, section: str, option: str) -> Optional[str]:
    try:
        if parser.has_option(section, option):
            return _clean(parser.get(section, option))
    except configparser.Error:
        return None
    return None


def _read_dotenv(path: str) -> Dict[str, str]:
    values = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, raw = stripped.partition("=")
                cleaned = _clean(raw)
                if cleaned is not None:
                    values[key.strip()] = cleaned
    except (OSError, UnicodeDecodeError):
        return {}
    return values


def _resolve_enabled(env: Mapping[str, str], dotenv: Mapping[str, str]) -> Tuple[bool, str]:
    if _truthy(env.get("CHATNOTIFY_DISABLED")):
        return False, "env: CHATNOTIFY_DISABLED"
    if _truthy(dotenv.get("CHATNOTIFY_DISABLED")):
        return False, ".env: CHATNOTIFY_DISABLED"
    if _truthy(env.get("CHATNOTIFY_ENABLED")):
        return True, "env: CHATNOTIFY_ENABLED"
    if _truthy(dotenv.get("CHATNOTIFY_ENABLED")):
        return True, ".env: CHATNOTIFY_ENABLED"
    if _clean(env.get("CI")):
        return True, "CI detected"
    return False, "default (local)"


def _resolve_webhook(
    layers, env: Mapping[str, str], repo_ini, machine_ini
) -> Tuple[Optional[str], str]:
    direct, source = layers("webhook_url")
    if direct:
        return direct, source

    name = _ini_get(repo_ini, "chatnotify", "webhook") or _clean(env.get("CHATNOTIFY_WEBHOOK_NAME"))
    if name:
        env_key = _env_key_for(name)
        from_env = _clean(env.get(env_key))
        if from_env:
            return from_env, "env: %s" % env_key
        from_machine = _ini_get(machine_ini, "webhooks", name)
        if from_machine:
            return from_machine, "machine config [webhooks]"
    return None, "unset"


def load(
    flags: Optional[Dict[str, object]] = None,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Config:
    flags = flags or {}
    cwd = os.getcwd() if cwd is None else cwd
    env = os.environ if env is None else env

    dotenv = _read_dotenv(os.path.join(cwd, ".env"))
    repo_ini = _read_ini(os.path.join(cwd, ".chatnotify.ini"))
    machine_ini = _read_ini(machine_config_path(env))

    def layers(name: str) -> Tuple[Optional[str], str]:
        from_flag = _clean(flags.get(name))
        if from_flag:
            return from_flag, "flag"
        for key in _ENV_KEYS.get(name, ()):
            found = _clean(env.get(key))
            if found:
                return found, "env: %s" % key
        for key in _ENV_KEYS.get(name, ()):
            found = _clean(dotenv.get(key))
            if found:
                return found, ".env"
        from_repo = _ini_get(repo_ini, "chatnotify", _INI_KEYS[name])
        if from_repo:
            return from_repo, ".chatnotify.ini"
        from_machine = _ini_get(machine_ini, "chatnotify", _INI_KEYS[name])
        if from_machine:
            return from_machine, "machine config"
        return None, "default"

    provenance = {}

    project, provenance["project"] = layers("project")
    environment, provenance["environment"] = layers("environment")
    webhook_url, provenance["webhook_url"] = _resolve_webhook(layers, env, repo_ini, machine_ini)

    raw_type, type_source = layers("message_type")
    if raw_type is None:
        message_type, type_source = CARD, "default"
    elif raw_type.upper() in VALID_MESSAGE_TYPES:
        message_type = raw_type.upper()
    else:
        message_type = CARD
        type_source = "default (invalid value %r from %s)" % (raw_type, type_source)
    provenance["message_type"] = type_source

    enabled, provenance["enabled"] = _resolve_enabled(env, dotenv)

    raw_report = _clean(flags.get("report"))
    if raw_report:
        patterns = tuple(part.strip() for part in raw_report.split(",") if part.strip())
        provenance["report_patterns"] = "flag"
    else:
        patterns = None
        provenance["report_patterns"] = "auto-detect"

    return Config(
        project=project or DEFAULT_PROJECT,
        environment=environment,
        webhook_url=webhook_url,
        message_type=message_type,
        enabled=enabled,
        only_on_failure=bool(flags.get("only_on_failure")),
        quiet=bool(flags.get("quiet")),
        report_patterns=patterns,
        provenance=provenance,
    )
