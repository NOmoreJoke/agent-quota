"""Typed errors exposed by the application service."""

from __future__ import annotations


class AgentQuotaError(RuntimeError):
    code = "agent_quota_error"


class ContractViolation(AgentQuotaError):
    code = "adapter_contract_violation"


class NotAuthorized(AgentQuotaError):
    code = "not_authorized"


class LeaseConflict(AgentQuotaError):
    code = "lease_conflict"


class FenceConflict(AgentQuotaError):
    code = "fence_conflict"


class RefreshInProgress(AgentQuotaError):
    code = "refresh_in_progress"


class OutcomeUnknown(AgentQuotaError):
    code = "outcome_unknown"


class ProviderFailure(AgentQuotaError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DestructiveConfirmationRequired(AgentQuotaError):
    code = "destructive_confirmation_required"
