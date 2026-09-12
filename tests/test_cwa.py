"""Binary fixtures exercise CWA timing, packing and damaged packet handling."""
import struct
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from cattrack.cwa import read


BASE = datetime(2026, 8, 30, 12)
BASE_SECONDS = (BASE - datetime(1970, 1, 1)).total_seconds()


def packed_time(value):
    return ((value.year - 2000) << 26 | value.month << 22 | value.day << 17 |
            value.hour << 12 | value.minute << 6 | value.second)


def packet(sequence, seconds=0, fraction=0, offset=0, count=120,
           axes_bps=0x30, scale=0, xyz=(0, 0, 256), exponent=0):
    b = bytearray(512)
    b[:2] = b'AX'
    struct.pack_into('<H', b, 2, 508)
    struct.pack_into('<H', b, 4, 0x8000 | int(fraction * 32768))
    struct.pack_into('<I', b, 6, 1)
    struct.pack_into('<I', b, 10, sequence)
    struct.pack_into('<I', b, 14, packed_time(BASE + timedelta(seconds=seconds)))
    struct.pack_into('<H', b, 18, scale << 13)
    b[24], b[25] = 8, axes_bps  # 25 Hz
    struct.pack_into('<hH', b, 26, offset, count)
    if axes_bps == 0x30:
        v = ((xyz[0] & 1023) | (xyz[1] & 1023) << 10 |
             (xyz[2] & 1023) << 20 | exponent << 30)
        for i in range(120):
            struct.pack_into('<I', b, 30 + i * 4, v)
    else:
        for i in range(80):
            struct.pack_into('<hhh', b, 30 + i * 6, *xyz)
    checksum = -sum(struct.unpack('<256H', b)) & 0xFFFF
    struct.pack_into('<H', b, 510, checksum)
    return bytes(b)


class CwaReaderTests(unittest.TestCase):
    def load(self, packets, trailing=b''):
        header = bytearray(1024)
        header[:2] = b'MD'
        struct.pack_into('<H', header, 2, 1020)
        header[36] = 8
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'fixture.cwa'
            p.write_bytes(bytes(header) + b''.join(packets) + trailing)
            return read(p)

    def test_fractional_timestamp_undoes_legacy_offset_shim(self):
        # Stored offset 8 means true offset 20: floor(0.5 s * 25 Hz) = 12.
        _, blocks, samples = self.load([packet(0, fraction=.5, offset=8)])
        self.assertEqual(blocks['ts_offset'][0], 20)
        self.assertAlmostEqual(samples['t'][0], BASE_SECONDS - .3, places=6)
        self.assertAlmostEqual(samples['t'][20], BASE_SECONDS + .5, places=6)

    def test_packed_negative_axes_and_exponent(self):
        _, _, samples = self.load([packet(0, xyz=(-512, 123, -1), exponent=3,
                                              count=3)])
        np.testing.assert_array_equal(samples['x'], [-16., -16., -16.])
        np.testing.assert_array_equal(samples['y'], [3.84375] * 3)
        np.testing.assert_array_equal(samples['z'], [-.03125] * 3)

    def test_unpacked_scales_are_applied_per_packet(self):
        _, _, samples = self.load([
            packet(0, axes_bps=0x32, xyz=(-256, 512, 128), count=2),
            packet(1, seconds=5, axes_bps=0x32, scale=1,
                   xyz=(-256, 512, 128), count=2),
        ])
        np.testing.assert_array_equal(samples['x'], [-1, -1, -.5, -.5])
        np.testing.assert_array_equal(samples['y'], [2, 2, 1, 1])
        np.testing.assert_array_equal(samples['z'], [.5, .5, .25, .25])

    def test_anchor_interpolation_recovers_actual_sensor_rate(self):
        # The second anchor is sample 125 at +5 s, giving exactly 25 Hz.
        # The third is sample 250 at +11 s: the clock then runs at 20.833 Hz.
        h, _, samples = self.load([
            packet(0), packet(1, seconds=5, offset=5),
            packet(2, seconds=11, offset=10),
        ])
        self.assertEqual(h['timing_segments'], 1)
        self.assertAlmostEqual(samples['t'][125] - BASE_SECONDS, 5, places=6)
        self.assertAlmostEqual(samples['t'][250] - BASE_SECONDS, 11, places=6)
        self.assertAlmostEqual(samples['t'][200] - samples['t'][150], 2.4, places=6)
        self.assertTrue(np.all(np.diff(samples['t']) > 0))

    def test_checksum_failure_preserves_acquisition_gap(self):
        corrupt = bytearray(packet(1, seconds=5))
        corrupt[30] ^= 1
        h, _, samples = self.load([
            packet(0), bytes(corrupt), packet(2, seconds=10),
        ], trailing=b'abc')
        self.assertEqual(h['checksum_failures'], 1)
        self.assertEqual(h['invalid_packets'], 1)
        self.assertEqual(h['timing_segments'], 2)
        self.assertEqual(h['trailing_bytes'], 3)
        self.assertEqual(len(samples['t']), 240)
        self.assertAlmostEqual(h['gaps'][0]['seconds'], 5.2, places=6)
        self.assertFalse(np.any((samples['t'] >= BASE_SECONDS + 4.8) &
                                (samples['t'] < BASE_SECONDS + 10)))

    def test_six_axis_data_is_rejected_instead_of_misreading_gyro(self):
        with self.assertRaisesRegex(ValueError, 'three-axis'):
            self.load([packet(0, axes_bps=0x62, count=40)])

    def test_no_valid_packets_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'no valid'):
            self.load([])


if __name__ == '__main__':
    unittest.main()
