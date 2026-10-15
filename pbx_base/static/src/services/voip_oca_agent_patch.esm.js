/** @odoo-module **/
/*
    Patch of the OCA voip_oca agent service.

    SIP.js 0.21.2 exposes two session class hierarchies with different
    methods:

                      Session (base)   Inviter (outgoing)   Invitation (incoming)
      bye                  yes                yes                   yes
      cancel                no                yes                    no
      reject                no                 no                   yes
      accept                no                 no                   yes

    An outgoing call creates an Inviter, which has cancel(). An incoming
    call is an Invitation, which has reject() and accept() but no cancel().

    OCA's hangup() calls cancel() unconditionally, so hanging up an
    incoming call throws "this.session.cancel is not a function". accept()
    is likewise called without checking that the session has it.

    This is patched here rather than in voip_oca itself so we do not carry
    local changes in a third-party repository.

    Rather than reimplementing hangup() — which would duplicate the state
    machine and drift from upstream — we normalise the session object
    before the original runs: whichever of cancel()/reject()/accept() the
    class does not provide is filled in with the closest equivalent. The
    original methods then run unmodified.
*/
import {VoipAgent} from "@voip_oca/services/voip_agent_service.esm";

const _originalHangup = VoipAgent.prototype.hangup;
const _originalAccept = VoipAgent.prototype.accept;

/**
 * Give a SIP.js session the teardown methods OCA's code may call, mapping
 * each missing one onto the equivalent the class does provide.
 *
 * @param {object} session SIP.js Inviter or Invitation
 * @returns {object} the same session, with the missing methods filled in
 */
function _normaliseSession(session) {
    if (!session) {
        return session;
    }
    if (typeof session.cancel !== "function" && typeof session.reject === "function") {
        // Invitation has no cancel(); rejecting is the equivalent for a
        // call that has not been answered yet.
        session.cancel = () => session.reject();
    }
    if (typeof session.reject !== "function" && typeof session.cancel === "function") {
        // Inviter has no reject(); cancelling is the equivalent.
        session.reject = () => session.cancel();
    }
    if (typeof session.accept !== "function") {
        // Inviter has no accept() — the call is already being placed, so
        // there is nothing to answer. A no-op keeps the original accept()
        // from throwing.
        session.accept = () => {};
    }
    return session;
}

VoipAgent.prototype.hangup = async function () {
    _normaliseSession(this.session);
    return _originalHangup.call(this);
};

VoipAgent.prototype.accept = async function () {
    _normaliseSession(this.session);
    return _originalAccept.call(this);
};
