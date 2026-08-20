/** @odoo-module **/
/*
    Override av OCA voip_oca-softphonen: fånga rejection från SIP.js-anrop
    så inga ohanterade promises når Odoos formatTraceback (som kraschar på
    'Cannot read properties of undefined (reading split)').
*/
import {VoipOCASoftphone} from "@voip_oca/components/softphone/softphone.esm";
import {registry} from "@web/core/registry";

export class PbxSoftphone extends VoipOCASoftphone {
    onCall() {
        try {
            const p = super.onCall();
            if (p && typeof p.catch === "function") {
                p.catch((err) => {
                    console.error("[pbx] Softphone call failed:", err);
                });
            }
            return p;
        } catch (err) {
            console.error("[pbx] Softphone call threw:", err);
            return Promise.resolve();
        }
    }
}

PbxSoftphone.props = {};
PbxSoftphone.template = "voip_oca.VoipOCASoftphone";

registry.category("main_components").add("voip_oca.VoipOCASoftphone", {
    Component: PbxSoftphone,
});
