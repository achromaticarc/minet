from typing import Optional, Dict, Union
from minet.types import AnyTimeout, RedirectionStack, Redirection, HTTPHeaderDict

import pycurl
import certifi
from io import BytesIO
from dataclasses import dataclass
from ebbe import format_repr, format_filesize
from threading import Event
from ural import is_url
from urllib3 import Timeout
from urllib.parse import urljoin
from urllib3.util.url import parse_url

from minet.constants import REDIRECT_STATUSES
from minet.exceptions import (
    CancelledRequestError,
    MaxRedirectsError,
    InvalidURLError,
    PycurlError,
    PycurlHostResolutionError,
    PycurlTimeoutError,
    PycurlConnectionRefusedError,
    PycurlSSLError,
    PycurlReceiveError,
)


@dataclass
class PycurlResult:
    url: str
    body: bytes
    headers: HTTPHeaderDict
    status: int
    stack: RedirectionStack

    def __repr__(self) -> str:
        return format_repr(
            self, ["url", "status", ("size", format_filesize(len(self.body)))]
        )


def sanitize_url(url: str) -> str:
    return parse_url(url).url


def coerce_error(
    error: pycurl.error,
) -> Union[PycurlError, CancelledRequestError, MaxRedirectsError]:
    code = error.args[0]

    if code == pycurl.E_ABORTED_BY_CALLBACK:
        return CancelledRequestError()

    if code == pycurl.E_TOO_MANY_REDIRECTS:
        return MaxRedirectsError()

    if code == pycurl.E_OPERATION_TIMEDOUT:
        return PycurlTimeoutError(error)

    if code == pycurl.E_COULDNT_RESOLVE_HOST:
        return PycurlHostResolutionError(error)

    if code == pycurl.E_COULDNT_CONNECT:
        return PycurlConnectionRefusedError(error)

    if code == pycurl.E_PEER_FAILED_VERIFICATION or code == pycurl.E_SSL_CONNECT_ERROR:
        return PycurlSSLError(error)

    if code == pycurl.E_RECV_ERROR:
        return PycurlReceiveError(error)

    return PycurlError(error)


