"""Canonical content-address contract tests for immutable P4 bundles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.ik_bundle_contract import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
    IkBundleContractError,
    build_ik_bundle_contract,
    ik_bundle_address_sha256,
)
from autospine_workbench.ik_probe_report import build_ik_probe_report  # noqa: E402
from tests.test_ik_probe_report import profile_fixture  # noqa: E402


def payload():
    profile = profile_fixture()
    probes = build_ik_probe_report(profile).document
    return profile["project_id"], profile, probes


def reverse_keys(value):
    if isinstance(value, dict):
        return {
            key: reverse_keys(item)
            for key, item in reversed(list(value.items()))
        }
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class IkBundleContractTests(unittest.TestCase):
    def test_contract_is_canonical_deterministic_frozen_and_cross_bound(self):
        values = payload()
        first = build_ik_bundle_contract(*values)
        second = build_ik_bundle_contract(*tuple(reverse_keys(item) if index else item
                                                  for index, item in enumerate(values)))
        self.assertEqual(first, second)
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual({"profile.json", "probes.json"}, set(first.document_bytes))
        self.assertEqual(values[1], json.loads(first.document_bytes["profile.json"]))
        self.assertEqual(values[2], json.loads(first.document_bytes["probes.json"]))
        for data in first.document_bytes.values():
            self.assertNotIn(b"\n", data)
        self.assertEqual(
            values[2]["source"]["profile_sha256"], first.profile_sha256
        )
        self.assertEqual(
            ik_bundle_address_sha256(
                first.project_id, first.profile_sha256, first.probes_sha256,
                values[1]["source"],
            ),
            first.bundle_sha256,
        )
        changed = first.document_bytes
        changed.clear()
        self.assertEqual(2, len(first.document_bytes))
        with self.assertRaises(FrozenInstanceError):
            first.bundle_sha256 = "0" * 64  # type: ignore[misc]

    def test_address_is_domain_project_documents_and_p3_identity_separated(self):
        contract = build_ik_bundle_contract(*payload())
        source = payload()[1]["source"]
        baseline = ik_bundle_address_sha256(
            contract.project_id, contract.profile_sha256,
            contract.probes_sha256, source,
        )
        cases = []
        changed_source = dict(source)
        changed_source["base_rig_sha256"] = "a" * 64
        cases.append(("sample-other", contract.profile_sha256, contract.probes_sha256, source))
        cases.append((contract.project_id, "a" * 64, contract.probes_sha256, source))
        cases.append((contract.project_id, contract.profile_sha256, "a" * 64, source))
        cases.append((contract.project_id, contract.profile_sha256, contract.probes_sha256, changed_source))
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(baseline, ik_bundle_address_sha256(*values))
        with patch(
            "autospine_workbench.ik_bundle_contract.BUNDLE_ADDRESS_DOMAIN",
            BUNDLE_ADDRESS_DOMAIN + "/changed",
        ):
            self.assertNotEqual(baseline, ik_bundle_address_sha256(
                contract.project_id, contract.profile_sha256,
                contract.probes_sha256, source,
            ))

    def test_project_p3_profile_and_probe_drift_fail_closed(self):
        baseline = payload()
        cases = []
        cases.append(("other", baseline[1], baseline[2]))
        profile_identity = deepcopy(baseline)
        profile_identity[1]["source"]["base_bundle_sha256"] = "a" * 64
        cases.append(tuple(profile_identity))
        probe_identity = deepcopy(baseline)
        probe_identity[2]["source"]["base_bundle_sha256"] = "a" * 64
        cases.append(tuple(probe_identity))
        profile_sha = deepcopy(baseline)
        profile_sha[2]["source"]["profile_sha256"] = "a" * 64
        cases.append(tuple(profile_sha))
        probe_body = deepcopy(baseline)
        probe_body[2]["handles"][0]["cases"].reverse()
        cases.append(tuple(probe_body))
        for values in cases:
            with self.subTest(values=values[0]), self.assertRaises(IkBundleContractError):
                build_ik_bundle_contract(*values)

    def test_nonfinite_unknown_and_resource_overflow_fail_closed(self):
        values = payload()
        nonfinite = deepcopy(values)
        nonfinite[1]["handles"][0]["root_xy"][0] = math.nan
        extra = deepcopy(values)
        extra[2]["unexpected"] = True
        for changed in (nonfinite, extra):
            with self.assertRaises(IkBundleContractError):
                build_ik_bundle_contract(*changed)
        with patch("autospine_workbench.ik_bundle_contract.MAX_DOCUMENT_BYTES", 1):
            with self.assertRaisesRegex(IkBundleContractError, "resource limit"):
                build_ik_bundle_contract(*values)
        with patch("autospine_workbench.ik_bundle_contract.MAX_TOTAL_DOCUMENT_BYTES", 1):
            with self.assertRaisesRegex(IkBundleContractError, "resource limit"):
                build_ik_bundle_contract(*values)

    def test_unsafe_address_inputs_are_rejected(self):
        source = payload()[1]["source"]
        cases = (
            ("../escape", "1" * 64, "2" * 64, source),
            ("sample", "latest", "2" * 64, source),
            ("sample", "1" * 64, "LATEST", source),
            ("sample", "1" * 64, "2" * 64, {**source, "extra": "3" * 64}),
        )
        for values in cases:
            with self.subTest(values=values[:3]), self.assertRaises(IkBundleContractError):
                ik_bundle_address_sha256(*values)


if __name__ == "__main__":
    unittest.main()
