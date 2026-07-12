import json
import tempfile
import unittest
from datetime import UTC, datetime
from unittest.mock import Mock

from tides import DATA_URL, fetch_station, write_tides


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class TideTests(unittest.TestCase):
    def test_fetch_station_combines_predictions_observations_and_metadata(self):
        session = Mock()
        session.get.side_effect = [
            FakeResponse({"predictions": [{"t": "2026-07-11 00:00", "v": "1.2"}]}),
            FakeResponse({"data": [{"t": "2026-07-11 00:00", "v": "1.3"}]}),
            FakeResponse({"stations": [{"name": "Test", "lat": 1.0, "lng": -2.0}]}),
        ]

        result = fetch_station(
            session,
            "1234567",
            now=datetime(2026, 7, 11, tzinfo=UTC),
        )

        self.assertEqual(result["name"], "Test")
        self.assertEqual(result["datum"], "MLLW")
        self.assertEqual(len(result["predictions"]), 1)
        self.assertEqual(len(result["observations"]), 1)
        prediction_call = session.get.call_args_list[0]
        self.assertEqual(prediction_call.args[0], DATA_URL)
        self.assertEqual(prediction_call.kwargs["params"]["interval"], "h")

    def test_write_tides_keeps_other_stations_when_one_fails(self):
        session = Mock()
        with tempfile.NamedTemporaryFile() as output:
            from unittest.mock import patch

            with patch(
                "tides.fetch_station",
                side_effect=[{"id": "good"}, RuntimeError("unavailable")],
            ):
                successes, failures = write_tides(
                    session,
                    ["good", "bad"],
                    output.name,
                    now=datetime(2026, 7, 11, tzinfo=UTC),
                )
            output.seek(0)
            payload = json.load(output)

        self.assertEqual((successes, failures), (1, 1))
        self.assertEqual(payload["stations"], [{"id": "good"}])
        self.assertEqual(payload["errors"][0]["station"], "bad")


if __name__ == "__main__":
    unittest.main()
