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
    }

    /** One row per resolved parameter: {key, label, value, help, secret}. */
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
                secret: /password|secret/i.test(key),
            };
        });
    }

    /** The readable one-liner, used when there is no structured config. */
    get fallback() {
        const display = this.props.record.data.config_display;
        return display ? String(display) : "";
    }

    openDialog() {
        this.dialogService.add(PbxSipConfigDialog, {
            title: _t("SIP configuration"),
            rows: this.rows,
            fallback: this.fallback,
        });
    }
}

registry.category("fields").add("pbx_sip_config_button", {
    component: PbxSipConfigButton,
    supportedTypes: ["char"],
    // `config` is not the field this widget renders — it is the structured
    // source the dialog reads. Declaring it here makes the web client load it
    // with the record instead of leaving it undefined.
    relatedFields: [{ name: "config", type: "json" }],
});
