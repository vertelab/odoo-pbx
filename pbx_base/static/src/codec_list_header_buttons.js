/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

/**
 * Header-knappar för pbx.codec-katalogen: "Sync" + "Deploy devices".
 *
 * Knapparna renderas via template-inherit av web.ListView i
 * codec_list_header_buttons.xml — i sloten control-panel-additional-actions,
 * dvs mellan kugghjulet och sökrutan (endast för pbx.codec via
 * props.resModel-check). Här ligger click-hantering + reload + toast.
 */
patch(ListController.prototype, {
    async onClickCodecSync() {
        const result = await this.model.orm.call("pbx.codec", "action_sync_codecs", []);
        await this.model.load();
        this.env.services.notification.add(
            result?.params?.message || "Codec-katalogen uppdaterad från pbx.codecs.available",
            { type: result?.params?.type || "success" }
        );
        return result;
    },

    async onClickCodecDeployDevices() {
        const result = await this.model.orm.call("pbx.codec", "action_deploy_devices", []);
        await this.model.load();
        this.env.services.notification.add(
            result?.params?.message || "Default-codecs applicerade på alla enheter",
            { type: result?.params?.type || "success" }
        );
        return result;
    },
});
