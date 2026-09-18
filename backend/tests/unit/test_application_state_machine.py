import pytest

from app.models.application import ApplicationState
from app.services.applications import IllegalStateTransition, validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ApplicationState.INTERESTED, ApplicationState.TAILORING),
        (ApplicationState.TAILORING, ApplicationState.READY_FOR_REVIEW),
        (ApplicationState.READY_FOR_REVIEW, ApplicationState.APPROVED),
        (ApplicationState.READY_FOR_REVIEW, ApplicationState.PENDING_CAPTCHA),
        (ApplicationState.READY_FOR_REVIEW, ApplicationState.REJECTED_BY_USER),
        (ApplicationState.PENDING_CAPTCHA, ApplicationState.SUBMITTED),
        (ApplicationState.APPROVED, ApplicationState.SUBMITTED),
        (ApplicationState.SUBMITTED, ApplicationState.RESPONSE_TRACKED),
    ],
)
def test_legal_transitions_do_not_raise(current: ApplicationState, target: ApplicationState) -> None:
    validate_transition(current, target)  # no exception = pass


@pytest.mark.parametrize(
    ("current", "target"),
    [
        # can't skip straight from interest to submission
        (ApplicationState.INTERESTED, ApplicationState.SUBMITTED),
        # can't go backwards
        (ApplicationState.READY_FOR_REVIEW, ApplicationState.INTERESTED),
        (ApplicationState.SUBMITTED, ApplicationState.APPROVED),
        # terminal states have no outgoing transitions at all
        (ApplicationState.RESPONSE_TRACKED, ApplicationState.SUBMITTED),
        (ApplicationState.REJECTED_BY_USER, ApplicationState.TAILORING),
        # can't self-transition
        (ApplicationState.TAILORING, ApplicationState.TAILORING),
    ],
)
def test_illegal_transitions_raise(current: ApplicationState, target: ApplicationState) -> None:
    with pytest.raises(IllegalStateTransition):
        validate_transition(current, target)


def test_rejected_by_user_reachable_from_every_non_terminal_state() -> None:
    non_terminal = {
        ApplicationState.INTERESTED,
        ApplicationState.TAILORING,
        ApplicationState.READY_FOR_REVIEW,
        ApplicationState.PENDING_CAPTCHA,
        ApplicationState.APPROVED,
    }
    for state in non_terminal:
        validate_transition(state, ApplicationState.REJECTED_BY_USER)  # no exception = pass


def test_legal_next_states_matches_allowed_transitions() -> None:
    from app.models.application import ALLOWED_TRANSITIONS, Application

    for state, expected in ALLOWED_TRANSITIONS.items():
        application = Application(profile_id=1, job_id=1, state=state)
        assert set(application.legal_next_states) == expected


def test_legal_next_states_is_empty_for_a_terminal_state() -> None:
    from app.models.application import Application, ApplicationState

    application = Application(profile_id=1, job_id=1, state=ApplicationState.RESPONSE_TRACKED)

    assert application.legal_next_states == []
