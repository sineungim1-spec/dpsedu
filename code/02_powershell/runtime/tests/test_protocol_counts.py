from pathlib import Path
from mvhd_ad import DatasetSpec
from mvhd_ad.protocol import build_protocol

def test_reference_517_counts(tmp_path):
    (tmp_path/'good').mkdir();(tmp_path/'bad').mkdir()
    for i in range(389):(tmp_path/'good'/f'good_{i+1:05}.jpg').touch()
    for i in range(128):(tmp_path/'bad'/f'bad_{i+1:05}.jpg').touch()
    p=build_protocol(DatasetSpec(tmp_path),42)
    assert p['counts']=={'train_good':292,'train_bad':0,'calibration_good':49,'calibration_bad':64,'final_test_good':48,'final_test_bad':64}
    assert p['leakage_check']['capture_group_leakage_count']==0
