"""Where kept documents live: one private Google Cloud Storage bucket.

Phase 1 D24. No key: on Cloud Run the API calls Storage as its own service
account, which is granted this one bucket and nothing else, so there is no
credential to leak. Locally, and in the suite, SYLLABUS_BUCKET is unset and
nothing is kept.

**Who may read a file is decided before this module is reached.** Storage has
no idea which user a file belongs to; the API only ever asks for an object
named after a row it has already read as that user, under row-level security.
So this module takes object names, never anything a request supplied.

Three operations, over the JSON API with the `google-auth` the app already
has -- no storage library:

* `put` never overwrites: `ifGenerationMatch=0` makes Storage refuse if the
  name is taken, so a bug cannot replace one person's file with another's.
* `get` returns the bytes.
* `delete` treats "not there" as done, so deleting is safe to retry.
"""

from urllib.parse import quote

from app.config import settings

API = "https://storage.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"
TIMEOUT_SECONDS = 30


class StorageError(Exception):
    """Storage answered with a failure, or not at all."""


class NotConfigured(StorageError):
    """No bucket: documents are not kept on this server."""


def configured() -> bool:
    return bool(settings.SYLLABUS_BUCKET)


_session = None


def _default_session():
    """An authorised session as the runtime's own identity, made once."""
    global _session
    if _session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(scopes=[SCOPE])
        _session = AuthorizedSession(credentials)
    return _session


def _request(method: str, url: str, **kwargs):
    """The network call. A module name of its own so the suite replaces it in
    one place (conftest's _no_storage_network)."""
    try:
        return _default_session().request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
    except Exception as exc:  # transport errors, and credentials that cannot load
        raise StorageError(f"Couldn't reach storage: {type(exc).__name__}") from exc


def _bucket() -> str:
    if not configured():
        raise NotConfigured
    return quote(settings.SYLLABUS_BUCKET, safe="")


def _object(name: str) -> str:
    # Slashes included: an object name is one path segment in the JSON API.
    return quote(name, safe="")


def put(name: str, content: bytes, media_type: str) -> None:
    url = f"{API}/upload/storage/v1/b/{_bucket()}/o"
    response = _request(
        "POST", url,
        params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
        data=content, headers={"Content-Type": media_type},
    )
    if response.status_code >= 400:
        raise StorageError(f"Storage refused the upload ({response.status_code})")


def get(name: str) -> bytes:
    response = _request("GET", f"{API}/storage/v1/b/{_bucket()}/o/{_object(name)}", params={"alt": "media"})
    if response.status_code >= 400:
        raise StorageError(f"Storage refused the download ({response.status_code})")
    return response.content


def delete(name: str) -> None:
    response = _request("DELETE", f"{API}/storage/v1/b/{_bucket()}/o/{_object(name)}")
    if response.status_code == 404:
        return  # already gone: what deleting was for
    if response.status_code >= 400:
        raise StorageError(f"Storage refused the delete ({response.status_code})")
