"""Find the release files that pip's configured package indexes mark as yanked."""

from __future__ import annotations

__lazy_modules__ = [
    "base64",
    "http.client",
    "json",
    "locale",
    "netrc",
    "packaging.utils",
    "pathlib",
    "platformdirs",
    "ssl",
    "urllib.parse",
    "urllib.request",
]

import codecs
import configparser
import json
import locale
import logging
import netrc
import os
import ssl
import sys
from base64 import b64encode
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from packaging.utils import canonicalize_name
from platformdirs import site_config_dir, site_data_dir, user_config_dir, user_data_dir

if TYPE_CHECKING:
    from collections.abc import Mapping
    from urllib.request import BaseHandler

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def yanked_files(distribution: str, env: Mapping[str, str]) -> frozenset[str] | None:
    """Return the files of a distribution that pip's configured indexes mark as yanked (PEP 592).

    Reads pip's index, certificate and proxy settings from its configuration files and ``PIP_*`` variables without
    running pip, then makes one simple API request per index (PEP 691 JSON or PEP 503 HTML).

    :param distribution: the distribution name, for example ``pip``
    :param env: the environment variables pip would run with

    :returns: the yanked file names, where a file on several indexes counts only if all of them yanked it; ``None`` when
        an index cannot be read or pip is configured not to use one

    """
    try:
        settings: Final[dict[str, str]] = _pip_settings(env)
    # platformdirs raises RuntimeError when it finds no home folder
    except (configparser.Error, UnicodeDecodeError, RuntimeError) as exception:
        _LOGGER.warning("could not read the pip configuration to check for yanked releases: %r", exception)
        return None
    if settings.get("no-index", "").lower() in {"y", "yes", "t", "true", "on", "1"}:
        return None
    flags: Final[dict[str, list[bool]]] = {}
    for index_url in [
        settings.get("index-url", "https://pypi.org/simple/"),
        *settings.get("extra-index-url", "").split(),
    ]:
        if (files := _read_project_page(index_url, distribution, settings, env)) is None:
            return None
        for filename, yanked in files.items():
            flags.setdefault(filename, []).append(yanked)
    return frozenset(filename for filename, yanked in flags.items() if all(yanked))


def _pip_settings(env: Mapping[str, str]) -> dict[str, str]:
    # pip's precedence: later files win, [download] beats [global], PIP_* beats both
    parser: Final[_PipConfigParser] = _PipConfigParser()
    if (env_file := env.get("PIP_CONFIG_FILE")) != os.devnull:
        # pip decodes its configuration files in the locale encoding outside UTF-8 mode
        encoding: Final[str] = "utf-8" if sys.flags.utf8_mode else _locale_encoding()
        # pip skips the per-user files when PIP_CONFIG_FILE exists; a read answers that without Path.exists, which
        # raised on an unreadable folder before Python 3.14
        env_file_read: Final[bool] = bool(env_file and _PipConfigParser().read(env_file, encoding=encoding))
        parser.read(_pip_config_files(env_file, skip_user=env_file_read), encoding=encoding)
    settings: Final[dict[str, str]] = {
        key: value
        for section in ("global", "download")
        if parser.has_section(section)
        for key, value in parser.items(section)
        if value
    }
    settings.update({
        key[4:].lower().replace("_", "-"): value for key, value in env.items() if key.startswith("PIP_") and value
    })
    return settings


