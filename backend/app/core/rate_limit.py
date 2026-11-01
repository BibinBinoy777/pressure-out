"""Process-safe and multi-worker rate limiting for Pressure Out (Phase 3 & Phase 12.1).

Supports:
1. `InMemoryRateLimitStore` (`RATE_LIMIT_BACKEND=memory`):
   Deterministic sliding-window limiter for local development and isolated single-process tests.
2. `RedisRateLimitStore` (`RATE_LIMIT_BACKEND=redis`):
   Shared multi-worker / multi-instance sliding-window rate limiter backed by Redis.
   Uses an atomic server-side Lua script (`EVAL`) so concurrent requests across Uvicorn workers
   cannot race, hashes caller keys with SHA-256 so no PII/IPs/handles appear in Redis keys,
   enforces bounded TTLs (`PEXPIRE`), and implements a strict fail-closed policy
   (`503 RATE_LIMIT_BACKEND_UNAVAILABLE`) when Redis is unreachable.
"""
from __future__ import annotations

import hashlib
import socket
import ssl
import threading
import time
import urllib.parse
import uuid
from collections import defaultdict, deque
from typing import Any, Callable, Optional, Protocol

from app.core.errors import AppError

# Atomic sliding-window Lua script for Redis:
# KEYS[1] = rate-limit key (SHA-256 hashed bucket + subject)
# ARGV[1] = now_ms (integer milliseconds)
# ARGV[2] = window_ms (integer milliseconds)
# ARGV[3] = limit (integer max requests in window)
# ARGV[4] = unique member id for ZADD
# Returns: {allowed (1 or 0), current_count}
SLIDING_WINDOW_LUA_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local cutoff = now_ms - window_ms

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    redis.call('PEXPIRE', key, window_ms)
    return {0, count}
