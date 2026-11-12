"""Synthetic safety tests for the hypothetical EV compatibility adapter."""
import unittest
from offline_ev_binding_adapter import adapt_sensitivity

def fixture():
    rows = []
    for rid,q,seed in (("tight",.2,1),("loose",.3,2)):
        ci = [q-.02,q+.02]
        bounds = [x*200-50 for x in ci]
        label = ("positive_under_interval" if bounds[0]>0 else
                 "negative_under_interval" if bounds[1]<0 else "uncertain_or_break_even")
        rows.append({"range_id":rid,"equity":q,"equity_ci_conditional":ci,
                     "ev_call_bb":q*200-50,"ev_ci_conditional_bb":bounds,
                     "conditional_label":label,"iterations":10000,"seed":seed})
    return {"schema_version":1,"analysis_status":"HYPOTHETICAL_RANGE_SENSITIVITY_ONLY",
            "pot_before_call_bb":150.,"call_cost_bb":50.,"break_even_equity":.25,
            "scenarios":rows,"range_sensitive":True,"gto_solution":False,
            "strategic_error_established":False,
            "automatic_clip_selection_authorized":False,
            "range_uncertainty_included_in_ci":False}

class AdapterTests(unittest.TestCase):
    def test_valid(self):
        v=adapt_sensitivity(fixture(),"scenario_1")
        self.assertTrue(v["range_sensitive"])
        self.assertFalse(v["gto_solution"])
        self.assertAlmostEqual(v["range_results"][0]["ev_call_bb"],-10)
    def test_tamper_ev(self):
        v=fixture();v["scenarios"][0]["ev_call_bb"]=999
        with self.assertRaises(ValueError):adapt_sensitivity(v,"scenario_1")
    def test_unsafe_provenance(self):
        v=fixture();v["gto_solution"]=True
        with self.assertRaises(ValueError):adapt_sensitivity(v,"scenario_1")
    def test_duplicate_ranges(self):
        v=fixture();v["scenarios"][1]["range_id"]="tight"
        with self.assertRaises(ValueError):adapt_sensitivity(v,"scenario_1")
    def test_bad_scenario(self):
        with self.assertRaises(ValueError):adapt_sensitivity(fixture(),"../bad")
    def test_nonfinite(self):
        v=fixture();v["scenarios"][0]["equity"]=float("nan")
        with self.assertRaises(ValueError):adapt_sensitivity(v,"scenario_1")
    def test_summary_tamper(self):
        v=fixture();v["range_sensitive"]=False
        with self.assertRaises(ValueError):adapt_sensitivity(v,"scenario_1")
    def test_count_limit(self):
        v=fixture();v["scenarios"]*=7
        with self.assertRaises(ValueError):adapt_sensitivity(v,"scenario_1")

if __name__=="__main__":
    unittest.main()
