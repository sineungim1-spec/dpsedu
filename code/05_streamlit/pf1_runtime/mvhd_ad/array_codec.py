from __future__ import annotations
import base64, io, zlib
import numpy as np

ENCODING = "npy+zlib+base64"

def encode_array(array: np.ndarray) -> dict:
    bio = io.BytesIO()
    np.save(bio, np.asarray(array), allow_pickle=False)
    payload = base64.b64encode(zlib.compress(bio.getvalue(), level=6)).decode("ascii")
    return {"encoding": ENCODING, "data": payload}

def decode_array(obj: dict) -> np.ndarray:
    if not isinstance(obj, dict) or obj.get("encoding") != ENCODING:
        raise ValueError("Unsupported ndarray encoding")
    raw = zlib.decompress(base64.b64decode(obj["data"]))
    return np.load(io.BytesIO(raw), allow_pickle=False)
