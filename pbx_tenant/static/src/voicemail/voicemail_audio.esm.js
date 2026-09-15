/** @odoo-module **/
/*
    Widget: spelar upp voicemail-inspelningen inline (HTML5 <audio>).
    Used on pbx.voicemail.message.audio_attachment_id (many2one ir.attachment).
*/
import {Component} from "@odoo/owl";
import {registry} from "@web/core/registry";

export class VoicemailAudioPlayer extends Component {
    static template = "pbx_tenant.VoicemailAudioPlayer";

    get audioAttachmentId() {
        const value = this.props.record.data.audio_attachment_id;
        return Array.isArray(value) ? value[0] : false;
    }
    get isAudio() {
        // Only play when the file really is audio (mimetype audio/*)
        const mime = this.props.record.data.audio_mimetype || "";
        return String(mime).startsWith("audio/");
    }
    get audioSrc() {
        return this.audioAttachmentId
            ? `/web/content/${this.audioAttachmentId}?download=true`
            : "";
    }
}

registry.category("fields").add("pbx_voicemail_audio", {
    component: VoicemailAudioPlayer,
    supportedTypes: ["many2one"],
});
