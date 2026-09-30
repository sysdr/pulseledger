"""
The service's own lifecycle, modeled as an explicit state machine.

    starting ──► ready ◄──► degraded
        │          │           │
        └──────────┴───────────┴──► stopping

Postgres is required: if it's unreachable at boot, the process fails to
start. Redis is not: losing it moves the service to `degraded`, and it
returns to `ready` on its own once Redis answers again.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ServiceState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"


ALLOWED: dict[ServiceState, set[ServiceState]] = {
    ServiceState.STARTING: {ServiceState.READY, ServiceState.DEGRADED, ServiceState.STOPPING},
    ServiceState.READY: {ServiceState.DEGRADED, ServiceState.STOPPING},
    ServiceState.DEGRADED: {ServiceState.READY, ServiceState.STOPPING},
    ServiceState.STOPPING: set(),
}


class IllegalTransition(RuntimeError):
    pass


@dataclass
class Lifecycle:
    state: ServiceState = ServiceState.STARTING
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    transitions: int = 0

    def move_to(self, target: ServiceState) -> bool:
        """Apply a transition. Returns True if the state actually changed."""
        if target == self.state:
            return False
        if target not in ALLOWED[self.state]:
            raise IllegalTransition(f"{self.state} -> {target} is not allowed")
        self.state = target
        self.changed_at = datetime.now(UTC)
        self.transitions += 1
        return True
