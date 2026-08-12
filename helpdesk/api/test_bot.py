import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.bot import claim, list_unclaimed, release, set_state
from helpdesk.consts import BOT_ROLE


class TestBotTriage(FrappeTestCase):
    """The claim has to be exactly-once. A recurring agent sees the same open ticket on every
    pass, so anything weaker here means duplicate replies to the customer."""

    original_user = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.original_user = frappe.session.user

    def tearDown(self):
        frappe.set_user(self.original_user or "Administrator")

    def _ticket(self, subject="bot triage test"):
        t = frappe.get_doc({"doctype": "HD Ticket", "subject": subject}).insert(
            ignore_permissions=True
        )
        frappe.db.commit()
        return t.name

    def test_first_claim_wins_and_second_is_refused(self):
        ticket = self._ticket()
        self.assertTrue(claim(ticket, run_id="run-a"))
        # Second run sees the same open ticket on its next pass — it must NOT get the claim.
        self.assertFalse(claim(ticket, run_id="run-b"))
        self.assertEqual(frappe.db.get_value("HD Ticket", ticket, "bot_run_id"), "run-a")

    def test_claim_is_idempotent_within_one_run(self):
        ticket = self._ticket()
        self.assertTrue(claim(ticket, run_id="run-a"))
        # A retry inside the same run should still report ownership rather than falsely skipping.
        self.assertTrue(claim(ticket, run_id="run-a"))

    def test_claim_marks_investigating(self):
        ticket = self._ticket()
        claim(ticket, run_id="run-a")
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket, "bot_triage_state"), "Investigating"
        )

    def test_only_the_owning_run_may_advance_state(self):
        ticket = self._ticket()
        claim(ticket, run_id="run-a")
        with self.assertRaises(frappe.PermissionError):
            set_state(ticket, "Fix Proposed", run_id="run-b")
        set_state(ticket, "Fix Proposed", run_id="run-a")
        self.assertEqual(
            frappe.db.get_value("HD Ticket", ticket, "bot_triage_state"), "Fix Proposed"
        )

    def test_invalid_state_is_rejected(self):
        ticket = self._ticket()
        claim(ticket, run_id="run-a")
        with self.assertRaises(frappe.ValidationError):
            set_state(ticket, "Deployed To Prod", run_id="run-a")

    def test_release_returns_the_ticket_to_the_pool(self):
        ticket = self._ticket()
        claim(ticket, run_id="run-a")
        release(ticket, run_id="run-a")
        self.assertIn(frappe.db.get_value("HD Ticket", ticket, "bot_triage_state"), ("", None))
        # ...and a later run can then pick it up.
        self.assertTrue(claim(ticket, run_id="run-c"))

    def test_unclaimed_list_excludes_claimed_tickets(self):
        ticket = self._ticket("unclaimed listing test")
        self.assertIn(ticket, [t.name for t in list_unclaimed(limit=50)])
        claim(ticket, run_id="run-a")
        self.assertNotIn(ticket, [t.name for t in list_unclaimed(limit=50)])

    def test_non_bot_user_is_refused(self):
        ticket = self._ticket()
        user = "helpdesk-not-a-bot@example.com"
        if not frappe.db.exists("User", user):
            frappe.get_doc(
                {"doctype": "User", "email": user, "first_name": "Not A Bot"}
            ).insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(user)
        with self.assertRaises(frappe.PermissionError):
            claim(ticket, run_id="run-a")

    def test_bot_role_exists(self):
        self.assertTrue(frappe.db.exists("Role", BOT_ROLE))
