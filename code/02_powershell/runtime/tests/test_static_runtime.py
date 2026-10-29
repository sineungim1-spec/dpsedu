from pathlib import Path
import ast

def test_inference_engine_has_no_disabled_checkpointing():
    src=(Path(__file__).parents[1]/'mvhd_ad/runners/anomalib_runner.py').read_text(encoding='utf-8')
    tree=ast.parse(src)
    bad=[];visualizer_false=False
    for n in ast.walk(tree):
        if isinstance(n,ast.Call):
            for kw in n.keywords:
                if kw.arg=='enable_checkpointing' and isinstance(kw.value,ast.Constant) and kw.value.value is False: bad.append(n.lineno)
                if kw.arg=='visualizer' and isinstance(kw.value,ast.Constant) and kw.value.value is False: visualizer_false=True
        if isinstance(n,ast.Dict):
            for k,v in zip(n.keys,n.values):
                if isinstance(k,ast.Constant) and k.value=='visualizer' and isinstance(v,ast.Constant) and v.value is False: visualizer_false=True
    assert not bad
    assert visualizer_false
