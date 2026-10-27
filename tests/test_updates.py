"""Real updater logic with in-memory HTTPS responses and isolated staging directories."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from threading import Event
from urllib.parse import quote

import httpx
import pytest

import nexus_ai.updates as updates
from nexus_ai.updates import DownloadApproval, ReleaseChecker, UpdateError, Version

CONTENT = b"MZ signed-by-no-one test fixture, never executed"
TAG = "v1.1.0"
NAME = "NEXUS-AI.exe"
URL = f"https://github.com/misha2271/NEXUS-AI/releases/download/{TAG}/{NAME}"


def metadata(tag=TAG, **changes):
    payload = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/misha2271/NEXUS-AI/releases/tag/{quote(tag)}",
        "assets": [
            {
                "name": NAME,
                "size": len(CONTENT),
                "browser_download_url": f"https://github.com/misha2271/NEXUS-AI/releases/download/{quote(tag)}/{NAME}",
                "digest": "sha256:" + hashlib.sha256(CONTENT).hexdigest(),
            }
        ],
    }
    payload.update(changes)
    return payload


def checker_for(payload=None, download=None, **kwargs):
    requests = []
    payload = metadata() if payload is None else payload

    def respond(request):
        requests.append(request)
        if str(request.url) == updates.LATEST_URL:
            return httpx.Response(200, json=payload)
        return download(request) if download else httpx.Response(200, content=CONTENT)

    return ReleaseChecker(transport=httpx.MockTransport(respond), **kwargs), requests


def approval(check, *, approved=True, major=False):
    return DownloadApproval(check.release.tag, NAME, approved, major)


@pytest.mark.parametrize("value", ["1.0.0", "v1.0.0", "1.2.3+build.4"])
def test_stable_versions(value):
    assert Version.parse(value).major == 1
    assert Version.parse(value).minor in (0, 2)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        "",
        "1",
        "1.2",
        "1.2.3-beta",
        "01.2.3",
        "１.2.3",
        " 1.2.3",
        "1.2.3+",
        "1.2.3+foo..bar",
    ],
)
def test_invalid_or_prerelease_versions_are_not_stable(value):
    with pytest.raises(UpdateError):
        Version.parse(value)


def test_version_order_is_numeric_not_lexicographic():
    assert Version.parse("1.10.0") > Version.parse("1.9.0")
    assert Version.parse("2.0.0") > Version.parse("1.999.999")


def test_read_only_check_uses_only_pinned_api_and_reports_candidates():
    with checker_for()[0] as checker:
        result = checker.check("1.0.0")
    assert result.status == "available"
    assert str(result.release.version) == "1.1.0"
    assert result.release.assets[0].verifiable
    assert not result.major_update


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_denied_unavailable_and_redirected_api_requests_are_not_updates(status):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, headers={"location": "https://evil.test/releases"})

    with ReleaseChecker(transport=httpx.MockTransport(handle)) as checker:
        result = checker.check()
    assert result.status == "unavailable" and result.release is None
    assert len(requests) == 1


def test_404_does_not_claim_access_or_invent_release():
    with ReleaseChecker(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as checker:
        result = checker.check()
    assert result.status == "no_release" and result.release is None
    assert "or access is denied" in result.message


def test_network_failure_is_actionable():
    def timeout(request):
        raise httpx.ConnectTimeout("not reachable", request=request)

    with ReleaseChecker(transport=httpx.MockTransport(timeout)) as checker:
        assert checker.check().status == "unavailable"


@pytest.mark.parametrize("field", ["draft", "prerelease"])
def test_unpublished_and_prerelease_metadata_is_not_a_candidate(field):
    with checker_for(metadata(**{field: True}))[0] as checker:
        result = checker.check()
    assert result.status == "no_release" and result.release is None


@pytest.mark.parametrize("version", ["1.1.0", "2.0.0"])
def test_same_or_older_release_is_never_offered(version):
    with checker_for()[0] as checker:
        assert checker.check(version).status == "up_to_date"


@pytest.mark.parametrize(
    "change",
    [
        {"tag_name": "v1.1.0-rc1"},
        {"draft": "false"},
        {"prerelease": None},
        {"html_url": "https://github.com/evil/NEXUS-AI/releases/tag/v1.1.0"},
        {"html_url": "http://github.com/misha2271/NEXUS-AI/releases/tag/v1.1.0"},
        {"assets": {}},
    ],
)
def test_invalid_release_metadata_is_not_silently_trusted(change):
    with checker_for(metadata(**change))[0] as checker:
        assert checker.check().status == "unavailable"


@pytest.mark.parametrize(
    "change",
    [
        {"name": "../bad.exe"},
        {"name": "CON.exe"},
        {"name": "NUL.zip"},
        {"name": "asset.exe."},
        {"name": "a\\b.exe"},
        {"size": True},
        {"size": 0},
        {"size": updates.MAX_DOWNLOAD_BYTES + 1},
        {"digest": "sha256:incorrect"},
        {
            "browser_download_url": "https://github.com/evil/NEXUS-AI/releases/download/v1.1.0/NEXUS-AI.exe"
        },
        {
            "browser_download_url": "https://user:password@github.com/misha2271/NEXUS-AI/releases/download/v1.1.0/NEXUS-AI.exe"
        },
        {"browser_download_url": URL + "?secret=not-accepted"},
        {"browser_download_url": URL + "\n"},
    ],
)
def test_unsafe_assets_are_rejected(change):
    payload = metadata()
    payload["assets"][0].update(change)
    with checker_for(payload)[0] as checker:
        assert checker.check().status == "unavailable"


def test_missing_digest_is_visible_but_download_is_forbidden(tmp_path):
    payload = metadata()
    payload["assets"][0].pop("digest")
    with checker_for(payload)[0] as checker:
        result = checker.check()
        assert result.status == "available" and not result.release.assets[0].verifiable
        with pytest.raises(UpdateError, match="no verifiable"):
            checker.stage_asset(result, NAME, tmp_path / "staging", approval(result))
    assert list(tmp_path.iterdir()) == []


def test_newer_release_requires_explicit_download_approval_before_io(tmp_path):
    checker, requests = checker_for()
    with checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="Explicit approval"):
            checker.stage_asset(
                result, NAME, tmp_path / "staging", approval(result, approved=False)
            )
    assert len(requests) == 1 and not list(tmp_path.iterdir())


def test_major_update_requires_distinct_release_bound_approval(tmp_path):
    checker, requests = checker_for(metadata("v2.0.0"))
    with checker:
        result = checker.check()
        assert result.major_update
        with pytest.raises(UpdateError, match="separate explicit"):
            checker.stage_asset(result, NAME, tmp_path / "staging", approval(result))
        with pytest.raises(UpdateError, match="Explicit approval"):
            checker.stage_asset(
                result, NAME, tmp_path / "staging", DownloadApproval("v3.0.0", NAME, True, True)
            )
        staged = checker.stage_asset(
            result, NAME, tmp_path / "staging", approval(result, major=True)
        )
    assert len(requests) == 2 and staged.path.read_bytes() == CONTENT
    assert staged.installed is False


def test_verified_stage_is_atomic_does_not_execute_and_never_overwrites(tmp_path):
    checker, requests = checker_for()
    folder = tmp_path / "staging"
    with checker:
        result = checker.check()
        staged = checker.stage_asset(result, NAME, folder, approval(result))
        assert staged.path.read_bytes() == CONTENT
        assert staged.sha256 == hashlib.sha256(CONTENT).hexdigest()
        assert staged.release_tag == TAG and not staged.installed
        assert list(folder.iterdir()) == [staged.path]
        with pytest.raises(UpdateError, match="not overwritten"):
            checker.stage_asset(result, NAME, folder, approval(result))
        assert staged.path.read_bytes() == CONTENT
    assert len(requests) == 2


def test_trusted_redirects_do_not_send_credentials(tmp_path):
    destination = "https://release-assets.githubusercontent.com/github-production-release-asset/123/test?signature=public-fixture"
    requests = []

    def download(request):
        requests.append(request)
        assert "authorization" not in request.headers
        if request.url.host == "github.com":
            return httpx.Response(302, headers={"location": destination})
        return httpx.Response(200, content=CONTENT)

    with checker_for(download=download)[0] as checker:
        result = checker.check()
        assert checker.stage_asset(
            result, NAME, tmp_path / "staging", approval(result)
        ).path.is_file()
    assert [request.url.host for request in requests] == [
        "github.com",
        "release-assets.githubusercontent.com",
    ]


@pytest.mark.parametrize(
    "destination",
    [
        "http://release-assets.githubusercontent.com/asset",
        "https://evil.test/asset",
        "https://release-assets.githubusercontent.com.evil.test/asset",
        "https://user@release-assets.githubusercontent.com/asset",
        "https://github.com/evil/repo/asset",
        "https://github.com/login",
    ],
)
def test_redirects_cannot_escape_trusted_https_destinations(tmp_path, destination):
    with checker_for(download=lambda _: httpx.Response(302, headers={"location": destination}))[
        0
    ] as checker:
        result = checker.check()
        with pytest.raises(UpdateError):
            checker.stage_asset(result, NAME, tmp_path / "staging", approval(result))
    assert not list((tmp_path / "staging").iterdir())


def test_redirect_loop_is_bounded_and_cleanup_is_complete(tmp_path):
    checker, requests = checker_for(
        download=lambda _: httpx.Response(302, headers={"location": URL})
    )
    with checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="redirects"):
            checker.stage_asset(result, NAME, tmp_path / "staging", approval(result))
    assert len(requests) == 7 and not list((tmp_path / "staging").iterdir())


@pytest.mark.parametrize("body", [b"wrong" * 9, CONTENT[:-1], CONTENT + b"oversize"])
def test_hash_and_declared_size_failures_remove_all_download_outputs(tmp_path, body):
    with checker_for(download=lambda _: httpx.Response(200, content=body))[0] as checker:
        result = checker.check()
        with pytest.raises(UpdateError):
            checker.stage_asset(result, NAME, tmp_path / "staging", approval(result))
    assert not list((tmp_path / "staging").iterdir())


def test_cancellation_before_download_performs_no_filesystem_or_network_io(tmp_path):
    checker, requests = checker_for()
    cancel = Event()
    cancel.set()
    with checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="cancelled"):
            checker.stage_asset(
                result, NAME, tmp_path / "staging", approval(result), cancel_event=cancel
            )
    assert len(requests) == 1 and not list(tmp_path.iterdir())


def test_cancellation_during_stream_removes_partial_file(tmp_path):
    cancel = Event()

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield CONTENT[:4]
            cancel.set()
            yield CONTENT[4:]

    with checker_for(download=lambda _: httpx.Response(200, stream=Stream()))[0] as checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="cancelled"):
            checker.stage_asset(
                result, NAME, tmp_path / "staging", approval(result), cancel_event=cancel
            )
    assert not list((tmp_path / "staging").iterdir())


def test_network_read_failure_removes_partial_file(tmp_path):
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield CONTENT[:4]
            raise httpx.ReadError("connection lost")

    with checker_for(download=lambda _: httpx.Response(200, stream=Stream()))[0] as checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="no update was installed"):
            checker.stage_asset(result, NAME, tmp_path / "staging", approval(result))
    assert not list((tmp_path / "staging").iterdir())


def test_metadata_limit_and_duplicate_assets_are_rejected(monkeypatch):
    monkeypatch.setattr(updates, "MAX_METADATA_BYTES", 20)
    with checker_for()[0] as checker:
        assert checker.check().status == "unavailable"
    monkeypatch.setattr(updates, "MAX_METADATA_BYTES", 4 * 1024**2)
    payload = metadata()
    payload["assets"].append(dict(payload["assets"][0]))
    with checker_for(payload)[0] as checker:
        assert checker.check().status == "unavailable"


def test_symlinked_directory_is_not_followed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("This Windows account cannot create symlinks")
    checker, requests = checker_for()
    with checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="symbolic links"):
            checker.stage_asset(result, NAME, link / "staging", approval(result))
    assert len(requests) == 1 and not list(real.iterdir())


def test_relative_directory_and_forged_downgrade_fail_before_download(tmp_path):
    checker, requests = checker_for()
    with checker:
        result = checker.check()
        with pytest.raises(UpdateError, match="absolute"):
            checker.stage_asset(result, NAME, updates.Path("relative"), approval(result))
        forged = replace(result, current_version=Version(9, 0, 0))
        with pytest.raises(UpdateError, match="newer checked"):
            checker.stage_asset(forged, NAME, tmp_path, approval(result))
    assert len(requests) == 1 and not list(tmp_path.iterdir())
