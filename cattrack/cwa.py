"""Minimal, dependency-light CWA (Axivity AX3/AX6) reader.

Format reference: openmovement Docs/ax3/ax3-technical.md
Header  = 1024 bytes ("MD"), data packets = 512 bytes each ("AX").
"""
import struct
from datetime import datetime
import numpy as np
from urllib.parse import unquote

HEADER_SIZE = 1024
PACKET_SIZE = 512


def _decode_time(t):
    """Unpack the CWA 32-bit packed datetime -> (y, mo, d, h, mi, s)."""
    if t in (0, 0xFFFFFFFF):
        return None
    return (2000 + ((t >> 26) & 0x3F), (t >> 22) & 0x0F, (t >> 17) & 0x1F,
            (t >> 12) & 0x1F, (t >> 6) & 0x3F, t & 0x3F)


def _to_epoch(t):
    """Packed datetime -> POSIX-ish seconds (naive, device local time)."""
    d = _decode_time(t)
    if d is None:
        return np.nan
    y, mo, dy, h, mi, s = d
    try:
        datetime(y, mo, dy, h, mi, s)
    except ValueError:
        return np.nan
    # days since 2000-01-01 via civil-from-days inverse
    yy = y - (mo <= 2)
    era = yy // 400
    yoe = yy - era * 400
    doy = (153 * (mo + (-3 if mo > 2 else 9)) + 2) // 5 + dy - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468  # epoch-shift to 1970-01-01
    return days * 86400 + h * 3600 + mi * 60 + s


def _s16(u):
    """Reinterpret low 16 bits as signed."""
    u = np.asarray(u, dtype=np.int64) & 0xFFFF
    return np.where(u >= 0x8000, u - 0x10000, u).astype(np.int64)


def read_header(buf):
    if len(buf) < HEADER_SIZE:
        raise ValueError("truncated CWA header")
    if buf[0:2] != b"MD":
        raise ValueError("not a CWA file (missing MD header)")
    g = lambda f, o: struct.unpack_from(f, buf, o)[0]
    device = g("<H", 5) | (0 if g("<H", 11) == 0xFFFF else g("<H", 11) << 16)
    rate_code = g("<B", 36)
    annotation = buf[64:64 + 448].split(b"\xff")[0].rstrip(b"\x00 ")
    return {
        "device_id": device,
        "session_id": g("<I", 7),
        "logging_start": _decode_time(g("<I", 13)),
        "logging_end": _decode_time(g("<I", 17)),
        "config_rate_hz": 3200 / (1 << (15 - (rate_code & 0x0F))) if rate_code else None,
        "config_range_g": 16 >> (rate_code >> 6) if rate_code else None,
        "firmware": g("<B", 41),
        "annotation": unquote(annotation.decode("ascii", "replace")).strip(),
    }


