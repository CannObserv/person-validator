"""Admin configuration for persons app models.

Covers Person, PersonName, PersonAttribute, AttributeLabel, ExternalPlatform,
and WikidataCandidateReview.
"""

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from src.core.enrichment.providers.wikidata import WikidataProvider
from src.core.enrichment.tasks import rollback_wikidata_autolink
from src.core.logging import get_logger
from src.web.persons.models import (
    AttributeLabel,
    EnrichmentRun,
    ExternalIdentifierProperty,
    ExternalPlatform,
    Person,
    PersonAttribute,
    PersonName,
    WikidataCandidateReview,
)

logger = get_logger(__name__)

# Statuses that have been resolved and should not accept further actions.
_RESOLVED_STATUSES = frozenset({"accepted", "confirmed", "rejected", "skipped"})


class PersonNameInline(admin.TabularInline):
    """Inline editor for PersonName records on the Person admin page."""

    model = PersonName
    extra = 0
    fields = (
        "name_type",
        "full_name",
        "given_name",
        "middle_name",
        "surname",
        "prefix",
        "suffix",
        "is_primary",
        "source",
        "confidence",
        "provenance",
    )
    readonly_fields = ("created_at", "updated_at")


class PersonAttributeInline(admin.TabularInline):
    """Read-only inline for PersonAttribute records on the Person admin page."""

    model = PersonAttribute
    extra = 0
    fields = ("source", "key", "value", "value_type", "confidence", "created_at")
    readonly_fields = ("source", "key", "value", "value_type", "confidence", "created_at")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """Admin interface for Person with PersonName and PersonAttribute inlines."""

    list_display = ("name", "given_name", "surname", "created_at")
    search_fields = ("name", "given_name", "surname")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [PersonNameInline, PersonAttributeInline]


@admin.register(PersonName)
class PersonNameAdmin(admin.ModelAdmin):
    """Standalone admin for PersonName — useful for inspecting enrichment-created names.

    PersonName records are also accessible as an inline on PersonAdmin (for
    contextual display within a single person record). Both registrations are
    intentional and serve different purposes.
    """

    list_display = (
        "person",
        "full_name",
        "name_type",
        "confidence",
        "is_primary",
        "source",
        "created_at",
    )
    list_filter = ("name_type", "source", "is_primary")
    search_fields = ("person__name", "full_name", "source")
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        "person",
        "name_type",
        "full_name",
        "given_name",
        "middle_name",
        "surname",
        "prefix",
        "suffix",
        "is_primary",
        "source",
        "confidence",
        "provenance",
        "effective_date",
        "end_date",
        "notes",
        "created_at",
        "updated_at",
    )


@admin.register(PersonAttribute)
class PersonAttributeAdmin(admin.ModelAdmin):
    """Standalone admin for PersonAttribute with filtering by type and source.

    PersonAttribute is intentionally registered both here (for cross-person
    querying and filtering) and as a read-only inline on PersonAdmin (for
    contextual display within a single person record). The two registrations
    serve different purposes and are both intentional.
    """

    list_display = ("person", "source", "key", "value", "value_type", "confidence", "created_at")
    list_filter = ("source", "key", "value_type")
    search_fields = ("person__name", "source", "key", "value")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(AttributeLabel)
class AttributeLabelAdmin(admin.ModelAdmin):
    """Admin for the controlled label vocabulary."""

    list_display = ("value_type", "slug", "display", "sort_order", "is_active")
    list_filter = ("value_type", "is_active")
    search_fields = ("slug", "display")
    ordering = ("value_type", "sort_order", "slug")


