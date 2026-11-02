/** @odoo-module **/
/*
    Copyright 2026 Vertel Sverige AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

    Gear button + dialog for a device's resolved SIP configuration.

    Used on the Devices list on My Profile (res.users.pbx_sub_extension_ids).
    The button sits next to `config_display` and opens a dialog that shows one
    row per parameter: label, value and help text.

    `config_display` is a Char (the readable one-line fallback). The structured
    per-parameter data lives in `config` (fields.Json). The dialog therefore
    reads `config` from the record and falls back to `config_display` when the
    device has no template — so a device without a template still shows
    something instead of an empty dialog.
*/

import { Component, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class PbxSipConfigDialog extends Component {
    static template = "pbx_tenant.PbxSipConfigDialog";
    static props = {
        title: { type: String, optional: true },
        rows: { type: Array, optional: true },
        fallback: { type: String, optional: true },
        extensionId: { type: Number, optional: true },
        onRotate: { type: Function, optional: true },
        sections: { type: Array, optional: true },
        templates: { type: Array, optional: true },
        selectedTemplateId: { type: [Number, Boolean], optional: true },
        onSelectTemplate: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.state = useState({ revealed: {} });
    }

    isRevealed(key) {
        return Boolean(this.state.revealed[key]);
    }

    toggleReveal(key) {
        this.state.revealed[key] = !this.state.revealed[key];
    }

    /** Switch template: the button re-resolves config and reopens the dialog. */
    onTemplateChange(ev) {
        const value = ev.target.value;
        if (this.props.onSelectTemplate) {
            this.props.onSelectTemplate(value ? Number(value) : false);
        }
    }

    /** Delegate to the button, which owns the confirmation dialog. */
    onRotatePassword(extensionId) {
        if (this.props.onRotate) {
            this.props.onRotate(extensionId);
        }
    }

    async onCopy(value) {
        if (!value) {
            return;
        }
        try {
            await navigator.clipboard.writeText(value);
            this.env.services.notification.add(_t("Copied"), { type: "success" });
        } catch {
            // Clipboard unavailable (non-secure context) — nothing to do.
        }
    }
}

export class PbxSipConfigButton extends Component {
    static template = "pbx_tenant.PbxSipConfigButton";
    static props = { ...standardFieldProps };

    setup() {
        this.dialogService = useService("dialog");
        this.orm = useService("orm");
    }

    /**
     * Rows grouped by the template's `section`, so the dialog reads as
     * Account / Network / Guide instead of one flat list. Parameters without
     * a section land under "Configuration".
     */
    get sections() {
        const groups = new Map();
        for (const row of this.rows) {
            const name = row.section || _t("Configuration");
            if (!groups.has(name)) {
                groups.set(name, []);
            }
            groups.get(name).push(row);
        }
        return Array.from(groups, ([name, rows]) => ({ name, rows }));
    }

    /** One row per resolved parameter: {key, label, value, help, secret, section}. */
    get rows() {
        const data = this.props.record.data || {};
        const config = data.config;
        if (!config || typeof config !== "object" || Array.isArray(config)) {
            return [];
        }
        return Object.entries(config).map(([key, spec]) => {
            const param = spec && typeof spec === "object" ? spec : {};
            const value =
                param.value !== undefined && param.value !== null
                    ? String(param.value)
                    : "";
            return {
                key,
                label: param.label || key,
                value,
                help: param.help || "",
                section: param.section || "",
                render: param.render || "",
                secret: /password|secret/i.test(key),
            };
        });
    }

    /** The readable one-liner, used when there is no structured config. */
    get fallback() {
        const display = this.props.record.data.config_display;
        return display ? String(display) : "";
    }

    /** The extension whose password the dialog can rotate. */
    get extensionId() {
        const ext = this.props.record.data.extension_id;
        return Array.isArray(ext) ? ext[0] : ext;
    }

    /** The user-selectable templates for this device's type. */
    async loadTemplates() {
        const type = this.props.record.data.type;
        if (!type) {
            return [];
        }
        return this.orm.searchRead(
            "pbx.device.template",
            [
                ["device_type", "=", type],
                ["user_selectable", "=", true],
                ["active", "=", true],
            ],
            ["id", "name", "vendor"],
            { order: "sequence, name" }
        );
    }

    async openDialog() {
        const templates = await this.loadTemplates();
        this.dialogService.add(PbxSipConfigDialog, {
            title: _t("SIP configuration"),
            rows: this.rows,
            sections: this.sections,
            fallback: this.fallback,
            extensionId: this.extensionId,
            templates,
            selectedTemplateId: this.props.record.data.template_id || false,
            onRotate: () => this.onRotatePassword(),
            onSelectTemplate: (id) => this.onSelectTemplate(id),
        });
    }

    /**
     * Store the chosen template on the device and reopen the dialog with the
     * freshly resolved configuration — no page reload needed.
     */
    async onSelectTemplate(templateId) {
        await this.orm.write("pbx.sub_extension", [this.props.record.resId], {
            template_id: templateId || false,
        });
        await this.props.record.model.load();
        this.openDialog();
    }

    /**
     * Rotate the shared SIP password. Guarded by a confirmation dialog —
     * every device on the extension loses its registration.
     */
    onRotatePassword() {
        const extensionId = this.extensionId;
        if (!extensionId) {
            return;
        }
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Generate a new SIP password?"),
            body: _t(
                "Every device on this extension loses its registration and " +
                    "must be reconfigured with the new password. Continue?"
            ),
            confirmLabel: _t("Generate"),
            cancelLabel: _t("Cancel"),
            confirm: async () => {
                try {
                    await this.orm.call("pbx.extension", "action_generate_new_password", [
                        [extensionId],
                    ]);
                    await this.props.record.model.load();
                    this.env.services.notification.add(_t("SIP password rotated"), {
                        type: "success",
                    });
                } catch (error) {
                    this.env.services.notification.add(
                        error?.data?.message || error?.message ||
                            _t("Could not rotate the password"),
                        { type: "danger" }
                    );
                }
            },
        });
    }
}

registry.category("fields").add("pbx_sip_config_button", {
    component: PbxSipConfigButton,
    supportedTypes: ["char"],
    // `config` is not the field this widget renders — it is the structured
    // source the dialog reads. Declaring it here makes the web client load it
    // with the record instead of leaving it undefined.
    relatedFields: [
        { name: "config", type: "json" },
        { name: "extension_id", type: "many2one" },
    ],
});
