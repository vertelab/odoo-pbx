/** @odoo-module **/
/* PBX Sync systray — visar när konfiguration väntar på att skickas till
   Asterisk (res.company.config_dirty) och kör synken vid klick. */

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PbxSyncSystray extends Component {
    static template = "pbx_tenant.PbxSyncSystray";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            dirty: false,
            domain: "",
            syncing: false,
        });
        this.canSync = false;
        this._pollTimer = null;
        onWillStart(async () => {
            this.canSync = await this._canSync();
            await this._refresh();
        });
        onWillUnmount(() => {
            if (this._pollTimer) {
                clearTimeout(this._pollTimer);
            }
        });
        this._schedulePoll();
    }

    async _canSync() {
        // "user"-tjänsten är inte tillgänglig i systray-miljön → fråga via RPC.
        try {
            const hasOffice = await this.orm.call(
                "res.users",
                "has_group",
                ["pbx_base.group_pbx_office"]
            );
            const hasAdmin = await this.orm.call(
                "res.users",
                "has_group",
                ["pbx_base.group_pbx_admin"]
            );
            return hasOffice || hasAdmin;
        } catch (err) {
            return false;
        }
    }

    _schedulePoll() {
        if (this._pollTimer) {
            clearTimeout(this._pollTimer);
        }
        this._pollTimer = setTimeout(() => {
            this._refresh().finally(() => this._schedulePoll());
        }, 15000);
    }

    async _refresh() {
        try {
            const state = await this.orm.call(
                "pbx.config.generator",
                "get_sync_state",
                []
            );
            this.state.dirty = Boolean(state.dirty);
            this.state.domain = state.domain || "";
        } catch (err) {
            // tyst — ingen PBX-konfig än
        }
    }

    async _sync() {
        if (this.state.syncing) {
            return;
        }
        this.state.syncing = true;
        try {
            const result = await this.orm.call(
                "pbx.config.generator",
                "sync_current_company",
                []
            );
            this.notification.add(
                result.message,
                {
                    title: "PBX Sync",
                    type: result.ok ? "success" : "danger",
                    sticky: true,
                }
            );
            await this._refresh();
        } finally {
            this.state.syncing = false;
        }
    }
}

export const pbxSyncSystrayItem = {
    Component: PbxSyncSystray,
};

registry.category("systray").add("pbx_tenant.PbxSyncSystray", pbxSyncSystrayItem);
