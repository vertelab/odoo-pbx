/** @odoo-module **/
/*
    Override of the OCA voip_oca softphone: catch rejections from SIP.js calls
    so no unhandled promises reach Odoo's formatTraceback (which crashes on
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

registry.category("main_components").add(
    "voip_oca.VoipOCASoftphone",
    {Component: PbxSoftphone},
    {force: true},  // Odoo 18: overriding an existing key requires force
);
