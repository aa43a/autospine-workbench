from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from autospine_workbench.automation.project_route_evidence import reviewed_project
from autospine_workbench.automation.animated_inputs import AnimatedSourceError


class RegisteredRouteTests(TestCase):
    def test_current_coordinates_and_review_are_used_without_changing_original(self):
        project = {'resolved': {'skeleton': {'joints': [
            {'id': 'wrist.left', 'x': 1, 'y': 2, 'review_state': 'unreviewed'}]}}}
        original = deepcopy(project)
        review = dict(input_identity_sha256='current', reviewed_joint_ids=['wrist.left'],
            records=[dict(joint_id='wrist.left', status='observed', position=[20, 30]),
                     dict(joint_id='elbow.left', status='observed', position=[10, 15])])
        with patch('autospine_workbench.automation.animated_joint_review.get_joint_review', return_value=review):
            result, identity = reviewed_project(None, 'p', project)
        self.assertEqual(project, original)
        self.assertEqual(identity, 'current')
        joints = {j['id']: j for j in result['resolved']['skeleton']['joints']}
        self.assertEqual(joints['wrist.left']['x'], 20)
        self.assertEqual(joints['wrist.left']['review_state'], 'reviewed')
        self.assertEqual(joints['elbow.left']['review_state'], 'unreviewed')

    def test_unobservable_does_not_reuse_old_coordinates(self):
        project = {'resolved': {'skeleton': {'joints': [{'id': 'wrist.left', 'x': 1, 'y': 2}]}}}
        review = dict(input_identity_sha256='current', reviewed_joint_ids=['wrist.left'],
            records=[dict(joint_id='wrist.left', status='unobservable', position=None)])
        with patch('autospine_workbench.automation.animated_joint_review.get_joint_review', return_value=review):
            result, _ = reviewed_project(None, 'p', project)
        self.assertIsNone(result['resolved']['skeleton']['joints'][0]['x'])

    def test_unavailable_registration_keeps_original_evidence(self):
        project = {'resolved': {}}
        with patch('autospine_workbench.automation.animated_joint_review.get_joint_review',
                   side_effect=AnimatedSourceError('animated_source_stale')):
            result, identity = reviewed_project(None, 'p', project)
        self.assertIs(result, project)
        self.assertIsNone(identity)
