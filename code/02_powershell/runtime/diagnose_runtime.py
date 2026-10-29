from __future__ import annotations
import sys,platform,ast
from pathlib import Path

def _scan_runner(path:Path):
    src=path.read_text(encoding='utf-8'); tree=ast.parse(src)
    bad=False; visualizer_false=False
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            for kw in node.keywords:
                if kw.arg=='enable_checkpointing' and isinstance(kw.value,ast.Constant) and kw.value.value is False:
                    bad=True
                if kw.arg=='visualizer' and isinstance(kw.value,ast.Constant) and kw.value.value is False:
                    visualizer_false=True
        if isinstance(node,ast.Dict):
            for k,v in zip(node.keys,node.values):
                if isinstance(k,ast.Constant) and k.value=='visualizer' and isinstance(v,ast.Constant) and v.value is False:
                    visualizer_false=True
    return bad,visualizer_false

def main():
    print('='*60);print('AI Vision company_runtime V6.4 ProductionFix - Diagnostic');print('='*60)
    print('Python:',sys.version.replace('\n',' '));print('OS:',platform.platform())
    for name in ['numpy','cv2','PIL','torch','lightning','anomalib','sklearn']:
        try:
            m=__import__(name);print(f'{name:10s}: OK  {getattr(m,"__version__","")}')
        except Exception as e: print(f'{name:10s}: MISSING/ERROR  {e}')
    from mvhd_ad import RUNTIME_VERSION;print('runtime   :',RUNTIME_VERSION)
    bad,vis=_scan_runner(Path(__file__).parent/'mvhd_ad/runners/anomalib_runner.py')
    print('EfficientAd visualizer=False:',vis)
    print('forbidden inference Engine(enable_checkpointing=False):',bad)
    if bad or not vis: raise SystemExit('STATIC CHECK FAIL')
    print('DIAGNOSTIC STATIC PASS')
if __name__=='__main__':main()
