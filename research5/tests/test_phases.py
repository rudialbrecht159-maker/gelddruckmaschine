"""UNIT TESTS with SYNTHETIC fixtures. These numbers are test data, NOT trading results."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import phases as P
D = P.DAY; S = 1_790_000_000_000
def fixture(nets, days, start=50.0, **kw):
    """SYNTHETIC: one trade per given day offset; equity = cumulative."""
    tr, eq, e = [], [(S, start)], start
    for i, (n, d) in enumerate(zip(nets, days)):
        e += n; tr.append(dict(t_out=S + int(d * D), net=n, gross=n + 0.02, fees=0.02, funding=0.0, strategy=kw.get("strat", "TEST"), coin=["BTC", "ETH"][i % 2], exit_reason="stop" if n < 0 else "signal")); eq.append((S + int(d * D), e))
    return tr, eq
class T(unittest.TestCase):
    def test_pass_after_p3(self):
        tr, eq = fixture([0.3, -0.1] * 20, [i * 0.8 for i in range(40)])
        r = P.evaluate(tr, eq, S, now_ts=S + 35 * D)
        p3 = [p for p in r["phases"] if p["phase"] == "P3"][0]
        self.assertEqual(p3["status"], "PASS"); self.assertEqual(r["action"], "continue")
    def test_p1_few_trades_inconclusive(self):
        tr, eq = fixture([0.3, 0.2, -0.1], [1, 2, 3]); r = P.evaluate(tr, eq, S, now_ts=S + 7 * D)
        self.assertEqual(r["phases"][0]["status"], "INCONCLUSIVE"); self.assertEqual(r["action"], "continue")
    def test_p3_few_trades_extend(self):
        tr, eq = fixture([0.3, 0.2, -0.1, 0.2], [1, 9, 15, 30]); r = P.evaluate(tr, eq, S, now_ts=S + 36 * D)
        self.assertEqual(r["action"], "extend")
    def test_fail_negative_net_pauses_with_causes(self):
        tr, eq = fixture([-0.5] * 5 + [0.1], [1, 2, 3, 4, 5, 6]); r = P.evaluate(tr, eq, S, now_ts=S + 8 * D)
        p1 = r["phases"][0]; self.assertEqual(p1["status"], "FAIL"); self.assertEqual(r["action"], "pause")
        self.assertIn("net_positive", p1["failed"]); self.assertIn("by_coin", p1["cause_analysis"]); self.assertIn("stop", p1["cause_analysis"]["by_exit_reason"])
        self.assertEqual(len(r["phases"]), 1)  # later phases not evaluated after pause
    def test_fail_maxdd(self):
        tr, eq = fixture([2.0, -6.0, 4.5], [1, 2, 3]); r = P.evaluate(tr, eq, S, now_ts=S + 7 * D)
        self.assertFalse(r["phases"][0]["checks"]["max_dd"]); self.assertEqual(r["action"], "pause")
    def test_fail_single_outlier(self):
        tr, eq = fixture([5.0] + [-0.1] * 35, [1] + [2 + i * 0.5 for i in range(35)])
        r = P.evaluate(tr, eq, S, now_ts=S + 7 * D); self.assertEqual(r["phases"][0]["status"], "INCONCLUSIVE")  # early: not a fail
        r = P.evaluate(tr, eq, S, now_ts=S + 22 * D); p = r["phases"][-1]
        self.assertEqual(p["phase"], "P3"); self.assertTrue(p["checks"]["net_positive"]); self.assertFalse(p["checks"]["robust_net"])
        r = P.evaluate(tr, eq, S, now_ts=S + 35 * D); self.assertEqual(r["phases"][-1]["status"], "FAIL"); self.assertEqual(r["action"], "pause")
    def test_running_phase(self):
        tr, eq = fixture([0.2], [1]); r = P.evaluate(tr, eq, S, now_ts=S + 3 * D)
        self.assertEqual(r["phases"][0]["status"], "running"); self.assertEqual(r["current_phase"], "P1")
    def test_iso_inputs_and_markdown(self):
        tr, eq = fixture([0.3, -0.5], [1, 2]); tr = [{**t, "t_out": P._iso(t["t_out"]).replace(" UTC", "").replace(" ", "T") + ":00Z"} for t in tr]
        r = P.evaluate(tr, eq, P._iso(S).replace(" UTC", "").replace(" ", "T") + ":00Z", now_ts=S + 8 * D); md = P.render_md(r)
        self.assertIn("Ursachenanalyse", md); self.assertIn("SIMULIERT", md)
class T2(unittest.TestCase):
    def test_no_trades_is_not_fail(self):
        r = P.evaluate([], [(S, 50.0), (S + 6 * D, 50.0)], S, now_ts=S + 8 * D)
        self.assertEqual(r["phases"][0]["status"], "INCONCLUSIVE"); self.assertEqual(r["action"], "continue")
if __name__ == "__main__": unittest.main(verbosity=2)
