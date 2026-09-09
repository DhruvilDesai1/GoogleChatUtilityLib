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
_REPLY_OPTION = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"


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
) -> bool:
    """Deliver payload to url. Returns True on 2xx. Never raises, never logs the URL."""
    try:
        target = _thread_url(url, thread_key) if thread_key else url
        body = json.dumps(payload).encode("utf-8")
        attempts = len(BACKOFF_SECONDS) + 1

        for attempt in range(attempts):
            retryable = False
            try:
                request = urllib.request.Request(
                    target,
                    data=body,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                    status = getattr(response, "status", None) or response.getcode()
                if 200 <= status < 300:
                    return True
                retryable = status in RETRY_STATUSES
                message = "webhook returned HTTP %d" % status
            except urllib.error.HTTPError as error:
                status = error.code
                retryable = status in RETRY_STATUSES
                message = "webhook returned HTTP %d" % status
            except Exception as error:
                retryable = True
                message = "could not reach webhook (%s)" % type(error).__name__

            if retryable and attempt < attempts - 1:
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
