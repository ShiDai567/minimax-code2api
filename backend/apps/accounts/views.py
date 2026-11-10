from django.db.models import Q
from rest_framework.views import APIView

from apps.accounts.models import Account, AccountGroup
from apps.accounts.serializers import account_payload
from apps.checkin.models import CheckinRecord
from common.pagination import envelope, page_params
from common.problems import ApiProblem
from common.utils import region_required, text
from services.account_service import create_account, delete_account, import_accounts, set_enabled, update_account, validate_group, verify_account
from services.checkin_service import checkin, enqueue
from services.credit_service import sync_credits


def _region(request):
    return region_required(request.query_params.get("region"))


class AccountListView(APIView):
    def get(self, request):
        region = _region(request)
        query = Account.objects.filter(region=region)
        search = request.query_params.get("search", "").strip()
        if search:
            query = query.filter(Q(name__icontains=search) | Q(identifier__icontains=search))
        if "enabled" in request.query_params:
            query = query.filter(enabled=request.query_params["enabled"] == "true")
        if "health" in request.query_params:
            health = request.query_params["health"]
            if health not in ("unknown", "healthy", "error", "expired"):
                raise ApiProblem("Invalid health filter")
            query = query.filter(health=health)
        if "group_id" in request.query_params:
            validate_group(int(request.query_params["group_id"]), region)
            query = query.filter(group_id=request.query_params["group_id"])
        try:
            limit, offset, sort, order = page_params(request, {"id", "name", "created_at", "last_active_at"}, "id")
        except ValueError as exc:
            raise ApiProblem(str(exc)) from None
        sort_map = {"created_at": "created_at", "last_active_at": "last_active_at", "id": "id", "name": "name"}
        column = sort_map[sort]
        if order == "desc":
            column = "-" + column
        total = query.count()
        items = [account_payload(row) for row in query.order_by(column)[offset : offset + limit]]
        return envelope({"items": items, "total": total})

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        account = create_account(body, body.get("model") or "")
        return envelope(account_payload(account), 201)


class AccountDetailView(APIView):
    def get(self, request, account_id):
        return envelope(account_payload(_get(account_id)))

    def patch(self, request, account_id):
        account = update_account(_get(account_id), request.data if isinstance(request.data, dict) else {})
        return envelope(account_payload(account))

    def delete(self, request, account_id):
        delete_account(_get(account_id))
        return envelope({"deleted": True})


class AccountImportView(APIView):
    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        created, failed = import_accounts(body.get("region"), body.get("accounts"))
        return envelope({"created": [account_payload(row) for row in created], "failed": failed})


class BulkDeleteView(APIView):
    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        region = region_required(body.get("region"))
        ids = body.get("account_ids") or body.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ApiProblem("account_ids is required")
        rows = list(Account.objects.filter(id__in=ids, region=region))
        if len(rows) != len(set(ids)):
            raise ApiProblem("All accounts must exist in the selected region")
        deleted = 0
        blocked = []
        for row in rows:
            try:
                delete_account(row)
                deleted += 1
            except ApiProblem:
                blocked.append(row.id)
        return envelope({"deleted": deleted, "blocked": blocked})


class VerifyView(APIView):
    def post(self, request, account_id):
        model = (request.data or {}).get("model") if isinstance(request.data, dict) else None
        return envelope(account_payload(verify_account(_get(account_id), model or "")))


class AccountCheckinView(APIView):
    def post(self, request, account_id):
        record = checkin(_get(account_id), "manual")
        return envelope(_checkin_payload(record), 200 if record.status != "failed" else 502)


class SyncCreditsView(APIView):
    def post(self, request, account_id):
        account, snapshot = sync_credits(_get(account_id))
        return envelope({
            "account": account_payload(account),
            "snapshot": {
                "amount": str(snapshot.amount),
                "unit": snapshot.unit,
                "certainty": "reported",
            },
        })


class EnableView(APIView):
    def post(self, request, account_id):
        return envelope(account_payload(set_enabled(_get(account_id), True)))


class DisableView(APIView):
    def post(self, request, account_id):
        return envelope(account_payload(set_enabled(_get(account_id), False)))


class GroupListView(APIView):
    def get(self, request):
        region = _region(request)
        query = AccountGroup.objects.filter(region=region)
        search = request.query_params.get("search", "").strip()
        if search:
            query = query.filter(name__icontains=search)
        items = [_group_payload(row) for row in query.order_by("id")]
        return envelope({"items": items, "total": len(items)})

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        region = region_required(body.get("region"))
        strategy = body.get("strategy") or "round_robin"
        if strategy not in AccountGroup.STRATEGIES:
            raise ApiProblem("Invalid strategy")
        group = AccountGroup.objects.create(
            region=region,
            name=text(body.get("name", ""), "name", 120),
            description=text(body.get("description", ""), "description", 4000, required=False),
            strategy=strategy,
        )
        return envelope(_group_payload(group), 201)


class GroupDetailView(APIView):
    def patch(self, request, group_id):
        group = _group(group_id)
        body = request.data if isinstance(request.data, dict) else {}
        if "name" in body:
            group.name = text(body.get("name", ""), "name", 120)
        if "description" in body:
            group.description = text(body.get("description", ""), "description", 4000, required=False)
        if "strategy" in body:
            if body["strategy"] not in AccountGroup.STRATEGIES:
                raise ApiProblem("Invalid strategy")
            group.strategy = body["strategy"]
        group.save()
        return envelope(_group_payload(group))

    def delete(self, request, group_id):
        group = _group(group_id)
        Account.objects.filter(group=group).update(group=None)
        group.delete()
        return envelope({"deleted": True})


def _get(account_id):
    account = Account.objects.filter(id=account_id).first()
    if account is None:
        raise ApiProblem("Resource not found", 404, "NOT_FOUND")
    return account


def _group(group_id):
    group = AccountGroup.objects.filter(id=group_id).first()
    if group is None:
        raise ApiProblem("Resource not found", 404, "NOT_FOUND")
    return group


def _group_payload(group):
    accounts = Account.objects.filter(group=group)
    from common.utils import epoch_ms

    return {
        "id": str(group.id),
        "region": group.region,
        "name": group.name,
        "description": group.description,
        "strategy": group.strategy,
        "createdAt": epoch_ms(group.created_at),
        "accountCount": accounts.count(),
        "healthyCount": accounts.filter(enabled=True, health="healthy").count(),
        "balance": None,
    }


def _checkin_payload(record):
    from common.utils import epoch_ms

    return {
        "id": str(record.id),
        "accountId": str(record.account_id),
        "region": record.region,
        "at": epoch_ms(record.updated_at),
        "day": record.day.isoformat(),
        "result": "success" if record.status in ("success", "skipped") else "failed",
        "status": record.status,
        "reward": None if record.reward is None else float(record.reward),
        "arrival": record.arrival or None,
        "ledgerId": str(record.ledger_id) if record.ledger_id else None,
        "failReason": record.message if record.status == "failed" else None,
        "message": record.message,
        "trigger": record.trigger,
    }


def checkin_payload(record):
    return _checkin_payload(record)
