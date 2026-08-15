/** @odoo-module */
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PbxSipConfigTable extends Component {
    static template = "pbx_base.PbxSipConfigTable";
    static props = { ...standardFieldProps };

    setup() {
        this.notification = this.env.services.notification;
        this.state = useState({ revealed: {} });
    }

    get rows() {
        const cfg = this.props.record.data[this.props.name] || {};
        return Object.entries(cfg).map(([key, spec]) => ({
            key,
            label: spec.label || key,
            value: spec.value !== undefined && spec.value !== null ? String(spec.value) : "",
            help: spec.help || "",
            secret: /password|secret/i.test(key),
        }));
    }

    isRevealed(rowKey) {
        return Boolean(this.state.revealed[rowKey]);
    }

    toggleReveal(rowKey) {
        this.state.revealed[rowKey] = !this.state.revealed[rowKey];
    }

    async onCopy(value) {
        if (!value) {
            return;
        }
        try {
            await navigator.clipboard.writeText(value);
            this.notification.add("Kopierat", { type: "success" });
        } catch {
            // clipboard not available - ignore silently
        }
    }
}

registry.category("fields").add("pbx_sip_config_table", {
    component: PbxSipConfigTable,
    supportedTypes: ["json"],
});