end
redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return {1, count + 1}
"""


def _hash_rate_limit_subject(bucket: str, raw_key: str) -> str:
    """Hash the caller key so raw IP addresses, handles, or emails are never stored in Redis."""
    safe_bucket = "".join(ch for ch in bucket if ch.isalnum() or ch in {"_", "-"})[:48] or "default"
    digest = hashlib.sha256(f"{safe_bucket}:{raw_key}".encode("utf-8")).hexdigest()[:32]
    return f"po:rl:{safe_bucket}:{digest}"


class RedisEvalTransport(Protocol):
    """Protocol for executing atomic rate-limit Lua evaluations and health pings."""

    def eval_sliding_window(
        self,
        *,
        redis_key: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member_id: str,
    ) -> tuple[bool, int]: ...

    def ping(self) -> bool: ...

    def reset(self) -> None: ...


class RedisRespClient:
    """Zero-dependency Redis RESP2 TCP/TLS client supporting AUTH, SELECT, PING, and EVAL."""

    def __init__(
        self,
        redis_url: str,
        *,
        socket_timeout_seconds: float = 2.0,
    ) -> None:
        parsed = urllib.parse.urlparse(redis_url)
        if parsed.scheme not in {"redis", "rediss"}:
            raise ValueError(f"Unsupported REDIS_URL scheme '{parsed.scheme}' (expected redis:// or rediss://).")
        self.use_tls = parsed.scheme == "rediss"
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 6379
        self.username = urllib.parse.unquote(parsed.username) if parsed.username else None
        self.password = urllib.parse.unquote(parsed.password) if parsed.password else None
        path_db = (parsed.path or "").lstrip("/")
        self.db = int(path_db) if path_db.isdigit() else 0
        self.timeout = max(0.1, float(socket_timeout_seconds))

    def _encode_command(self, *args: str) -> bytes:
        parts = [f"*{len(args)}\r\n".encode("utf-8")]
        for arg in args:
            raw = str(arg).encode("utf-8")
            parts.append(f"${len(raw)}\r\n".encode("utf-8"))
            parts.append(raw + b"\r\n")
        return b"".join(parts)

    def _read_line(self, sock_file: Any) -> bytes:
        line = sock_file.readline()
        if not line:
            raise ConnectionError("Redis connection closed unexpectedly.")
        return line[:-2] if line.endswith(b"\r\n") else line

    def _read_resp(self, sock_file: Any) -> Any:
        line = self._read_line(sock_file)
        if not line:
            raise ConnectionError("Empty response from Redis.")
        prefix = line[:1]
        payload = line[1:]
        if prefix == b"+":
            return payload.decode("utf-8", errors="replace")
        if prefix == b"-":
            raise RuntimeError(f"Redis error response: {payload.decode('utf-8', errors='replace')}")
        if prefix == b":":
            return int(payload)
        if prefix == b"$":
            length = int(payload)
            if length == -1:
                return None
            data = sock_file.read(length)
            sock_file.read(2)  # trailing CRLF
            return data.decode("utf-8", errors="replace")
        if prefix == b"*":
            count = int(payload)
            if count == -1:
                return None
            return [self._read_resp(sock_file) for _ in range(count)]
        raise RuntimeError("Unrecognized RESP frame from Redis.")

    def _execute(self, *args: str) -> Any:
        raw_sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            if self.use_tls:
                ctx = ssl.create_default_context()
                sock: Any = ctx.wrap_socket(raw_sock, server_hostname=self.host)
            else:
                sock = raw_sock
            sock.settimeout(self.timeout)
            sock_file = sock.makefile("rwb")
            if self.password is not None:
                if self.username:
                    sock_file.write(self._encode_command("AUTH", self.username, self.password))
                else:
                    sock_file.write(self._encode_command("AUTH", self.password))
                sock_file.flush()
                self._read_resp(sock_file)
            if self.db != 0:
                sock_file.write(self._encode_command("SELECT", str(self.db)))
                sock_file.flush()
                self._read_resp(sock_file)
            sock_file.write(self._encode_command(*args))
            sock_file.flush()
            return self._read_resp(sock_file)
        finally:
            try:
                raw_sock.close()
            except Exception:
                pass

    def eval_sliding_window(
        self,
        *,
        redis_key: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member_id: str,
    ) -> tuple[bool, int]:
        res = self._execute(
            "EVAL",
            SLIDING_WINDOW_LUA_SCRIPT,
            "1",
            redis_key,
            str(now_ms),
            str(window_ms),
            str(limit),
            member_id,
        )
        if not isinstance(res, list) or len(res) < 2:
            raise RuntimeError("Unexpected EVAL response structure from Redis.")
        return bool(int(res[0]) == 1), int(res[1])

    def ping(self) -> bool:
        res = self._execute("PING")
        return str(res).upper() == "PONG"

    def reset(self) -> None:
        pass


class SharedMemoryRedisEvalClient:
    """Thread-safe deterministic test double implementing the exact Redis Lua ZSET + PEXPIRE semantics.

    Allows multiple independent worker `SlidingWindowRateLimiter` instances in automated tests
    to share a single atomic backing store, simulate clock advancement, or inject connection failures.
    """

    def __init__(
        self,
        *,
        time_ms_fn: Optional[Callable[[], int]] = None,
        max_keys: Optional[int] = None,
        eviction_policy: str = "noeviction",
    ) -> None:
        self._lock = threading.Lock()
        self._zsets: dict[str, dict[str, int]] = {}
        self._expires_at_ms: dict[str, int] = {}
        self._time_ms_fn = time_ms_fn
        self.max_keys = max_keys
        self.eviction_policy = eviction_policy
        self.simulate_unavailable: bool = False
        self.simulate_oom: bool = False
        self.eval_calls: int = 0

    def _purge_if_expired(self, redis_key: str, now_ms: int) -> None:
        exp = self._expires_at_ms.get(redis_key)
        if exp is not None and now_ms >= exp:
            self._zsets.pop(redis_key, None)
            self._expires_at_ms.pop(redis_key, None)

    def eval_sliding_window(
        self,
        *,
        redis_key: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member_id: str,
    ) -> tuple[bool, int]:
        if self.simulate_unavailable:
            raise ConnectionError("Simulated Redis connection failure.")
        effective_now = self._time_ms_fn() if self._time_ms_fn is not None else now_ms
        with self._lock:
            self.eval_calls += 1
            for k in list(self._expires_at_ms.keys()):
                self._purge_if_expired(k, effective_now)
            if self.simulate_oom or (
                self.max_keys is not None
                and redis_key not in self._zsets
                and len(self._zsets) >= self.max_keys
            ):
                raise RuntimeError("OOM command not allowed when used memory > 'maxmemory'.")
            zset = self._zsets.setdefault(redis_key, {})
            cutoff = effective_now - window_ms
            expired_members = [m for m, score in zset.items() if score <= cutoff]
            for m in expired_members:
                del zset[m]
            current_count = len(zset)
            if current_count >= limit:
                self._expires_at_ms[redis_key] = effective_now + window_ms
                return False, current_count
            zset[member_id] = effective_now
            self._expires_at_ms[redis_key] = effective_now + window_ms
            return True, current_count + 1

    def ping(self) -> bool:
        if self.simulate_unavailable:
            raise ConnectionError("Simulated Redis ping failure.")
        return True

    def inspect_keys(self) -> list[str]:
        with self._lock:
            return list(self._zsets.keys())

    def reset(self) -> None:
        with self._lock:
            self._zsets.clear()
            self._expires_at_ms.clear()
            self.eval_calls = 0
            self.simulate_unavailable = False


class RateLimitStore(Protocol):
    backend_name: str

    def check_and_record(
        self,
        *,
        bucket: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> None: ...

    def is_healthy(self) -> bool: ...

    def reset(self) -> None: ...


class InMemoryRateLimitStore:
    """Process-local sliding-window rate limiter for local development and unit tests."""

    backend_name = "memory"

    def __init__(self, *, time_fn: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._time_fn = time_fn

    def check_and_record(
        self,
        *,
        bucket: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        now = self._time_fn()
        composite_key = _hash_rate_limit_subject(bucket, key)
        cutoff = now - float(window_seconds)
        with self._lock:
            timestamps = self._buckets[composite_key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                raise AppError(
                    code="RATE_LIMITED",
                    message="Too many attempts in a short period. Please wait before trying again.",
                    status_code=429,
                    details={
                        "bucket": bucket,
                        "limit": limit,
                        "window_seconds": window_seconds,
                    },
                )
            timestamps.append(now)

    def is_healthy(self) -> bool:
        return True

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


class RedisRateLimitStore:
    """Shared multi-worker rate limiter backed by atomic Redis ZSET evaluation."""

    backend_name = "redis"

    def __init__(
        self,
        *,
        redis_url: str = "redis://127.0.0.1:6379/0",
        socket_timeout_seconds: float = 2.0,
        fail_closed: bool = True,
        transport: Optional[RedisEvalTransport] = None,
        time_ms_fn: Optional[Callable[[], int]] = None,
    ) -> None:
        self.redis_url = redis_url
        self.socket_timeout_seconds = socket_timeout_seconds
        self.fail_closed = fail_closed
        self._transport: RedisEvalTransport = transport or RedisRespClient(
            redis_url, socket_timeout_seconds=socket_timeout_seconds
        )
        self._time_ms_fn = time_ms_fn or (lambda: int(time.time() * 1000))

    def check_and_record(
        self,
        *,
        bucket: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        redis_key = _hash_rate_limit_subject(bucket, key)
        now_ms = self._time_ms_fn()
        window_ms = max(1000, int(window_seconds) * 1000)
        member_id = f"{now_ms}:{uuid.uuid4().hex[:12]}"

        try:
            allowed, _ = self._transport.eval_sliding_window(
                redis_key=redis_key,
                now_ms=now_ms,
                window_ms=window_ms,
                limit=int(limit),
                member_id=member_id,
            )
        except Exception:
            if self.fail_closed:
                raise AppError(
                    code="RATE_LIMIT_BACKEND_UNAVAILABLE",
                    message="Rate-limiting service is temporarily unavailable. Please try again shortly.",
                    status_code=503,
                    details={"bucket": bucket, "fail_mode": "closed"},
                )
            return

        if not allowed:
            raise AppError(
                code="RATE_LIMITED",
                message="Too many attempts in a short period. Please wait before trying again.",
                status_code=429,
                details={
                    "bucket": bucket,
                    "limit": limit,
                    "window_seconds": window_seconds,
                },
            )

    def is_healthy(self) -> bool:
        try:
            return bool(self._transport.ping())
        except Exception:
            return False

    def reset(self) -> None:
        self._transport.reset()


class SlidingWindowRateLimiter:
    """Configurable rate-limiter facade delegating to `InMemoryRateLimitStore` or `RedisRateLimitStore`."""

    def __init__(self, store: Optional[RateLimitStore] = None) -> None:
        self._store: RateLimitStore = store or InMemoryRateLimitStore()

    @property
    def backend_name(self) -> str:
        return self._store.backend_name

    @property
    def store(self) -> RateLimitStore:
        return self._store

    def configure(self, store: RateLimitStore) -> None:
        """Bind the active backing store (called during application initialization)."""
        self._store = store

    def configure_from_settings(
        self,
        settings: Any,
        *,
        redis_transport: Optional[RedisEvalTransport] = None,
    ) -> None:
        backend = getattr(settings, "rate_limit_backend", "memory").strip().lower()
        if backend == "redis":
            self._store = RedisRateLimitStore(
                redis_url=getattr(settings, "redis_url", "") or "redis://127.0.0.1:6379/0",
                socket_timeout_seconds=float(
                    getattr(settings, "redis_socket_timeout_seconds", 2.0)
                ),
                fail_closed=bool(getattr(settings, "rate_limit_fail_closed", True)),
                transport=redis_transport,
            )
        elif backend == "memory":
            self._store = InMemoryRateLimitStore()
        else:
            raise ValueError(f"Unsupported rate_limit_backend '{backend}'.")

    def check_and_record(
        self,
        *,
        bucket: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        self._store.check_and_record(
            bucket=bucket,
            key=key,
            limit=limit,
            window_seconds=window_seconds,
        )

    def is_healthy(self) -> bool:
        return self._store.is_healthy()

    def reset(self) -> None:
        self._store.reset()


rate_limiter = SlidingWindowRateLimiter()



class LocalResp2TestServer:
    """Loopback TCP server speaking Redis RESP2 protocol for wire-level qualification of `RedisRespClient`."""

    def __init__(
        self,
        backing_store: SharedMemoryRedisEvalClient,
        *,
        requirepass: str = "staging_redis_pass",
    ) -> None:
        self.backing_store = backing_store
        self.requirepass = requirepass
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(64)
        self.host, self.port = self._sock.getsockname()
        self._stop = threading.Event()
        self.accept_connections = True
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()

    @property
    def redis_url(self) -> str:
        return f"redis://:{self.requirepass}@{self.host}:{self.port}/0"

    def _read_resp_command(self, rfile: Any) -> Optional[list[str]]:
        line = rfile.readline()
        if not line:
            return None
        if not line.startswith(b"*"):
            return None
        argc = int(line[1:].strip())
        args: list[str] = []
        for _ in range(argc):
            sz_line = rfile.readline()
            if not sz_line or not sz_line.startswith(b"$"):
                return None
            length = int(sz_line[1:].strip())
            raw = rfile.read(length)
            rfile.read(2)  # CRLF
            args.append(raw.decode("utf-8", errors="replace"))
        return args

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(2.0)
            f = conn.makefile("rwb")
            authenticated = not bool(self.requirepass)
            while not self._stop.is_set():
                if not self.accept_connections:
                    break
                cmd = self._read_resp_command(f)
                if cmd is None:
                    break
                op = cmd[0].upper()
                if op == "AUTH":
                    pw = cmd[-1] if len(cmd) >= 2 else ""
                    if pw == self.requirepass:
                        authenticated = True
                        f.write(b"+OK\r\n")
                    else:
                        f.write(b"-WRONGPASS invalid username-password pair\r\n")
                    f.flush()
                    continue
                if not authenticated:
                    f.write(b"-NOAUTH Authentication required.\r\n")
                    f.flush()
                    continue
                if op == "SELECT":
                    f.write(b"+OK\r\n")
                elif op == "PING":
                    if self.backing_store.simulate_unavailable:
                        f.write(b"-LOADING Redis is loading the dataset in memory\r\n")
                    else:
                        f.write(b"+PONG\r\n")
                elif op == "EVAL":
                    # EVAL <script> <numkeys> <key> <now_ms> <window_ms> <limit> <member_id>
                    try:
                        allowed, cnt = self.backing_store.eval_sliding_window(
                            redis_key=cmd[3],
                            now_ms=int(cmd[4]),
                            window_ms=int(cmd[5]),
                            limit=int(cmd[6]),
                            member_id=cmd[7],
                        )
                        f.write(f"*2\r\n:{1 if allowed else 0}\r\n:{cnt}\r\n".encode("utf-8"))
                    except Exception as exc:
                        msg = str(exc).replace("\r", " ").replace("\n", " ")
                        f.write(f"-ERR {msg}\r\n".encode("utf-8"))
                else:
                    f.write(b"-ERR unknown command\r\n")
                f.flush()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _serve_loop(self) -> None:
        self._sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
                if not self.accept_connections:
                    conn.close()
                    continue
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except Exception:
            pass

