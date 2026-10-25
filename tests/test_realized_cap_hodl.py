import unittest
from datetime import date
from scripts.update_realized_cap_hodl import parse_latest


class RealizedCapHODLTests(unittest.TestCase):
    def test_extracts_public_latest_value_and_maps_score(self):
        page = """
        <h2>Latest Values</h2><p>as of 24 Oct 2026</p>
        <div>1w-1m 10.000%</div>
        """
        result = parse_latest(page, today=date(2026, 10, 25))
        self.assertEqual(result["bandPercent"], 10.0)
        self.assertEqual(result["score"], 2.0)

    def test_midpoint_is_neutral(self):
        page = "<p>Latest Values as of 24 Oct 2026</p><div>1w-1m 30%</div>"
        self.assertEqual(parse_latest(page, today=date(2026, 10, 25))["score"], 0.0)

    def test_rejects_stale_page(self):
        page = "<p>Latest Values as of 14 Oct 2026</p><div>1w-1m 6.842%</div>"
        with self.assertRaises(ValueError):
            parse_latest(page, today=date(2026, 10, 25))


if __name__ == "__main__":
    unittest.main()
