"""Model names are passed through. Nothing is invented, and nothing is aliased unless the operator set a default."""
from apps.models_manager.models import UpstreamModel
from apps.system_settings.services import get_settings
from common.problems import ApiProblem
from common.utils import utcnow


def resolve(region, requested):
    if not isinstance(requested, str) or not 0 < len(requested) <= 255:
        raise ApiProblem("A model is required", 400)
    known = UpstreamModel.objects.filter(region=region, model_id=requested, enabled=True).first()
    if known:
        return requested
    default = get_settings()["api"].get("defaultModel") or ""
    catalog_exists = UpstreamModel.objects.filter(region=region, enabled=True).exists()
    if catalog_exists and default and requested != default:
        if UpstreamModel.objects.filter(region=region, model_id=default, enabled=True).exists():
            return default
        raise ApiProblem("Requested model is not in the verified catalog", 400, "UNKNOWN_MODEL")
    if catalog_exists and not known:
        raise ApiProblem("Requested model is not in the verified catalog", 400, "UNKNOWN_MODEL")
    return requested


def observe(region, model_id):
    if not model_id or len(model_id) > 255:
        return
    row, _created = UpstreamModel.objects.get_or_create(
        region=region,
        model_id=model_id,
        defaults={
            "display_name": model_id,
            "source": "observed",
            "protocols": ["anthropic", "openai_chat", "openai_responses"],
            "last_used_at": utcnow(),
        },
    )
    if not _created:
        row.last_used_at = utcnow()
        row.save(update_fields=["last_used_at", "updated_at"])
