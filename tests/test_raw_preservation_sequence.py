import unittest
from unittest.mock import patch
from m4_raw_preservation_sequence import inspect


class SequenceTests(unittest.TestCase):
    def test_midpoint_failure_is_not_hidden_by_successful_keys(self):
        raw={'kind':'raw'};result={'kind':'result'}
        def sample(doc,name,time):
            height=.4 if doc is raw or time in (0,1) else .3
            return {'arm':[[0,0],[1,0],[0,height]]},{}
        with patch('m4_raw_preservation_sequence.sample',side_effect=sample):
            times,failures=inspect(raw,result,'motion','arm',[0,1],[[0,1,2]],[.5])
        self.assertEqual(times,[0,.5,1])
        self.assertEqual(len(failures),1)
        self.assertFalse(failures[0]['at_key'])
        self.assertEqual(failures[0]['time'],.5)
        self.assertAlmostEqual(failures[0]['before'],.4)
        self.assertAlmostEqual(failures[0]['after'],.3)

    def test_key_failure_remains_explicit(self):
        raw={};result={}
        def sample(doc,name,time):
            return {'arm':[[0,0],[1,0],[0,.4 if doc is raw else .3]]},{}
        with patch('m4_raw_preservation_sequence.sample',side_effect=sample):
            _,failures=inspect(raw,result,'motion','arm',[0,1],[[0,1,2]],[.5])
        self.assertEqual(sum(r['at_key'] for r in failures),2)
