"""Media storage abstraction, LocalFilesystemStorageAdapter, and S3CompatibleStorageAdapter (Phase 8 & 12.1).

Enforces:
- Allowed MIME types (`image/png`, `image/webp`, `image/jpeg`)
- Magic-byte verification and Pillow image decoding
- EXIF/metadata stripping via clean pixel re-encoding
- Maximum file size (`<= 5 MB`) and dimensions (`16..4096` px)
- SHA-256 content hashing
- Path traversal protection (`..`, absolute paths, or symlink escapes rejected)
- S3 / Cloudflare R2 compatibility with AWS Signature Version 4 (`AWS4-HMAC-SHA256`),
  bounded request timeouts, private-bucket presigned URLs, and zero hardcoded credentials.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import io
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import urllib3
from PIL import Image

from app.core.errors import AppError

ALLOWED_MIME_TO_FORMAT: dict[str, str] = {
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/jpeg": "JPEG",
}
ALLOWED_FORMAT_TO_EXT: dict[str, str] = {
    "PNG": "png",
    "WEBP": "webp",
    "JPEG": "jpg",
}
MAX_ASSET_BYTES: int = 5 * 1024 * 1024  # 5 MB
MIN_IMAGE_DIMENSION: int = 16
MAX_IMAGE_DIMENSION: int = 4096

_SAFE_KEY_RE = re.compile(r"^[a-zA-Z0-9_\-/]+\.(png|webp|jpg)$")


@dataclass(frozen=True)
class StoredAssetMetadata:
    storage_key: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    width: int
    height: int
    sanitized_bytes: bytes


class StorageAdapter(Protocol):
    """Abstract storage interface for rendered, uploaded, and AI-generated meme assets."""

    def validate_and_store(
        self,
        *,
        raw_bytes: bytes,
        expected_mime_type: str,
        storage_prefix: str = "memes",
        asset_id: str,
    ) -> StoredAssetMetadata: ...

    def read_bytes(self, storage_key: str) -> bytes: ...

    def delete_object(self, storage_key: str) -> bool: ...

    def is_healthy(self) -> bool: ...


def validate_storage_key_safety(storage_key: str) -> str:
    """Validate that a storage key is strictly relative and free of path traversal."""
    cleaned = storage_key.strip().lstrip("/")
    if ".." in cleaned or not _SAFE_KEY_RE.match(cleaned):
        raise AppError(
            code="INVALID_STORAGE_KEY",
            message="Invalid or unsafe storage key path.",
            status_code=400,
        )
    return cleaned


def verify_magic_bytes(raw_bytes: bytes) -> str:
    """Inspect magic bytes and return detected MIME type or raise AppError."""
    if len(raw_bytes) < 12:
        raise AppError(
            code="INVALID_IMAGE_FILE",
            message="Image payload is empty or truncated.",
            status_code=422,
        )
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise AppError(
        code="UNSUPPORTED_IMAGE_FORMAT",
        message="Only valid PNG, WebP, or JPEG image binaries are permitted.",
        status_code=422,
    )


def validate_and_sanitize_image_bytes(
    raw_bytes: bytes,
    *,
    expected_mime_type: str = "image/png",
) -> tuple[bytes, str, int, int, str]:
    """Validate magic bytes, decode with Pillow, strip EXIF, and return clean bytes."""
    if len(raw_bytes) > MAX_ASSET_BYTES:
        raise AppError(
            code="IMAGE_TOO_LARGE",
            message=f"Image exceeds the maximum allowed size of {MAX_ASSET_BYTES // (1024 * 1024)} MB.",
            status_code=422,
        )

    detected_mime = verify_magic_bytes(raw_bytes)
    if expected_mime_type not in ALLOWED_MIME_TO_FORMAT:
        raise AppError(
            code="UNSUPPORTED_IMAGE_FORMAT",
            message=f"Unsupported MIME type '{expected_mime_type}'.",
            status_code=422,
        )
    if detected_mime != expected_mime_type:
        raise AppError(
            code="MIME_MISMATCH",
            message=f"Declared MIME type '{expected_mime_type}' does not match binary signature '{detected_mime}'.",
            status_code=422,
        )

    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.verify()
        with Image.open(io.BytesIO(raw_bytes)) as img2:
            width, height = img2.size
            if (
                width < MIN_IMAGE_DIMENSION
                or height < MIN_IMAGE_DIMENSION
                or width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
            ):
                raise AppError(
                    code="INVALID_IMAGE_DIMENSIONS",
                    message=f"Image dimensions ({width}x{height}) must be between {MIN_IMAGE_DIMENSION} and {MAX_IMAGE_DIMENSION} pixels.",
                    status_code=422,
                )
            # Re-encode onto a fresh pixel buffer so any EXIF/GPS/comment metadata is stripped
            target_fmt = ALLOWED_MIME_TO_FORMAT[detected_mime]
            clean_mode = "RGBA" if target_fmt in {"PNG", "WEBP"} and img2.mode == "RGBA" else "RGB"
            clean_img = img2.convert(clean_mode)
            out_buf = io.BytesIO()
            if target_fmt == "WEBP":
                clean_img.save(out_buf, format="WEBP", quality=90)
            elif target_fmt == "JPEG":
                clean_img.save(out_buf, format="JPEG", quality=90, optimize=True)
            else:
                clean_img.save(out_buf, format="PNG", optimize=True)
            sanitized_bytes = out_buf.getvalue()
    except AppError:
        raise
    except Exception:
        raise AppError(
            code="CORRUPT_IMAGE_DATA",
            message="The provided image binary could not be decoded safely.",
            status_code=422,
        )

    if len(sanitized_bytes) > MAX_ASSET_BYTES:
        raise AppError(
            code="IMAGE_TOO_LARGE",
            message="Sanitized image exceeds maximum 5 MB limit.",
            status_code=422,
        )

    sha256_hash = hashlib.sha256(sanitized_bytes).hexdigest()
    return sanitized_bytes, detected_mime, width, height, sha256_hash


class LocalFilesystemStorageAdapter:
    """Stores validated meme assets on the local filesystem inside `base_dir`."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_key: str) -> Path:
        cleaned = validate_storage_key_safety(storage_key)
        candidate = (self.base_dir / cleaned).resolve()
        if not str(candidate).startswith(str(self.base_dir)):
            raise AppError(
                code="INVALID_STORAGE_KEY",
                message="Path traversal attempt blocked.",
                status_code=400,
            )
        return candidate

    def validate_and_store(
        self,
        *,
        raw_bytes: bytes,
        expected_mime_type: str = "image/png",
        storage_prefix: str = "memes",
        asset_id: str,
    ) -> StoredAssetMetadata:
        sanitized, mime_type, width, height, sha256_hash = validate_and_sanitize_image_bytes(
            raw_bytes, expected_mime_type=expected_mime_type
        )
        fmt = ALLOWED_MIME_TO_FORMAT[mime_type]
        ext = ALLOWED_FORMAT_TO_EXT[fmt]
        safe_prefix = re.sub(r"[^a-zA-Z0-9_\-]", "", storage_prefix) or "memes"
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", asset_id)
        storage_key = f"{safe_prefix}/{safe_id}.{ext}"

        target_path = self._resolve_safe_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Write via temporary sibling file and atomic replace so partial writes never persist
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        try:
            tmp_path.write_bytes(sanitized)
            tmp_path.replace(target_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

        return StoredAssetMetadata(
            storage_key=storage_key,
            mime_type=mime_type,
            file_size_bytes=len(sanitized),
            sha256_hash=sha256_hash,
            width=width,
            height=height,
            sanitized_bytes=sanitized,
        )

    def read_bytes(self, storage_key: str) -> bytes:
        target_path = self._resolve_safe_path(storage_key)
        if not target_path.is_file():
            raise AppError(
                code="ASSET_FILE_NOT_FOUND",
                message="The requested meme image file is no longer available on storage.",
                status_code=404,
            )
        return target_path.read_bytes()

    def delete_object(self, storage_key: str) -> bool:
        target_path = self._resolve_safe_path(storage_key)
        if target_path.is_file():
            target_path.unlink()
            return True
        return False

    def is_healthy(self) -> bool:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            return self.base_dir.is_dir()
        except Exception:
            return False


class S3HttpTransport(Protocol):
    """HTTP transport interface for S3-compatible object operations."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[int, bytes, Dict[str, str]]: ...


class Urllib3S3Transport:
    """Default production HTTP transport for S3/R2 requests with bounded timeouts."""

    def __init__(self) -> None:
        self._pool = urllib3.PoolManager()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[int, bytes, Dict[str, str]]:
        timeout = urllib3.Timeout(connect=timeout_seconds, read=timeout_seconds)
        resp = self._pool.request(
            method=method.upper(),
            url=url,
            headers=headers,
            body=body,
            timeout=timeout,
            retries=False,
        )
        resp_headers = {str(k).lower(): str(v) for k, v in resp.headers.items()}
        return int(resp.status), bytes(resp.data or b""), resp_headers


class InMemoryS3Transport:
    """Deterministic in-memory S3/R2 transport test double verifying SigV4 headers & object lifecycle."""

    def __init__(self) -> None:
        self.objects: Dict[str, tuple[bytes, Dict[str, str]]] = {}
        self.request_log: list[Dict[str, Any]] = []
        self.simulate_failure: bool = False

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        timeout_seconds: float = 10.0,
    ) -> tuple[int, bytes, Dict[str, str]]:
        self.request_log.append(
            {
                "method": method.upper(),
                "url": url,
                "headers": dict(headers),
                "body_len": len(body) if body else 0,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.simulate_failure:
            raise ConnectionError("Simulated S3/R2 transport outage.")

        # Verify SigV4 Authorization header is present on every request
        auth_hdr = headers.get("Authorization") or headers.get("authorization") or ""
        if not auth_hdr.startswith("AWS4-HMAC-SHA256 Credential="):
            return 403, b"<Error><Code>AccessDenied</Code></Error>", {}

        parsed = urllib.parse.urlparse(url)
        path_key = parsed.path.lstrip("/")
        m = method.upper()
        if m == "HEAD":
            return 200, b"", {}
        if m == "PUT":
            assert body is not None
            self.objects[path_key] = (bytes(body), dict(headers))
            return 200, b"", {"etag": '"mock-etag"'}
        if m == "GET":
            if path_key not in self.objects:
                return 404, b"<Error><Code>NoSuchKey</Code></Error>", {}
            raw, meta = self.objects[path_key]
            return 200, raw, {"content-type": meta.get("Content-Type", "application/octet-stream")}
        if m == "DELETE":
            existed = path_key in self.objects
            self.objects.pop(path_key, None)
            return (204 if existed else 404), b"", {}
        return 405, b"", {}

    def request_presigned_get(
        self,
        presigned_url: str,
        *,
        secret_access_key: str,
        now_utc: Optional[datetime.datetime] = None,
    ) -> tuple[int, bytes, Dict[str, str]]:
        """Simulate S3/R2 presigned GET URL verification including signature check and TTL expiration."""
        if self.simulate_failure:
            raise ConnectionError("Simulated S3/R2 transport outage.")
        parsed = urllib.parse.urlparse(presigned_url)
        qs = dict(urllib.parse.parse_qsl(parsed.query))
        amz_date = qs.get("X-Amz-Date", "")
        expires_str = qs.get("X-Amz-Expires", "0")
        cred = qs.get("X-Amz-Credential", "")
        provided_sig = qs.get("X-Amz-Signature", "")
        if not (amz_date and expires_str and cred and provided_sig):
            return 403, b"<Error><Code>AccessDenied</Code></Error>", {}

        cred_parts = cred.split("/")
        if len(cred_parts) < 5:
            return 403, b"<Error><Code>AuthorizationQueryParametersError</Code></Error>", {}
        date_stamp, region = cred_parts[1], cred_parts[2]

        unsigned_pairs = [
            (k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if k != "X-Amz-Signature"
        ]
        canonical_qs = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(unsigned_pairs)
        )
        canonical_req = "\n".join(
            [
                "GET",
                parsed.path,
                canonical_qs,
                f"host:{parsed.netloc}\n",
                "host",
                "UNSIGNED-PAYLOAD",
            ]
        )
        scope = f"{date_stamp}/{region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_req.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _derive_sigv4_signing_key(secret_access_key, date_stamp, region, "s3")
        expected_sig = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, provided_sig):
            return 403, b"<Error><Code>SignatureDoesNotMatch</Code></Error>", {}

        signed_dt = datetime.datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
        eval_dt = now_utc or datetime.datetime.now(datetime.timezone.utc)
        if (eval_dt - signed_dt).total_seconds() > int(expires_str):
            return 403, b"<Error><Code>AccessDenied</Code><Message>Request has expired</Message></Error>", {}

        path_key = parsed.path.lstrip("/")
        if path_key not in self.objects:
            return 404, b"<Error><Code>NoSuchKey</Code></Error>", {}
        raw, meta = self.objects[path_key]
        return 200, raw, {"content-type": meta.get("Content-Type", "application/octet-stream")}


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_sigv4_signing_key(secret_key: str, date_stamp: str, region: str, service: str = "s3") -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


class S3CompatibleStorageAdapter:
    """Provider-neutral S3 / Cloudflare R2 object storage adapter using AWS Signature Version 4.

    Never makes buckets public; all objects are written with private access semantics and
    validated through `validate_and_sanitize_image_bytes` before upload.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
        key_prefix: str = "memes",
        timeout_seconds: float = 10.0,
        presigned_url_ttl_seconds: int = 3600,
        transport: Optional[S3HttpTransport] = None,
    ) -> None:
        if not endpoint_url or not bucket_name or not access_key_id or not secret_access_key:
            raise ValueError("S3CompatibleStorageAdapter requires endpoint_url, bucket_name, access_key_id, and secret_access_key.")
        self.endpoint_url = endpoint_url.rstrip("/")
        parsed = urllib.parse.urlparse(self.endpoint_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError(f"Invalid S3_ENDPOINT_URL: {endpoint_url}")
        self.host = parsed.netloc
        self.bucket_name = bucket_name.strip("/")
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region or "auto"
        self.key_prefix = re.sub(r"[^a-zA-Z0-9_\-]", "", key_prefix) or "memes"
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.presigned_url_ttl_seconds = max(60, min(86400, int(presigned_url_ttl_seconds)))
        self._transport: S3HttpTransport = transport or Urllib3S3Transport()

    def _object_uri_path(self, storage_key: str) -> str:
        safe_key = validate_storage_key_safety(storage_key)
        encoded_key = urllib.parse.quote(safe_key, safe="/-_.~")
        return f"/{self.bucket_name}/{encoded_key}"

    def _sign_headers(
        self,
        *,
        method: str,
        uri_path: str,
        payload_hash: str,
        extra_headers: Optional[Dict[str, str]] = None,
        now_utc: Optional[datetime.datetime] = None,
    ) -> Dict[str, str]:
        dt = now_utc or datetime.datetime.now(datetime.timezone.utc)
        amz_date = dt.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = dt.strftime("%Y%m%d")

        headers: Dict[str, str] = {
            "Host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if extra_headers:
            headers.update(extra_headers)

        sorted_lower = sorted((k.lower(), v.strip()) for k, v in headers.items())
        canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted_lower)
        signed_headers = ";".join(k for k, _ in sorted_lower)
        canonical_request = "\n".join(
            [
                method.upper(),
                uri_path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _derive_sigv4_signing_key(
            self.secret_access_key, date_stamp, self.region, "s3"
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return headers

    def validate_and_store(
        self,
        *,
        raw_bytes: bytes,
        expected_mime_type: str = "image/png",
        storage_prefix: str = "memes",
        asset_id: str,
    ) -> StoredAssetMetadata:
        sanitized, mime_type, width, height, sha256_hash = validate_and_sanitize_image_bytes(
            raw_bytes, expected_mime_type=expected_mime_type
        )
        fmt = ALLOWED_MIME_TO_FORMAT[mime_type]
        ext = ALLOWED_FORMAT_TO_EXT[fmt]
        safe_prefix = re.sub(r"[^a-zA-Z0-9_\-]", "", storage_prefix or self.key_prefix) or "memes"
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", asset_id)
        storage_key = f"{safe_prefix}/{safe_id}.{ext}"

        uri_path = self._object_uri_path(storage_key)
        headers = self._sign_headers(
            method="PUT",
            uri_path=uri_path,
            payload_hash=sha256_hash,
            extra_headers={
                "Content-Type": mime_type,
                "Content-Length": str(len(sanitized)),
                "x-amz-acl": "private",
            },
        )
        try:
            status_code, _, _ = self._transport.request(
                "PUT",
                f"{self.endpoint_url}{uri_path}",
                headers=headers,
                body=sanitized,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception:
            raise AppError(
                code="STORAGE_BACKEND_UNAVAILABLE",
                message="Object storage is temporarily unreachable. Please try again shortly.",
                status_code=503,
            )

        if status_code not in {200, 201, 204}:
            raise AppError(
                code="STORAGE_WRITE_FAILED",
                message="Object storage rejected the asset upload.",
                status_code=503,
            )

        return StoredAssetMetadata(
            storage_key=storage_key,
            mime_type=mime_type,
            file_size_bytes=len(sanitized),
            sha256_hash=sha256_hash,
            width=width,
            height=height,
            sanitized_bytes=sanitized,
        )

    def read_bytes(self, storage_key: str) -> bytes:
        uri_path = self._object_uri_path(storage_key)
        empty_hash = hashlib.sha256(b"").hexdigest()
        headers = self._sign_headers(
            method="GET",
            uri_path=uri_path,
            payload_hash=empty_hash,
        )
        try:
            status_code, data, _ = self._transport.request(
                "GET",
                f"{self.endpoint_url}{uri_path}",
                headers=headers,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception:
            raise AppError(
                code="STORAGE_BACKEND_UNAVAILABLE",
                message="Object storage is temporarily unreachable.",
                status_code=503,
            )

        if status_code == 404:
            raise AppError(
                code="ASSET_FILE_NOT_FOUND",
                message="The requested meme image file is no longer available on storage.",
                status_code=404,
            )
        if status_code != 200:
            raise AppError(
                code="STORAGE_READ_FAILED",
                message="Failed to retrieve image asset from object storage.",
                status_code=503,
            )
        return data

    def delete_object(self, storage_key: str) -> bool:
        uri_path = self._object_uri_path(storage_key)
        empty_hash = hashlib.sha256(b"").hexdigest()
        headers = self._sign_headers(
            method="DELETE",
            uri_path=uri_path,
            payload_hash=empty_hash,
        )
        try:
            status_code, _, _ = self._transport.request(
                "DELETE",
                f"{self.endpoint_url}{uri_path}",
                headers=headers,
                timeout_seconds=self.timeout_seconds,
            )
            return status_code in {200, 202, 204}
        except Exception:
            return False

    def generate_presigned_get_url(
        self,
        storage_key: str,
        *,
        expires_seconds: Optional[int] = None,
        now_utc: Optional[datetime.datetime] = None,
    ) -> str:
        """Generate a time-bounded AWS SigV4 presigned GET URL without exposing bucket credentials."""
        uri_path = self._object_uri_path(storage_key)
        dt = now_utc or datetime.datetime.now(datetime.timezone.utc)
        amz_date = dt.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = dt.strftime("%Y%m%d")
        ttl = max(60, min(86400, int(expires_seconds or self.presigned_url_ttl_seconds)))
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"

        query_params = [
            ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
            ("X-Amz-Credential", f"{self.access_key_id}/{credential_scope}"),
            ("X-Amz-Date", amz_date),
            ("X-Amz-Expires", str(ttl)),
            ("X-Amz-SignedHeaders", "host"),
        ]
        canonical_querystring = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(query_params)
        )
        canonical_request = "\n".join(
            [
                "GET",
                uri_path,
                canonical_querystring,
                f"host:{self.host}\n",
                "host",
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _derive_sigv4_signing_key(
            self.secret_access_key, date_stamp, self.region, "s3"
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{self.endpoint_url}{uri_path}?{canonical_querystring}&X-Amz-Signature={signature}"

    def is_healthy(self) -> bool:
        uri_path = f"/{self.bucket_name}"
        empty_hash = hashlib.sha256(b"").hexdigest()
        headers = self._sign_headers(
            method="HEAD",
            uri_path=uri_path,
            payload_hash=empty_hash,
        )
        try:
            status_code, _, _ = self._transport.request(
                "HEAD",
                f"{self.endpoint_url}{uri_path}",
                headers=headers,
                timeout_seconds=self.timeout_seconds,
            )
            return status_code in {200, 204, 301, 403}
        except Exception:
            return False


def create_storage_adapter(
    settings: Any,
    *,
    s3_transport: Optional[S3HttpTransport] = None,
) -> StorageAdapter:
    """Instantiate the configured storage adapter (`local` filesystem or `s3`/`r2` object storage)."""
    backend = getattr(settings, "storage_backend", "local").strip().lower()
    if backend in {"s3", "r2"}:
        return S3CompatibleStorageAdapter(
            endpoint_url=getattr(settings, "s3_endpoint_url", ""),
            bucket_name=getattr(settings, "s3_bucket_name", ""),
            access_key_id=getattr(settings, "s3_access_key_id", ""),
            secret_access_key=getattr(settings, "s3_secret_access_key", ""),
            region=getattr(settings, "s3_region", "auto"),
            key_prefix=getattr(settings, "s3_key_prefix", "memes"),
            timeout_seconds=float(getattr(settings, "s3_timeout_seconds", 10.0)),
            presigned_url_ttl_seconds=int(
                getattr(settings, "s3_presigned_url_ttl_seconds", 3600)
            ),
            transport=s3_transport,
        )
    return LocalFilesystemStorageAdapter(getattr(settings, "local_storage_path"))
