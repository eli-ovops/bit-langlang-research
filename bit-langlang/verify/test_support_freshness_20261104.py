import unittest
from verify.market_support_freshness_20261104 import gate
from verify.market_support_directional_20261104 import classify

class FreshnessTest(unittest.TestCase):
    def test_distance_and_age_boundaries(self):
        x=gate('PRIOR_UNBROKEN_ABOVE',90,100,'2025-01-01T00:00:00Z','2025-01-29T00:00:00Z')
        self.assertEqual((x['D10'],x['A28'],x['BOTH']),('PRIOR_UNBROKEN_ABOVE',)*3)
        y=gate('PRIOR_UNBROKEN_ABOVE',89.99,100,'2025-01-01T00:00:00Z','2025-01-29T00:00:01Z')
        self.assertEqual((y['D10'],y['A28'],y['BOTH']),('UNKNOWN_FAR','UNKNOWN_OLD','UNKNOWN_FAR_OLD'))
    def test_broken_sign_and_missing(self):
        x=gate('PRIOR_BROKEN_BELOW',120,100,'2025-01-01T00:00:00Z','2025-01-10T00:00:00Z')
        self.assertLess(x['signed_distance'],0);self.assertEqual(x['D10'],'UNKNOWN_FAR')
        for level,known in ((None,'2025-01-01T00:00:00Z'),(90,'2025-01-11T00:00:00Z')):
            self.assertEqual(gate('PRIOR_UNBROKEN_ABOVE',level,100,known,'2025-01-10T00:00:00Z')['BOTH'],'UNKNOWN_INPUT')
    def test_directional_guard_is_posthoc_and_retains_break(self):
        self.assertEqual(classify('PRIOR_BROKEN_BELOW',120,100),('PRIOR_BROKEN_BELOW','FAR_ABOVE_PRICE'))
        self.assertEqual(classify('PRIOR_UNBROKEN_ABOVE',89,100),('UNKNOWN_FAR_BELOW_PRICE','FAR_BELOW_PRICE'))
        self.assertEqual(classify('PRIOR_UNBROKEN_ABOVE',90,100),('PRIOR_UNBROKEN_ABOVE','WITHIN_10PCT'))
        self.assertEqual(classify('PRIOR_BROKEN_BELOW',90,100)[0],'UNKNOWN_INCONSISTENT')

if __name__=='__main__':unittest.main()
