"""CosmosIQ operations toolkit (Phase 019).

Operator-side tooling only: CI gate, backup/restore, production smoke,
performance probe, environment report. Everything here is:

* offline — backup/restore/smoke/perf are local file operations only;
* deterministic — clocks are injected (``now``) wherever behaviour depends
  on time; wall-clock measurement exists ONLY in ``perf.py`` and is an ops
  measurement, never a runtime behaviour;
* secret-safe — env var NAMES and presence labels only, never values;
* append-only respecting — retention means SNAPSHOT/ARCHIVE of whole
  stores; no line of any store is ever pruned, deleted, or rewritten.

``subprocess`` use (git ls-files in the CI gate, suite run) is confined to
this package: cosmosiq_ops is an operator tool, not runtime code.
"""

from cosmosiq_ops.backup import (  # noqa: F401
    ARCHIVE_POLICY,
    RestoreCheckReport,
    SnapshotReport,
    VerifyReport,
    archive_snapshot,
    restore_check,
    restore_snapshot,
    snapshot_store,
    verify_snapshot,
)
from cosmosiq_ops.ci_gate import (  # noqa: F401
    CiGateReport,
    format_ci_gate_report,
    run_ci_gate,
)
from cosmosiq_ops.env_config import (  # noqa: F401
    EnvReport,
    environment_report,
    format_env_report,
)
from cosmosiq_ops.perf import PerfReport, format_perf_report, run_perf_probe  # noqa: F401
from cosmosiq_ops.env_profiles import (  # noqa: F401
    DEFAULT_PROFILE_ID,
    PROFILES,
    EnvironmentProfile,
    default_profile,
    get_profile,
    resolve_profile,
)
from cosmosiq_ops.secrets_config import (  # noqa: F401
    ALL_CONFIG_ENV_VARS,
    CONFIG_SCHEMA,
    ENV_UNTRACKED_RULE,
    REQUIRED_ENV_VARS,
    CapabilityConfig,
    SecretCheck,
    SecretsReport,
    file_is_secret_free,
    format_secrets_report,
    is_secret_free,
    required_env_vars_for_profile,
    secret_scan_paths,
    secret_value_findings,
    validate_secrets,
)
from cosmosiq_ops.smoke import (  # noqa: F401
    SmokeReport,
    format_smoke_report,
    run_production_smoke,
)
from cosmosiq_ops.persistence_hardening import (  # noqa: F401
    RETENTION_POLICY,
    SUPPORTED_SCHEMA_VERSIONS,
    HardenedBackupReport,
    HardenedRestoreReport,
    HardeningReport,
    IntegrityReport,
    RetentionReport,
    SchemaReport,
    StoreIntegrity,
    WriterLockError,
    apply_retention,
    hardened_backup,
    hardened_restore,
    integrity_check,
    run_persistence_hardening_check,
    schema_compatibility_check,
    seal_store,
    single_writer_lock,
    release_writer_lock,
)
from cosmosiq_ops.backup_ops import (  # noqa: F401
    STATUS_DEGRADED as BACKUP_STATUS_DEGRADED,
    STATUS_FAILED as BACKUP_STATUS_FAILED,
    STATUS_OK as BACKUP_STATUS_OK,
    BackupFileRecord,
    BackupHealthReport,
    BackupReport,
    RestoreReport,
    apply_retention_policy,
    backup as backup_operator,
    backup_health,
    dry_run_restore,
    restore as restore_operator,
)
from cosmosiq_ops.observability import (  # noqa: F401
    STATUS_DEGRADED,
    STATUS_FAILED,
    STATUS_OK,
    ObservabilityReport,
    aggregate_observability,
    emit_structured_log,
    render_health_json,
    render_metrics,
)
from cosmosiq_ops.security_audit import (  # noqa: F401
    AUDIT_PACKAGES,
    INTELLIGENCE_PACKAGES,
    SecurityAuditCategory,
    SecurityAuditReport,
    render_security_audit,
    run_security_audit,
    scan_text_for_secret_values,
)
