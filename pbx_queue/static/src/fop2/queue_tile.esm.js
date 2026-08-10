/*
    Copyright 2026 Vertel AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component} from "@odoo/owl";
import {registry} from "@web/core/registry";

export class PbxQueuePanel extends Component {
    static template = "pbx_queue.PbxQueuePanel";
}

PbxQueuePanel.props = {
    queue: {type: Object, optional: true},
    domain: {type: String, optional: true},
    states: {type: Object, optional: true},
    waiting: {type: Object, optional: true},
    onAction: {type: Function, optional: true},
};

registry.category("fop2.tiles").add("PbxQueuePanel", PbxQueuePanel);
