"""
GET /v1/sessions/progress: the current user's score trend.

Uses real signed access tokens (get_current_user is NOT overridden),
so the actual JWT decode + user lookup path runs, as in
test_cross_user_authorization.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

URL = "/v1/sessions/progress"

METRIC_COLUMNS = {
    "overall": "overall_score",
    "argumentation": "score_argumentation",
    "rebuttal": "score_rebuttal",
    "structure": "score_structure",
    "persuasion": "score_persuasion",
    "logic": "score_logic",
}


@pytest.fixture
def token_client(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def get(user, **params):
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"} if user else {}
        return client.get(URL, params=params, headers=headers)

    yield get
    app.dependency_overrides.clear()


NOW = datetime.now(timezone.utc)


@pytest.fixture
def add_session(db):
    from app.models.session import DebateSession, SessionStatus

    def _add(user, hours_ago, status=SessionStatus.completed, **scores):
        values = {column: 50.0 for column in METRIC_COLUMNS.values()}
        values.update(scores)
        row = DebateSession(
            user_id=user.id,
            status=status,
            created_at=NOW - timedelta(hours=hours_ago),
            **values,
        )
        db.add(row)
        db.commit()
        return row

    return _add


def ids(response):
    assert response.status_code == 200, response.text
    return [uuid.UUID(point["session_id"]) for point in response.json()]


# ---------------------------------------------------------------
# 🔒 Isolation and status
# ---------------------------------------------------------------

@pytest.mark.parametrize("range_", ["1d", "1w", "1m", "5", "10", "15"])
def test_a_user_never_sees_another_users_sessions(token_client, add_session, make_user, range_):
    alice, bob = make_user("a@test"), make_user("b@test")
    mine = [add_session(alice, hours).id for hours in (3, 50, 200)]
    # Bob's are newer, so a leak would take the "newest N" slots too.
    for hours in (1, 2, 4, 5, 6, 7, 8):
        add_session(bob, hours)

    returned = ids(token_client(alice, metric="overall", range=range_))

    assert set(returned) <= set(mine)
    assert returned  # every range covers at least Alice's 3h-old session


def test_only_completed_sessions_are_returned(token_client, add_session, make_user):
    from app.models.session import SessionStatus

    alice = make_user("a@test")
    done = add_session(alice, 1).id
    for status in SessionStatus:
        if status is not SessionStatus.completed:
            add_session(alice, 2, status=status, overall_score=99.0)

    for range_ in ("1d", "15"):
        assert ids(token_client(alice, metric="overall", range=range_)) == [done]


# ---------------------------------------------------------------
# Ranges
# ---------------------------------------------------------------

# 17 sessions, newest first. Chosen to straddle every window edge.
HOURS_AGO = [0.5, 6, 23, 25, 48, 100, 160, 170, 200, 400, 700, 719, 721, 900, 1200, 1500, 2000]


@pytest.fixture
def history(add_session, make_user):
    alice = make_user("a@test")
    rows = {hours: add_session(alice, hours).id for hours in HOURS_AGO}
    return alice, rows


@pytest.mark.parametrize(
    "range_, expected_hours",
    [
        ("1d", [h for h in HOURS_AGO if h < 24]),
        ("1w", [h for h in HOURS_AGO if h < 24 * 7]),
        ("1m", [h for h in HOURS_AGO if h < 24 * 30]),
        ("5", HOURS_AGO[:5]),
        ("10", HOURS_AGO[:10]),
        ("15", HOURS_AGO[:15]),
    ],
)
def test_each_range_returns_the_right_sessions_oldest_first(token_client, history, range_, expected_hours):
    alice, rows = history
    expected = [rows[h] for h in sorted(expected_hours, reverse=True)]  # oldest first

    assert ids(token_client(alice, metric="overall", range=range_)) == expected


def test_windows_are_rolling_from_now_not_calendar_days(token_client, history):
    alice, rows = history
    one_day = ids(token_client(alice, metric="overall", range="1d"))

    assert rows[23] in one_day and rows[25] not in one_day
    month = ids(token_client(alice, metric="overall", range="1m"))
    assert rows[719] in month and rows[721] not in month


def test_count_range_with_fewer_sessions_returns_what_exists(token_client, add_session, make_user):
    alice = make_user("a@test")
    only = [add_session(alice, hours).id for hours in (5, 1)]
    assert ids(token_client(alice, metric="overall", range="15")) == only


# ---------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------

@pytest.mark.parametrize("metric, column", METRIC_COLUMNS.items())
def test_each_metric_returns_its_own_score(token_client, add_session, make_user, metric, column):
    alice = make_user("a@test")
    # A distinct value per column, so reading the wrong one shows.
    distinct = {c: 10.0 + i for i, c in enumerate(METRIC_COLUMNS.values())}
    row = add_session(alice, 1, **distinct)

    [point] = token_client(alice, metric=metric, range="5").json()

    assert point["score"] == distinct[column]
    assert point["session_id"] == str(row.id)
    assert set(point) == {"session_id", "created_at", "score"}


def test_rebuttal_not_scored_comes_back_null(token_client, add_session, make_user):
    alice = make_user("a@test")
    add_session(alice, 2, score_rebuttal=60.0)
    add_session(alice, 1, score_rebuttal=None)

    scores = [p["score"] for p in token_client(alice, metric="rebuttal", range="5").json()]
    assert scores == [60.0, None]


# ---------------------------------------------------------------
# Validation and auth
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "params",
    [
        {"metric": "quantitative", "range": "5"},
        {"metric": "Overall", "range": "5"},
        {"metric": "", "range": "5"},
        {"metric": "overall", "range": "7"},
        {"metric": "overall", "range": "1y"},
        {"metric": "overall", "range": "-5"},
        {"metric": "overall", "range": "5 "},
        {"metric": "overall"},
        {"range": "5"},
        {},
    ],
)
def test_invalid_or_missing_parameters_are_422(token_client, make_user, params):
    response = token_client(make_user("a@test"), **params)
    assert response.status_code == 422
    # Reached this route's validation, not /{session_id}'s UUID parse.
    assert all(err["loc"][0] == "query" for err in response.json()["detail"])


def test_requires_authentication(token_client):
    assert token_client(None, metric="overall", range="5").status_code == 401


# ---------------------------------------------------------------
# The pipeline writes the columns
# ---------------------------------------------------------------

def test_pipeline_records_category_scores(db, make_user):
    from app.models.session import DebateSession
    from app.services.pipeline import _record_summary
    from coaching_engine.models.scores import CategoryScores, CoachingScores

    alice = make_user("a@test")
    row = DebateSession(user_id=alice.id)
    scores = CoachingScores(
        categories=CategoryScores(
            quantitative=85.0, argumentation=75.0, rebuttal=None, structure=60.0, persuasion=40.0, logic=20.0
        ),
        overall=56.0,
    )

    _record_summary(row, raw_metrics={"speech": {}}, scores=scores, feedback_count=5)

    assert (row.score_argumentation, row.score_rebuttal, row.score_structure, row.score_persuasion, row.score_logic) == (
        75.0,
        None,
        60.0,
        40.0,
        20.0,
    )
    assert row.overall_score == 56.0