def setup_curl_handle(
    curl: pycurl.Curl,
    url: str,
    response_headers: HTTPHeaderDict,
    buffer: BytesIO,
    stack: RedirectionStack,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    max_redirects: int = 5,
    timeout: Optional[AnyTimeout] = None,
    cancel_event: Optional[Event] = None,
    verbose: bool = False,
) -> None:
    # Basics
    curl.setopt(pycurl.URL, sanitize_url(url))
    curl.setopt(pycurl.WRITEDATA, buffer)
    curl.setopt(pycurl.CAINFO, certifi.where())

    # NOTE: this is important for multithreading
    curl.setopt(pycurl.NOSIGNAL, True)

    if verbose:
        curl.setopt(pycurl.VERBOSE, True)

    # Method
    method = method.upper()

    curl.setopt(pycurl.HTTPGET, False)
    curl.setopt(pycurl.NOBODY, False)
    curl.setopt(pycurl.POST, False)
    curl.setopt(pycurl.PUT, False)
    curl.unsetopt(pycurl.CUSTOMREQUEST)

    if method == "GET":
        curl.setopt(pycurl.HTTPGET, True)
    elif method == "HEAD":
        curl.setopt(pycurl.NOBODY, True)
    elif method == "POST":
        curl.setopt(pycurl.POST, True)
    elif method == "PUT":
        curl.setopt(pycurl.PUT, True)
    else:
        curl.setopt(pycurl.CUSTOMREQUEST, method)

    # Timeout
    if timeout is not None:
        if isinstance(timeout, Timeout):
            total_timeout = None

            if timeout.total is not None:
                total_timeout = timeout.total
            else:
                if timeout.read_timeout is not None:
                    total_timeout = timeout.read_timeout
                if timeout.connect_timeout is not None:
                    if total_timeout is not None:
                        total_timeout += timeout.connect_timeout
                    else:
                        total_timeout = timeout.connect_timeout

            if total_timeout is not None:
                curl.setopt(pycurl.TIMEOUT_MS, int(total_timeout * 1000))

            if timeout.connect_timeout is not None:
                curl.setopt(
                    pycurl.CONNECTTIMEOUT_MS, int(timeout.connect_timeout * 1000)
                )

        else:
            curl.setopt(pycurl.TIMEOUT_MS, int(timeout * 1000))

    # Writing headers
    if headers is not None:
        curl_headers = [
            b"%s: %s" % (n.encode("ascii"), v.encode("latin1"))
            for n, v in headers.items()
        ]
        curl.setopt(pycurl.HTTPHEADER, curl_headers)

    # Reading headers
    current_url = url
    expecting_location_with_status: Optional[int] = None

    def header_function(header_line):
        nonlocal current_url
        nonlocal expecting_location_with_status

        header_line = header_line.rstrip()
        header_line = header_line.decode("iso-8859-1")

        # Detecting new call, resetting headers
        if header_line.startswith("HTTP/"):
            response_headers.clear()

            status = int(header_line.split(" ", 1)[1][:3])

            if status in REDIRECT_STATUSES:
                expecting_location_with_status = status

            return

        if ":" not in header_line:
            return

        name, value = header_line.split(":", 1)

        name = name.strip()
        value = value.strip()

        if expecting_location_with_status is not None and name.lower() == "location":
            stack.append(
                Redirection(
                    current_url,
                    "location-header",
                    status=expecting_location_with_status,
                )
            )
            next_url = urljoin(current_url, value).strip()
            current_url = next_url
            expecting_location_with_status = None

        response_headers[name] = value

    curl.setopt(pycurl.HEADERFUNCTION, header_function)

    # Redirections
    if follow_redirects:
        curl.setopt(pycurl.FOLLOWLOCATION, True)
        curl.setopt(pycurl.MAXREDIRS, max_redirects)

    # Cancellation
    if cancel_event is not None:
        curl.setopt(pycurl.NOPROGRESS, False)

        def progress_function(
            download_total, downloaded_total, upload_total, uploaded_total
        ) -> int:
            if cancel_event.is_set():
                return 1

            return 0

        curl.setopt(pycurl.XFERINFOFUNCTION, progress_function)


SHARE = pycurl.CurlShare()
SHARE.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_DNS)
SHARE.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_SSL_SESSION)
SHARE.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_CONNECT)


# TODO: body
# TODO: decompress?
# TODO: invalid status error (pycurl has a way I think)?
# TODO: error serialization, error retrying conversion
# TODO: pool of curl handles with multi (tricks from https://github.com/tornadoweb/tornado/blob/master/tornado/curl_httpclient.py)
def request_with_pycurl(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    max_redirects: int = 5,
    timeout: Optional[AnyTimeout] = None,
    cancel_event: Optional[Event] = None,
    verbose: bool = False,
    share: bool = False,
) -> PycurlResult:
    # Preemptive cancellation
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledRequestError

    if not is_url(
        url, require_protocol=True, tld_aware=True, allow_spaces_in_path=True
    ):
        raise InvalidURLError(url)

    curl = pycurl.Curl()

    if share:
        curl.setopt(pycurl.SHARE, SHARE)

    buffer = BytesIO()
    response_headers = HTTPHeaderDict()
    stack = []

    setup_curl_handle(
        curl,
        url=url,
        response_headers=response_headers,
        buffer=buffer,
        stack=stack,
        method=method,
        headers=headers,
        follow_redirects=follow_redirects,
        max_redirects=max_redirects,
        timeout=timeout,
        cancel_event=cancel_event,
        verbose=verbose,
    )

    # Performing
    try:
        curl.perform()
    except pycurl.error as error:
        curl.close()

        raise coerce_error(error)

    status = curl.getinfo(pycurl.HTTP_CODE)
    effective_url = curl.getinfo(pycurl.EFFECTIVE_URL)
    curl.close()

    stack.append(Redirection(effective_url, status=status))

    return PycurlResult(
        url=url,
        body=buffer.getvalue(),
        headers=response_headers,
        status=status,
        stack=stack,
    )
