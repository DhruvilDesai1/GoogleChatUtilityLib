"""Detect CI provider metadata from the environment. No subprocess calls."""

import os
from typing import Mapping, Optional

from .models import CiInfo

_SHORT_SHA = 8


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _short(value: Optional[str]) -> Optional[str]:
    cleaned = _clean(value)
    return cleaned[:_SHORT_SHA] if cleaned else None


def _branch_from_ref(ref: Optional[str]) -> Optional[str]:
    cleaned = _clean(ref)
    if not cleaned:
        return None
    for prefix in ("refs/heads/", "refs/tags/", "origin/"):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):]
    return cleaned


def detect(env: Optional[Mapping[str, str]] = None) -> CiInfo:
    env = os.environ if env is None else env

    if _clean(env.get("GITHUB_ACTIONS")):
        repository = _clean(env.get("GITHUB_REPOSITORY"))
        run_id = _clean(env.get("GITHUB_RUN_ID"))
        build_url = None
        if repository and run_id:
            build_url = "https://github.com/%s/actions/runs/%s" % (repository, run_id)
        return CiInfo(
            provider="GitHub Actions",
            branch=_clean(env.get("GITHUB_HEAD_REF")) or _branch_from_ref(env.get("GITHUB_REF")),
            commit=_short(env.get("GITHUB_SHA")),
            actor=_clean(env.get("GITHUB_ACTOR")),
            build_url=build_url,
        )

    if _clean(env.get("GITLAB_CI")):
        return CiInfo(
            provider="GitLab CI",
            branch=_branch_from_ref(env.get("CI_COMMIT_REF_NAME")),
            commit=_short(env.get("CI_COMMIT_SHA")),
            actor=_clean(env.get("GITLAB_USER_LOGIN")),
            build_url=_clean(env.get("CI_PIPELINE_URL")),
        )

    if _clean(env.get("JENKINS_URL")):
        return CiInfo(
            provider="Jenkins",
            branch=_branch_from_ref(env.get("GIT_BRANCH")),
            commit=_short(env.get("GIT_COMMIT")),
            actor=_clean(env.get("BUILD_USER_ID")),
            build_url=_clean(env.get("BUILD_URL")),
        )

    if _clean(env.get("CI")):
        return CiInfo(provider="CI")

    return CiInfo()
