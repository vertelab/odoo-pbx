# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PbxNumbering(models.AbstractModel):
    """Number plan (pbx-numbering).

    Central helper methods for the per-company dial namespace:
      - extension width based on organisation size (2/3/4 digits)
      - service ranges (queue 4x, IVR 5x, conference 6x — one digit longer
        than the extensions, with fixed leading prefixes)
      - unique dial namespace per company (validation across model borders)
      - feature codes + operator-0
    """

    _name = "pbx.numbering"
    _description = "PBX Number Plan (helpers)"

    # Feature codes — fasta i MVP (per-tenant-override framtida).
    FEATURE_CODES = {
        "*97": "VoiceMailMain(${CALLERID(num)})",
        "*98": "VoiceMailMain(${CALLERID(num)},default,s)",
        "*43": "QueueStatus()",
        "*82": "Pickup()",
    }

    # Prefix per service (first digit of the service range).
    SERVICE_PREFIX = {
        "queue": 4,
        "ivr": 5,
        "conference": 6,
        "time_condition": 7,
        "recording": 8,
    }

    # Dialable models: (model name, field holding the number).
    DIALABLE_MODELS = [
        ("pbx.extension", "public_number"),
        ("pbx.queue", "extension"),
        ("pbx.ivr", "extension"),
        ("pbx.conference", "extension"),
        ("pbx.time_condition", "extension"),
        ("pbx.recording.policy", "extension"),
    ]

    @api.model
    def _active_employee_count(self, company):
        """Number of active employees in the company (for width calculation)."""
        if "hr.employee" not in self.env:
            return 0
        return self.env["hr.employee"].search_count(
            [("company_id", "=", company.id), ("active", "=", True)]
        )

    @api.model
    def _get_extension_width(self, company):
        """Extension width by organisation size: ≤70 → 2, 71–699 → 3,
        ≥700 → 4 siffror."""
        n = self._active_employee_count(company)
        if n <= 70:
            return 2
        if n < 700:
            return 3
        return 4

    @api.model
    def _format_number(self, number, width):
        return str(number).zfill(width)

    @api.model
    def _service_range(self, company, service_type):
        """(lo, hi) for a service type: prefix*10^width … (prefix+1)*10^width-1."""
        prefix = self.SERVICE_PREFIX[service_type]
        w = self._get_extension_width(company)
        base = 10 ** w
        return prefix * base, (prefix + 1) * base - 1

    @api.model
    def _used_dialable_numbers(self, company):
        """All taken dialable numbers in the company (across model borders)."""
        used = set()
        for model_name, field in self.DIALABLE_MODELS:
            if model_name not in self.env:
                continue
            model = self.env[model_name]
            recs = model.search([("company_id", "=", company.id)])
            for rec in recs:
                val = rec[field]
                if val:
                    used.add(str(val))
        return used

    @api.model
    def _next_free_service_number(self, company, service_type):
        """Lowest free number in the service range (or False)."""
        lo, hi = self._service_range(company, service_type)
        used = self._used_dialable_numbers(company)
        for n in range(lo, hi + 1):
            s = str(n)
            if s not in used:
                return s
        return False

    @api.model
    def _next_free_extension_number(self, company, include_existing=True):
        """Lowest free extension number in the company's scheme.

        Used by pbx_hr (auto-assignment on create + "Assign
        extension"). Returns (existing_extension|False, number).

        include_existing=False → skip existing free extensions
        (for the "create new" default: only the next unused number).
        """
        if "pbx.extension" not in self.env:
            return False, False
        w = self._get_extension_width(company)
        if include_existing:
            # 1) Existing free extension (without user): lowest numeric number.
            free = self.env["pbx.extension"].search(
                [("company_id", "=", company.id), ("user_id", "=", False)],
                order="public_number asc",
            )
            # Exclude extensions already assigned to an employee via
            # hr.employee.pbx_extension_id (an employee without login has no
            # user_id on the extension, but is still taken).
            if "hr.employee" in self.env and free:
                used_by_emp = self.env["hr.employee"].search(
                    [("pbx_extension_id", "in", free.ids)]
                ).mapped("pbx_extension_id")
                free = free - used_by_emp
            for ext in free:
                num = str(ext.public_number or "")
                if num.isdigit():
                    return ext, ext.public_number
        # 2) None free → next number not taken by ANY dialable
        #    object (extension, queue, IVR, conference) in the company.
        used = self._used_dialable_numbers(company)
        for n in range(1, 10 ** w):
            s = str(n).zfill(w)
            if s not in used:
                return False, s
        return False, False

    @api.model
    def _check_dialable_number(self, company, number, exclude=None):
        """Validate that `number` does not collide with any other dialable
        object in the company. Raises ValidationError on collision."""
        if not number:
            return
        number = str(number).strip()
        if not number:
            return
        if number.startswith("*"):
            raise ValidationError(
                _("Number must not start with '*' — the prefix is reserved "
                  "for feature codes (*97/*98/*43/*82).")
            )
        if not number.isdigit():
            raise ValidationError(
                _("Dialable number must be numeric: %s") % number
            )
        exclude_id = exclude.id if exclude else False
        exclude_model = exclude._name if exclude else False
        for model_name, field in self.DIALABLE_MODELS:
            if model_name not in self.env:
                continue
            model = self.env[model_name]
            dom = [
                ("company_id", "=", company.id),
                (field, "=", number),
            ]
            if exclude_model == model_name:
                dom.append(("id", "!=", exclude_id))
            if model.search_count(dom):
                raise ValidationError(
                    _("Number %s is already taken in this company "
                      "(%s)") % (number, model._description)
                )

    @api.model
    def _reception_route(self, domain, company):
        """Operator-0: route to the manual reception queue if one exists.

        Returns a dialplan line for the internal context (or "").
        """
        if "pbx.queue" not in self.env:
            return ""
        company_id = company.id if isinstance(company, models.Model) else company
        queue = self.env["pbx.queue"].search(
            [("company_id", "=", company_id), ("is_manual", "=", True),
             ("active", "=", True)],
            limit=1,
        )
        if not queue:
            return ""
        slug = (queue.name or "").lower().replace(" ", "-")
        return "exten => 0,1,Goto(%s-queue-%s,s,1)" % (domain, slug)

    @api.model
    def _feature_code_entries(self, domain, company):
        """Dialplan lines for feature codes in the internal context."""
        lines = []
        for code, app in self.FEATURE_CODES.items():
            lines.append("exten => %s,1,%s" % (code, app))
            lines.append("same => n,Hangup()")
        operator = self._reception_route(domain, company)
        if operator:
            lines.append(operator)
            lines.append("same => n,Hangup()")
        return "\n".join(lines)
