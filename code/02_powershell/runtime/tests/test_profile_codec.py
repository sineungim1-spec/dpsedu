import numpy as np
from mvhd_ad.array_codec import encode_array,decode_array

def test_codec_roundtrip():
    a=np.arange(100,dtype=np.float32).reshape(10,10)
    b=decode_array(encode_array(a))
    assert np.array_equal(a,b)
