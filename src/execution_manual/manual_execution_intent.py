"""Manual Execution Intent -- the USER's explicit manual-execution choice, the
proper Kriya boundary object downstream of Saarathi's ``PersonalizedAction``.

This is where the chosen SIZE first exists. Saarathi (Personal CIO) recommends a
sizing RANGE / max exposure % and NEVER an exact order; the USER selects an
explicit size HERE, at the Kriya boundary; Kriya then makes a manual trade-ticket
PREVIEW from this intent; and the broker trade is placed MANUALLY, by hand,
outside the system (no broker adapter, no automated submission).

The intent is a ``ReasoningObject`` -- it records the user's chosen intent, not a
deed in the world. It is deliberately NOT a broker order: it carries no
``broker_order_id``, no ``order_type``, no ``limit_price`` / ``stop_price``, and
no ``venue``. Those order parameters live only on the operational
``ManualTradeTicket`` that Kriya builds from this intent.

Layer purity: this module imports NO reasoning layer (no ``personal_cio`` /
``prometheus`` / ``genesis`` / ``reality_intelligence``). The upstream
``PersonalizedAction`` is consumed duck-typed, so the execution (Kriya) layer
never depends on the cognition layers (ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

# The manual-execution intent vocabulary. This is candidate/lifecycle language at
# the actuation boundary -- it is NOT a broker side: ``_side_for_execution`` in
# ``manual_trade_ticket`` maps it to the ticket's buy/sell.
EXECUTION_SIDES = frozenset({"open_candidate", "reduce_candidate", "close_candidate"})


@dataclass(frozen=True)
class ManualExecutionIntent(ReasoningObject):
    """The user-approved manual-execution intent, downstream of a
    ``PersonalizedAction``.

    Carries the USER's explicit chosen size (``user_selected_allocation_amount``)
    -- the number Saarathi deliberately never produces -- plus the selected
    instrument, the execution side, the account, and the provenance binding back
    to the personalized action (and transitively to the thesis, action, and
    observations). It is NOT a broker order: no ``broker_order_id`` /
    ``order_type`` / ``limit_price`` / ``stop_price`` / ``venue``.
    """

    source_personalized_action_id: str = ""
    source_personalized_action_version: int = 1
    source_action_id: str = ""
    source_thesis_id: str = ""
    selected_instrument: str = ""
    user_selected_allocation_amount: float = 0.0
    user_selected_allocation_pct: Optional[float] = None
    execution_side: str = "open_candidate"
    user_confirmation_required: bool = True
    stale_check_required: bool = True
    preview_required: bool = True
    account: str = ""
    upstream_observation_ids: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def execution_intent_id(self) -> str:
        return self.id


def make_manual_execution_intent(personalized_action, *, selected_instrument,
                                 user_selected_allocation_amount, execution_side,
                                 user_selected_allocation_pct=None, actor="user", now):
    """Build the user's ``ManualExecutionIntent`` from Saarathi's
    ``PersonalizedAction`` plus the user's EXPLICIT chosen size.

    The personalized action is consumed duck-typed (it must expose
    ``recommendation_status``, ``source_action_id``, ``id`` and ``ref()``); no
    ``personal_cio`` import, so the Kriya layer never depends on the reasoning
    layer. ``user_selected_allocation_amount`` must be an explicit positive number
    -- the user must CHOOSE a size; Saarathi only recommends a range.
    """
    if personalized_action is None:
        raise ValueError(
            "make_manual_execution_intent requires a PersonalizedAction (the "
            "Saarathi product the user is acting on); got None"
        )
    for attr in ("recommendation_status", "source_action_id", "id", "ref"):
        if not hasattr(personalized_action, attr):
            raise ValueError(
                "make_manual_execution_intent requires a PersonalizedAction-like "
                "object exposing recommendation_status / source_action_id / id / "
                "ref(); missing {0!r}".format(attr)
            )

    if user_selected_allocation_amount is None or float(user_selected_allocation_amount) <= 0.0:
        raise ValueError(
            "make_manual_execution_intent requires an explicit, positive "
            "user_selected_allocation_amount: the user must choose an explicit "
            "size; Saarathi only recommends a range"
        )

    if execution_side not in EXECUTION_SIDES:
        raise ValueError(
            "execution_side must be one of {0}; got {1!r}".format(
                sorted(EXECUTION_SIDES), execution_side)
        )

    source_personalized_action_id = personalized_action.id
    source_personalized_action_version = int(getattr(personalized_action, "version", 1))
    source_action_id = getattr(personalized_action, "source_action_id", "")
    source_thesis_id = getattr(personalized_action, "source_thesis_id", "")
    account = getattr(personalized_action, "account", "")
    upstream_observation_ids = tuple(getattr(personalized_action, "upstream_observation_ids", ()))

    sources = (personalized_action.ref("PersonalizedAction"),)
    oid = stable_id(
        "MEI", source_action_id, source_personalized_action_id,
        source_personalized_action_version, execution_side, selected_instrument
    )
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)

    return ManualExecutionIntent(
        id=oid,
        version=1,
        provenance=prov,
        source_personalized_action_id=source_personalized_action_id,
        source_personalized_action_version=source_personalized_action_version,
        source_action_id=source_action_id,
        source_thesis_id=source_thesis_id,
        selected_instrument=selected_instrument,
        user_selected_allocation_amount=float(user_selected_allocation_amount),
        user_selected_allocation_pct=(
            None if user_selected_allocation_pct is None
            else float(user_selected_allocation_pct)
        ),
        execution_side=execution_side,
        user_confirmation_required=True,
        stale_check_required=True,
        preview_required=True,
        account=account,
        upstream_observation_ids=upstream_observation_ids,
    )
