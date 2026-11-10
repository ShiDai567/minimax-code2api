import json

import httpx
import pytest

from apps.checkin.models import CheckinJob, CheckinRecord, CheckinTask
from common.problems import ApiProblem
from services.checkin_service import checkin, enqueue, run_one
from tests.conftest import json_response, panel


def signin(today_status=2):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/signin/status"):
            return json_response({"base_resp": {"status_code": 0}, "data": panel(today_status)})
        if path.endswith("/signin/claim"):
            return json_response({
                "base_resp": {"status_code": 0},
                "data": {"claim_id": "claim-1", "claim_result": 1, "points": 10, "panel": panel(3)},
            })
        return json_response({"detail": "no"}, 404)

    return handler


@pytest.mark.django_db
def test_success_does_not_post_a_ledger_entry(account, transport):
    transport["handler"] = signin()
    record = checkin(account, "manual")
    assert record.status == "success"
    assert record.reward == 10
    assert record.arrival == "pending"
    from apps.credits.models import CreditEntry

    assert CreditEntry.objects.count() == 0


@pytest.mark.django_db
def test_already_claimed_is_skipped(account, transport):
    transport["handler"] = signin(today_status=3)
    record = checkin(account, "manual")
    assert record.status == "skipped"


@pytest.mark.django_db
def test_pending_row_is_never_replayed(account, transport):
    CheckinRecord.objects.create(account=account, region="cn", day=account.created_at.date(), status="pending", trigger="manual")
    with pytest.raises(ApiProblem) as caught:
        checkin(account, "manual")
    assert caught.value.code == "CHECKIN_PENDING"
    assert transport["handler"] is not None


@pytest.mark.django_db
def test_worker_runs_queued_tasks_and_a_second_pass_is_idle(account, transport):
    transport["handler"] = signin()
    job = enqueue("cn", [account.id], "batch")
    assert run_one() is True
    job.refresh_from_db()
    assert job.status == "completed"
    assert job.success_count == 1
    assert CheckinTask.objects.get().status == "success"
    assert run_one() is False


@pytest.mark.django_db
def test_schedule_key_dedup(account):
    enqueue("cn", [account.id], "schedule", "tz:2026-11-10:cn")
    with pytest.raises(ApiProblem) as caught:
        enqueue("cn", [account.id], "schedule", "tz:2026-11-10:cn")
    assert caught.value.code == "CONFLICT"
    assert CheckinJob.objects.count() == 1


@pytest.mark.django_db
def test_upstream_rejection_marks_the_account_expired(account, transport):
    transport["handler"] = lambda request: json_response({"detail": "no"}, 401)
    record = checkin(account, "manual")
    assert record.status == "failed"
    account.refresh_from_db()
    assert account.health == "expired"


@pytest.mark.django_db
def test_global_uses_its_own_origin(transport, db):
    from common.encryption import encrypt
    from apps.accounts.models import Account

    seen = {}
    global_account = Account.objects.create(
        region="global", name="g", identifier="g@example.com",
        credential_encrypted=encrypt("tok"), real_user_id="7", health="healthy",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        return json_response({"base_resp": {"status_code": 0}, "data": panel(3)})

    transport["handler"] = handler
    checkin(global_account, "manual")
    assert seen["host"] == "agent.minimax.io"
    assert json.dumps(seen)  # touch import so the assertion above is the contract
