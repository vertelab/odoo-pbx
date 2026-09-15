/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

/**
 * Header buttons for the pbx.codec catalogue: "Sync" + "Deploy devices".
 *
 * The buttons are rendered via template inherit of web.ListView in
 * codec_list_header_buttons.xml — in the control-panel-additional-actions slot,
 * i.e. between the cog wheel and the search box (only for pbx.codec via the
 * props.resModel check). Click handling + reload + toast live here.
 */
patch(ListController.prototype, {
    async onClickCodecSync() {
        const result = await this.model.orm.call("pbx.codec", "action_sync_codecs", []);
        await this.model.load();
        this.env.services.notification.add(
            result?.params?.message || "Codec catalogue updated from pbx.codecs.available",
            { type: result?.params?.type || "success" }
        );
        return result;
    },

    async onClickCodecDeployDevices() {
        const result = await this.model.orm.call("pbx.codec", "action_deploy_devices", []);
        await this.model.load();
        this.env.services.notification.add(
            result?.params?.message || "Default codecs applied to all devices",
            { type: result?.params?.type || "success" }
        );
        return result;
    },
});
