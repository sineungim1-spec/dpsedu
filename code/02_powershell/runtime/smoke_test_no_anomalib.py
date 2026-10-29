"""Offline smoke test for code paths that do not require Anomalib/GPU."""
from pathlib import Path
import tempfile,cv2,numpy as np
from mvhd_ad import DatasetSpec
from mvhd_ad.protocol import build_protocol
from mvhd_ad.preprocess import build_preprocess_profile,prepare_standardized_dataset,_decode_profile

def main():
    with tempfile.TemporaryDirectory(prefix='v64_smoke_') as td:
        root=Path(td)/'data';(root/'good').mkdir(parents=True);(root/'bad').mkdir()
        def mk(bad=False):
            a=np.full((128,192,3),255,np.uint8);cv2.rectangle(a,(30,35),(162,93),(42,48,58),-1);cv2.rectangle(a,(70,50),(125,78),(255,255,255),-1)
            if bad:cv2.circle(a,(150,52),5,(0,0,0),-1)
            return a
        for i in range(20):cv2.imwrite(str(root/'good'/f'good_{i:03}.png'),mk())
        for i in range(8):cv2.imwrite(str(root/'bad'/f'bad_{i:03}.png'),mk(True))
        protocol=build_protocol(DatasetSpec(root),42);run=Path(td)/'run';run.mkdir();pp=run/'preprocess_profile_v6.json';build_preprocess_profile(protocol,pp);protocol=prepare_standardized_dataset(protocol,pp,run);g=_decode_profile(pp)['groups']['GENERIC']
        assert g['count']==protocol['counts']['train_good'] and g['count']>0
        assert g['master_mask'].mean()>g['surface_mask'].mean()
        assert protocol['leakage_check']['capture_group_leakage_count']==0
        print('V6.4 offline smoke PASS')
        print('counts:',protocol['counts'])
        print('profile count:',g['count'],'surface:',float(g['surface_mask'].mean()),'inspection:',float(g['master_mask'].mean()))
if __name__=='__main__':main()
