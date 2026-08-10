/*
    Copyright 2026 Vertel AB
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/

import {Component, useState, onMounted, onWillUnmount} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {registry} from "@web/core/registry";

/** Map Asterisk device states to FOP2 colors. */
function stateColor(state) {
    switch (state) {
        case "NOT_INUSE":
        case "UNAVAILABLE":
            return "green";
        case "INUSE":
        case "BUSY":
        case "ONHOLD":
            return "red";
        case "RINGING":
        case "RINGINUSE":
            return "yellow";
        default:
            return "gray";
    }
}

function extFromDevice(device, domain) {
    if (!device) {
        return null;
    }
    const m = device.match(new RegExp(`${domain}-(\\d+)`));
    return m ? m[1] : null;
}

export class Fop2Panel extends Component {
    static template = "pbx_tenant.Fop2Panel";

    setup() {
        this.rpc = useService("rpc");
        this.bus = useService("bus_service");
        this.state = useState({
            loading: true,
            domain: "",
            isReceptionist: false,
            extensions: [],
            queues: [],
            ivrs: [],
            widgets: [],
            incoming: [],
            manual: [],
            states: {},
            waiting: {},
            activeCalls: {},
        });
        onMounted(() => this.init());
        onWillUnmount(() => this.cleanup());
    }

    async init() {
        const [grid, widgets] = await Promise.all([
            this.rpc("/pbx/fop2/grid"),
            this.rpc("/pbx/fop2/widgets"),
        ]);
        this.state.domain = grid.domain || "";
        this.state.isReceptionist = grid.is_receptionist || false;
        this.state.extensions = grid.extensions || [];
        this.state.queues = grid.queues || [];
        this.state.ivrs = grid.ivrs || [];
        this.state.widgets = widgets.widgets || [];
        this.state.loading = false;
        this.subscribe();
    }

    subscribe() {
        if (!this.state.domain) {
            return;
        }
        const channel = `pbx.${this.state.domain}`;
        this.bus.addChannel(channel);
        // Odoo 18 bus: subscribe on notification_type, receive payload
        this._sub = this.bus.subscribe("pbx_event", (payload) =>
            this.onEvent(payload)
        );
    }

    cleanup() {
        if (this._sub) {
            this._sub.unsubscribe();
        }
        if (this.state.domain) {
            this.bus.deleteChannel(`pbx.${this.state.domain}`);
        }
    }

    // ── events ──────────────────────────────────────────────────

    onEvent(payload) {
        const event = payload.event || {};
        const eventName = event.Event;
        switch (eventName) {
            case "DeviceStateChange": {
                const ext = extFromDevice(event.Device, this.state.domain);
                if (ext) {
                    this.state.states[ext] = stateColor(event.State || "UNKNOWN");
                }
                break;
            }
            case "Newchannel": {
                const ext = extFromDevice(event.Channel, this.state.domain);
                if (ext && this.state.states[ext] === undefined) {
                    this.state.states[ext] = "yellow";
                }
                if (!event.CallerIDNum && !event.ConnectedLineNum) {
                    break;
                }
                const caller = event.CallerIDNum || event.ConnectedLineNum || "";
                const name = event.CallerIDName || "";
                const call = {
                    channel: event.Channel,
                    uniqueid: event.Uniqueid,
                    number: caller,
                    name: name,
                    direction: "incoming",
                    started: Date.now(),
                };
                this.state.incoming = this.state.incoming.filter(
                    (c) => c.channel !== call.channel
                );
                this.state.incoming.push(call);
                this.state.activeCalls[call.uniqueid || call.channel] = call;
                break;
            }
            case "Newstate": {
                const ext = extFromDevice(event.Channel, this.state.domain);
                if (ext) {
                    this.state.states[ext] = stateColor(event.ChannelStateDesc || "");
                }
                break;
            }
            case "Hangup": {
                const uniqueid = event.Uniqueid;
                const channel = event.Channel;
                const callKey = uniqueid || channel;
                if (this.state.activeCalls[callKey]) {
                    this.state.incoming = this.state.incoming.filter(
                        (c) => c.uniqueid !== uniqueid && c.channel !== channel
                    );
                    delete this.state.activeCalls[callKey];
                }
                const ext = extFromDevice(channel, this.state.domain);
                if (ext && this.state.states[ext] === "red") {
                    this.state.states[ext] = "green";
                }
                break;
            }
            case "QueueEntry": {
                const q = this._queueNameFromEvent(event);
                if (q) {
                    this.state.waiting[q] = parseInt(event.Count || "0", 10);
                }
                break;
            }
            case "QueueCallerLeave": {
                const q = this._queueNameFromEvent(event);
                if (q) {
                    this.state.waiting[q] = Math.max(
                        0,
                        (this.state.waiting[q] || 1) - 1
                    );
                }
                break;
            }
            case "QueueMemberStatus": {
                const ext = extFromDevice(event.Interface, this.state.domain);
                const st = event.State;
                if (ext) {
                    this.state.states[ext] =
                        st === "0" || st === "5" || st === "6"
                            ? "green"
                            : "red";
                }
                break;
            }
            case "UserEvent": {
                if (event.UserEvent === "ManualRequired") {
                    const caller = event.CallerIDNum || "";
                    const queue = event.Queue || "";
                    const entry = {
                        id: `${Date.now()}-${caller}-${queue}`,
                        number: caller,
                        name: event.CallerIDName || "",
                        source: event.Source || "",
                        queue: queue,
                        target: event.Target || "",
                        channel: event.Channel || "",
                    };
                    this.state.manual = this.state.manual.filter(
                        (m) => !(m.number === entry.number && m.queue === entry.queue)
                    );
                    this.state.manual.push(entry);
                }
                break;
            }
        }
    }

