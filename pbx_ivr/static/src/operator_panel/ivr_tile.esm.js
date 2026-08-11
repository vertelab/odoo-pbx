/*
    Copyright 2026 Vertel AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component} from "@odoo/owl";
import {registry} from "@web/core/registry";

export class PbxIvrPanel extends Component {
    static template = "pbx_ivr.PbxIvrPanel";
}

PbxIvrPanel.props = {
    ivr: {type: Object, optional: true},
};

registry.category("operator_panel.tiles").add("PbxIvrPanel", PbxIvrPanel);
