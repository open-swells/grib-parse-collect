import datetime as dt
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import gfs_to_contours


class FakeMessage:
    def __init__(self, values, valid_date):
        self.values = values
        self.validDate = valid_date

    def __getitem__(self, key):
        return None

    def latlons(self):
        lats = np.array([[1.0, 1.0], [0.0, 0.0]])
        lons = np.array([[10.0, 11.0], [10.0, 11.0]])
        return lats, lons


class FakeGribFile:
    def __init__(self, messages):
        self.messages = messages
        self.closed = False

    def select(self, *, name):
        return self.messages[name]

    def close(self):
        self.closed = True


class ExtractHeightTests(unittest.TestCase):
    def test_render_height_uses_combined_field_even_when_swell_is_valid(self):
        valid_date = dt.datetime(2026, 7, 13, tzinfo=dt.UTC)
        # This is the failure mode seen in storm eyes: partition 1 is valid,
        # but it contains a small background swell while combined seas are high.
        swell = np.ma.array([[0.4, 2.0], [3.0, 4.0]], mask=False)
        combined = np.ma.array([[9.0, 3.0], [4.0, 5.0]], mask=False)
        period = np.ma.array([[10.0, 10.0], [10.0, 10.0]], mask=False)
        direction = np.ma.array([[90.0, 90.0], [90.0, 90.0]], mask=False)

        height_messages = [FakeMessage(swell, valid_date) for _ in range(3)]
        period_messages = [FakeMessage(period, valid_date) for _ in range(3)]
        direction_messages = [FakeMessage(direction, valid_date) for _ in range(3)]
        combined_message = FakeMessage(combined, valid_date)
        grib_file = FakeGribFile(
            {
                "Significant height of total swell": height_messages,
                "Mean period of total swell": period_messages,
                "Direction of swell waves": direction_messages,
                "Significant height of combined wind waves and swell": [
                    combined_message
                ],
            }
        )

        gfs_to_contours._GRID_CACHE.clear()
        with patch.object(gfs_to_contours.pygrib, "open", return_value=grib_file):
            result = gfs_to_contours.extract_from_grib2_to_np("forecast.grib2")

        np.testing.assert_array_equal(result["height"], combined.astype(np.float32))
        self.assertEqual(result["height"][0, 0], 9.0)
        self.assertFalse(result["height_mask"].any())
        self.assertTrue(grib_file.closed)

        with tempfile.TemporaryDirectory() as directory:
            png_path = f"{directory}/heatmap.png"
            gfs_to_contours.render_heatmap_png(result, png_path, rows_scale=1.0)
            pixels = np.asarray(Image.open(png_path))

        # Palette index zero is transparent. The storm-eye cell must remain
        # an opaque, high-value ramp color.
        self.assertGreater(pixels[0, 0], 200)


if __name__ == "__main__":
    unittest.main()
