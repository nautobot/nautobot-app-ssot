import logging

from django import template


logger = logging.getLogger(__name__)


register = template.Library()


@register.inclusion_tag("nautobot_ssot/templatetags/dashboard_data.html")
def dashboard_data(sync_worker_class, queryset, kind="source"):
    if kind == "source":
        records = queryset.filter(source=sync_worker_class.name).order_by("-start_time")
    else:
        records = queryset.filter(target=sync_worker_class.name).order_by("-start_time")
    return {"statuses": [record.job_result.status for record in records[:10]], "count": records.count()}
