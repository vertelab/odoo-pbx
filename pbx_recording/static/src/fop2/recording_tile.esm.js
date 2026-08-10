/*
    Copyright 2026 Vertel AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component, useState} from "@odoo/owl";
import {registry} from "@web/core/registry";

export class PbxRecordingControl extends Component {
    static template = "pbx_recording.PbxRecordingControl";

    setup() {
        this.state = useState({recording: false});
    }

    toggle() {
        const call = (this.props.incoming || [])[0];
        if (!call) {
            return;
        }
        this.state.recording = !this.state.recording;
        this.props.onAction("/pbx/fop2/mixmonitor", {
            channel: call.channel,
            file: `recording-${call.uniqueid || Date.now()}`,
            stop: this.state.recording ? false : true,
        });
    }
}

PbxRecordingControl.props = {
    incoming: {type: Array, optional: true},
    onAction: {type: Function, optional: true},
};

registry.category("fop2.tiles").add("PbxRecordingControl", PbxRecordingControl);
