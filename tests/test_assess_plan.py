import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from dee.approval import ApprovalError, approve, is_agent
from dee.audit import AuditLog, verify
from dee.assess import assess_deal
from dee.ingest import load_deals, norm_category
from dee.pipeline import load_policy, run
from dee.util import read_json

POL = load_policy("config/policy.json")
AS_OF = date(2026, 11, 25)
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)


def ev(field, value, age, strength="buyer_stated", pol="pos", doc="D1", cue=False):
    d = date(2026, 11, 25).toordinal() - age
    return {"deal_id": "D-1", "doc_id": f"{doc}-{field}-{age}", "doc_date": date.fromordinal(d).isoformat(), "field": field, "value": value,
            "span": "x", "polarity": pol, "speaker": "S", "speaker_title": "", "strength": strength, "supersedes_cue": cue, "extractor": "rules"}


DEAL = {"deal_id": "D-1", "category_norm": "Commit", "close_date_d": date(2026, 12, 20)}
GOOD = [ev("economic_buyer", "Dana Cole", 3), ev("decision_process", "2026-12-02", 3), ev("paper_process", "in_progress", 3), ev("identify_pain", "pain", 3)]


class AssessTests(unittest.TestCase):
    def a(self, evid, deal=DEAL):
        return assess_deal(deal, evid, POL, AS_OF, {}, [])

    def test_commit_when_all_three_buyer_fresh(self):
        self.assertEqual(self.a(GOOD)["allowed_category"], "Commit")

    def test_rep_only_is_not_evidence(self):
        reps = [dict(e, strength="rep_reported") for e in GOOD]
        r = self.a(reps)
        self.assertEqual(r["allowed_category"], "Pipeline")
        self.assertEqual(r["fields"]["economic_buyer"]["status"], "rep_reported_only")

    def test_stale(self):
        r = self.a([ev("economic_buyer", "Dana Cole", 60)] + GOOD[1:])
        self.assertEqual(r["fields"]["economic_buyer"]["status"], "stale")
        self.assertNotEqual(r["allowed_category"], "Commit")

    def test_decision_after_close_date(self):
        r = self.a([GOOD[0], ev("decision_process", "2027-01-15", 3), GOOD[2]])
        self.assertEqual(r["fields"]["decision_process"]["status"], "after_close_date")

    def test_decision_date_passed(self):
        r = self.a([GOOD[0], ev("decision_process", "2026-11-10", 3), GOOD[2]])
        self.assertEqual(r["fields"]["decision_process"]["status"], "date_passed")

    def test_conflicting_economic_buyers(self):
        r = self.a(GOOD + [ev("economic_buyer", "Raj Mehta", 1)])
        self.assertEqual(r["fields"]["economic_buyer"]["status"], "conflict")
        self.assertNotEqual(r["allowed_category"], "Commit")

    def test_superseding_cue_resolves_date_change(self):
        r = self.a([GOOD[0], ev("decision_process", "2026-12-01", 14), ev("decision_process", "2026-12-09", 2, cue=True), GOOD[2]])
        self.assertEqual(r["fields"]["decision_process"]["status"], "satisfied")
        self.assertEqual(r["fields"]["decision_process"]["value"], "2026-12-09")

    def test_paper_regression_is_conflict(self):
        r = self.a([GOOD[0], GOOD[1], ev("paper_process", "complete", 15), ev("paper_process", "not_started", 2)])
        self.assertEqual(r["fields"]["paper_process"]["status"], "conflict")

    def test_later_negation_conflicts(self):
        r = self.a([ev("economic_buyer", "Dana Cole", 12)] + GOOD[1:] + [ev("economic_buyer", "Dana Cole", 2, pol="neg")])
        self.assertEqual(r["fields"]["economic_buyer"]["status"], "conflict")

    def test_best_case_and_change_labels(self):
        r = self.a([GOOD[3], ev("champion", "Dana Cole", 2)])
        self.assertEqual(r["allowed_category"], "Best Case")
        self.assertEqual(r["change"], "downgrade")
        up = self.a(GOOD, dict(DEAL, category_norm="Pipeline"))
        self.assertEqual(up["change"], "upgrade_suggestion")

    def test_category_normalisation(self):
        self.assertEqual([norm_category(x) for x in ("COMMIT", "best case", " Pipeline ", "Commit?")], ["Commit", "Best Case", "Pipeline", "UNKNOWN"])


class AuditAndApprovalTests(unittest.TestCase):
    def test_audit_chain(self):
        with tempfile.TemporaryDirectory() as t:
            log = AuditLog(Path(t) / "a.log")
            for i in range(3):
                log.append({"event": "x", "i": i})
            self.assertTrue(verify(Path(t) / "a.log")[0])
            p = Path(t) / "a.log"
            p.write_text(p.read_text().replace('"i": 1', '"i": 9').replace('"i":1', '"i":9'))
            self.assertFalse(verify(p)[0])

    def test_agent_identity_detection(self):
        blocked = read_json("config/approvers.json")["blocked_identities"]
        for who in ("claude", "deal-evidence-engine", "n8n_workflow", "", "automation-user"):
            self.assertTrue(is_agent(who, blocked), who)
        self.assertFalse(is_agent("revops-lead", blocked))

    def test_run_is_deterministic_and_writes_files_only(self):
        with tempfile.TemporaryDirectory() as t:
            a = run("sample_deals.csv", "sample_notes.csv", Path(t) / "a", AS_OF)
            b = run("sample_deals.csv", "sample_notes.csv", Path(t) / "b", AS_OF)
            self.assertEqual(a["manifest"]["plan_sha256"], b["manifest"]["plan_sha256"])
            self.assertFalse((Path(t) / "a" / "crm_state.json").exists())  # no CRM touched by `run`

    def test_plan_ops_are_limited_to_known_types_and_properties(self):
        with tempfile.TemporaryDirectory() as t:
            run("sample_deals.csv", "sample_notes.csv", Path(t) / "a", AS_OF)
            plan = read_json(Path(t) / "a" / "crm_update_plan.json")
            allowed = {"meddpicc_" + f for f in POL["meddpicc_fields"]} | {"forecast_category"}
            for op in plan["ops"]:
                self.assertIn(op["type"], ("update_meddpicc", "update_forecast_category"))
                self.assertTrue(set(op["payload"]) <= allowed)
                self.assertEqual(op["requires_approval"], op["type"] == "update_forecast_category")


if __name__ == "__main__":
    unittest.main()