def read(path):
    """Parse a CWA file. Returns (header, blocks, samples)."""
    raw = np.fromfile(path, dtype=np.uint8)
    header = read_header(raw[:HEADER_SIZE].tobytes())

    body = raw[HEADER_SIZE:]
    trailing_bytes = len(body) % PACKET_SIZE
    n = len(body) // PACKET_SIZE
    body = body[:n * PACKET_SIZE].reshape(n, PACKET_SIZE)

    candidate = (body[:, 0] == ord("A")) & (body[:, 1] == ord("X"))
    length_ok = (body[:, 2] == 0xFC) & (body[:, 3] == 0x01)
    checksum_ok = (body.view("<u2").sum(axis=1, dtype=np.uint64) & 0xFFFF) == 0
    ok = candidate & length_ok & checksum_ok
    header["invalid_packets"] = int((~ok).sum())
    header["checksum_failures"] = int((candidate & ~checksum_ok).sum())
    header["trailing_bytes"] = trailing_bytes
    body = body[ok]
    n = len(body)
    if not n:
        raise ValueError("CWA file has no valid acceleration packets")

    u16 = lambda o: body[:, o].astype(np.uint32) | (body[:, o + 1].astype(np.uint32) << 8)
    u32 = lambda o: u16(o) | (u16(o + 2) << 16)

    frac_raw = u16(4)
    ts_raw = u32(14)
    light_scale = u16(18)
    blocks = {
        "sequence": u32(10),
        "timestamp": np.array([_to_epoch(int(t)) for t in ts_raw]),
        "fraction": np.where(frac_raw & 0x8000, (frac_raw & 0x7FFF) / 32768.0, 0.0),
        "light": light_scale & 0x03FF,
        "temperature": (u16(20) & 0x03FF) * 75.0 / 256.0 - 50.0,
        "events": body[:, 22].astype(np.uint8),
        "battery_v": (body[:, 23].astype(np.float64) + 512.0) * 6.0 / 1024.0,
        "rate_code": body[:, 24].astype(np.uint8),
        "axes_bps": body[:, 25].astype(np.uint8),
        "ts_offset": _s16(u16(26)),
        "count": u16(28),
    }
    blocks["rate_hz"] = 3200.0 / (1 << (15 - (blocks["rate_code"] & 0x0F)))

    if np.any((blocks["axes_bps"] >> 4) != 3):
        raise ValueError("only three-axis accelerometer CWA packets are supported")
    if np.any(blocks["axes_bps"] != blocks["axes_bps"][0]):
        raise ValueError("mixed CWA sample packing is unsupported")
    if np.any(blocks["rate_code"] == 0):
        raise ValueError("legacy zero-rate CWA packets are unsupported")
    if np.any(~np.isfinite(blocks["timestamp"])):
        raise ValueError("CWA packet has an invalid timestamp")

    # Restore the true sample index represented by a fractional RTC timestamp.
    # AX firmware subtracts this whole-sample shift for legacy integer-time readers.
    blocks["ts_offset_raw"] = blocks["ts_offset"].copy()
    blocks["ts_offset"] += np.floor(
        blocks["fraction"] * blocks["rate_hz"].astype(np.int64)
    ).astype(np.int64)

    # ---- samples -------------------------------------------------------
    packing = int(blocks["axes_bps"][0]) & 0x0F
    payload = body[:, 30:510]
    if packing == 0:                      # 3x10-bit + 2-bit exponent, 120/packet
        v = (payload[:, 0::4].astype(np.uint32)
             | (payload[:, 1::4].astype(np.uint32) << 8)
             | (payload[:, 2::4].astype(np.uint32) << 16)
             | (payload[:, 3::4].astype(np.uint32) << 24))
        expo = ((v >> 30) & 0x03).astype(np.int64)
        x = _s16((v << 6) & 0xFFC0) >> (6 - expo)
        y = _s16((v >> 4) & 0xFFC0) >> (6 - expo)
        z = _s16((v >> 14) & 0xFFC0) >> (6 - expo)
        scale = 256.0
        per_packet = 120
    elif packing == 2:                    # 3x 16-bit signed, 80/packet
        w = payload[:, 0::2].astype(np.uint32) | (payload[:, 1::2].astype(np.uint32) << 8)
        x, y, z = _s16(w[:, 0::3]), _s16(w[:, 1::3]), _s16(w[:, 2::3])
        scale = (1 << (8 + ((light_scale >> 13) & 0x07))).astype(float)[:, None]
        per_packet = 80
    else:
        raise ValueError(f"unsupported packing format {packing}")

    if np.any((blocks["count"] < 1) | (blocks["count"] > per_packet)):
        raise ValueError("CWA sample count exceeds packet capacity or is zero")
    times, timing = _sample_times(blocks)
    header.update(timing)
    valid = np.arange(per_packet)[None, :] < blocks["count"][:, None]
    samples = {
        "t": times,
        "x": (x / scale)[valid],
        "y": (y / scale)[valid],
        "z": (z / scale)[valid],
    }
    header["packing"] = packing
    header["samples_per_packet"] = per_packet
    header["n_packets"] = n
    return header, blocks, samples


def _sample_times(blocks):
    """Interpolate RTC anchors within continuous runs, preserving acquisition gaps.

    The configured sample frequency is nominal. Interpolation recovers the actual
    sensor clock rate; using nominal rates separately per packet can create gaps
    or overlapping timestamps. Extrapolate edge samples at the nominal rate.
    """
    count = blocks["count"].astype(np.int64)
    starts = np.r_[0, np.cumsum(count)]
    anchor_sample = starts[:-1] + blocks["ts_offset"]
    anchor_time = blocks["timestamp"] + blocks["fraction"]
    hz = blocks["rate_hz"]
    di = np.diff(anchor_sample)
    dt = np.diff(anchor_time)
    expected = di / hz[:-1]
    contiguous = (
        (np.diff(blocks["sequence"].astype(np.int64)) == 1)
        & (hz[1:] == hz[:-1]) & (di > 0) & (dt > 0)
        & (dt >= expected * 0.5) & (dt <= expected * 1.5)
    )
    bounds = np.r_[0, np.flatnonzero(~contiguous) + 1, len(count)]
    times = np.empty(int(starts[-1]), dtype=np.float64)
    gaps = []
    for begin, end in zip(bounds[:-1], bounds[1:]):
        sample_indices = np.arange(starts[begin], starts[end], dtype=np.float64)
        xp = anchor_sample[begin:end]
        fp = anchor_time[begin:end]
        values = np.interp(sample_indices, xp, fp)
        before = sample_indices < xp[0]
        after = sample_indices > xp[-1]
        values[before] = fp[0] + (sample_indices[before] - xp[0]) / hz[begin]
        values[after] = fp[-1] + (sample_indices[after] - xp[-1]) / hz[end - 1]
        times[starts[begin]:starts[end]] = values
        if begin:
            prior_end = times[starts[begin] - 1] + 1 / hz[begin - 1]
            gaps.append({"start": float(prior_end), "end": float(values[0]),
                         "seconds": float(values[0] - prior_end)})
    if np.any(np.diff(times) <= 0):
        raise ValueError("CWA timestamps overlap or reverse across acquisition segments")
    return times, {
        "timing_segments": int(len(bounds) - 1),
        "gaps": gaps,
        "median_actual_rate_hz": float(np.median(di[contiguous] / dt[contiguous]))
        if np.any(contiguous) else float(hz[0]),
    }
