/** @odoo-module */
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class PbxCallButton extends Component {
    static template = "pbx_base.PbxCallButton";
    static props = { number: String };

    setup() {
        this.state = useState({ calling: false });
        this.notification = this.env.services.notification;
        this.orm = this.env.services.orm;
    }

    async onClickCall() {
        if (this.state.calling || !this.props.number) {
            return;
        }
        this.state.calling = true;
        try {
            await this.orm.call(
                "pbx.extension",
                "action_click_to_call_current_user",
                [this.props.number]
            );
            this.notification.add(`Ringer ${this.props.number}`, { type: "success" });
        } catch (e) {
            this.notification.add(e.message || "Kunde inte ringa", { type: "danger" });
        } finally {
            this.state.calling = false;
        }
    }
}

registry.category("components").add("pbxCallButton", PbxCallButton);

import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PbxCallField extends Component {
    static template = "pbx_base.PbxCallField";
    static props = { ...standardFieldProps };
    get value() {
        return this.props.record.data[this.props.name] || "";
    }
    onInput(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }
}

registry.category("fields").add("pbx_call", {
    component: PbxCallField,
    supportedTypes: ["char"],
});