@admin.register(ExternalPlatform)
class ExternalPlatformAdmin(admin.ModelAdmin):
    """Admin for the external platform/identity vocabulary."""

    list_display = ("slug", "display", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug", "display")
    ordering = ("sort_order", "slug")


@admin.register(EnrichmentRun)
class EnrichmentRunAdmin(admin.ModelAdmin):
    """Read-only admin for the EnrichmentRun audit log."""

    list_display = (
        "person",
        "provider",
        "status",
        "attributes_saved",
        "attributes_refreshed",
        "attributes_skipped",
        "triggered_by",
        "started_at",
        "completed_at",
    )
    list_filter = ("provider", "status", "triggered_by")
    search_fields = ("person__name", "provider")
    readonly_fields = (
        "id",
        "person",
        "provider",
        "status",
        "attributes_saved",
        "attributes_refreshed",
        "attributes_skipped",
        "warnings",
        "error",
        "triggered_by",
        "started_at",
        "completed_at",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ANN001
        """Prevent manual creation of audit log entries."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ANN001
        """Prevent editing of audit log entries."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ANN001
        """Prevent deletion of audit log entries."""
        return False


@admin.register(WikidataCandidateReview)
class WikidataCandidateReviewAdmin(admin.ModelAdmin):
    """Admin interface for WikidataCandidateReview with custom adjudication UI."""

    list_display = (
        "query_name",
        "person_link",
        "review_type",
        "candidate_count",
        "status",
        "linked_qid",
        "reviewed_by",
        "created_at",
    )
    list_display_links = ("query_name",)
    list_filter = ("status",)
    search_fields = ("person__name", "query_name", "linked_qid")
    readonly_fields = (
        "id",
        "person",
        "query_name",
        "candidates",
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    change_form_template = "admin/persons/wikidatacandidatereview/change_form.html"

    def get_queryset(self, request):  # noqa: ANN001
        """Default to showing only actionable (pending + auto_linked) reviews."""
        qs = super().get_queryset(request).select_related("person", "reviewed_by")
        # Django's ChoicesFieldListFilter generates ?status__exact=<val>; a
        # manually typed URL may use ?status=<val>.  Either signals explicit intent.
        if request.GET.get("status__exact") or request.GET.get("status"):
            return qs
        return qs.filter(status__in=["pending", "auto_linked"])

    def candidate_count(self, obj):  # noqa: ANN001
        """Return the number of candidates in this review."""
        return len(obj.candidates or [])

    candidate_count.short_description = "Candidates"

    def review_type(self, obj):  # noqa: ANN001
        """Display a human-readable type badge based on status."""
        _LABELS = {
            "auto_linked": '<span style="color:#1d76db">&#9679; Auto-linked</span>',
            "pending": '<span style="color:#e67e22">&#9679; Ambiguous</span>',
            "accepted": '<span style="color:#28a745">&#9679; Accepted</span>',
            "confirmed": '<span style="color:#17a2b8">&#9679; Confirmed</span>',
            "rejected": '<span style="color:#dc3545">&#9679; Rejected</span>',
            "skipped": '<span style="color:#6c757d">&#9679; Skipped</span>',
        }
        html = _LABELS.get(obj.status, obj.get_status_display())
        return mark_safe(html)  # noqa: S308

    review_type.short_description = "Type"

    def person_link(self, obj):  # noqa: ANN001
        """Render the person as a link to their admin change page."""
        url = reverse("admin:persons_person_change", args=[obj.person_id])
        return format_html('<a href="{}">{}</a>', url, obj.person)

    person_link.short_description = "Person"

    # ------------------------------------------------------------------
    # Change view — inject confidence constants into template context
    # ------------------------------------------------------------------

    def change_view(self, request, object_id, form_url="", extra_context=None):  # noqa: ANN001
        """Inject WikidataProvider confidence constants; short-circuit custom action POSTs.

        Django's standard change_view runs ModelForm validation before calling
        response_change.  Our adjudication form does not submit model fields, so
        validation always fails and response_change is never reached.  We detect
        the custom ``_action`` POST parameter here and route directly to
        response_change, bypassing the ModelForm pipeline entirely.
        """
        extra_context = extra_context or {}
        extra_context["auto_link_confidence"] = WikidataProvider.AUTO_LINK_CONFIDENCE
        extra_context["confirmed_confidence"] = WikidataProvider.CONFIRMED_CONFIDENCE

        if request.method == "POST" and request.POST.get("_action"):
            obj = self.get_object(request, object_id)
            if obj is None:
                return self._get_obj_does_not_exist_redirect(request, self.model._meta, object_id)
            response = self.response_change(request, obj)
            # response_change has already mutated obj; log after so the message
            # reflects the new state.  This preserves the admin history tab.
            self.log_change(request, obj, f"Adjudication action: {request.POST['_action']}")
            return response

        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    # ------------------------------------------------------------------
    # Form action dispatch
    # ------------------------------------------------------------------

    def response_change(self, request, obj):  # noqa: ANN001
        """Handle adjudication form actions: accept, reject, skip, confirm."""
        action = request.POST.get("_action")
        if not action:
            return super().response_change(request, obj)

        # Guard against double-submit on already-resolved reviews.
        if obj.status in _RESOLVED_STATUSES:
            self.message_user(request, "This review has already been resolved.", level="warning")
            return HttpResponseRedirect(request.path)

        if action == "accept":
            return self._handle_accept(request, obj)
        if action == "confirm":
            return self._handle_confirm(request, obj)
        if action == "reject":
            return self._handle_reject(request, obj)
        if action == "skip":
            return self._handle_skip(request, obj)

        # Unknown action — fall back to default Django behaviour.
        return super().response_change(request, obj)

    @staticmethod
    def _changelist_url():
        """Return the changelist URL (default actionable filter)."""
        return reverse("admin:persons_wikidatacandidatereview_changelist")

    @staticmethod
    def _person_url(person_id):
        """Return the admin change URL for a person."""
        return reverse("admin:persons_person_change", args=[person_id])

    def _handle_accept(self, request, obj):  # noqa: ANN001
        """Accept a pending review: validate the QID, set status, trigger enrichment."""
        qid = request.POST.get("linked_qid", "").strip()
        valid_qids = {c["qid"] for c in (obj.candidates or [])}

        if not qid or qid not in valid_qids:
            self.message_user(
                request,
                "Please select a candidate before accepting.",
                level="error",
            )
            return HttpResponseRedirect(request.path)

        obj.status = "accepted"
        obj.linked_qid = qid
        obj.reviewed_by = request.user
        obj.reviewed_at = timezone.now()
        obj.save()

        self.message_user(request, f"Review accepted with QID {qid}.")
        return HttpResponseRedirect(self._changelist_url())

    def _handle_confirm(self, request, obj):  # noqa: ANN001
        """Confirm an auto_linked review: set status to confirmed, bump confidence."""
        obj.status = "confirmed"
        obj.reviewed_by = request.user
        obj.reviewed_at = timezone.now()
        obj.save()

        self.message_user(
            request,
            f"Review confirmed. Confidence bumped to "
            f"{WikidataProvider.CONFIRMED_CONFIDENCE} for {obj.linked_qid}.",
        )
        return HttpResponseRedirect(self._changelist_url())

    def _handle_reject(self, request, obj):  # noqa: ANN001
        """Reject a review.  For auto_linked reviews, rolls back attributes first.

        The rollback is attempted *before* saving the review so that a rollback
        failure leaves the review in its prior state — the operator can retry.
        """
        was_auto_linked = obj.status == "auto_linked"
        person_id = str(obj.person_id)

        if was_auto_linked:
            try:
                rollback_wikidata_autolink(person_id=person_id)
            except Exception:
                logger.exception(
                    "rollback_wikidata_autolink failed — review not changed",
                    extra={"review_id": str(obj.pk), "person_id": person_id},
                )
                self.message_user(
                    request,
                    "Rollback failed. Review not changed. Check logs.",
                    level="error",
                )
                return HttpResponseRedirect(request.path)

        obj.status = "rejected"
        obj.reviewed_by = request.user
        obj.reviewed_at = timezone.now()
        obj.save()

        if was_auto_linked:
            self.message_user(
                request,
                "Auto-link rejected and rolled back. Person re-queued for manual review.",
            )
            return HttpResponseRedirect(self._person_url(person_id))

        self.message_user(request, "Review rejected.")
        return HttpResponseRedirect(self._changelist_url())

    def _handle_skip(self, request, obj):  # noqa: ANN001
        """Skip a review: defer it for later."""
        obj.status = "skipped"
        obj.reviewed_by = request.user
        obj.reviewed_at = timezone.now()
        obj.save()

        self.message_user(request, "Review skipped.")
        return HttpResponseRedirect(self._changelist_url())


@admin.register(ExternalIdentifierProperty)
class ExternalIdentifierPropertyAdmin(admin.ModelAdmin):
    """Admin interface for ExternalIdentifierProperty with inline is_enabled toggle."""

    list_display = (
        "wikidata_property_id",
        "display",
        "is_enabled",
        "platform",
        "formatter_url",
        "last_synced_at",
    )
    list_filter = ("is_enabled",)
    search_fields = ("wikidata_property_id", "slug", "display", "description")
    list_editable = ("is_enabled",)
    readonly_fields = ("wikidata_property_id", "slug", "last_synced_at")
    raw_id_fields = ("platform",)
