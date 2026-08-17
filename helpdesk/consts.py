DEFAULT_TICKET_TYPE = "Unspecified"
DEFAULT_TICKET_PRIORITY = "Medium"
DEFAULT_TICKET_TEMPLATE = "Default"
DEFAULT_SLA = "Standard"
DEFAULT_ARTICLE_CATEGORY = "General"

# --- automated triage agent ---
# Role held by the automation user. It is NOT an HD Agent: no desk access, and it may only advance
# the bot_* triage fields — it cannot reassign, close, or edit ticket content.
BOT_ROLE = "Support Bot"

# The empty first state is the unclaimed state, and it is load-bearing: the atomic claim in
# helpdesk/api/bot.py matches on IFNULL(bot_triage_state,'')='' to decide which run wins.
TRIAGE_STATES = [
    "",
    "Investigating",
    "Fix Proposed",
    "Awaiting Approval",
    "Shipped",
    "Needs Human",
]
