"""Read GitHub Releases and stage explicitly approved, SHA256-verified assets.

This module never installs, launches, extracts, merges, publishes or self-updates.
All requests preserve httpx TLS verification and inherited proxy/CA configuration.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from nexus_ai.i18n import Text

REPOSITORY = "misha2271/NEXUS-AI"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_METADATA_BYTES = 4 * 1024**2
MAX_DOWNLOAD_BYTES = 512 * 1024**2
_REDIRECT_HOSTS = frozenset(
    {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
)
_VERSION = re.compile(
    r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?\Z"
)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,149}\Z")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


class UpdateError(Exception):
    """An actionable update-check, approval or integrity failure."""


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        if (
            not isinstance(value, str)
            or len(value) > 80
            or not (match := _VERSION.fullmatch(value))
        ):
            raise UpdateError(Text("A stable version must have the form 1.2.3 or v1.2.3."))
        return cls(*(int(component) for component in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size_bytes: int
    sha256: str | None

    @property
    def verifiable(self) -> bool:
        return self.sha256 is not None


@dataclass(frozen=True)
class Release:
    tag: str
    version: Version
    page_url: str
    assets: tuple[ReleaseAsset, ...]


@dataclass(frozen=True)
class UpdateCheck:
    status: str
    message: str
    current_version: Version
    release: Release | None = None

    @property
    def major_update(self) -> bool:
        return self.release is not None and self.release.version.major > self.current_version.major


@dataclass(frozen=True)
class DownloadApproval:
    release_tag: str
    asset_name: str
    download_approved: bool = False
    major_approved: bool = False


@dataclass(frozen=True)
class StagedUpdate:
    path: Path
    sha256: str
    release_tag: str
    installed: bool = field(default=False, init=False)


def _https_url(value: str, hosts: frozenset[str]) -> str:
    try:
        if not isinstance(value, str) or any(ord(char) <= 32 for char in value):
            raise ValueError
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in hosts
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.fragment
        ):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise UpdateError(Text("The release contains an untrusted download address.")) from exc
    return value


def _asset_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not _NAME.fullmatch(value)
        or value.endswith(".")
        or ".." in value
        or value.split(".", 1)[0].upper() in _RESERVED_NAMES
    ):
        raise UpdateError(Text("The release contains an unsafe asset filename."))
    return value


def _asset_url(url: str, tag: str, name: str) -> str:
    _https_url(url, frozenset({"github.com"}))
    parsed = urlsplit(url)
    expected = f"/{REPOSITORY}/releases/download/{tag}/{name}"
    if parsed.query or unquote(parsed.path) != expected:
        raise UpdateError(Text("The release asset does not belong to this repository and tag."))
    return url


def _release(payload: object, maximum: int) -> Release:
    if not isinstance(payload, dict):
        raise UpdateError(Text("GitHub returned invalid release metadata."))
    if type(payload.get("draft")) is not bool or type(payload.get("prerelease")) is not bool:
        raise UpdateError(Text("GitHub returned invalid release metadata."))
    tag = payload.get("tag_name")
    version = Version.parse(tag)
    page = _https_url(payload.get("html_url"), frozenset({"github.com"}))
    parsed = urlsplit(page)
    if parsed.query or unquote(parsed.path) != f"/{REPOSITORY}/releases/tag/{tag}":
        raise UpdateError(Text("The release page does not belong to this repository."))
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list) or len(raw_assets) > 1000:
        raise UpdateError(Text("GitHub returned invalid release assets."))
    assets = []
    seen = set()
    for item in raw_assets:
        if not isinstance(item, dict):
            raise UpdateError(Text("GitHub returned invalid release assets."))
        name = _asset_name(item.get("name"))
        if name in seen:
            raise UpdateError(Text("GitHub returned duplicate release asset names."))
        seen.add(name)
        size = item.get("size")
        if type(size) is not int or not 0 < size <= maximum:
            raise UpdateError(Text("A release asset exceeds the permitted download size."))
        url = _asset_url(item.get("browser_download_url"), tag, name)
        digest = item.get("digest")
        checksum = None
        if isinstance(digest, str) and digest.startswith("sha256:"):
            candidate = digest[7:]
            if not _SHA256.fullmatch(candidate):
                raise UpdateError(Text("GitHub returned an invalid SHA256 digest."))
            checksum = candidate.lower()
        if name.lower().endswith((".exe", ".zip")):
            assets.append(ReleaseAsset(name, url, size, checksum))
    return Release(tag, version, page, tuple(assets))


def _trusted_directory(directory: Path) -> Path:
    directory = Path(directory)
    if not directory.is_absolute():
        raise UpdateError(Text("The update staging directory must be an absolute path."))
    for component in reversed((directory, *directory.parents)):
        if component.is_symlink():
            raise UpdateError(Text("Update staging cannot use symbolic links or junctions."))
        if component.exists():
            info = component.lstat()
            if getattr(info, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
            ):
                raise UpdateError(Text("Update staging cannot use symbolic links or junctions."))
            if not stat.S_ISDIR(info.st_mode):
                raise UpdateError(Text("The update staging path is not a directory."))
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


class ReleaseChecker:
    """Synchronous worker service; callers must not use it on the Qt UI thread."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        max_download_bytes: int = MAX_DOWNLOAD_BYTES,
    ) -> None:
        if type(max_download_bytes) is not int or not 0 < max_download_bytes <= MAX_DOWNLOAD_BYTES:
            raise ValueError("Invalid maximum download size")
        self.maximum = max_download_bytes
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=5, read=30, write=15, pool=5),
            headers={
                "User-Agent": "NEXUS-AI-Update-Checker",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def __enter__(self) -> ReleaseChecker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def check(self, current_version: str = "1.0.0") -> UpdateCheck:
        current = Version.parse(current_version)
        try:
            with self._client.stream("GET", LATEST_URL) as response:
                if response.status_code == 404:
                    return UpdateCheck(
                        "no_release",
                        Text("No published GitHub release is available, or access is denied."),
                        current,
                    )
                if response.status_code != 200:
                    raise UpdateError(
                        Text(
                            "GitHub release checking failed with HTTP {status}.",
                            status=response.status_code,
                        )
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_METADATA_BYTES:
                        raise UpdateError(
                            Text("GitHub release metadata exceeds the permitted size.")
                        )
                import json

                try:
                    payload = json.loads(data)
                except (ValueError, UnicodeError) as exc:
                    raise UpdateError(Text("GitHub returned invalid release metadata.")) from exc
            if isinstance(payload, dict) and (
                payload.get("draft") is True or payload.get("prerelease") is True
            ):
                return UpdateCheck(
                    "no_release", Text("No stable published release is available."), current
                )
            release = _release(payload, self.maximum)
            if release.version <= current:
                return UpdateCheck(
                    "up_to_date", Text("No newer stable release is available."), current, release
                )
            return UpdateCheck(
                "available",
                Text(
                    "A newer stable release is available: {version}.", version=str(release.version)
                ),
                current,
                release,
            )
        except httpx.RequestError:
            return UpdateCheck(
                "unavailable", Text("Cannot reach GitHub to check for updates."), current
            )
        except UpdateError as exc:
            return UpdateCheck("unavailable", exc.args[0], current)

    def stage_asset(
        self,
        check: UpdateCheck,
        asset_name: str,
        directory: Path,
        approval: DownloadApproval,
        *,
        cancel_event: Event | None = None,
    ) -> StagedUpdate:
        """Verify and stage one approved asset. Never execute or install its contents."""
        release = check.release
        if (
            check.status != "available"
            or release is None
            or release.version <= check.current_version
        ):
            raise UpdateError(Text("Only a newer checked release can be staged."))
        if (
            type(approval.download_approved) is not bool
            or not approval.download_approved
            or approval.release_tag != release.tag
            or approval.asset_name != asset_name
        ):
            raise UpdateError(Text("Explicit approval is required for this release download."))
        if check.major_update and (
            type(approval.major_approved) is not bool or not approval.major_approved
        ):
            raise UpdateError(Text("A major update requires a separate explicit approval."))
        asset = next((item for item in release.assets if item.name == asset_name), None)
        if asset is None or asset.sha256 is None or not _SHA256.fullmatch(asset.sha256):
            raise UpdateError(Text("The selected asset has no verifiable GitHub SHA256 digest."))
        name = _asset_name(asset.name)
        _asset_url(asset.url, release.tag, name)
        if type(asset.size_bytes) is not int or not 0 < asset.size_bytes <= self.maximum:
            raise UpdateError(Text("A release asset exceeds the permitted download size."))
        if cancel_event is not None and cancel_event.is_set():
            raise UpdateError(Text("Update download cancelled."))
        temporary = None
        published = None
        try:
            folder = _trusted_directory(directory)
            destination = folder / f"{release.version}-{name}"
            # Refuse existing files, including dangling symbolic links, before network I/O.
            if destination.exists() or destination.is_symlink():
                raise UpdateError(Text("A staged update already exists; it was not overwritten."))
            descriptor, filename = tempfile.mkstemp(
                prefix=".nexus-update-", suffix=".part", dir=folder
            )
            temporary = Path(filename)
            digest = hashlib.sha256()
            received = 0
            with os.fdopen(descriptor, "wb") as file:
                url = asset.url
                for redirect in range(6):
                    with self._client.stream(
                        "GET", url, headers={"Accept": "application/octet-stream"}
                    ) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            if redirect == 5 or "location" not in response.headers:
                                raise UpdateError(
                                    Text("The release download has too many or invalid redirects.")
                                )
                            url = _https_url(
                                urljoin(url, response.headers["location"]), _REDIRECT_HOSTS
                            )
                            if urlsplit(url).hostname == "github.com":
                                _asset_url(url, release.tag, name)
                            continue
                        if response.status_code != 200:
                            raise UpdateError(
                                Text(
                                    "Release download failed with HTTP {status}.",
                                    status=response.status_code,
                                )
                            )
                        length = response.headers.get("content-length")
                        if length is not None:
                            try:
                                parsed_length = int(length)
                            except ValueError as exc:
                                raise UpdateError(
                                    Text("The release download has an invalid size.")
                                ) from exc
                            if not 0 < parsed_length <= self.maximum:
                                raise UpdateError(
                                    Text("A release asset exceeds the permitted download size.")
                                )
                        for chunk in response.iter_bytes():
                            if cancel_event is not None and cancel_event.is_set():
                                raise UpdateError(Text("Update download cancelled."))
                            received += len(chunk)
                            if received > self.maximum or received > asset.size_bytes:
                                raise UpdateError(
                                    Text("The release download exceeds its declared size.")
                                )
                            file.write(chunk)
                            digest.update(chunk)
                        break
                if received != asset.size_bytes or digest.hexdigest() != asset.sha256.lower():
                    raise UpdateError(
                        Text("Release integrity verification failed; the download was removed.")
                    )
                file.flush()
                os.fsync(file.fileno())
                verified_file = os.fstat(file.fileno())
            _trusted_directory(folder)
            # A same-directory hard link atomically publishes without overwriting
            # an existing file or following an attacker-created destination symlink.
            os.link(temporary, destination, follow_symlinks=False)
            published = destination
            actual = destination.lstat()
            if not stat.S_ISREG(actual.st_mode) or (actual.st_ino, actual.st_dev) != (
                verified_file.st_ino,
                verified_file.st_dev,
            ):
                raise UpdateError(Text("The update staging directory changed during verification."))
            temporary.unlink()
            temporary = None
            published = None
            return StagedUpdate(destination, digest.hexdigest(), release.tag)
        except httpx.RequestError as exc:
            raise UpdateError(
                Text("The release download failed; no update was installed.")
            ) from exc
        except OSError as exc:
            raise UpdateError(
                Text("The release could not be safely staged; no update was installed.")
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if published is not None:
                published.unlink(missing_ok=True)
