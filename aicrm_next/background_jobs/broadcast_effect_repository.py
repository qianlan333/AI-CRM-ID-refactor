from __future__ import annotations

from sqlalchemy import text

from aicrm_next.platform_foundation.external_effects.continuations import ExternalEffectContinuation
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.runtime import fixture_mode


def _matches(job, _dispatch_result) -> bool:
    return job.business_type == "broadcast_job" and str(job.business_id or "").strip().isdigit()


def _project(job, _dispatch_result):
    if fixture_mode():
        return {"ok": True, "projected": False, "reason": "fixture_read_model_not_persisted"}
    broadcast_job_id = int(job.business_id)
    with get_session_factory()() as session:
        rows = (
            session.execute(
                text(
                    """
                SELECT status
                FROM external_effect_job
                WHERE business_type = 'broadcast_job' AND business_id = :business_id
                ORDER BY id ASC
                """
                ),
                {"business_id": str(broadcast_job_id)},
            )
            .scalars()
            .all()
        )
        if not rows or any(status != "succeeded" for status in rows):
            session.rollback()
            return {
                "ok": True,
                "projected": False,
                "reason": "broadcast_effects_waiting",
                "effect_count": len(rows),
                "succeeded_count": len([status for status in rows if status == "succeeded"]),
            }
        session.execute(
            text(
                """
                UPDATE broadcast_jobs
                SET status = 'sent', sent_count = GREATEST(target_count, 1), failed_count = 0,
                    side_effect_executed = TRUE, provider_result_received = TRUE,
                    sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP),
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :job_id AND execution_owner = 'external_effect_job'
                """
            ),
            {"job_id": broadcast_job_id},
        )
        session.execute(
            text(
                """
                UPDATE cloud_broadcast_plan_recipients
                SET send_status = 'sent', last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE broadcast_job_id = :job_id
                """
            ),
            {"job_id": broadcast_job_id},
        )
        session.execute(
            text(
                """
                UPDATE cloud_broadcast_plan_recipient_messages message
                SET status = 'sent', sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP),
                    last_error = '', updated_at = CURRENT_TIMESTAMP
                FROM cloud_broadcast_plan_recipients recipient
                WHERE recipient.broadcast_job_id = :job_id
                  AND message.recipient_id = recipient.id
                  AND message.status <> 'sent'
                """
            ),
            {"job_id": broadcast_job_id},
        )
        session.commit()
    return {
        "ok": True,
        "projected": True,
        "broadcast_job_id": broadcast_job_id,
        "effect_count": len(rows),
    }


BROADCAST_EXTERNAL_EFFECT_READ_MODEL_CONTINUATION = ExternalEffectContinuation(
    name="broadcast_external_effect_read_model",
    matches=_matches,
    run=_project,
)


__all__ = ["BROADCAST_EXTERNAL_EFFECT_READ_MODEL_CONTINUATION"]
