"""HTTP delivery. The only guarantee that matters: post() never raises."""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

TIMEOUT_SECONDS = 10.0
RETRY_STATUSES = (429, 500, 502, 503, 504)
BACKOFF_SECONDS = (1.0, 4.0)
TOTAL_BUDGET_SECONDS = 20.0
_REPLY_OPTION = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A Google Chat webhook never legitimately redirects; treat any 3xx as a failure
    instead of silently following it (which drops the POST body on 301/302/303)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# A module-private opener, deliberately NOT installed process-wide: this package is
# importable, and urllib.request.install_opener() would silently stop redirects being
# followed for every other urllib caller in the same process.
_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _open(request, timeout):
    """Single seam for the HTTP call, so tests can substitute it."""
    return _OPENER.open(request, timeout=timeout)


def _is_loopback(hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    hostname = hostname.lower()
    return hostname in _LOOPBACK_HOSTS or hostname.startswith("127.")


def _warn(message: str, quiet: bool) -> None:
    if quiet:
        return
    try:
        print("chatnotify: " + message, file=sys.stderr)
    except Exception:
        pass


def _thread_url(url: str, thread_key: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key not in ("threadKey", "messageReplyOption")
    ]
    query.append(("threadKey", thread_key))
    query.append(("messageReplyOption", _REPLY_OPTION))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
    )


def post(
    url: str,
    payload: dict,
    thread_key: Optional[str] = None,
    quiet: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Deliver payload to url. Returns True on 2xx. Never raises, never logs the URL."""
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https"):
            _warn("refusing to post to unsupported URL scheme: %s" % parts.scheme, quiet)
            return False
        if parts.scheme == "http" and not _is_loopback(parts.hostname):
            _warn("posting to webhook over unencrypted http; url is a credential", quiet)

        target = _thread_url(url, thread_key) if thread_key else url
        body = json.dumps(payload).encode("utf-8")
        attempts = len(BACKOFF_SECONDS) + 1
        started = monotonic()

        for attempt in range(attempts):
            if monotonic() - started >= TOTAL_BUDGET_SECONDS:
                _warn(
                    "giving up on notification after exceeding %.0fs budget"
                    % TOTAL_BUDGET_SECONDS,
                    quiet,
                )
                return False

            retryable = False
            permanent = False
            try:
                request = urllib.request.Request(
                    target,
                    data=body,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                    method="POST",
                )
                with _open(request, TIMEOUT_SECONDS) as response:
                    status = getattr(response, "status", None) or response.getcode()
                if 200 <= status < 300:
                    return True
                retryable = status in RETRY_STATUSES
                message = "webhook returned HTTP %d" % status
            except urllib.error.HTTPError as error:
                status = error.code
                retryable = status in RETRY_STATUSES
                message = "webhook returned HTTP %d" % status
            except ValueError as error:
                # A malformed URL (e.g. "unknown url type") can never succeed on retry.
                permanent = True
                message = "could not reach webhook (%s)" % type(error).__name__
            except Exception as error:
                retryable = True
                message = "could not reach webhook (%s)" % type(error).__name__

            if permanent:
                _warn(message, quiet)
                return False

            if retryable and attempt < attempts - 1:
                if monotonic() - started >= TOTAL_BUDGET_SECONDS:
                    _warn(
                        "giving up on notification after exceeding %.0fs budget"
                        % TOTAL_BUDGET_SECONDS,
                        quiet,
                    )
                    return False
                sleep(BACKOFF_SECONDS[attempt])
                continue
            _warn(message, quiet)
            return False

        return False
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as error:  # never fatal, by contract
        _warn("notification error (%s)" % type(error).__name__, quiet)
        return False
