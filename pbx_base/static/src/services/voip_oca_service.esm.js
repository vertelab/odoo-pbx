/** @odoo-module **/
/*
    Override av OCA voip_oca-tjänsten: wrappa accept/reject-samtal med
    try/catch så RPC-fel aldrig blir ohanterade promise-rejections
    (Odoo 18 formatTraceback kraschar på malformed reasons).
*/
import {voipOCAService} from "@voip_oca/services/voip_oca_service.esm";
import {registry} from "@web/core/registry";

export const pbxVoipOCAService = {
    dependencies: voipOCAService.dependencies,
    async start(env, services) {
        const base = await voipOCAService.start(env, services);
        const origAccept = base.acceptCall.bind(base);
        const origReject = base.rejectCall.bind(base);

        base.acceptCall = async (...args) => {
            try {
                return await origAccept(...args);
            } catch (err) {
                console.error("[pbx] acceptCall failed:", err);
                return false;
            }
        };
        base.rejectCall = async (...args) => {
            try {
                return await origReject(...args);
            } catch (err) {
                console.error("[pbx] rejectCall failed:", err);
                return false;
            }
        };
        return base;
    },
};

registry.category("services").add("voip_oca", pbxVoipOCAService, {force: true});
