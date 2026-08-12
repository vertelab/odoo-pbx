# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pbx_extension_id = fields.Many2one(
        "pbx.extension",
        string="PBX-anknytning",
        help="Samma anknytning som personen har i PBX/res.users. "
             "Auto-fylls från länkad användare eller fördelas (nästa lediga).",
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        """Fyll anknytningen från användarens extension vid användarbyte —
        men respektera en manuell override (fältet redan satt)."""
        if self.user_id and self.user_id.pbx_extension_id:
            if not self.pbx_extension_id:
                self.pbx_extension_id = self.user_id.pbx_extension_id
        elif self.user_id:
            # Användare bytt till en utan anknytning — rensa bara om värdet
            # härstammade från en tidigare användare (enkel: rensa ej manuell).
            pass

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            if not rec.pbx_extension_id:
                rec._assign_from_user_or_next_free()
        return recs

    def _assign_from_user_or_next_free(self):
        """1) Användarens extension om en finns; 2) annars nästa lediga."""
        self.ensure_one()
        user = self.user_id
        if user and user.pbx_extension_id:
            self.pbx_extension_id = user.pbx_extension_id
            return
        self._assign_next_free()

    def _assign_next_free(self):
        """Fördela nästa lediga anknytning (pbx-numbering)."""
        self.ensure_one()
        company = self.company_id
        if not company:
            return
        numbering = self.env["pbx.numbering"]
        existing, number = numbering._next_free_extension_number(company)
        if existing:
            if not existing.user_id and self.user_id:
                existing.user_id = self.user_id.id
            self.pbx_extension_id = existing
            return
        if not number:
            raise ValidationError(
                _("Ingen ledig anknytning i företaget %s — omnumrera "
                  "organisationen eller utöka nummerplanen.") % company.name
            )
        ext = self.env["pbx.extension"].create(
            {
                "company_id": company.id,
                "public_number": number,
                "user_id": self.user_id.id if self.user_id else False,
                "callerid_name": self.name,
            }
        )
        self.pbx_extension_id = ext

    def action_assign_extension(self):
        """Knapp 'Fördela anknytning' — nästa lediga."""
        for rec in self:
            rec._assign_next_free()
        return True

    def action_sync_from_user(self):
        """Knapp 'Synka från användare' — hämta användarens anknytning."""
        for rec in self:
            user = rec.user_id
            if user and user.pbx_extension_id:
                rec.pbx_extension_id = user.pbx_extension_id
        return True

    # ------------------------------------------------------------------
    # Omnumrering (server action i kugghjulet)
    # ------------------------------------------------------------------

    def action_renumber_organization(self):
        """Server action 'Numrera om organisation'.

        För varje företag i markeringen: numrera alla aktiva anställda
        hierarkiskt (VD=01, BFS nedåt) med bredd efter orgstorlek;
        inaktiva anställdas extensioner flyttas efter det aktiva intervallet.
        """
        companies = self.mapped("company_id")
        if not companies:
            return True
        for company in companies:
            self._renumber_company(company)
        return True

    def _hierarchical_order(self, company):
        """Aktiva anställda i BFS-ordning från organisationsroten.

        Rot = aktiv anställd utan chef (parent_id False), lägst id vid flera.
        Samma nivå sorteras på id. Anställda som inte nås (separata träd)
        läggs till sist i id-ordning.
        """
        employees = self.search(
            [("company_id", "=", company.id), ("active", "=", True)]
        )
        if not employees:
            return []
        roots = employees.filtered(lambda e: not e.parent_id).sorted("id")
        if not roots:
            roots = employees.sorted("id")[:1]
        children = {}
        for emp in employees:
            children.setdefault(emp.parent_id.id, []).append(emp)
        ordered = []
        visited = set()
        queue = [roots[0].id]
        while queue:
            emp_id = queue.pop(0)
            if emp_id in visited:
                continue
            visited.add(emp_id)
            emp = employees.browse(emp_id)
            ordered.append(emp)
            for child in sorted(children.get(emp_id, []), key=lambda c: c.id):
                queue.append(child.id)
        for emp in employees.sorted("id"):
            if emp.id not in visited:
                ordered.append(emp)
        return ordered

    def _renumber_company(self, company):
        numbering = self.env["pbx.numbering"]
        width = numbering._get_extension_width(company)
        ordered = self._hierarchical_order(company)
        ordered_rs = self.env["hr.employee"].concat(*ordered) if ordered else self.env["hr.employee"]
        inactive = self.search(
            [("company_id", "=", company.id), ("active", "=", False)],
            order="id",
        )
        all_emps = ordered_rs + inactive
        # 1) Säkerställ att alla anställda har en extension (annars skapa).
        for emp in all_emps:
            if not emp.pbx_extension_id:
                emp._assign_next_free()
        # 2) Beräkna mappning anställd → nummer.
        mapping = {}
        for idx, emp in enumerate(ordered, start=1):
            mapping[emp.id] = str(idx).zfill(width)
        for idx, emp in enumerate(inactive, start=1):
            mapping[emp.id] = str(len(ordered) + idx).zfill(width)
        # 3) Applicera i två faser (undvik transienta unik-kollisioner vid
        #    nummerbyten). OBS: Odoo slår ihop pending writes per fält —
        #    därför MÅSTE fas 1 flushen till DB innan fas 2 skrivs.
        all_exts = all_emps.mapped("pbx_extension_id")
        ctx = {"pbx_skip_number_check": True}
        for emp in all_emps:
            ext = emp.pbx_extension_id
            if ext and ext.public_number != mapping[emp.id]:
                ext.with_context(ctx).write(
                    {"public_number": "tmp-%s" % ext.id}
                )
        self.env.flush_all()
        for emp in all_emps:
            ext = emp.pbx_extension_id
            if ext and ext.public_number != mapping[emp.id]:
                ext.with_context(ctx).write(
                    {"public_number": mapping[emp.id]}
                )
        self.env.flush_all()
        # 4) Sanity: inga dubbletter kvar i företaget.
        numbers = all_exts.mapped("public_number")
        if len(numbers) != len(set(numbers)):
            raise ValidationError(
                _("Omnumreringen gav dubbletter i %s — återställ manuellt.") %
                company.name
            )
        # 5) Markera config-dirty (pbx.config.dirty.mixin på extension).
        all_exts._pbx_mark_dirty()
        return True


class HrEmployeePublic(models.Model):
    """SQL-view-modellen bakom org chart — måste deklareras explicit."""

    _inherit = "hr.employee.public"

    pbx_extension_id = fields.Many2one(
        "pbx.extension",
        related="employee_id.pbx_extension_id",
        readonly=True,
        string="PBX-anknytning",
    )
