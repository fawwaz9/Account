"""The private Cloud Storage bucket kept syllabi live in, over the JSON API.

On Cloud Run the API calls Storage as its own service account, so there is no key.
This module takes object names only, never anything a request supplied: callers
name an object after a row they already read as the user. Unset `SYLLABUS_BUCKET`
means nothing is kept.
"""

from urllib.parse import quote

from app.config import settings

API = "https://storage.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"
TIMEOUT_SECONDS = 30


class StorageError(Exception):
    """Raised when Storage refuses a request or cannot be reached."""


class NotConfigured(StorageError):
    """Raised when no bucket is configured, so documents are not kept."""


def configured() -> bool:
    """Return whether a syllabus bucket is configured.

    Returns:
        True when `SYLLABUS_BUCKET` is set.
    """
    return bool(settings.SYLLABUS_BUCKET)


_session = None
"""The authorised Storage session, created on first use."""


def _default_session():
    """Return an authorised session as the runtime's own identity, created once."""
    global _session
    if _session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(scopes=[SCOPE])
        _session = AuthorizedSession(credentials)
    return _session


def _request(method: str, url: str, **kwargs):
    """Make one Storage call (30 s timeout); any failure becomes StorageError."""
    try:
        return _default_session().request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
    except Exception as exc:  # transport errors, and credentials that cannot load
        raise StorageError(f"Couldn't reach storage: {type(exc).__name__}") from exc


def _bucket() -> str:
    """Return the bucket name, URL-encoded, or raise NotConfigured."""
    if not configured():
        raise NotConfigured
    return quote(settings.SYLLABUS_BUCKET, safe="")


def _object(name: str) -> str:
    """Return an object name URL-encoded as one path segment, slashes included."""
    # Slashes included: an object name is one path segment in the JSON API.
    return quote(name, safe="")


def put(name: str, content: bytes, media_type: str) -> None:
    """Upload a new object, refusing to overwrite one that exists.

    Args:
        name: Object name, such as "syllabi/<parse id>".
        content: The file's bytes.
        media_type: Its MIME type.

    Raises:
        NotConfigured: If no bucket is configured.
        StorageError: If Storage refuses (including because the name is taken) or
            cannot be reached.
    """
    url = f"{API}/upload/storage/v1/b/{_bucket()}/o"
    response = _request(
        "POST", url,
        params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
        data=content, headers={"Content-Type": media_type},
    )
    if response.status_code >= 400:
        raise StorageError(f"Storage refused the upload ({response.status_code})")


def get(name: str) -> bytes:
    """Download an object's bytes.

    Args:
        name: Object name.

    Returns:
        The file's bytes.

    Raises:
        NotConfigured: If no bucket is configured.
        StorageError: If Storage refuses or cannot be reached.
    """
    response = _request("GET", f"{API}/storage/v1/b/{_bucket()}/o/{_object(name)}", params={"alt": "media"})
    if response.status_code >= 400:
        raise StorageError(f"Storage refused the download ({response.status_code})")
    return response.content


def delete(name: str) -> None:
    """Delete an object; one already gone counts as deleted, so retries are safe.

    Args:
        name: Object name.

    Raises:
        NotConfigured: If no bucket is configured.
        StorageError: If Storage refuses for any reason but "not found", or cannot be
            reached.
    """
    response = _request("DELETE", f"{API}/storage/v1/b/{_bucket()}/o/{_object(name)}")
    if response.status_code == 404:
        return  # already gone: what deleting was for
    if response.status_code >= 400:
        raise StorageError(f"Storage refused the delete ({response.status_code})")
