import os
import sys
import pathlib
import importlib

import numpy as np
from PIL import Image

print("==========================================")
print("AI Vision Dashboard v5 - Environment Check")
print("==========================================")
print("Python:", sys.version)
print("OS:", os.name)
print("pathlib file:", pathlib.__file__)

from dashboard_core import (
    install_pathlib_pickle_compat,
    RUNTIME_ROOT,
    anomaly_visuals,
)

install_pathlib_pickle_compat()
mod = importlib.import_module("pathlib._local")
print("pathlib._local: OK")
print("shim PosixPath:", mod.PosixPath)
print("runtime root:", RUNTIME_ROOT)

import torch
import torchvision
import anomalib
import lightning
import streamlit
import matplotlib

print("torch:", torch.__version__)
print("torchvision:", torchvision.__version__)
print("anomalib:", anomalib.__version__)
print("lightning:", lightning.__version__)
print("streamlit:", streamlit.__version__)
print("matplotlib:", matplotlib.__version__)

# Modern Matplotlib colormap API used by the dashboard.
_ = matplotlib.colormaps["turbo"]
print("matplotlib colormap registry: OK")

# Run the actual visualization function used after EfficientAD inference.
img = Image.new("RGB", (256, 256), "gray")
amap = np.linspace(0.0, 1.0, 256 * 256, dtype=np.float32).reshape(256, 256)
vis = anomaly_visuals(img, amap)
assert set(vis) == {"original", "heatmap", "overlay", "contour"}
assert all(v.size == (256, 256) for v in vis.values())
print("dashboard visualization test: OK")

print("==========================================")
print("DIAGNOSTIC PASS")
print("==========================================")
