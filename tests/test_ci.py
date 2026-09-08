from chatnotify import ci


def test_no_ci_environment_returns_undetected():
    info = ci.detect({})
    assert info.detected is False
    assert info.provider is None


def test_github_actions_is_fully_detected():
    info = ci.detect(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a1b2c3d4e5f6a7b8",
            "GITHUB_ACTOR": "dhruvil",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "12345",
        }
    )
    assert info.provider == "GitHub Actions"
    assert info.branch == "main"
    assert info.commit == "a1b2c3d4"
    assert info.actor == "dhruvil"
    assert info.build_url == "https://github.com/owner/repo/actions/runs/12345"


def test_github_pull_request_prefers_head_ref():
    info = ci.detect(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/pull/7/merge",
            "GITHUB_HEAD_REF": "feature/checkout",
        }
    )
    assert info.branch == "feature/checkout"


def test_gitlab_is_detected():
    info = ci.detect(
        {
            "GITLAB_CI": "true",
            "CI_COMMIT_REF_NAME": "develop",
            "CI_COMMIT_SHA": "0123456789abcdef",
            "GITLAB_USER_LOGIN": "asha",
            "CI_PIPELINE_URL": "https://gitlab.example/p/1",
        }
    )
    assert info.provider == "GitLab CI"
    assert info.branch == "develop"
    assert info.commit == "01234567"
    assert info.actor == "asha"
    assert info.build_url == "https://gitlab.example/p/1"


def test_jenkins_is_detected():
    info = ci.detect(
        {
            "JENKINS_URL": "https://ci.example/",
            "GIT_BRANCH": "origin/main",
            "GIT_COMMIT": "fedcba9876543210",
            "BUILD_URL": "https://ci.example/job/nightly/9/",
        }
    )
    assert info.provider == "Jenkins"
    assert info.branch == "main"
    assert info.commit == "fedcba98"
    assert info.build_url == "https://ci.example/job/nightly/9/"


def test_generic_ci_flag_is_detected_without_metadata():
    info = ci.detect({"CI": "true"})
    assert info.provider == "CI"
    assert info.branch is None
    assert info.build_url is None


def test_missing_repository_omits_build_url():
    info = ci.detect({"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1"})
    assert info.build_url is None


def test_blank_values_become_none_not_empty_strings():
    info = ci.detect({"GITHUB_ACTIONS": "true", "GITHUB_SHA": "", "GITHUB_ACTOR": ""})
    assert info.commit is None
    assert info.actor is None
