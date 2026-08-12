"""Adds the fields + role an automated agent needs to work tickets safely.

Kept as a patch using Frappe's Custom Field API (rather than editing the HD Ticket doctype JSON)
so this fork stays rebaseable on upstream — none of upstream's files are touched.

The bot is deliberately NOT an HD Agent: it gets its own role with no desk access, so it cannot
reassign, close, or edit ticket content. It may only advance the triage fields added here.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from helpdesk.consts import BOT_ROLE, TRIAGE_STATES


def execute():
    create_custom_fields(get_custom_fields())
    setup_bot_role()


def get_custom_fields():
    return {
        "HD Ticket": [
            {
                "fieldname": "bot_triage_section",
                "label": "Automated Triage",
                "fieldtype": "Section Break",
                "insert_after": "status",
                "collapsible": 1,
            },
            {
                "fieldname": "bot_triage_state",
                "label": "Bot Triage State",
                "fieldtype": "Select",
                "options": "\n".join(TRIAGE_STATES),
                "insert_after": "bot_triage_section",
                "read_only": 1,
                "no_copy": 1,
                "description": (
                    "Set by the automated triage agent. Empty means unclaimed — a recurring agent "
                    "run claims a ticket by moving this off empty, exactly once."
                ),
            },
            {
                "fieldname": "bot_claimed_by",
                "label": "Bot Claimed By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "bot_triage_state",
                "read_only": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "bot_claimed_at",
                "label": "Bot Claimed At",
                "fieldtype": "Datetime",
                "insert_after": "bot_claimed_by",
                "read_only": 1,
                "no_copy": 1,
            },
            {
                "fieldname": "bot_run_id",
                "label": "Bot Run ID",
                "fieldtype": "Data",
                "insert_after": "bot_claimed_at",
                "read_only": 1,
                "no_copy": 1,
                "description": "Identifier of the agent run that owns this ticket — used to decide "
                "which of two overlapping runs won the claim.",
            },
        ],
    }


def setup_bot_role():
    """A non-desk role for the automation user. Permissions are granted explicitly elsewhere;
    the role itself exists so a bot session can be identified and audited."""
    if frappe.db.exists("Role", BOT_ROLE):
        role = frappe.get_doc("Role", BOT_ROLE)
    else:
        role = frappe.new_doc("Role")
        role.role_name = BOT_ROLE
    role.desk_access = 0
    role.save()
