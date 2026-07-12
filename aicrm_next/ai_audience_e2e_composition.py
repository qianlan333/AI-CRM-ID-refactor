from __future__ import annotations

from dataclasses import dataclass

from .ai_audience_ops.e2e_runner import AudienceRealE2ERunner
from .ai_audience_ops.repository import AudienceRepository
from .ops_enrollment.ai_audience_e2e_gateway import OpsEnrollmentAudienceE2EGateway


@dataclass(frozen=True)
class AiAudienceE2ERunnerFactory:
    user_ops_gateway: OpsEnrollmentAudienceE2EGateway

    def __call__(self, *, repository: AudienceRepository | None = None) -> AudienceRealE2ERunner:
        return AudienceRealE2ERunner(
            repository=repository,
            user_ops_gateway=self.user_ops_gateway,
        )


def build_ai_audience_e2e_runner_factory() -> AiAudienceE2ERunnerFactory:
    return AiAudienceE2ERunnerFactory(
        user_ops_gateway=OpsEnrollmentAudienceE2EGateway(),
    )
