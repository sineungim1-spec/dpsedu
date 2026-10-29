from mvhd_ad.fusion_policy import _classify


def test_score_ng_is_never_downgraded():
    p={'ok_cut':0.2,'ng_cut':0.7,'safety_review_floor':0.18,
       'safety_fail_safe_enabled':True,'safety_requires_visible_agreement':True}
    for visible in (False,True):
        for safety in (False,True):
            assert _classify(0.8,visible,safety,p)[0]=='NG'


def test_localization_never_promotes_review_to_ng():
    p={'ok_cut':0.2,'ng_cut':0.7,'safety_review_floor':0.18,
       'safety_fail_safe_enabled':True,'safety_requires_visible_agreement':True}
    assert _classify(0.4,True,True,p)[0]=='REVIEW'


def test_safety_can_only_hold_borderline_ok_with_dual_evidence():
    p={'ok_cut':0.2,'ng_cut':0.7,'safety_review_floor':0.18,
       'safety_fail_safe_enabled':True,'safety_requires_visible_agreement':True}
    assert _classify(0.19,True,True,p)[0]=='REVIEW'
    assert _classify(0.19,False,True,p)[0]=='OK'
    assert _classify(0.10,True,True,p)[0]=='OK'
