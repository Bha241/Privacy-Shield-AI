import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from pii_detector.db.database import db_manager
from pii_detector.db.models import AuditLogEntryModel

logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    log_id: str
    actor_id: str
    action_type: str  # DETECTION, HITL_VERIFICATION, MASKING, QNA_QUERY, DEMASK_REQUEST, DPDP_COMPLIANCE, RETENTION_CLEANUP
    document_id: Optional[str]
    timestamp: str
    prev_hash: str
    entry_hash: str
    details: Dict[str, Any]
    dpdp_compliant: bool = False
    hitl_approved: bool = False
    demasking_approved: bool = False


class AuditLogAgent:
    """
    Audit Log Agent: Responsible for maintaining an immutable, hash-chained compliance log
    as per Section 4 specifications and DPDP Act 2025 (Rule 6(1)(c) & Rule 12).
    Tracks every PII detection, Human-in-the-Loop review, masking event, cloud LLM query transmission,
    de-masking request, data retention enforcement, and DPDP guardrail check.

    Security & Integrity Principles:
    - Zero raw PII in audit entries or application logs (fail-safe recursive sanitization).
    - Authorization separation: HITL masking approval != demasking authorization.
    - Fail-closed persistence: last_hash advances ONLY when database commit succeeds.
    - Deterministic cryptographic hash chain with sort_keys canonical serialization.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path(__file__).resolve().parent.parent / "web" / "output"
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit_log.json"
        # Ensure database tables exist
        db_manager.init_db()
        self.last_hash = self._get_latest_hash()

    def _get_latest_hash(self) -> str:
        """Fetch the entry_hash of the most recent audit entry in the database."""
        session = db_manager.get_session()
        try:
            latest = session.query(AuditLogEntryModel).order_by(
                AuditLogEntryModel.timestamp.desc(),
                AuditLogEntryModel.log_id.desc()
            ).first()
            return latest.entry_hash if latest else self.GENESIS_HASH
        except Exception:
            return self.GENESIS_HASH
        finally:
            session.close()

    @classmethod
    def _sanitize_details(cls, data: Any) -> Any:
        """
        Recursively sanitizes dictionary/list details to remove or redact sensitive fields
        containing raw PII, raw text, mapping values, or demasked text.
        """
        SENSITIVE_KEYS = {
            "raw_text", "text", "value", "raw_value", "pii", "pii_value",
            "mapping", "token_mapping", "detailed_mapping", "demasked_text",
            "unmasked_text", "leaked_value", "entity_text", "entity_value",
            "detected_entities", "approved_entities", "prompt", "query",
            "response", "context", "original_value", "original_text"
        }

        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                k_lower = str(k).lower().strip()
                if k_lower in SENSITIVE_KEYS:
                    # Provide safe metadata / count instead of raw values
                    if isinstance(v, (list, tuple)):
                        sanitized[f"{k_lower}_count"] = len(v)
                    elif isinstance(v, dict):
                        sanitized[f"{k_lower}_count"] = len(v)
                    elif isinstance(v, (int, float, bool)) and k_lower not in {"text", "raw_text", "value", "raw_value", "leaked_value"}:
                        sanitized[k] = v
                    else:
                        sanitized[f"{k_lower}_present"] = True if v else False
                elif k_lower.endswith("_mapping") or k_lower.endswith("_text") or k_lower.endswith("_entities"):
                    if isinstance(v, (list, tuple, dict)):
                        sanitized[f"{k_lower}_count"] = len(v)
                    else:
                        sanitized[f"{k_lower}_present"] = True if v else False
                else:
                    sanitized[k] = cls._sanitize_details(v)
            return sanitized
        elif isinstance(data, list):
            return [cls._sanitize_details(item) for item in data]
        elif isinstance(data, (str, int, float, bool)) or data is None:
            return data
        else:
            return str(data)

    def _compute_hash(
        self,
        prev_hash: str,
        log_id: str,
        actor_id: str,
        action_type: str,
        document_id: str,
        timestamp_str: str,
        details: Dict[str, Any]
    ) -> str:
        """Generate tamper-evident SHA-256 hash for the log entry."""
        payload = f"{prev_hash}|{log_id}|{actor_id}|{action_type}|{document_id}|{timestamp_str}|{json.dumps(details, sort_keys=True, ensure_ascii=False)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log_event(
        self,
        agent_name: str,
        action_type: str,
        details: Dict[str, Any],
        actor_id: str = "usr_system",
        document_id: Optional[str] = None,
        dpdp_compliant: bool = True,
        hitl_approved: bool = False,
        demasking_approved: bool = False,
        user_approved: Optional[bool] = None,
        persist_document_fk: bool = True,
    ) -> Dict[str, Any]:
        """
        Record an immutable, hash-chained audit entry in PostgreSQL and JSON storage.
        Fails closed: last_hash advances only when database persistence succeeds.
        """
        # Backward compatibility for user_approved parameter
        if user_approved is not None and not hitl_approved and action_type != "DEMASK_REQUEST":
            hitl_approved = bool(user_approved)

        timestamp_dt = datetime.utcnow()
        timestamp_str = timestamp_dt.isoformat()
        log_id = f"LOG-{uuid.uuid4().hex}"

        doc_id_str = document_id or details.get("document_id") or details.get("file_name") or "doc_system"

        # 1. Sanitize untrusted details BEFORE hashing and persistence
        safe_details = self._sanitize_details(details)

        full_details = {
            **safe_details,
            "agent_name": agent_name,
            "document_id": doc_id_str,
            "dpdp_compliant": bool(dpdp_compliant),
            "hitl_approved": bool(hitl_approved),
            "demasking_approved": bool(demasking_approved),
        }

        prev_hash = self.last_hash
        entry_hash = self._compute_hash(prev_hash, log_id, actor_id, action_type, doc_id_str, timestamp_str, full_details)

        # 2. Database Model Persistence (PostgreSQL)
        persistence_success = False
        session = db_manager.get_session()
        try:
            # Verify FK exists to prevent constraint abort if document isn't registered yet
            target_doc_fk = None
            if persist_document_fk and doc_id_str and doc_id_str.startswith("doc_") and doc_id_str != "doc_system":
                from pii_detector.db.models import DocumentModel
                doc_row = session.query(DocumentModel.document_id).filter_by(document_id=doc_id_str).first()
                if doc_row:
                    target_doc_fk = doc_id_str

            entry = AuditLogEntryModel(
                log_id=log_id,
                actor_id=actor_id,
                action_type=action_type,
                document_id=target_doc_fk,
                timestamp=timestamp_dt,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                details_json=json.dumps(full_details, sort_keys=True, ensure_ascii=False)
            )
            session.add(entry)
            session.commit()
            persistence_success = True
        except Exception as e:
            session.rollback()
            logger.exception("Failed to persist audit event %s to the database", log_id)
            persistence_success = False
        finally:
            session.close()

        # 3. Only advance hash-chain on confirmed persistence success
        if persistence_success:
            self.last_hash = entry_hash

        # 4. Local JSON backup with sanitized details
        event_dict = {
            "status": "success" if persistence_success else "failed",
            "persisted": persistence_success,
            "log_id": log_id,
            "event_id": log_id,
            "actor_id": actor_id,
            "timestamp": timestamp_str,
            "agent_name": agent_name,
            "action_type": action_type,
            "document_id": doc_id_str,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "dpdp_compliant": bool(dpdp_compliant),
            "hitl_approved": bool(hitl_approved),
            "demasking_approved": bool(demasking_approved),
            "details": full_details,
        }
        if not persistence_success:
            event_dict["error"] = "Audit database persistence failed"

        self._append_json_log(event_dict)

        return event_dict

    def _append_json_log(self, event: Dict[str, Any]):
        logs = []
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.insert(0, event)
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Cryptographically verifies the hash-chain integrity of all audit log entries.
        Returns tamper verification status.
        """
        session = db_manager.get_session()
        try:
            entries = session.query(AuditLogEntryModel).order_by(
                AuditLogEntryModel.timestamp.asc(),
                AuditLogEntryModel.log_id.asc()
            ).all()

            if not entries:
                return {"is_tamper_free": True, "total_verified": 0, "message": "Audit chain empty."}

            expected_prev = self.GENESIS_HASH
            for idx, entry in enumerate(entries):
                if entry.prev_hash != expected_prev:
                    return {
                        "is_tamper_free": False,
                        "tampered_log_id": entry.log_id,
                        "expected_prev_hash": expected_prev,
                        "actual_prev_hash": entry.prev_hash,
                        "error": f"Hash chain broken at index {idx} (prev_hash mismatch)."
                    }

                try:
                    details = json.loads(entry.details_json) if entry.details_json else {}
                except Exception:
                    details = {}

                doc_id = entry.document_id or details.get("document_id") or details.get("file_name") or "doc_system"
                ts_str = entry.timestamp.isoformat() if entry.timestamp else ""

                computed = self._compute_hash(
                    entry.prev_hash,
                    entry.log_id,
                    entry.actor_id,
                    entry.action_type,
                    doc_id,
                    ts_str,
                    details
                )

                if computed != entry.entry_hash:
                    # Legacy fallback check (where timestamp had +00:00 or raw unformatted json)
                    legacy_payload1 = f"{entry.prev_hash}|{entry.log_id}|{entry.actor_id}|{entry.action_type}|{doc_id}|{ts_str}+00:00|{json.dumps(details, sort_keys=True)}"
                    legacy_payload2 = f"{entry.prev_hash}|{entry.log_id}|{entry.actor_id}|{entry.action_type}|{doc_id}|{ts_str}|{json.dumps(details)}"
                    legacy_computed1 = hashlib.sha256(legacy_payload1.encode("utf-8")).hexdigest()
                    legacy_computed2 = hashlib.sha256(legacy_payload2.encode("utf-8")).hexdigest()
                    if legacy_computed1 == entry.entry_hash or legacy_computed2 == entry.entry_hash:
                        computed = entry.entry_hash
                    else:
                        return {
                            "is_tamper_free": False,
                            "tampered_log_id": entry.log_id,
                            "computed_hash": computed,
                            "stored_hash": entry.entry_hash,
                            "error": f"Entry content payload modified at log_id {entry.log_id}."
                        }

                expected_prev = entry.entry_hash

            return {
                "is_tamper_free": True,
                "total_verified": len(entries),
                "latest_hash": expected_prev,
                "message": "All audit log entries cryptographically verified tamper-free."
            }
        finally:
            session.close()

    def get_all_logs(self) -> List[Dict[str, Any]]:
        """Retrieves audit entries with sanitized details to prevent PII exposure."""
        session = db_manager.get_session()
        try:
            entries = session.query(AuditLogEntryModel).order_by(
                AuditLogEntryModel.timestamp.desc(),
                AuditLogEntryModel.log_id.desc()
            ).all()
            return [e.to_dict() for e in entries]
        except Exception:
            if self.log_file.exists():
                try:
                    with open(self.log_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    return []
            return []
        finally:
            session.close()

    def get_summary(self) -> Dict[str, Any]:
        """Aggregates audit metrics with strict boolean validation (no implicit True defaults)."""
        logs = self.get_all_logs()
        total = len(logs)
        action_counts: Dict[str, int] = {}
        dpdp_violations = 0
        hitl_approvals = 0
        demasking_requests = 0
        demasking_approved_count = 0
        demasking_blocked_count = 0

        for e in logs:
            act = e.get("action_type", "UNKNOWN")
            action_counts[act] = action_counts.get(act, 0) + 1
            details = e.get("details", {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except Exception:
                    details = {}

            # Explicit check for DPDP violations (dpdp_compliant == False)
            dpdp_val = e.get("dpdp_compliant") if "dpdp_compliant" in e else details.get("dpdp_compliant")
            if dpdp_val is False:
                dpdp_violations += 1

            # Explicit check for HITL approvals (hitl_approved == True)
            hitl_val = e.get("hitl_approved") if "hitl_approved" in e else details.get("hitl_approved")
            if hitl_val is True:
                hitl_approvals += 1

            # Demasking action metrics
            if "DEMASK" in act:
                demasking_requests += 1
                demask_val = e.get("demasking_approved") if "demasking_approved" in e else details.get("demasking_approved")
                if demask_val is True or details.get("status") == "success":
                    demasking_approved_count += 1
                elif demask_val is False or details.get("status") == "blocked":
                    demasking_blocked_count += 1

        integrity = self.verify_integrity()

        return {
            "total_audit_events": total,
            "action_counts": action_counts,
            "dpdp_violations": dpdp_violations,
            "hitl_approvals": hitl_approvals,
            "demasking_requests": demasking_requests,
            "demasking_approved": demasking_approved_count,
            "demasking_blocked": demasking_blocked_count,
            "compliance_rate": f"{100.0 if total == 0 else round((total - dpdp_violations) / total * 100, 1)}%",
            "hash_chain_integrity": integrity
        }
