from typing import Any

from app.agents.jerarquico.graph.state import ServiceState


def make_team_supervisor(team: str):
    def team_supervisor(_state: ServiceState) -> dict[str, Any]:
        return {"team": team}

    return team_supervisor
