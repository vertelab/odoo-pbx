/** @odoo-module **/
/*
    Copyright 2026 Vertel Sverige AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

    "Generate new password" button for a shared SIP password.

    Rotating the password drops the registration on every device that uses it,
    so the click is guarded by a confirmation dialog. The button is used in two
    places (pbx-device-templates 7.2/7.3/7.4):

      * the admin extension form  -> resModel "pbx.extension"
      * the gear dialog on My Profile -> resModel "pbx.sub_extension"
        (rotates the password of the device's extension)

    Both call `pbx.extension.action_generate_new_password`, which enforces the
    ownership check server side — the dialog is a courtesy, not the guard.
*/

import { Component } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { useService } from "@web/core/utils/hooks";

export class PbxRotatePassword extends Component {
    static template = "pbx_base.PbxRotatePassword";
    static props = { ...standardWidgetProps };

    setup() {
        this.dialogService = useService("dialog");
        this.notificationService = useService("notification");
        this.orm = useService("orm");
    }

    /** The extension record whose password is rotated. */
    get extensionId() {
        const record = this.props.record;
        if (record.resModel === "pbx.extension") {
            return record.resId;
        }
        // pbx.sub_extension -> rotate the extension it belongs to.
        const ext = record.data.extension_id;
        return Array.isArray(ext) ? ext[0] : ext;
    }

    get canRotate() {
        return Boolean(this.extensionId);
    }

    onClick() {
        if (!this.canRotate) {
            return;
        }
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Generate a new SIP password?"),
            body: _t(
                "Every device on this extension loses its registration and " +
                    "must be reconfigured with the new password. Continue?"
            ),
            confirmLabel: _t("Generate"),
            cancelLabel: _t("Cancel"),
            confirm: () => this._rotate(),
        });
    }

    async _rotate() {
        try {
            await this.orm.call("pbx.extension", "action_generate_new_password", [
                [this.extensionId],
            ]);
            await this.props.record.model.load();
            this.notificationService.add(_t("SIP password rotated"), {
                type: "success",
            });
        } catch (error) {
            // AccessError from the ownership check, or a network/provider
            // failure — surface it instead of failing silently.
            this.notificationService.add(
                error?.data?.message || error?.message || _t("Could not rotate the password"),
                { type: "danger" }
            );
        }
    }
}

registry.category("view_widgets").add("pbx_rotate_password", {
    component: PbxRotatePassword,
});
