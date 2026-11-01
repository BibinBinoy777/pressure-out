"""Identity, Authentication, Session, and Privacy service layer (Phase 3)."""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import Settings
from app.core.errors import AppError
from app.core.security import (
    decrypt_recovery_email,
    encrypt_recovery_email,
    generate_backup_recovery_code,
    generate_session_credentials,
    hash_email_for_lookup,
    hash_ip_subnet,
    hash_password,
    hash_session_token,
    validate_password_strength,
    verify_password,
)
import hashlib
from app.core.unicode import normalize_optional_unicode_nfc
from app.modules.memes.storage import create_storage_adapter
from app.modules.identity.schemas import (
    ActiveSessionItem,
    DeleteAccountRequest,
    LoginRequest,
    PrivateAccountResponse,
    PublicAuthorDisplay,
    PublicProfileResponse,
    RecoveryResetRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UpdateSettingsRequest,
    validate_bcp47_tag,
    validate_handle,
    validate_identity_mode,
)
from app.modules.identity.serializers import (
    serialize_author_for_identity_mode,
    serialize_private_account,
    serialize_public_profile,
)

USER_COLUMNS = (
    "id",
    "email_hash",
    "email_encrypted",
    "recovery_code_hash",
    "password_hash",
    "account_status",
    "role",
    "default_identity_mode",
    "preferred_ui_locale",
    "preferred_content_locales",
    "cooldown_until",
    "created_at",
    "updated_at",
    "deleted_at",
)

PROFILE_COLUMNS = (
    "id",
    "user_id",
    "handle",
    "handle_normalized",
    "display_name",
    "bio",
    "avatar_storage_key",
    "show_karma",
    "created_at",
    "updated_at",
)

PROF_COLUMNS = (
    "id",
    "user_id",
    "role_title",
    "industry",
    "experience_band",
    "region_label",
    "is_enabled",
    "created_at",
    "updated_at",
)

SESSION_COLUMNS = (
    "id",
    "user_id",
    "token_hash",
    "csrf_secret",
    "user_agent_summary",
    "ip_subnet_hash",
    "expires_at",
    "revoked_at",
    "created_at",
    "last_active_at",
)


