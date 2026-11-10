from django.db.models import Count, Q
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.accounts.views import checkin_payload
from apps.checkin.models import CheckinJob, CheckinRecord, CheckinTask
from common.pagination import envelope
from common.problems import ApiProblem
from common.utils import epoch_ms, region_required
from services.checkin_service import enqueue


class CheckinRecordView(APIView):
    def get(self, request):
        region = region_required(request.query_params.get("region")) if request.query_params.get("region") else None
        query = CheckinRecord.objects.select_related("account").order_by("-id")
        if region:
            query = query.filter(region=region)
        if "status" in request.query_params:
            query = query.filter(status=request.query_params["status"])
        items = [checkin_payload(row) for row in query[:200]]
        return envelope({"items": items, "total": query.count()})


class CheckinJobView(APIView):
    def get(self, request):
        region = request.query_params.get("region")
        query = CheckinJob.objects.order_by("-created_at")
        if region:
            region_required(region)
            query = query.filter(region=region)
        return envelope({"items": [_job(row) for row in query[:100]], "total": query.count()})

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        region = body.get("region")
        scope = body.get("scope")
        if scope == "all":
            ids = list(Account.objects.filter(enabled=True).values_list("id", flat=True))
            if not ids:
                raise ApiProblem("No enabled accounts")
            jobs = []
            for item in ("cn", "global"):
                regional = [account_id for account_id in ids if Account.objects.filter(id=account_id, region=item).exists()]
                if regional:
                    jobs.append(enqueue(item, regional, "batch"))
            return envelope({"jobs": [_job(job) for job in jobs]}, 202)
        region_required(region)
        if scope == "region":
            ids = list(Account.objects.filter(region=region, enabled=True).values_list("id", flat=True))
        else:
            ids = body.get("account_ids") or []
        if not ids:
            raise ApiProblem("No accounts selected")
        return envelope(_job(enqueue(region, ids, body.get("trigger") or "batch")), 202)


class CheckinJobDetailView(APIView):
    def get(self, request, job_id):
        job = CheckinJob.objects.filter(id=job_id).first()
        if job is None:
            raise ApiProblem("Resource not found", 404, "NOT_FOUND")
        return envelope(_job(job, include_tasks=True))


class CheckinSummaryView(APIView):
    def get(self, request):
        from django.utils import timezone

        today = timezone.now().date()
        records = CheckinRecord.objects.filter(day=today)
        return envelope({
            "total": Account.objects.count(),
            "pending": records.filter(status="pending").count(),
            "success": records.filter(status="success").count(),
            "failed": records.filter(status="failed").count(),
            "skipped": records.filter(status="skipped").count(),
            "awaitingArrival": records.filter(status="success", arrival="pending").count(),
            "notRun": Account.objects.exclude(id__in=records.values("account_id")).count(),
        })


def _job(job, include_tasks=False):
    payload = {
        "id": job.id,
        "region": job.region,
        "status": job.status,
        "trigger": job.trigger,
        "total": job.total,
        "success": job.success_count,
        "failed": job.failure_count,
        "skipped": job.skipped_count,
        "createdAt": epoch_ms(job.created_at),
        "finishedAt": epoch_ms(job.finished_at),
    }
    if include_tasks or job.status != "completed":
        tasks = CheckinTask.objects.filter(job=job).order_by("id")
        counts = tasks.aggregate(
            success=Count("id", filter=Q(status="success")),
            failed=Count("id", filter=Q(status="failed")),
            skipped=Count("id", filter=Q(status="skipped")),
        )
        payload.update({"success": counts["success"], "failed": counts["failed"], "skipped": counts["skipped"]})
        payload["tasks"] = [
            {"accountId": str(task.account_id), "status": task.status, "message": task.message} for task in tasks
        ]
    return payload
