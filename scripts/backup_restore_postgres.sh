#!/usr/bin/env bash
# Pressure Out — Hardened PostgreSQL 16 Backup, Integrity Check & Disposable Restore Drill (Phase 12.1)
# Security & Safety Invariants:
#   - Enforces umask 077 so dump files and checksums are created with 0600 permissions.
#   - Validates disposable database identifiers against ^pressure_out_restore_drill_[0-9]{8,16}$.
#   - Never allows restore drills to target a production or non-disposable database name.
#   - Verifies post-restore Alembic revision == 0010_phase11_workplace.
#
# Usage:
#   ./scripts/backup_restore_postgres.sh validate-config <output_file.dump> <drill_db_name>
#   ./scripts/backup_restore_postgres.sh backup          <pg_dsn> <output_file.dump>
#   ./scripts/backup_restore_postgres.sh verify          <output_file.dump>
#   ./scripts/backup_restore_postgres.sh drill           <pg_admin_dsn> <output_file.dump> [drill_db_name]

set -euo pipefail
umask 077

EXPECTED_HEAD="0010_phase11_workplace"
MODE="${1:-}"

if [[ -z "${MODE}" ]]; then
  echo "Usage: $0 {validate-config|backup|verify|drill} ..." >&2
  exit 1
fi

validate_output_path() {
  local out_path="$1"
  if [[ -z "${out_path}" || "${out_path}" == *".."* ]]; then
    echo "[ERROR] Invalid or unsafe backup output path: '${out_path}'." >&2
    exit 1
  fi
  if [[ "${out_path}" != *.dump ]]; then
    echo "[ERROR] Backup file path must end with .dump: '${out_path}'." >&2
    exit 1
  fi
}

validate_disposable_db_name() {
  local db_name="$1"
  if [[ ! "${db_name}" =~ ^pressure_out_restore_drill_[0-9]{8,16}$ ]]; then
    echo "[ERROR] Unsafe restore target database '${db_name}'. Must match ^pressure_out_restore_drill_[0-9]{8,16}$." >&2
    exit 1
  fi
}

require_pg_binaries() {
  for bin in "$@"; do
    if ! command -v "${bin}" >/dev/null 2>&1; then
      echo "[BLOCKED] Required PostgreSQL binary '${bin}' is not installed in this environment." >&2
      exit 2
    fi
  done
}

case "${MODE}" in
  validate-config)
    OUT_FILE="${2:?Output file path (.dump) required}"
    DRILL_DB="${3:-pressure_out_restore_drill_2026103001}"
    validate_output_path "${OUT_FILE}"
    validate_disposable_db_name "${DRILL_DB}"
    echo "[OK] Backup path '${OUT_FILE}', umask 077, and disposable target '${DRILL_DB}' validated."
    ;;
  backup)
    DSN="${2:?Database DSN required}"
    OUT_FILE="${3:-pressure_out_$(date -u +%Y%m%dT%H%M%SZ).dump}"
    validate_output_path "${OUT_FILE}"
    require_pg_binaries pg_dump sha256sum
    pg_dump --format=custom --no-owner --no-privileges --dbname="${DSN}" --file="${OUT_FILE}"
    chmod 600 "${OUT_FILE}"
    sha256sum "${OUT_FILE}" > "${OUT_FILE}.sha256"
    chmod 600 "${OUT_FILE}.sha256"
    echo "[OK] Backup written to ${OUT_FILE} (mode 0600) and checksummed."
    ;;
  verify)
    DUMP_FILE="${2:?Dump file required}"
    validate_output_path "${DUMP_FILE}"
    if [[ ! -f "${DUMP_FILE}" || ! -f "${DUMP_FILE}.sha256" ]]; then
      echo "[ERROR] Dump file or .sha256 checksum file missing for '${DUMP_FILE}'." >&2
      exit 1
    fi
    sha256sum -c "${DUMP_FILE}.sha256"
    require_pg_binaries pg_restore
    pg_restore --list "${DUMP_FILE}" >/dev/null
    echo "[OK] Archive checksum and pg_restore catalog verified."
    ;;
  drill)
    ADMIN_DSN="${2:?Admin DSN required}"
    DUMP_FILE="${3:?Dump file required}"
    DRILL_DB="${4:-pressure_out_restore_drill_$(date -u +%s)}"
    validate_output_path "${DUMP_FILE}"
    validate_disposable_db_name "${DRILL_DB}"
    require_pg_binaries psql pg_restore sha256sum
    sha256sum -c "${DUMP_FILE}.sha256"
    psql "${ADMIN_DSN}" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${DRILL_DB}\";"
    trap 'psql "${ADMIN_DSN}" -c "DROP DATABASE IF EXISTS \"${DRILL_DB}\";" >/dev/null 2>&1 || true' EXIT
    DRILL_DSN="${ADMIN_DSN%/*}/${DRILL_DB}"
    pg_restore --no-owner --no-privileges --exit-on-error --dbname="${DRILL_DSN}" "${DUMP_FILE}"
    REV=$(psql "${DRILL_DSN}" -t -A -c "SELECT version_num FROM alembic_version LIMIT 1;")
    if [[ "${REV}" != "${EXPECTED_HEAD}" ]]; then
      echo "[ERROR] Restored database revision '${REV}' does not match expected head '${EXPECTED_HEAD}'." >&2
      exit 1
    fi
    USER_CNT=$(psql "${DRILL_DSN}" -t -A -c "SELECT COUNT(1) FROM users;")
    echo "[OK] Restore drill succeeded into ${DRILL_DB} (alembic_version=${REV}, users=${USER_CNT})."
    ;;
  *)
    echo "Unknown mode: ${MODE}" >&2
    exit 1
    ;;
esac