def _row_to_dict(columns: tuple[str, ...], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IdentityService:
    """Transactional business logic for accounts, sessions, profiles, and privacy."""

    def __init__(self, session: Any, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def _fetch_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        rows = await self.session.execute(
            f"SELECT {', '.join(USER_COLUMNS)} FROM users WHERE id = ?",
            (user_id,),
        )
        return _row_to_dict(USER_COLUMNS, rows[0]) if rows else None

    async def _fetch_public_profile_by_user_id(self, user_id: str) -> Optional[dict[str, Any]]:
        rows = await self.session.execute(
            f"SELECT {', '.join(PROFILE_COLUMNS)} FROM public_profiles WHERE user_id = ?",
            (user_id,),
        )
        return _row_to_dict(PROFILE_COLUMNS, rows[0]) if rows else None

    async def _fetch_public_profile_by_handle(self, handle: str) -> Optional[dict[str, Any]]:
        norm = handle.strip().lower()
        rows = await self.session.execute(
            f"SELECT {', '.join(PROFILE_COLUMNS)} FROM public_profiles WHERE handle_normalized = ?",
            (norm,),
        )
        return _row_to_dict(PROFILE_COLUMNS, rows[0]) if rows else None

    async def _fetch_professional_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        rows = await self.session.execute(
            f"SELECT {', '.join(PROF_COLUMNS)} FROM professional_profiles WHERE user_id = ?",
            (user_id,),
        )
        return _row_to_dict(PROF_COLUMNS, rows[0]) if rows else None

    async def _create_session(
        self,
        *,
        user_id: str,
        user_agent: Optional[str],
        client_ip: Optional[str],
    ) -> tuple[str, str]:
        raw_token, token_hash, csrf_secret = generate_session_credentials()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=self.settings.session_ttl_hours)
        ua_summary = (user_agent or "unknown")[:200]
        ip_hash = hash_ip_subnet(client_ip, self.settings.email_hmac_pepper)

        session_id = str(uuid.uuid4())
        await self.session.execute(
            """
            INSERT INTO user_sessions (
                id, user_id, token_hash, csrf_secret, user_agent_summary,
                ip_subnet_hash, expires_at, revoked_at, created_at, last_active_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                session_id,
                user_id,
                token_hash,
                csrf_secret,
                ua_summary,
                ip_hash,
                expires.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        return raw_token, csrf_secret

    async def register_user(
        self,
        payload: RegisterRequest,
        *,
        user_agent: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> tuple[PrivateAccountResponse, str]:
        """Register a new pseudonymous user without requiring real name or employer."""
        handle = validate_handle(payload.handle)
        handle_norm = handle.lower()
        validate_password_strength(payload.password)
        ui_locale = validate_bcp47_tag(payload.preferred_ui_locale)

        existing_handle = await self._fetch_public_profile_by_handle(handle_norm)
        if existing_handle is not None:
            raise AppError(
                code="HANDLE_TAKEN",
                message="That pseudonymous handle is already in use. Please choose another.",
                status_code=409,
            )

        email_hash: Optional[str] = None
        email_encrypted: Optional[bytes] = None
        if payload.recovery_email and payload.recovery_email.strip():
            email_hash = hash_email_for_lookup(
                payload.recovery_email, self.settings.email_hmac_pepper
            )
            existing_email = await self.session.execute(
                "SELECT 1 FROM users WHERE email_hash = ?",
                (email_hash,),
            )
            if existing_email:
                raise AppError(
                    code="EMAIL_ALREADY_REGISTERED",
                    message="That recovery email is already associated with an account.",
                    status_code=409,
                )
            email_encrypted = encrypt_recovery_email(
                payload.recovery_email, self.settings.email_encryption_key_base64
            )

        user_id = str(uuid.uuid4())
        profile_id = str(uuid.uuid4())
        now_str = _now_iso()
        pwd_hash = hash_password(payload.password)

        raw_recovery_code = generate_backup_recovery_code()
        recovery_code_hash = hash_password(raw_recovery_code)

        await self.session.execute(
            """
            INSERT INTO users (
                id, email_hash, email_encrypted, recovery_code_hash, password_hash,
                account_status, role, default_identity_mode, preferred_ui_locale,
                preferred_content_locales, cooldown_until, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, 'active', 'member', 'pseudonymous', ?, ?, NULL, ?, ?, NULL)
            """,
            (
                user_id,
                email_hash,
                email_encrypted,
                recovery_code_hash,
                pwd_hash,
                ui_locale,
                json.dumps([ui_locale]),
                now_str,
                now_str,
            ),
        )

        await self.session.execute(
            """
            INSERT INTO public_profiles (
                id, user_id, handle, handle_normalized, display_name, bio,
                avatar_storage_key, show_karma, created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, 1, ?, ?)
            """,
            (profile_id, user_id, handle, handle_norm, now_str, now_str),
        )

        raw_session_token, csrf_secret = await self._create_session(
            user_id=user_id, user_agent=user_agent, client_ip=client_ip
        )

        user_row = await self._fetch_user_by_id(user_id)
        profile_row = await self._fetch_public_profile_by_user_id(user_id)
        assert user_row is not None and profile_row is not None

        response = serialize_private_account(
            user_row=user_row,
            profile_row=profile_row,
            prof_row=None,
            email_encryption_key_b64=self.settings.email_encryption_key_base64,
            csrf_token=csrf_secret,
            one_time_recovery_code=raw_recovery_code,
        )
        return response, raw_session_token

    async def login_user(
        self,
        payload: LoginRequest,
        *,
        user_agent: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> tuple[PrivateAccountResponse, str]:
        """Authenticate by handle + password and issue a new server-managed session."""
        profile_row = await self._fetch_public_profile_by_handle(payload.handle)
        if profile_row is None:
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Invalid handle or password.",
                status_code=401,
            )

        user_row = await self._fetch_user_by_id(str(profile_row["user_id"]))
        if user_row is None or not verify_password(payload.password, str(user_row["password_hash"])):
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Invalid handle or password.",
                status_code=401,
            )

        status = str(user_row["account_status"])
        if status in {"suspended", "deleted"}:
            raise AppError(
                code="ACCOUNT_SUSPENDED",
                message="This account is not permitted to sign in.",
                status_code=403,
            )

        raw_session_token, csrf_secret = await self._create_session(
            user_id=str(user_row["id"]), user_agent=user_agent, client_ip=client_ip
        )
        prof_row = await self._fetch_professional_profile(str(user_row["id"]))

        response = serialize_private_account(
            user_row=user_row,
            profile_row=profile_row,
            prof_row=prof_row,
            email_encryption_key_b64=self.settings.email_encryption_key_base64,
            csrf_token=csrf_secret,
        )
        return response, raw_session_token

    async def authenticate_session(self, raw_session_token: Optional[str]) -> dict[str, Any]:
        """Validate session cookie token and return `{user, profile, prof, session}`."""
        if not raw_session_token:
            raise AppError(
                code="UNAUTHORIZED",
                message="Authentication is required to access this resource.",
                status_code=401,
            )

        token_hash = hash_session_token(raw_session_token)
        rows = await self.session.execute(
            f"SELECT {', '.join(SESSION_COLUMNS)} FROM user_sessions WHERE token_hash = ?",
            (token_hash,),
        )
        if not rows:
            raise AppError(
                code="UNAUTHORIZED",
                message="Session is invalid or has expired.",
                status_code=401,
            )

        sess_row = _row_to_dict(SESSION_COLUMNS, rows[0])
        if sess_row.get("revoked_at") is not None:
            raise AppError(
                code="UNAUTHORIZED",
                message="Session has been revoked. Please sign in again.",
                status_code=401,
            )

        expires_at = datetime.fromisoformat(str(sess_row["expires_at"]))
        now = datetime.now(timezone.utc)
        if expires_at <= now:
            raise AppError(
                code="UNAUTHORIZED",
                message="Session has expired. Please sign in again.",
                status_code=401,
            )

        user_row = await self._fetch_user_by_id(str(sess_row["user_id"]))
        if user_row is None or str(user_row["account_status"]) in {"suspended", "deleted"}:
            raise AppError(
                code="ACCOUNT_SUSPENDED",
                message="Account is no longer active.",
                status_code=403,
            )

        profile_row = await self._fetch_public_profile_by_user_id(str(user_row["id"]))
        if profile_row is None:
            raise AppError(
                code="UNAUTHORIZED",
                message="Account profile is missing.",
                status_code=401,
            )

        prof_row = await self._fetch_professional_profile(str(user_row["id"]))

        await self.session.execute(
            "UPDATE user_sessions SET last_active_at = ? WHERE id = ?",
            (now.isoformat(), str(sess_row["id"])),
        )

        return {
            "user": user_row,
            "profile": profile_row,
            "prof": prof_row,
            "session": sess_row,
        }

    async def logout_session(self, session_id: str) -> None:
        now_str = _now_iso()
        await self.session.execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE id = ?",
            (now_str, session_id),
        )

    async def list_active_sessions(
        self, user_id: str, current_session_id: str
    ) -> list[ActiveSessionItem]:
        now_str = _now_iso()
        rows = await self.session.execute(
            f"""
            SELECT {', '.join(SESSION_COLUMNS)}
            FROM user_sessions
            WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?
            ORDER BY last_active_at DESC
            """,
            (user_id, now_str),
        )
        items: list[ActiveSessionItem] = []
        for r in rows:
            d = _row_to_dict(SESSION_COLUMNS, r)
            items.append(
                ActiveSessionItem(
                    session_id=str(d["id"]),
                    user_agent_summary=d.get("user_agent_summary"),
                    is_current=(str(d["id"]) == current_session_id),
                    created_at=str(d["created_at"]),
                    last_active_at=str(d["last_active_at"]),
                    expires_at=str(d["expires_at"]),
                )
            )
        return items

    async def revoke_all_sessions(self, user_id: str, *, keep_session_id: Optional[str] = None) -> int:
        now_str = _now_iso()
        if keep_session_id:
            await self.session.execute(
                """
                UPDATE user_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND id != ? AND revoked_at IS NULL
                """,
                (now_str, user_id, keep_session_id),
            )
        else:
            await self.session.execute(
                "UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now_str, user_id),
            )
        return 1

    async def initiate_email_recovery(self, recovery_email: str) -> Optional[str]:
        """Generate a recovery token if the email matches an active user (constant-shape response)."""
        email_hash = hash_email_for_lookup(recovery_email, self.settings.email_hmac_pepper)
        rows = await self.session.execute(
            "SELECT id, account_status FROM users WHERE email_hash = ?",
            (email_hash,),
        )
        if not rows or rows[0][1] != "active":
            return None

        user_id = str(rows[0][0])
        raw_token = secrets.token_urlsafe(24)
        token_hash = hash_session_token(raw_token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=30)

        await self.session.execute(
            """
            INSERT INTO password_recovery_tokens (id, user_id, token_hash, expires_at, used_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (str(uuid.uuid4()), user_id, token_hash, expires.isoformat(), now.isoformat()),
        )
        return raw_token

    async def reset_password_with_recovery(self, payload: RecoveryResetRequest) -> None:
        """Reset password using either the user's backup recovery code or a valid email token.

        Immediately revokes all active sessions for the account upon password reset.
        """
        validate_password_strength(payload.new_password)
        profile_row = await self._fetch_public_profile_by_handle(payload.handle)
        if profile_row is None:
            raise AppError(
                code="INVALID_RECOVERY_CODE",
                message="Invalid handle or recovery credential.",
                status_code=400,
            )

        user_id = str(profile_row["user_id"])
        user_row = await self._fetch_user_by_id(user_id)
        if user_row is None or str(user_row["account_status"]) != "active":
            raise AppError(
                code="INVALID_RECOVERY_CODE",
                message="Invalid handle or recovery credential.",
                status_code=400,
            )

        code_or_token = payload.recovery_code_or_token.strip()
        stored_code_hash = user_row.get("recovery_code_hash")
        used_backup_code = False

        if stored_code_hash and verify_password(code_or_token, str(stored_code_hash)):
            used_backup_code = True
        else:
            token_hash = hash_session_token(code_or_token)
            now_str = _now_iso()
            token_rows = await self.session.execute(
                """
                SELECT id FROM password_recovery_tokens
                WHERE user_id = ? AND token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (user_id, token_hash, now_str),
            )
            if not token_rows:
                raise AppError(
                    code="INVALID_RECOVERY_CODE",
                    message="Invalid or expired recovery credential.",
                    status_code=400,
                )
            token_id = str(token_rows[0][0])
            await self.session.execute(
                "UPDATE password_recovery_tokens SET used_at = ? WHERE id = ?",
                (now_str, token_id),
            )

        new_pwd_hash = hash_password(payload.new_password)
        now_str = _now_iso()

        if used_backup_code:
            # Rotate backup recovery code hash so a used backup code cannot be replayed
            rotated_code = generate_backup_recovery_code()
            rotated_hash = hash_password(rotated_code)
            await self.session.execute(
                "UPDATE users SET password_hash = ?, recovery_code_hash = ?, updated_at = ? WHERE id = ?",
                (new_pwd_hash, rotated_hash, now_str, user_id),
            )
        else:
            await self.session.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (new_pwd_hash, now_str, user_id),
            )

        # Security requirement: revoke all existing sessions on password reset
        await self.revoke_all_sessions(user_id)

    async def update_profile(
        self,
        user_id: str,
        payload: UpdateProfileRequest,
        *,
        csrf_token: str,
    ) -> PrivateAccountResponse:
        now_str = _now_iso()
        profile_row = await self._fetch_public_profile_by_user_id(user_id)
        assert profile_row is not None

        display_name = (
            normalize_optional_unicode_nfc(payload.display_name)
            if payload.display_name is not None
            else profile_row.get("display_name")
        )
        if display_name is not None:
            display_name = display_name.strip() or None
            if display_name and len(display_name) > 64:
                raise AppError(
                    code="VALIDATION_ERROR",
                    message="Display name must not exceed 64 characters.",
                    status_code=422,
                )

        bio = (
            normalize_optional_unicode_nfc(payload.bio)
            if payload.bio is not None
            else profile_row.get("bio")
        )
        if bio is not None:
            bio = bio.strip() or None
            if bio and len(bio) > 500:
                raise AppError(
                    code="VALIDATION_ERROR",
                    message="Bio must not exceed 500 characters.",
                    status_code=422,
                )

        show_karma = (
            payload.show_karma
            if payload.show_karma is not None
            else bool(profile_row.get("show_karma", True))
        )

        await self.session.execute(
            """
            UPDATE public_profiles
            SET display_name = ?, bio = ?, show_karma = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (display_name, bio, 1 if show_karma else 0, now_str, user_id),
        )

        if payload.professional_profile is not None:
            norm_prof = payload.professional_profile.normalized()
            existing_prof = await self._fetch_professional_profile(user_id)
            if existing_prof is None:
                await self.session.execute(
                    """
                    INSERT INTO professional_profiles (
                        id, user_id, role_title, industry, experience_band,
                        region_label, is_enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        norm_prof.role_title,
                        norm_prof.industry,
                        norm_prof.experience_band,
                        norm_prof.region_label,
                        1 if norm_prof.is_enabled else 0,
                        now_str,
                        now_str,
                    ),
                )
            else:
                await self.session.execute(
                    """
                    UPDATE professional_profiles
                    SET role_title = ?, industry = ?, experience_band = ?,
                        region_label = ?, is_enabled = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        norm_prof.role_title,
                        norm_prof.industry,
                        norm_prof.experience_band,
                        norm_prof.region_label,
                        1 if norm_prof.is_enabled else 0,
                        now_str,
                        user_id,
                    ),
                )

        user_row = await self._fetch_user_by_id(user_id)
        updated_profile = await self._fetch_public_profile_by_user_id(user_id)
        updated_prof = await self._fetch_professional_profile(user_id)
        assert user_row is not None and updated_profile is not None

        return serialize_private_account(
            user_row=user_row,
            profile_row=updated_profile,
            prof_row=updated_prof,
            email_encryption_key_b64=self.settings.email_encryption_key_base64,
            csrf_token=csrf_token,
        )

    async def update_settings(
        self,
        user_id: str,
        payload: UpdateSettingsRequest,
        *,
        csrf_token: str,
    ) -> PrivateAccountResponse:
        now_str = _now_iso()
        user_row = await self._fetch_user_by_id(user_id)
        assert user_row is not None

        default_mode = (
            validate_identity_mode(payload.default_identity_mode)
            if payload.default_identity_mode is not None
            else str(user_row["default_identity_mode"])
        )
        if default_mode == "professional":
            prof_row_check = await self._fetch_professional_profile(user_id)
            if not prof_row_check or not bool(prof_row_check.get("is_enabled")):
                raise AppError(
                    code="PROFESSIONAL_PROFILE_REQUIRED",
                    message="Please configure and enable your optional Professional Profile before setting 'professional' as your default identity mode.",
                    status_code=422,
                )

        ui_locale = (
            validate_bcp47_tag(payload.preferred_ui_locale)
            if payload.preferred_ui_locale is not None
            else str(user_row["preferred_ui_locale"])
        )

        if payload.preferred_content_locales is not None:
            if not payload.preferred_content_locales:
                raise AppError(
                    code="VALIDATION_ERROR",
                    message="At least one preferred content language must be selected.",
                    status_code=422,
                )
            validated_locales = [validate_bcp47_tag(loc) for loc in payload.preferred_content_locales]
            content_locales_json = json.dumps(validated_locales)
        else:
            content_locales_json = str(user_row["preferred_content_locales"])

        email_hash = user_row.get("email_hash")
        email_encrypted = user_row.get("email_encrypted")
        if payload.recovery_email is not None:
            if payload.recovery_email.strip() == "":
                email_hash = None
                email_encrypted = None
            else:
                new_hash = hash_email_for_lookup(
                    payload.recovery_email, self.settings.email_hmac_pepper
                )
                conflict = await self.session.execute(
                    "SELECT 1 FROM users WHERE email_hash = ? AND id != ?",
                    (new_hash, user_id),
                )
                if conflict:
                    raise AppError(
                        code="EMAIL_ALREADY_REGISTERED",
                        message="That recovery email is already associated with another account.",
                        status_code=409,
                    )
                email_hash = new_hash
                email_encrypted = encrypt_recovery_email(
                    payload.recovery_email, self.settings.email_encryption_key_base64
                )

        await self.session.execute(
            """
            UPDATE users
            SET default_identity_mode = ?, preferred_ui_locale = ?,
                preferred_content_locales = ?, email_hash = ?, email_encrypted = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                default_mode,
                ui_locale,
                content_locales_json,
                email_hash,
                email_encrypted,
                now_str,
                user_id,
            ),
        )

        updated_user = await self._fetch_user_by_id(user_id)
        profile_row = await self._fetch_public_profile_by_user_id(user_id)
        prof_row = await self._fetch_professional_profile(user_id)
        assert updated_user is not None and profile_row is not None

        return serialize_private_account(
            user_row=updated_user,
            profile_row=profile_row,
            prof_row=prof_row,
            email_encryption_key_b64=self.settings.email_encryption_key_base64,
            csrf_token=csrf_token,
        )

    async def delete_account(self, user_id: str, payload: DeleteAccountRequest) -> None:
        """Verify password and execute the complete Phase 12.1 account deletion & anonymization lifecycle."""
        user_row = await self._fetch_user_by_id(user_id)
        if user_row is None or not verify_password(
            payload.password_confirmation, str(user_row["password_hash"])
        ):
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Password confirmation failed.",
                status_code=401,
            )

        now_str = _now_iso()
        storage = create_storage_adapter(self.settings)

        # 1. Clean up custom avatar storage object if present
        profile_row = await self._fetch_public_profile_by_user_id(user_id)
        if profile_row and profile_row.get("avatar_storage_key"):
            try:
                storage.delete_object(str(profile_row["avatar_storage_key"]))
            except Exception:
                pass

        # 2. Clean up meme_assets underlying binary files and rows according to policy
        try:
            if payload.delete_published_posts:
                asset_rows = await self.session.execute(
                    "SELECT id, storage_key FROM meme_assets WHERE owner_user_id = ?",
                    (user_id,),
                )
                for _, skey in asset_rows:
                    storage.delete_object(str(skey))
                await self.session.execute(
                    "DELETE FROM meme_assets WHERE owner_user_id = ?",
                    (user_id,),
                )
            else:
                unpub_rows = await self.session.execute(
                    "SELECT id, storage_key FROM meme_assets WHERE owner_user_id = ? AND is_published = 0",
                    (user_id,),
                )
                for _, skey in unpub_rows:
                    storage.delete_object(str(skey))
                await self.session.execute(
                    "DELETE FROM meme_assets WHERE owner_user_id = ? AND is_published = 0",
                    (user_id,),
                )
                await self.session.execute(
                    "UPDATE meme_assets SET owner_user_id = NULL WHERE owner_user_id = ?",
                    (user_id,),
                )
        except Exception:
            pass

        # 3. Purge cached content_translations for user's comments (and posts if deleted)
        try:
            await self.session.execute(
                """
                DELETE FROM content_translations
                WHERE source_type = 'comment'
                  AND source_id IN (SELECT id FROM comments WHERE author_user_id = ?)
                """,
                (user_id,),
            )
            if payload.delete_published_posts:
                await self.session.execute(
                    """
                    DELETE FROM content_translations
                    WHERE source_type = 'post'
                      AND source_id IN (SELECT id FROM posts WHERE author_user_id = ?)
                    """,
                    (user_id,),
                )
        except Exception:
            pass

        # 4. Handle authored posts, workplace_experience_details, and polls
        if payload.delete_published_posts:
            for post_child_sql in (
                "DELETE FROM workplace_experience_details WHERE post_id IN (SELECT id FROM posts WHERE author_user_id = ?)",
                "DELETE FROM poll_votes WHERE poll_post_id IN (SELECT id FROM posts WHERE author_user_id = ?)",
                "DELETE FROM poll_options WHERE poll_post_id IN (SELECT id FROM posts WHERE author_user_id = ?)",
                "DELETE FROM polls WHERE post_id IN (SELECT id FROM posts WHERE author_user_id = ?)",
            ):
                try:
                    await self.session.execute(post_child_sql, (user_id,))
                except Exception:
                    pass
            await self.session.execute(
                """
                UPDATE posts
                SET title = '[deleted]',
                    body = '[deleted by author]',
                    author_user_id = NULL,
                    professional_snapshot = NULL,
                    meme_asset_id = NULL,
                    moderation_status = 'removed',
                    deleted_at = ?,
                    updated_at = ?
                WHERE author_user_id = ?
                """,
                (now_str, now_str, user_id),
            )
        else:
            await self.session.execute(
                """
                UPDATE posts
                SET author_user_id = NULL,
                    identity_mode = 'anonymous',
                    professional_snapshot = NULL,
                    updated_at = ?
                WHERE author_user_id = ?
                """,
                (now_str, user_id),
            )

        # 5. Scrub comments while preserving nested discussion tree structure
        await self.session.execute(
            """
            UPDATE comments
            SET body = '[deleted by author]',
                author_user_id = NULL,
                identity_mode = 'anonymous',
                professional_snapshot = NULL,
                deleted_at = COALESCE(deleted_at, ?),
                updated_at = ?
            WHERE author_user_id = ?
            """,
            (now_str, now_str, user_id),
        )

        # 6. Decrement community member counts and remove memberships
        try:
            await self.session.execute(
                """
                UPDATE communities
                SET member_count = CASE WHEN member_count > 0 THEN member_count - 1 ELSE 0 END,
                    updated_at = ?
                WHERE id IN (
                    SELECT community_id FROM community_memberships
                    WHERE user_id = ? AND status = 'active'
                )
                """,
                (now_str, user_id),
            )
            await self.session.execute(
                "DELETE FROM community_memberships WHERE user_id = ?",
                (user_id,),
            )
            await self.session.execute(
                "UPDATE communities SET created_by_user_id = NULL WHERE created_by_user_id = ?",
                (user_id,),
            )
        except Exception:
            pass

        # 7. Delete private interactions, bookmarks, preferences, jobs, contributions, reports, and appeals
        for cleanup_sql in (
            "DELETE FROM workplace_insight_contributions WHERE user_id = ?",
            "DELETE FROM saved_posts WHERE user_id = ?",
            "DELETE FROM votes WHERE user_id = ?",
            "DELETE FROM reactions WHERE user_id = ?",
            "DELETE FROM poll_votes WHERE user_id = ?",
            "DELETE FROM user_topic_preferences WHERE user_id = ?",
            "DELETE FROM notifications WHERE recipient_user_id = ?",
            "DELETE FROM meme_jobs WHERE user_id = ?",
            "DELETE FROM moderation_appeals WHERE appellant_user_id = ?",
            "UPDATE moderation_appeals SET reviewed_by_user_id = NULL WHERE reviewed_by_user_id = ?",
            "UPDATE moderation_actions SET affected_user_id = NULL WHERE affected_user_id = ?",
            "DELETE FROM reports WHERE reporter_user_id = ?",
            "UPDATE ai_provider_usage SET user_id = NULL WHERE user_id = ?",
        ):
            try:
                await self.session.execute(cleanup_sql, (user_id,))
            except Exception:
                pass

        try:
            await self.session.execute(
                "DELETE FROM user_blocks WHERE blocker_user_id = ? OR blocked_user_id = ?",
                (user_id, user_id),
            )
        except Exception:
            pass

        # 8. Delete sessions, recovery tokens, professional profile, and public profile
        await self.session.execute(
            "DELETE FROM user_sessions WHERE user_id = ?", (user_id,)
        )
        await self.session.execute(
            "DELETE FROM password_recovery_tokens WHERE user_id = ?", (user_id,)
        )
        await self.session.execute(
            "DELETE FROM professional_profiles WHERE user_id = ?", (user_id,)
        )
        await self.session.execute(
            "DELETE FROM public_profiles WHERE user_id = ?", (user_id,)
        )

        # 9. Scrub user row and mark deleted
        await self.session.execute(
            """
            UPDATE users
            SET email_hash = NULL,
                email_encrypted = NULL,
                recovery_code_hash = NULL,
                password_hash = 'DELETED_ACCOUNT',
                account_status = 'deleted',
                updated_at = ?,
                deleted_at = ?
            WHERE id = ?
            """,
            (now_str, now_str, user_id),
        )

        # 10. Record an append-only, identity-redacted audit_events entry (never deleting existing audit_events)
        try:
            subject_fingerprint = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
            await self.session.execute(
                """
                INSERT INTO audit_events (
                    id, actor_user_id, actor_role, event_category, action_name,
                    target_type, target_id, reason_code, redacted_metadata,
                    correlation_id, created_at
                ) VALUES (?, NULL, 'member', 'account_security', 'account_self_deleted', 'user', NULL, 'user_requested_deletion', ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    json.dumps(
                        {
                            "subject_sha256_prefix": subject_fingerprint,
                            "delete_published_posts": bool(payload.delete_published_posts),
                        }
                    ),
                    f"acct_del_{subject_fingerprint}",
                    now_str,
                ),
            )
        except Exception:
            pass

    async def get_public_profile_by_handle(self, handle: str) -> PublicProfileResponse:
        profile_row = await self._fetch_public_profile_by_handle(handle)
        if profile_row is None:
            raise AppError(
                code="PROFILE_NOT_FOUND",
                message="No public profile found for that handle.",
                status_code=404,
            )
        user_id = str(profile_row["user_id"])
        user_row = await self._fetch_user_by_id(user_id)
        if user_row is None or str(user_row["account_status"]) in {"suspended", "deleted"}:
            raise AppError(
                code="PROFILE_NOT_FOUND",
                message="No public profile found for that handle.",
                status_code=404,
            )
        prof_row = await self._fetch_professional_profile(user_id)
        return serialize_public_profile(profile_row, prof_row)

    async def preview_display_identity(
        self,
        *,
        user_id: str,
        identity_mode: str,
        is_anonymous_op: bool = False,
    ) -> PublicAuthorDisplay:
        profile_row = await self._fetch_public_profile_by_user_id(user_id)
        assert profile_row is not None
        prof_row = await self._fetch_professional_profile(user_id)
        return serialize_author_for_identity_mode(
            identity_mode=identity_mode,
            profile_row=profile_row,
            prof_row=prof_row,
            is_anonymous_op=is_anonymous_op,
        )

    async def export_my_data(self, *, user_id: str) -> dict[str, Any]:
        """Return a complete, strictly owner-scoped export of the authenticated user's data (FR-ID-05 & Phase 12.1)."""
        user_row = await self._fetch_user_by_id(user_id)
        if user_row is None:
            raise AppError(
                code="USER_NOT_FOUND",
                message="User account not found.",
                status_code=404,
            )
        profile_row = await self._fetch_public_profile_by_user_id(user_id)
        prof_row = await self._fetch_professional_profile(user_id)

        decrypted_email: Optional[str] = None
        if user_row.get("email_encrypted"):
            try:
                decrypted_email = decrypt_recovery_email(
                    user_row["email_encrypted"],
                    self.settings.email_encryption_key_base64,
                )
            except Exception:
                decrypted_email = None

        post_rows = await self.session.execute(
            """
            SELECT p.id, p.community_slug, p.post_type, p.identity_mode, p.title, p.body,
                   p.content_language, p.meme_asset_id, p.created_at,
                   w.experience_kind, w.experience_category, w.primary_resignation_reason,
                   w.secondary_resignation_reason, w.experience_band, w.industry_category,
                   w.transition_outcome, w.lesson_learned
            FROM posts p
            LEFT JOIN workplace_experience_details w ON w.post_id = p.id
            WHERE p.author_user_id = ? AND p.deleted_at IS NULL
            ORDER BY p.created_at DESC
            """,
            (user_id,),
        )
        comm_rows = await self.session.execute(
            "SELECT id, post_id, identity_mode, body, content_language, created_at FROM comments WHERE author_user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC",
            (user_id,),
        )
        saved_rows = await self.session.execute(
            "SELECT post_id, created_at FROM saved_posts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        vote_rows = await self.session.execute(
            "SELECT target_type, target_id, value, created_at FROM votes WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        reaction_rows = await self.session.execute(
            "SELECT target_type, target_id, reaction_kind, created_at FROM reactions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        poll_vote_rows = await self.session.execute(
            "SELECT poll_post_id, option_id, created_at FROM poll_votes WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        membership_rows = await self.session.execute(
            """
            SELECT c.slug, cm.role, cm.status, cm.joined_at
            FROM community_memberships cm
            JOIN communities c ON c.id = cm.community_id
            WHERE cm.user_id = ?
            ORDER BY cm.joined_at DESC
            """,
            (user_id,),
        )
        topic_pref_rows = await self.session.execute(
            "SELECT tag_slug, preference_type, created_at FROM user_topic_preferences WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        block_rows = await self.session.execute(
            """
            SELECT pp.handle, ub.block_mode, ub.created_at
            FROM user_blocks ub
            LEFT JOIN public_profiles pp ON pp.user_id = ub.blocked_user_id
            WHERE ub.blocker_user_id = ?
            ORDER BY ub.created_at DESC
            """,
            (user_id,),
        )
        notif_rows = await self.session.execute(
            "SELECT id, notification_type, reference_type, reference_id, title, body_preview, is_read, created_at FROM notifications WHERE recipient_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        asset_rows = await self.session.execute(
            "SELECT id, source_type, storage_key, mime_type, file_size_bytes, width, height, caption_language, alt_text, is_published, created_at FROM meme_assets WHERE owner_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        job_rows = await self.session.execute(
            "SELECT id, job_type, status, user_prompt, prompt_language, style_tone, result_asset_id, created_at FROM meme_jobs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        report_rows = await self.session.execute(
            "SELECT id, target_type, target_id, reason_code, status, created_at FROM reports WHERE reporter_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        appeal_rows = await self.session.execute(
            "SELECT id, moderation_action_id, appeal_statement, status, decision_reason_code, created_at, resolved_at FROM moderation_appeals WHERE appellant_user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        contrib_rows = await self.session.execute(
            """
            SELECT id, aggregation_consent, industry_category, role_family, experience_band,
                   company_size_band, broad_region, work_arrangement, overall_satisfaction,
                   workload_rating, management_support, work_life_balance, career_growth,
                   workplace_flexibility, compensation_satisfaction, team_culture,
                   employee_autonomy, resignation_reason, created_at, updated_at
            FROM workplace_insight_contributions
            WHERE user_id = ?
            """,
            (user_id,),
        )

        try:
            content_locales = json.loads(str(user_row.get("preferred_content_locales") or '["en"]'))
        except Exception:
            content_locales = ["en"]

        return {
            "export_metadata": {
                "schema_version": "1.2.1",
                "exported_at": _now_iso(),
                "owner_user_id": user_id,
            },
            "account": {
                "user_id": user_id,
                "recovery_email": decrypted_email,
                "account_status": str(user_row["account_status"]),
                "role": str(user_row["role"]),
                "default_identity_mode": str(user_row["default_identity_mode"]),
                "preferred_ui_locale": str(user_row["preferred_ui_locale"]),
                "preferred_content_locales": content_locales,
                "created_at": str(user_row["created_at"]),
            },
            "public_profile": {
                "handle": profile_row["handle"] if profile_row else None,
                "display_name": profile_row.get("display_name") if profile_row else None,
                "bio": profile_row.get("bio") if profile_row else None,
                "show_karma": bool(profile_row.get("show_karma", True)) if profile_row else True,
            },
            "professional_profile": {
                "role_title": prof_row["role_title"],
                "industry": prof_row["industry"],
                "experience_band": prof_row["experience_band"],
                "region_label": prof_row.get("region_label"),
                "is_enabled": bool(prof_row["is_enabled"]),
            }
            if prof_row
            else None,
            "authored_posts": [
                {
                    "id": str(r[0]),
                    "community_slug": str(r[1]),
                    "post_type": str(r[2]),
                    "identity_mode": str(r[3]),
                    "title": str(r[4]),
                    "body": str(r[5]),
                    "content_language": str(r[6]),
                    "meme_asset_id": str(r[7]) if r[7] else None,
                    "created_at": str(r[8]),
                    "workplace_detail": {
                        "experience_kind": str(r[9]),
                        "experience_category": str(r[10]),
                        "primary_resignation_reason": r[11],
                        "secondary_resignation_reason": r[12],
                        "experience_band": r[13],
                        "industry_category": r[14],
                        "transition_outcome": r[15],
                        "lesson_learned": r[16],
                    }
                    if r[9] is not None
                    else None,
                }
                for r in post_rows
            ],
            "authored_comments": [
                {
                    "id": str(r[0]),
                    "post_id": str(r[1]),
                    "identity_mode": str(r[2]),
                    "body": str(r[3]),
                    "content_language": str(r[4]),
                    "created_at": str(r[5]),
                }
                for r in comm_rows
            ],
            "votes": [
                {
                    "target_type": str(r[0]),
                    "target_id": str(r[1]),
                    "value": int(r[2]),
                    "created_at": str(r[3]),
                }
                for r in vote_rows
            ],
            "reactions": [
                {
                    "target_type": str(r[0]),
                    "target_id": str(r[1]),
                    "reaction_kind": str(r[2]),
                    "created_at": str(r[3]),
                }
                for r in reaction_rows
            ],
            "poll_votes": [
                {
                    "poll_post_id": str(r[0]),
                    "option_id": str(r[1]),
                    "created_at": str(r[2]),
                }
                for r in poll_vote_rows
            ],
            "saved_bookmarks": [
                {"post_id": str(r[0]), "saved_at": str(r[1])} for r in saved_rows
            ],
            "community_memberships": [
                {
                    "community_slug": str(r[0]),
                    "role": str(r[1]),
                    "status": str(r[2]),
                    "joined_at": str(r[3]),
                }
                for r in membership_rows
            ],
            "topic_preferences": [
                {
                    "tag_slug": str(r[0]),
                    "preference_type": str(r[1]),
                    "created_at": str(r[2]),
                }
                for r in topic_pref_rows
            ],
            "blocks_and_mutes": [
                {
                    "target_handle": str(r[0]) if r[0] else "[deleted]",
                    "block_mode": str(r[1]),
                    "created_at": str(r[2]),
                }
                for r in block_rows
            ],
            "notifications": [
                {
                    "id": str(r[0]),
                    "notification_type": str(r[1]),
                    "reference_type": str(r[2]),
                    "reference_id": str(r[3]),
                    "title": str(r[4]),
                    "body_preview": r[5],
                    "is_read": bool(r[6]),
                    "created_at": str(r[7]),
                }
                for r in notif_rows
            ],
            "meme_assets": [
                {
                    "id": str(r[0]),
                    "source_type": str(r[1]),
                    "storage_key": str(r[2]),
                    "mime_type": str(r[3]),
                    "file_size_bytes": int(r[4]),
                    "width": int(r[5]),
                    "height": int(r[6]),
                    "caption_language": str(r[7]),
                    "alt_text": str(r[8]),
                    "is_published": bool(r[9]),
                    "created_at": str(r[10]),
                }
                for r in asset_rows
            ],
            "meme_jobs": [
                {
                    "id": str(r[0]),
                    "job_type": str(r[1]),
                    "status": str(r[2]),
                    "user_prompt": r[3],
                    "prompt_language": str(r[4]),
                    "style_tone": str(r[5]),
                    "result_asset_id": r[6],
                    "created_at": str(r[7]),
                }
                for r in job_rows
            ],
            "submitted_reports": [
                {
                    "id": str(r[0]),
                    "target_type": str(r[1]),
                    "target_id": str(r[2]),
                    "reason_code": str(r[3]),
                    "status": str(r[4]),
                    "created_at": str(r[5]),
                }
                for r in report_rows
            ],
            "moderation_appeals": [
                {
                    "id": str(r[0]),
                    "moderation_action_id": str(r[1]),
                    "appeal_statement": str(r[2]),
                    "status": str(r[3]),
                    "decision_reason_code": r[4],
                    "created_at": str(r[5]),
                    "resolved_at": r[6],
                }
                for r in appeal_rows
            ],
            "structured_workplace_contribution": {
                "id": str(contrib_rows[0][0]),
                "aggregation_consent": bool(contrib_rows[0][1]),
                "industry_category": contrib_rows[0][2],
                "role_family": contrib_rows[0][3],
                "experience_band": contrib_rows[0][4],
                "company_size_band": contrib_rows[0][5],
                "broad_region": contrib_rows[0][6],
                "work_arrangement": contrib_rows[0][7],
                "overall_satisfaction": contrib_rows[0][8],
                "workload_rating": contrib_rows[0][9],
                "management_support": contrib_rows[0][10],
                "work_life_balance": contrib_rows[0][11],
                "career_growth": contrib_rows[0][12],
                "workplace_flexibility": contrib_rows[0][13],
                "compensation_satisfaction": contrib_rows[0][14],
                "team_culture": contrib_rows[0][15],
                "employee_autonomy": contrib_rows[0][16],
                "resignation_reason": contrib_rows[0][17],
                "created_at": str(contrib_rows[0][18]),
                "updated_at": str(contrib_rows[0][19]),
            }
            if contrib_rows
            else None,
        }
