"""API for an automated triage agent working tickets.

Separate from `helpdesk/api/agent.py`, which is the HUMAN agent (HD Agent) API — this module is
only for a bot identity holding the `Support Bot` role.

Why this exists: the agent runs on a recurring schedule (every 15 minutes), so the same open
ticket is seen again on every pass, and two runs can overlap. Without a claim that is atomic,
both runs would decide the ticket is unhandled, reply to the customer twice, and open duplicate
fixes. `claim()` is therefore a single conditional UPDATE — the database, not the caller, decides
who wins.

Nothing here can ship a change to a customer. The agent records findings and state; a human still
approves and deploys.
"""

import frappe
from frappe import _

from helpdesk.consts import BOT_ROLE, TRIAGE_STATES

# States the agent may set once it holds the claim. "" is excluded on purpose: releasing a ticket
# goes through release(), so an accidental empty write can't silently un-claim a live one.
SETTABLE_STATES = [s for s in TRIAGE_STATES if s]


def _require_bot():
    """Only the automation user (or an administrator) may drive these endpoints."""
    if frappe.session.user == "Administrator":
        return
    if BOT_ROLE not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted: requires the {0} role.").format(BOT_ROLE), frappe.PermissionError)


@frappe.whitelist()
def claim(ticket: str, run_id: str) -> bool:
    """Atomically take ownership of an unclaimed ticket. True = this run owns it, False = someone
    else already did (skip it — do NOT reply to the customer).

    The UPDATE only matches while the ticket is still unclaimed, so of two concurrent runs exactly
    one can match. We then read the stored run id back to find out which one that was, rather than
    relying on the driver's rowcount.
    """
    _require_bot()
    if not run_id:
        frappe.throw(_("run_id is required to claim a ticket."))

    frappe.db.sql(
        """
        UPDATE `tabHD Ticket`
           SET bot_triage_state = 'Investigating',
               bot_claimed_by   = %(user)s,
               bot_claimed_at   = %(now)s,
               bot_run_id       = %(run_id)s
         WHERE name = %(ticket)s
           AND IFNULL(bot_triage_state, '') = ''
        """,
        {
            "user": frappe.session.user,
            "now": frappe.utils.now(),
            "run_id": run_id,
            "ticket": ticket,
        },
    )
    frappe.db.commit()

    return frappe.db.get_value("HD Ticket", ticket, "bot_run_id") == run_id


@frappe.whitelist()
def set_state(ticket: str, state: str, run_id: str) -> None:
    """Advance the triage state. Refuses unless this run still holds the claim, so a stale run
    that resumes after a restart cannot stomp on a newer one."""
    _require_bot()
    if state not in SETTABLE_STATES:
        frappe.throw(_("Invalid triage state: {0}").format(state))

    current = frappe.db.get_value("HD Ticket", ticket, "bot_run_id")
    if current != run_id:
        frappe.throw(
            _("Ticket {0} is owned by run {1}, not {2}.").format(ticket, current, run_id),
            frappe.PermissionError,
        )

    frappe.db.set_value("HD Ticket", ticket, "bot_triage_state", state)
    frappe.db.commit()


@frappe.whitelist()
def release(ticket: str, run_id: str) -> None:
    """Return a ticket to the unclaimed pool — for a run that died mid-investigation. Only the
    owning run may release, for the same reason set_state checks."""
    _require_bot()
    current = frappe.db.get_value("HD Ticket", ticket, "bot_run_id")
    if current != run_id:
        frappe.throw(
            _("Ticket {0} is owned by run {1}, not {2}.").format(ticket, current, run_id),
            frappe.PermissionError,
        )

    frappe.db.set_value(
        "HD Ticket",
        ticket,
        {"bot_triage_state": "", "bot_claimed_by": None, "bot_claimed_at": None, "bot_run_id": None},
    )
    frappe.db.commit()


@frappe.whitelist()
def list_unclaimed(limit: int = 20, status: str = "Open") -> list:
    """Tickets no agent run has taken yet — the work list for one pass.

    Bounded by `limit` so a backlog (or an outage that queues hundreds of tickets) can't turn a
    single scheduled run into an unbounded batch.
    """
    _require_bot()
    return frappe.get_all(
        "HD Ticket",
        # "is not set" compiles to IFNULL(field,'')='' — deliberately the SAME predicate the claim
        # matches on. Tickets created before this patch ran have NULL here, not "", so a plain
        # equality filter would quietly hide the entire existing backlog from the agent.
        filters={"bot_triage_state": ["is", "not set"], "status": status},
        fields=["name", "subject", "customer", "contact", "priority", "creation"],
        order_by="creation asc",
        limit_page_length=frappe.utils.cint(limit) or 20,
    )
