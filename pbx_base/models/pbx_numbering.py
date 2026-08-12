# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import ValidationError


class PbxNumbering(models.AbstractModel):
    """Nummerplan (pbx-numbering).

    Centrala hjälpmetoder för dial-namnrymden per företag:
      - extensionbredd efter organisationsstorlek (2/3/4 siffror)
      - tjänsteintervall (kö 4x, IVR 5x, konferens 6x — en siffra längre
        än extensionerna, med fasta ledande prefix)
      - unik dial-namnrymd per företag (validering över modellgränser)
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

    # Prefix per tjänst (första siffran i tjänsteintervallet).
    SERVICE_PREFIX = {
        "queue": 4,
        "ivr": 5,
        "conference": 6,
    }

    # Dialbara modeller: (modellnamn, fält med numret).
    DIALABLE_MODELS = [
        ("pbx.extension", "public_number"),
        ("pbx.queue", "extension"),
        ("pbx.ivr", "extension"),
        ("pbx.conference", "extension"),
    ]

    @api.model
    def _active_employee_count(self, company):
        """Antal aktiva anställda i företaget (för breddberäkning)."""
        if "hr.employee" not in self.env:
            return 0
        return self.env["hr.employee"].search_count(
            [("company_id", "=", company.id), ("active", "=", True)]
        )

    @api.model
    def _get_extension_width(self, company):
        """Extensionbredd efter organisationsstorlek: ≤70 → 2, 71–699 → 3,
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
        """(lo, hi) för en tjänstetyp: prefix*10^bredd … (prefix+1)*10^bredd-1."""
        prefix = self.SERVICE_PREFIX[service_type]
        w = self._get_extension_width(company)
        base = 10 ** w
        return prefix * base, (prefix + 1) * base - 1

    @api.model
    def _used_dialable_numbers(self, company):
        """Alla upptagna dialbara nummer i företaget (över modellgränser)."""
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
        """Lägsta lediga nummer i tjänstens intervall (eller False)."""
        lo, hi = self._service_range(company, service_type)
        used = self._used_dialable_numbers(company)
        for n in range(lo, hi + 1):
            s = str(n)
            if s not in used:
                return s
        return False

    @api.model
    def _next_free_extension_number(self, company):
        """Lägsta lediga extension-nummer i företagets schema.

        Används av pbx_hr (auto-tilldelning vid skapande + "Fördela
        anknytning"). Returnerar (existing_extension|False, number).
        """
        if "pbx.extension" not in self.env:
            return False, False
        w = self._get_extension_width(company)
        # 1) Befintlig fri extension (utan användare): lägsta numeriska nummer.
        free = self.env["pbx.extension"].search(
            [("company_id", "=", company.id), ("user_id", "=", False)],
            order="public_number asc",
        )
        # Exkludera extensioner som redan tilldelats en anställd via
        # hr.employee.pbx_extension_id (anställd utan inloggning har ingen
        # user_id på extensionen, men är ändå upptagen).
        if "hr.employee" in self.env and free:
            used_by_emp = self.env["hr.employee"].search(
                [("pbx_extension_id", "in", free.ids)]
            ).mapped("pbx_extension_id")
            free = free - used_by_emp
        for ext in free:
            num = str(ext.public_number or "")
            if num.isdigit():
                return ext, ext.public_number
        # 2) Ingen fri → nästa nummer som inte är upptaget av NÅGOT dialbart
        #    objekt (extension, kö, IVR, konferens) i företaget.
        used = self._used_dialable_numbers(company)
        for n in range(1, 10 ** w):
            s = str(n).zfill(w)
            if s not in used:
                return False, s
        return False, False

    @api.model
    def _check_dialable_number(self, company, number, exclude=None):
        """Validera att `number` inte krockar med något annat dialbart objekt
        i företaget. Höjer ValidationError vid kollision."""
        if not number:
            return
        number = str(number).strip()
        if not number:
            return
        if number.startswith("*"):
            raise ValidationError(
                _("Nummer får inte börja med '*' — prefixet är reserverat "
                  "för feature codes (*97/*98/*43/*82).")
            )
        if not number.isdigit():
            raise ValidationError(
                _("Dialbart nummer måste vara numeriskt: %s") % number
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
                    _("Numret %s är redan upptaget i detta företag "
                      "(%s)") % (number, model._description)
                )

    @api.model
    def _reception_route(self, domain, company):
        """Operator-0: route till manuell reception-kö om en finns.

        Returnerar en dialplan-rad för den interna kontexten (eller "").
        """
        if "pbx.queue" not in self.env:
            return ""
        queue = self.env["pbx.queue"].search(
            [("company_id", "=", company.id), ("is_manual", "=", True),
             ("active", "=", True)],
            limit=1,
        )
        if not queue:
            return ""
        slug = (queue.name or "").lower().replace(" ", "-")
        return "exten => 0,1,Goto(%s-queue-%s,s,1)" % (domain, slug)

    @api.model
    def _feature_code_entries(self, domain, company):
        """Dialplan-rader för feature codes i den interna kontexten."""
        lines = []
        for code, app in self.FEATURE_CODES.items():
            lines.append("exten => %s,1,%s" % (code, app))
            lines.append("same => n,Hangup()")
        operator = self._reception_route(domain, company)
        if operator:
            lines.append(operator)
            lines.append("same => n,Hangup()")
        return "\n".join(lines)