    _queueNameFromEvent(event) {
        const q = event.Queue || "";
        // Queue field is like "vertel-support" → strip domain prefix
        if (this.state.domain && q.startsWith(`${this.state.domain}-`)) {
            return q.slice(this.state.domain.length + 1);
        }
        return q;
    }

    // ── widget registry ─────────────────────────────────────────

    tileComponent(name) {
        return registry.category("fop2.tiles").get(name, {component: null}).component;
    }

    tileProps(props) {
        return Object.assign(
            {
                domain: this.state.domain,
                states: this.state.states,
                waiting: this.state.waiting,
                incoming: this.state.incoming,
                onAction: (route, params) => this.callAction(route, params),
            },
            props || {}
        );
    }

    // ── drag & drop transfer ───────────────────────────────────

    onDragStart(ev, call) {
        ev.dataTransfer.setData("text/pbx-channel", call.channel);
    }

    onDragOver(ev) {
        ev.preventDefault();
    }

    onDropToQueue(ev, queue) {
        ev.preventDefault();
        const channel = ev.dataTransfer.getData("text/pbx-channel");
        if (channel) {
            this.redirectToQueue(channel, queue);
        }
    }

    onDropToAgent(ev, ext) {
        ev.preventDefault();
        const channel = ev.dataTransfer.getData("text/pbx-channel");
        if (channel) {
            this.redirectToAgent(channel, ext.key);
        }
    }

    // ── actions ──────────────────────────────────────────────────

    async callAction(route, params) {
        return this.rpc(route, params || {});
    }

    hangup(channel) {
        this.callAction("/pbx/fop2/hangup", {channel});
    }

    chanspy(extension, mode) {
        this.callAction("/pbx/fop2/chanspy", {extension, mode});
    }

    originate(target) {
        this.callAction("/pbx/fop2/originate", {target});
    }

    queuePause(queue, paused) {
        this.callAction("/pbx/fop2/queue_pause", {queue, paused});
    }

    redirectToQueue(channel, queue) {
        if (!queue) {
            return;
        }
        const qname = queue.description.toLowerCase().replace(/\s+/g, "-");
        this.callAction("/pbx/fop2/redirect", {
            channel,
            context: `${this.state.domain}-queue-${qname}`,
            exten: "s",
        });
        this.state.manual = this.state.manual.filter(
            (m) => m.channel !== channel
        );
        this.state.incoming = this.state.incoming.filter(
            (c) => c.channel !== channel
        );
    }

    redirectToAgent(channel, agentNumber) {
        this.callAction("/pbx/fop2/redirect", {
            channel,
            context: `${this.state.domain}-internal`,
            exten: agentNumber,
        });
        this.state.manual = this.state.manual.filter(
            (m) => m.channel !== channel
        );
        this.state.incoming = this.state.incoming.filter(
            (c) => c.channel !== channel
        );
    }

    handleManual(entry) {
        const context = entry.target || `${this.state.domain}-reception`;
        this.callAction("/pbx/fop2/redirect", {
            channel: entry.channel,
            context,
            exten: "s",
        });
        this.state.manual = this.state.manual.filter(
            (m) => m.channel !== entry.channel
        );
        this.state.incoming = this.state.incoming.filter(
            (c) => c.channel !== entry.channel
        );
    }

    fmtDuration(started) {
        const s = Math.floor((Date.now() - started) / 1000);
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    }
}

registry.category("actions").add("pbx_tenant.fop2_panel", Fop2Panel);