class _PipConfigParser(configparser.RawConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr.lower().replace("_", "-")


def _locale_encoding() -> str:
    if sys.version_info >= (3, 11):
        return locale.getencoding()
    return locale.getpreferredencoding(do_setlocale=False)


def _pip_config_files(env_file: str | None, skip_user: bool) -> list[Path]:
    name: Final[str] = "pip.ini" if sys.platform == "win32" else "pip.conf"
    if sys.platform == "darwin":
        site_folders = site_data_dir("pip", appauthor=False, multipath=True).split(os.pathsep)
    elif sys.platform == "win32":
        site_folders = [site_config_dir("pip", appauthor=False)]
    else:
        site_folders = [*site_config_dir("pip", appauthor=False, multipath=True).split(os.pathsep), "/etc"]
    files: Final[list[Path]] = [Path(folder, name) for folder in site_folders]
    if not skip_user:
        files.extend(_pip_user_config_files(name))
    files.append(Path(sys.prefix, name))
    if env_file:
        files.append(Path(env_file))
    return files


def _pip_user_config_files(name: str) -> list[Path]:
    try:
        user_folder = Path(user_config_dir("pip", appauthor=False, roaming=True))
        if sys.platform == "darwin":
            mac_folder = user_data_dir("pip", appauthor=False, roaming=True)
            user_folder = Path(mac_folder if os.path.isdir(mac_folder) else os.path.expanduser("~/.config/pip"))
    # without a home folder there is no per-user configuration
    except RuntimeError:
        return []
    # os.path leaves ~ as is without a home folder, where Path.expanduser raises
    legacy_folder: Final[str] = os.path.expanduser(os.path.join("~", "pip" if sys.platform == "win32" else ".pip"))
    return [Path(legacy_folder, name), user_folder / name]


def _read_project_page(
    index_url: str, distribution: str, settings: Mapping[str, str], env: Mapping[str, str]
) -> dict[str, bool] | None:
    # the index URL may carry a password, so only the stripped URL is logged
    page_url = "an index URL that does not parse"
    try:
        split = urlsplit(index_url)
        page_url = urlunsplit((
            split.scheme,
            split.netloc.rpartition("@")[2],
            f"{split.path.rstrip('/')}/{canonicalize_name(distribution)}/",
            "",
            "",
        ))
        if split.scheme == "file":
            page_url += "index.html"
        files: Final[dict[str, bool]] = _parse_project_page(
            *_fetch(page_url, split.username, split.password, settings, env)
        )
    # json.loads raises RecursionError on deeply nested input
    except (OSError, ValueError, HTTPException, RecursionError) as exception:
        _LOGGER.warning("could not read %s to check for yanked releases: %r", page_url, exception)
        return None
    return files


def _parse_project_page(content_type: str, body: str) -> dict[str, bool]:
    if content_type != "application/vnd.pypi.simple.v1+json":
        anchors: Final[_AnchorParser] = _AnchorParser()
        try:
            anchors.feed(body)
        except (AssertionError, NotImplementedError) as exception:
            # html.parser before its 2025 hardening raises on some malformed markup: NotImplementedError on 3.9,
            # AssertionError on 3.10+
            msg = f"the project page has markup the parser rejects: {exception}"
            raise ValueError(msg) from exception
        return anchors.files
    if not isinstance(document := json.loads(body), dict) or not isinstance(files := document.get("files"), list):
        msg = "the project page has no files list"
        # ValueError, not TypeError, so the caller reports it like an unparsable page
        raise ValueError(msg)  # ruff:ignore[type-check-without-type-error]
    result: Final[dict[str, bool]] = {}
    for entry in files:
        if isinstance(entry, dict) and isinstance(filename := entry.get("filename"), str):
            # PEP 691 sets yanked to true or to the reason
            _add_listing(result, filename, yanked=bool(entry.get("yanked")))
    return result


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.files: dict[str, bool] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes: Final[dict[str, str | None]] = dict(attrs)
        if tag == "a" and (href := attributes.get("href")):
            # PEP 592 allows an empty data-yanked value, so its presence marks the yank
            _add_listing(
                self.files, unquote(urlsplit(href).path.rpartition("/")[2]), yanked="data-yanked" in attributes
            )


def _add_listing(files: dict[str, bool], filename: str, *, yanked: bool) -> None:
    # a file listed twice is yanked only if every listing says so
    files[filename] = files.get(filename, True) and yanked


def _fetch(
    page_url: str, username: str | None, password: str | None, settings: Mapping[str, str], env: Mapping[str, str]
) -> tuple[str, str]:
    # file:// is allowed because pip accepts a local mirror as its index
    request: Final[Request] = Request(  # ruff:ignore[suspicious-url-open-usage]
        page_url, headers={"Accept": "application/vnd.pypi.simple.v1+json, text/html;q=0.1"}
    )
    if (credentials := _credentials(username, password, urlsplit(page_url).hostname, env)) is not None:
        request.add_unredirected_header("Authorization", f"Basic {b64encode(credentials.encode()).decode()}")
    limit: Final[int] = 16 * 1024 * 1024
    with build_opener(*_handlers(settings)).open(request, timeout=15) as response:
        body = response.read(limit + 1)
        # http.client ignores Content-Length on a chunked response
        chunked = response.headers.get("Transfer-Encoding", "").lower() == "chunked"
        declared = "" if chunked else response.headers.get("Content-Length", "")
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
    if len(body) > limit:
        msg = f"the project page is larger than {limit} bytes"
        raise ValueError(msg)
    # read() returns a truncated body without error, which would pass for a shorter listing
    if declared.isdecimal() and len(body) < int(declared):
        msg = f"the project page ended after {len(body)} of {declared} bytes"
        raise ValueError(msg)
    try:
        # CPython's decode rejects non-text codecs such as base64 by this flag; GraalPy runs them and fails
        text_encoding = getattr(codecs.lookup(charset), "_is_text_encoding", True)
    except LookupError:
        text_encoding = False
    return content_type, body.decode(charset if text_encoding else "utf-8", errors="replace")


def _credentials(
    username: str | None, password: str | None, hostname: str | None, env: Mapping[str, str]
) -> str | None:
    # pip's order: user and password from the URL, then .netrc, then the URL's user alone
    if username is not None and password is not None:
        return f"{unquote(username)}:{unquote(password)}"
    if (from_netrc := _netrc_credentials(hostname, env)) is not None:
        return from_netrc
    return None if username is None else f"{unquote(username)}:"


def _netrc_credentials(hostname: str | None, env: Mapping[str, str]) -> str | None:
    # matches how requests, which pip uses, finds the file
    candidates: Final[list[str]] = [env["NETRC"]] if "NETRC" in env else ["~/.netrc", "~/_netrc"]
    path: Final[str | None] = next((path for path in map(os.path.expanduser, candidates) if os.path.exists(path)), None)
    if hostname is None or path is None:
        return None
    try:
        # an explicit path skips netrc's ownership and permission checks on the default file
        entry = netrc.netrc(path).authenticators(hostname)
    except (netrc.NetrcParseError, OSError):
        return None
    if entry is None or not any(entry):
        return None
    return f"{entry[0] or entry[1] or ''}:{entry[2] or ''}"


def _handlers(settings: Mapping[str, str]) -> list[BaseHandler]:
    handlers: Final[list[BaseHandler]] = []
    if proxy := settings.get("proxy"):
        handlers.append(ProxyHandler({"http": proxy, "https": proxy}))
    if cert := settings.get("cert"):
        handlers.append(HTTPSHandler(context=ssl.create_default_context(cafile=cert)))
    return handlers


__all__ = [
    "yanked_files",
]
