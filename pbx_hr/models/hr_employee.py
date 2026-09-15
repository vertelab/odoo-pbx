# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pbx_extension_id = fields.Many2one(
        "pbx.extension",
        string="PBX Extension",
        help="Same extension the person has in the PBX/res.users. "
             "Auto-filled from the linked user or assigned (next available).",
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        """Fill the extension from the user's extension when the user changes —
        but respect a manual override (field already set)."""
        if self.user_id and self.user_id.pbx_extension_id:
            if not self.pbx_extension_id:
                self.pbx_extension_id = self.user_id.pbx_extension_id
        elif self.user_id:
            # User changed to one without an extension — only clear if the value
            # came from a previous user (simple: do not clear a manual value).
            pass

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            if not rec.pbx_extension_id:
                rec._assign_from_user_or_next_free()
        return recs

    def _assign_from_user_or_next_free(self):
        """1) The user's extension if one exists; 2) otherwise the next available."""
        self.ensure_one()
        user = self.user_id
        if user and user.pbx_extension_id:
            self.pbx_extension_id = user.pbx_extension_id
            return
        self._assign_next_free()

    def _assign_next_free(self):
        """Assign the next available extension (pbx-numbering)."""
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
                _("No available extension in company %s — renumber "
                  "the organization or extend the number plan.") % company.name
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
        """Button 'Assign Extension' — next available."""
        for rec in self:
            rec._assign_next_free()
        return True

    def action_sync_from_user(self):
        """Button 'Sync from User' — fetch the user's extension."""
        for rec in self:
            user = rec.user_id
            if user and user.pbx_extension_id:
                rec.pbx_extension_id = user.pbx_extension_id
        return True

    # ------------------------------------------------------------------
    # Renumbering (server action from the cogwheel)
    # ------------------------------------------------------------------

    def action_renumber_organization(self):
        """Server action 'Renumber Organization'.

        For each company in the selection: number all active employees
        hierarchically (CEO=01, BFS downwards) with width based on org size;
        inactive employees' extensions are moved after the active range.
        """
        companies = self.mapped("company_id")
        if not companies:
            return True
        for company in companies:
            self._renumber_company(company)
        return True

    def _hierarchical_order(self, company):
        """Active employees in BFS order from the organization root.

        Root = active employee without a manager (parent_id False), lowest id
        when there are several. The same level is sorted by id. Employees that
        cannot be reached (separate trees) are added last in id order.
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
        # 1) Ensure every employee has an extension (create one otherwise).
        for emp in all_emps:
            if not emp.pbx_extension_id:
                emp._assign_next_free()
        # 2) Compute the employee -> number mapping.
        mapping = {}
        for idx, emp in enumerate(ordered, start=1):
            mapping[emp.id] = str(idx).zfill(width)
        for idx, emp in enumerate(inactive, start=1):
            mapping[emp.id] = str(len(ordered) + idx).zfill(width)
        # 3) Apply in two phases (avoid transient unique collisions when
        #    numbers are swapped). NOTE: Odoo merges pending writes per field —
        #    therefore phase 1 MUST flush to the DB before phase 2 is written.
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
        # 4) Sanity: no duplicates left in the company.
        numbers = all_exts.mapped("public_number")
        if len(numbers) != len(set(numbers)):
            raise ValidationError(
                _("The renumbering produced duplicates in %s — restore manually.") %
                company.name
            )
        # 5) Mark config-dirty (pbx.config.dirty.mixin on extension).
        all_exts._pbx_mark_dirty()
        return True


class HrEmployeePublic(models.Model):
    """The SQL view model behind the org chart — must be declared explicitly."""

    _inherit = "hr.employee.public"

    pbx_extension_id = fields.Many2one(
        "pbx.extension",
        related="employee_id.pbx_extension_id",
        readonly=True,
        string="PBX Extension",
    )
