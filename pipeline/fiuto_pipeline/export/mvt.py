"""Decoder minimale di Mapbox Vector Tile (protobuf), senza dipendenze.

Serve solo a verificare quello che scriviamo: nomi dei layer, proprietà delle
feature e tipo di geometria. La geometria non viene decodificata.
"""

from __future__ import annotations

import gzip
import struct

GEOM_TYPES = {0: "unknown", 1: "point", 2: "linestring", 3: "polygon"}


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _fields(buf: bytes):
    """Itera (numero campo, wire type, valore) su un messaggio protobuf."""
    pos = 0
    n = len(buf)
    while pos < n:
        key, pos = _varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            val, pos = _varint(buf, pos)
        elif wire == 1:
            val = buf[pos : pos + 8]
            pos += 8
        elif wire == 2:
            length, pos = _varint(buf, pos)
            val = buf[pos : pos + length]
            pos += length
        elif wire == 5:
            val = buf[pos : pos + 4]
            pos += 4
        else:
            raise ValueError(f"wire type protobuf non gestito: {wire}")
        yield field, wire, val


def _packed_varints(buf: bytes) -> list[int]:
    out = []
    pos = 0
    while pos < len(buf):
        v, pos = _varint(buf, pos)
        out.append(v)
    return out


def _zigzag(v: int) -> int:
    return (v >> 1) ^ -(v & 1)


def _value(buf: bytes):
    """Decodifica un Value MVT. Ritorna (valore, tipo protobuf)."""
    for field, _wire, val in _fields(buf):
        if field == 1:
            return val.decode("utf-8"), "string"
        if field == 2:
            return struct.unpack("<f", val)[0], "float"
        if field == 3:
            return struct.unpack("<d", val)[0], "double"
        if field == 4:
            # int64 codificato come varint complemento a due
            return (val - (1 << 64) if val >= (1 << 63) else val), "int"
        if field == 5:
            return val, "uint"
        if field == 6:
            return _zigzag(val), "sint"
        if field == 7:
            return bool(val), "bool"
    return None, "none"


def decode_tile(data: bytes) -> list[dict]:
    """Decodifica un tile MVT (eventualmente gzip) in una lista di layer.

    Ogni layer: {"name", "extent", "features": [{"id", "type", "properties",
    "value_types"}]}.
    """
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    layers = []
    for field, _wire, val in _fields(data):
        if field != 3:
            continue
        name = None
        extent = 4096
        keys: list[str] = []
        values: list[tuple] = []
        raw_features: list[bytes] = []
        for lf, _lw, lv in _fields(val):
            if lf == 1:
                name = lv.decode("utf-8")
            elif lf == 2:
                raw_features.append(lv)
            elif lf == 3:
                keys.append(lv.decode("utf-8"))
            elif lf == 4:
                values.append(_value(lv))
            elif lf == 5:
                extent = lv
        features = []
        for raw in raw_features:
            fid = None
            gtype = 0
            tags: list[int] = []
            for ff, fw, fv in _fields(raw):
                if ff == 1:
                    fid = fv
                elif ff == 2:
                    tags = _packed_varints(fv) if fw == 2 else [fv]
                elif ff == 3:
                    gtype = fv
            props = {}
            vtypes = {}
            for i in range(0, len(tags) - 1, 2):
                k = keys[tags[i]]
                v, t = values[tags[i + 1]]
                props[k] = v
                vtypes[k] = t
            features.append(
                {
                    "id": fid,
                    "type": GEOM_TYPES.get(gtype, "unknown"),
                    "properties": props,
                    "value_types": vtypes,
                }
            )
        layers.append({"name": name, "extent": extent, "features": features})
    return layers


def layer_names(data: bytes) -> list[str]:
    """Nomi dei layer di un tile (eventualmente gzip), senza decodificare le feature."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    names = []
    for field, _wire, val in _fields(data):
        if field != 3:
            continue
        for lf, _lw, lv in _fields(val):
            if lf == 1:
                names.append(lv.decode("utf-8"))
                break
    return names
