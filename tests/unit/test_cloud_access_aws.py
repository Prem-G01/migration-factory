"""Tests for cloud_access.aws (STS cross-account role assumption).

Uses moto to mock AWS entirely -- no real AWS account or credentials
needed to exercise the assume-role flow end to end.
"""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from migration_factory.cloud_access.aws import (
    generate_external_id,
    generate_setup_instructions,
    generate_trust_policy,
    platform_identity_arn,
    verify_role_access,
)


def test_generate_external_id_is_long_and_random() -> None:
    a = generate_external_id()
    b = generate_external_id()
    assert len(a) >= 24
    assert a != b


def test_generate_trust_policy_shape() -> None:
    policy = json.loads(generate_trust_policy("arn:aws:iam::123456789012:user/platform", "ext-123"))
    statement = policy["Statement"][0]
    assert statement["Principal"]["AWS"] == "arn:aws:iam::123456789012:user/platform"
    assert statement["Condition"]["StringEquals"]["sts:ExternalId"] == "ext-123"
    assert statement["Action"] == "sts:AssumeRole"


def test_generate_setup_instructions_includes_role_name_and_policy() -> None:
    instructions = generate_setup_instructions("mf-role", "arn:aws:iam::123456789012:user/platform", "ext-123")
    assert "mf-role" in instructions
    assert "ext-123" in instructions
    assert "sts:AssumeRole" in instructions


def test_platform_identity_arn_none_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", raising=False)
    assert platform_identity_arn() is None


def test_verify_role_access_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", raising=False)
    ok, message = verify_role_access("arn:aws:iam::123456789012:role/some-role", "ext-123")
    assert ok is False
    assert "MF_AWS_PLATFORM" in message


@mock_aws
def test_platform_identity_arn_with_moto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", "testing")
    arn = platform_identity_arn()
    assert arn is not None
    assert "arn:aws:" in arn


@mock_aws
def test_verify_role_access_succeeds_against_a_real_trust_relationship(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", "testing")

    external_id = generate_external_id()
    platform_arn = platform_identity_arn()
    assert platform_arn is not None

    iam = boto3.client("iam", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    role = iam.create_role(
        RoleName="test-role",
        AssumeRolePolicyDocument=generate_trust_policy(platform_arn, external_id),
    )
    role_arn = role["Role"]["Arn"]

    ok, message = verify_role_access(role_arn, external_id)
    assert ok is True
    assert "Verified access as" in message



def test_verify_role_access_surfaces_assume_role_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """moto's STS mock doesn't enforce trust-policy conditions (external_id
    mismatch) or even role existence -- it assumes any ARN regardless, so
    those specific failure modes can't be exercised through moto. Real AWS
    does enforce both; what's actually ours to test is that this module's
    error handling correctly surfaces whatever ClientError botocore raises,
    which we can simulate directly instead.
    """
    monkeypatch.setenv("MF_AWS_PLATFORM_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("MF_AWS_PLATFORM_SECRET_ACCESS_KEY", "testing")

    from botocore.exceptions import ClientError

    def _raise_access_denied(*_args: object, **_kwargs: object) -> None:
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "External ID mismatch"}}, "AssumeRole"
        )

    monkeypatch.setattr("migration_factory.cloud_access.aws.assume_role", _raise_access_denied)

    ok, message = verify_role_access("arn:aws:iam::123456789012:role/does-not-exist", "wrong-id")
    assert ok is False
    assert "External ID mismatch" in message
