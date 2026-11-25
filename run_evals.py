"""python run_evals.py : evaluates the engine and the keyword baseline on gold_v1 (dev and held-out). Offline, no API key."""
import json
from pathlib import Path

from evals.harness import model_robustness, run_all


def show(name, r):
    print(f"\n== {name} ==")
    for k in ("engine", "baseline"):
        print(f"evidence {k:8s}: {r[k]['frac']}")
    print("value accuracy (typed TPs):", r["value_accuracy_typed_tp"])
    print("unsupported claims:", r["unsupported_claims"]["engine"], "engine;", r["unsupported_claims"]["baseline"], "baseline")
    print("claims not in gold:", r["claims_not_in_gold"])
    print("conflict detection:", r["conflict_detection"]["frac"])
    c = r["category"]
    print(f"category agreement: engine {c['engine_agreement']}, baseline {c['baseline_agreement']}, rep-called {c['rep_called_agreement']}; false Commit {c['false_commit']}")
    i = r["injection"]
    print(f"injection: quarantined {i['quarantined_correct']}/{i['screened_docs_gold']} (wrong {i['quarantined_wrong']}), leaked evidence {i['evidence_leaked_from_quarantined_docs']}, "
          f"screen-evading injections accepted as evidence {i['unscreened_injection_accepted_as_evidence']}/{i['unscreened_injections_in_gold']}")
    for m in c["engine_misses"]:
        print("  category miss:", m)


if __name__ == "__main__":
    res = run_all()
    Path("evals/results.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print("gold_v1 held-out sha256 verified:", res["heldout_sha256"])
    show("DEV (58 deals, used for tuning)", res["dev"])
    show("HELD-OUT (not used for tuning)", res["heldout"])
    res["scripted_model"] = model_robustness()
    Path("evals/results.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print("\n== SCRIPTED FAKE MODEL (every failure mode, round-robin per document; no network) ==")
    for split, m in res["scripted_model"].items():
        print(f"{split}: bad candidates produced {m['bad_candidates_produced']}, rejected by validators {m['bad_candidates_rejected']}, unparseable outputs {m['unparseable_outputs']}, "
              f"unsupported spans in accepted evidence {m['unsupported_spans_in_accepted_evidence']}, "
              f"docs fell back to rules {m['docs_fell_back_to_rules']}, category agreement {m['category_agreement_with_gold']}")
    print("\nwrote evals/results.json")
