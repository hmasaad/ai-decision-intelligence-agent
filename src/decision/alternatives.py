"""Generate more than one way to decide, including doing nothing."""

from decision.models import Option


def migration_options() -> list[Option]:
    return [
        Option(
            key="A",
            name="Do nothing",
            summary="Keep the current architecture and change nothing.",
            role="status_quo",
        ),
        Option(
            key="B",
            name="Partial migration",
            summary="Hybrid: keep the service and move one slice behind a strangler facade.",
            role="hybrid",
        ),
        Option(
            key="C",
            name="Full migration",
            summary="Replace the architecture in one cutover.",
            role="replacement",
        ),
        Option(
            key="D",
            name="Managed billing service",
            summary="Buy a managed billing service instead of migrating this one.",
            role="alternative",
        ),
    ]


def complete_alternatives(options: list[Option], pattern: str) -> list[Option]:
    """Always keep a status-quo option. A migration also keeps a hybrid."""

    if pattern == "migration" and not options:
        return migration_options()
    labeled = [_label(option) for option in options]
    if not any(option.role == "status_quo" for option in labeled):
        labeled = [_status_quo(_keys(labeled))] + labeled
    if pattern == "migration" and not any(option.role == "hybrid" for option in labeled):
        labeled.append(_hybrid(_keys(labeled)))
    return labeled


def _label(option: Option) -> Option:
    if option.role:
        return option
    name = option.name.lower()
    if name in {"do nothing", "keep current architecture"} or "status quo" in name:
        role = "status_quo"
    elif any(token in name for token in ("partial", "hybrid", "strangler")):
        role = "hybrid"
    elif "full" in name:
        role = "replacement"
    else:
        role = "alternative"
    return option.model_copy(update={"role": role})


def _keys(options: list[Option]) -> set[str]:
    return {option.key for option in options}


def _next_key(used: set[str]) -> str:
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if letter not in used:
            return letter
    return "Z"


def _status_quo(used: set[str]) -> Option:
    return Option(
        key=_next_key(used),
        name="Do nothing",
        summary="Leave the current state unchanged.",
        role="status_quo",
    )


def _hybrid(used: set[str]) -> Option:
    return Option(
        key=_next_key(used),
        name="Partial migration",
        summary="Hybrid: keep the service and move one slice behind a strangler facade.",
        role="hybrid",
    )
