/*
    Copyright 2026 Vertel AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component} from "@odoo/owl";
import {registry} from "@web/core/registry";

export class PbxConferencePanel extends Component {
    static template = "pbx_conference.PbxConferencePanel";

    join() {
        this.props.onAction("/pbx/operator_panel/originate", {
            target: `conference:${this.props.conference.name}`,
        });
    }
}

PbxConferencePanel.props = {
    conference: {type: Object, optional: true},
    onAction: {type: Function, optional: true},
};

registry.category("operator_panel.tiles").add("PbxConferencePanel", PbxConferencePanel);
