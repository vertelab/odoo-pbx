/** @odoo-module **/
/* PBX Sync systray — shows when configuration is waiting to be sent to
   Asterisk (res.company.config_dirty) and runs the sync on click. */

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
            syncState: "clean",
            version: 0,
            appliedVersion: 0,
            error: "",
            syncing: false,
        });
        this.canSync = false;
        this._pollTimer = null;
        onWillStart(async () => {
            await this._refresh();
        });
        onWillUnmount(() => {
            if (this._pollTimer) {
                clearTimeout(this._pollTimer);
            }
        });
        this._schedulePoll();
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
            this.state.syncState = state.state || "clean";
            this.state.version = state.version || 0;
            this.state.appliedVersion = state.applied_version || 0;
            this.state.error = state.error || "";
            this.canSync = Boolean(state.can_sync);
        } catch (err) {
            // silent — no PBX configuration yet
        }
    }

    pbxSyncClass() {
        if (this.state.syncState === "sent") {
            return "o_pbx_sync_sent";
        }
        if (this.state.syncState === "error") {
            return "o_pbx_sync_error";
        }
        if (this.state.dirty) {
            return "o_pbx_sync_dirty";
        }
        return "o_pbx_sync_ok";
    }

    pbxSyncIcon() {
        if (this.state.syncState === "error") {
            return "fa-exclamation-triangle";
        }
        if (this.state.syncState === "sent" || this.state.dirty) {
            return "fa-cloud-upload";
        }
        return "fa-cloud";
    }

    pbxSyncTitle() {
        const version =
            this.state.appliedVersion >= this.state.version
                ? this.state.version
                : this.state.version;
        if (this.state.syncState === "error") {
            return `PBX: error applying (v${this.state.version}) — ${this.state.error || "unknown error"}`;
        }
        if (this.state.syncState === "sent") {
            return `PBX: v${this.state.version} sent — waiting for confirmation`;
        }
        if (this.state.dirty) {
            return "PBX: changes waiting to be synced";
        }
        return `PBX: configuration applied (v${version})`;
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
        } catch (err) {
            // Never leave an unhandled rejection (masks real errors in
            // Odoo's formatTraceback)
            this.notification.add(
                err && err.message ? err.message : "PBX Sync failed",
                {
                    title: "PBX Sync",
                    type: "danger",
                    sticky: true,
                }
            );
        } finally {
            this.state.syncing = false;
        }
    }
}

export const pbxSyncSystrayItem = {
    Component: PbxSyncSystray,
};

registry.category("systray").add("pbx_tenant.PbxSyncSystray", pbxSyncSystrayItem);
