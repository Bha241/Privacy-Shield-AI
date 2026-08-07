import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from pii_detector.db.database import db_manager
from pii_detector.db.models import AuditLogEntryModel


@dataclass
class AuditEvent:
    log_id: str
    actor_id: str
    action_type: str  # DETECTION, HITL_VERIFICATION, MASKING, QNA_QUERY, DEMASKING, DPDP_COMPLIANCE, RETENTION_CLEANUP
    document_id: Optional[str]
    timestamp: str
    prev_hash: str
    entry_hash: str
    details: Dict[str, Any]
    dpdp_compliant: bool = True
    user_approved: bool = True


class AuditLogAgent:
    """
    Audit Log Agent: Responsible for maintaining an immutable, hash-chained compliance log
    as per Section 4 specifications and DPDP Act 2025 (Rule 6(1)(c) & Rule 12).
    Tracks every PII detection, Human-in-the-Loop review, masking event, cloud LLM query transmission,
    de-masking request, data retention enforcement, and DPDP guardrail check.
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
            latest = session.query(AuditLogEntryModel).order_by(AuditLogEntryModel.timestamp.desc()).first()
            return latest.entry_hash if latest else self.GENESIS_HASH
        except Exception:
            return self.GENESIS_HASH
        finally:
            session.close()

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
        payload = f"{prev_hash}|{log_id}|{actor_id}|{action_type}|{document_id}|{timestamp_str}|{json.dumps(details, sort_keys=True)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log_event(
        self,
        agent_name: str,
        action_type: str,
        details: Dict[str, Any],
        actor_id: str = "usr_system",
        document_id: Optional[str] = None,
        dpdp_compliant: bool = True,
        user_approved: bool = True
    ) -> Dict[str, Any]:
        """Record an immutable, hash-chained audit entry in PostgreSQL and JSON storage."""
        timestamp_dt = datetime.utcnow()
        timestamp_str = timestamp_dt.isoformat()
        log_id = f"LOG-{int(time.time() * 1000)}"

        doc_id_str = document_id or details.get("document_id") or details.get("file_name") or "doc_system"

        full_details = {
            "agent_name": agent_name,
            "dpdp_compliant": dpdp_compliant,
            "user_approved": user_approved,
            **details
        }

        prev_hash = self.last_hash
        entry_hash = self._compute_hash(prev_hash, log_id, actor_id, action_type, doc_id_str, timestamp_str, full_details)

        # 1. Database Model Persistence (PostgreSQL)
        session = db_manager.get_session()
        try:
            entry = AuditLogEntryModel(
                log_id=log_id,
                actor_id=actor_id,
                action_type=action_type,
                document_id=doc_id_str if doc_id_str.startswith("doc_") else None,
                timestamp=timestamp_dt,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                details_json=json.dumps(full_details, ensure_ascii=False)
            )
            session.add(entry)
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

        self.last_hash = entry_hash

        # 2. Local JSON file backup for UI fallback
        event_dict = {
            "log_id": log_id,
            "event_id": log_id,
            "actor_id": actor_id,
            "timestamp": timestamp_str,
            "agent_name": agent_name,
            "action_type": action_type,
            "document_id": doc_id_str,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "dpdp_compliant": dpdp_compliant,
            "user_approved": user_approved,
            "details": full_details,
        }
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
            entries = session.query(AuditLogEntryModel).order_by(AuditLogEntryModel.timestamp.asc()).all()
            if not entries:
                return {"is_tamper_free": True, "total_verified": 0, "message": "Audit chain empty"}

            expected_prev = self.GENESIS_HASH
            for idx, entry in enumerate(entries):
                if entry.prev_hash != expected_prev:
                    return {
                        "is_tamper_free": False,
                        "tampered_log_id": entry.log_id,
                        "expected_prev_hash": expected_prev,
                        "actual_prev_hash": entry.prev_hash,
                        "error": f"Hash chain broken at index {idx}"
                    }

                details = json.loads(entry.details_json) if entry.details_json else {}
                doc_id = entry.document_id or details.get("document_id") or details.get("file_name") or "doc_system"
                computed = self._compute_hash(
                    entry.prev_hash,
                    entry.log_id,
                    entry.actor_id,
                    entry.action_type,
                    doc_id,
                    entry.timestamp.isoformat(),
                    details
                )

                if computed != entry.entry_hash:
                    return {
                        "is_tamper_free": False,
                        "tampered_log_id": entry.log_id,
                        "computed_hash": computed,
                        "stored_hash": entry.entry_hash,
                        "error": f"Entry content payload modified at log_id {entry.log_id}"
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
        session = db_manager.get_session()
        try:
            entries = session.query(AuditLogEntryModel).order_by(AuditLogEntryModel.timestamp.desc()).all()
            return [e.to_dict() for e in entries]
        except Exception:
            if self.log_file.exists():
                with open(self.log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
        finally:
            session.close()

    def get_summary(self) -> Dict[str, Any]:
        logs = self.get_all_logs()
        total = len(logs)
        action_counts = {}
        dpdp_violations = 0
        hitl_approvals = 0

        for e in logs:
            act = e.get("action_type", "UNKNOWN")
            action_counts[act] = action_counts.get(act, 0) + 1
            if not e.get("dpdp_compliant", True):
                dpdp_violations += 1
            if e.get("user_approved", True):
                hitl_approvals += 1

        integrity = self.verify_integrity()

        return {
            "total_audit_events": total,
            "action_counts": action_counts,
            "dpdp_violations": dpdp_violations,
            "hitl_approvals": hitl_approvals,
            "compliance_rate": f"{100.0 if total == 0 else round((total - dpdp_violations) / total * 100, 1)}%",
            "hash_chain_integrity": integrity
        }
