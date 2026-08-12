from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from agent_quota.providers import MANIFESTS, manifest, parse_provider_response


def encoded(document: object) -> str:
    return base64.b64encode(json.dumps(document).encode()).decode()


def encoded_raw(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_sanitized_recordings_match_parser_contract_and_digest() -> None:
    fixture_root = Path(__file__).parent / "fixtures/providers"
    recordings = [json.loads(path.read_text()) for path in sorted(fixture_root.glob("*.json"))]
    assert {item["provider_id"] for item in recordings} == {
        "deepseek",
        "glm-cn",
        "kimi-code",
        "kimi-cn",
        "minimax-cn",
    }
    assert {item["provider_id"] for item in recordings if item["live_verified"]} == {
        "deepseek",
        "glm-cn",
        "kimi-code",
        "minimax-cn",
    }
    for recording in recordings:
        response = recording["response"]
        canonical = json.dumps(response, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        assert hashlib.sha256(canonical.encode()).hexdigest() == recording["response_sha256"]
        result = parse_provider_response(recording["provider_id"], 200, encoded(response))
        assert result.ok
        assert [row["value_display"] for row in result.rows] == recording["expected_projection"]


def test_manifests_are_fixed_https_official_endpoints() -> None:
    assert len(MANIFESTS) == 11
    assert all(item.endpoint.startswith("https://") for item in MANIFESTS.values())
    assert all("example" not in item.endpoint for item in MANIFESTS.values())
    with pytest.raises(ValueError, match="unsupported"):
        manifest("attacker-controlled")


def test_deep_json_nesting_fails_closed_before_json_parser_recursion() -> None:
    deeply_nested = b"[" * 1_000 + b"0" + b"]" * 1_000
    result = parse_provider_response("deepseek", 200, encoded_raw(deeply_nested))
    assert not result.ok
    assert result.safe_error_code == "contract-error"


def test_json_nesting_scan_ignores_brackets_inside_escaped_strings() -> None:
    result = parse_provider_response(
        "deepseek",
        200,
        encoded(
            {
                "is_available": True,
                "metadata": '[{}]\\"',
                "balance_infos": [{"currency": "CNY", "total_balance": "1"}],
            }
        ),
    )
    assert result.ok
    assert result.rows[0]["value_display"] == "CNY 1 可用"


def test_deepseek_balance_projection() -> None:
    result = parse_provider_response(
        "deepseek",
        200,
        encoded(
            {
                "is_available": True,
                "balance_infos": [
                    {
                        "currency": "CNY",
                        "total_balance": "110.00",
                        "granted_balance": "10.00",
                        "topped_up_balance": "100.00",
                    }
                ],
            }
        ),
    )
    assert result.ok
    assert result.rows[0]["value_display"] == "CNY 110 可用"


@pytest.mark.parametrize(
    "amount",
    ["1e-129", "1e-20000000", "-1e-20000000", "1e20000000", "-1e20000000"],
)
def test_decimal_exponent_is_rejected_before_fixed_point_expansion(amount: str) -> None:
    result = parse_provider_response(
        "deepseek",
        200,
        encoded(
            {
                "is_available": True,
                "balance_infos": [{"currency": "CNY", "total_balance": amount}],
            }
        ),
    )
    assert not result.ok
    assert result.safe_error_code == "contract-error"


@pytest.mark.parametrize("amount", ["0e20000000", "-0e20000000", "0e-20000000"])
def test_zero_with_huge_exponent_is_normalized_without_context_overflow(amount: str) -> None:
    result = parse_provider_response(
        "deepseek",
        200,
        encoded(
            {
                "is_available": True,
                "balance_infos": [{"currency": "CNY", "total_balance": amount}],
            }
        ),
    )
    assert result.ok
    assert result.rows[0]["value_display"] == "CNY 0 可用"


@pytest.mark.parametrize(
    ("provider", "document"),
    [
        (
            "deepseek",
            {
                "is_available": True,
                "balance_infos": [{"currency": "CNY", "total_balance": "1e20000000"}],
            },
        ),
        ("kimi-cn", {"code": 0, "data": {"available_balance": "1e20000000"}}),
        (
            "bailian-wallet",
            {
                "Code": "200",
                "Success": True,
                "Data": {"Currency": "CNY", "AvailableAmount": "1e20000000"},
            },
        ),
        ("volc-wallet", {"Result": {"AvailableBalance": "1e20000000"}}),
        ("kimi-code", {"usage": {"remaining": 1, "limit": "1e20000000"}, "limits": []}),
        (
            "minimax-cn",
            {
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "model_name": "general",
                        "current_interval_remaining_percent": "1e20000000",
                        "current_weekly_status": 3,
                    }
                ],
            },
        ),
        ("glm-cn", {"data": {"limits": [{"type": "TOKENS_LIMIT", "percentage": "1e20000000"}]}}),
        (
            "volc-plan",
            {
                "Result": {
                    "AFPFiveHour": {"Used": 0, "Quota": "1e20000000"},
                    "AFPWeekly": {"Used": 0, "Quota": 1},
                }
            },
        ),
    ],
)
def test_all_numeric_provider_paths_fail_closed_on_huge_exponent(
    provider: str, document: object
) -> None:
    result = parse_provider_response(provider, 200, encoded(document))
    assert not result.ok
    assert result.safe_error_code == "contract-error"


def test_volcengine_wallet_projection() -> None:
    result = parse_provider_response(
        "volc-wallet",
        200,
        encoded(
            {
                "Result": {
                    "AccountID": 210000001,
                    "AvailableBalance": "77.01",
                    "CashBalance": "83.01",
                    "CreditLimit": "0.01",
                    "FreezeAmount": "5.01",
                    "ArrearsBalance": "1.01",
                }
            }
        ),
    )
    assert result.ok
    assert [row["value_display"] for row in result.rows] == [
        "CNY 77.01 可用余额",
        "CNY 83.01 现金余额",
        "CNY 0.01 信控额度",
        "CNY 5.01 冻结金额",
        "CNY 1.01 欠费金额",
    ]


def test_bailian_wallet_projection() -> None:
    result = parse_provider_response(
        "bailian-wallet",
        200,
        encoded(
            {
                "Code": "200",
                "Success": True,
                "Data": {
                    "AvailableAmount": "10000.00",
                    "AvailableCashAmount": "9000.00",
                    "CreditAmount": "1000.00",
                    "MybankCreditAmount": "0.00",
                    "Currency": "CNY",
                },
            }
        ),
    )
    assert result.ok
    assert [row["value_display"] for row in result.rows] == [
        "CNY 10000 可用额度",
        "CNY 9000 现金余额",
        "CNY 1000 信控额度",
        "CNY 0 网商银行额度",
    ]


def test_volcengine_plan_projection() -> None:
    result = parse_provider_response(
        "volc-plan",
        200,
        encoded(
            {
                "Result": {
                    "PlanType": "AFP",
                    "AFPFiveHour": {"Quota": 1000, "Used": 250, "ResetTime": 1},
                    "AFPWeekly": {"Quota": 8000, "Used": 2000, "ResetTime": 2},
                }
            }
        ),
    )
    assert result.ok
    assert [row["value_display"] for row in result.rows] == ["5小时剩余 75%", "周剩余 75%"]


@pytest.mark.parametrize(
    "provider,document",
    [
        ("volc-wallet", {"Result": {"AvailableBalance": "1"}}),
        ("volc-plan", {"Result": {"AFPFiveHour": {}, "AFPWeekly": {}}}),
        (
            "volc-plan",
            {
                "Result": {
                    "AFPFiveHour": {"Quota": 0, "Used": 0},
                    "AFPWeekly": {"Quota": 1, "Used": 0},
                }
            },
        ),
    ],
)
def test_volcengine_contract_mismatch_fails_closed(provider: str, document: object) -> None:
    result = parse_provider_response(provider, 200, encoded(document))
    assert not result.ok
    assert result.safe_error_code == "contract-error"


@pytest.mark.parametrize("provider", ["kimi-cn", "kimi-global"])
def test_kimi_balance_projection(provider: str) -> None:
    result = parse_provider_response(
        provider,
        200,
        encoded(
            {
                "code": 0,
                "status": True,
                "data": {
                    "available_balance": 12.5,
                    "cash_balance": -1,
                    "voucher_balance": 13.5,
                },
            }
        ),
    )
    assert result.ok
    assert len(result.rows) == 3
    assert "12.5" in result.rows[0]["value_display"]


def test_kimi_code_token_plan_projection() -> None:
    result = parse_provider_response(
        "kimi-code",
        200,
        encoded(
            {
                "usage": {"used": "400", "limit": "1000", "resetTime": "2026-08-03T05:20:51Z"},
                "limits": [
                    {
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {
                            "used": "25",
                            "limit": "100",
                            "resetTime": "2026-08-01T10:00:00Z",
                        },
                    }
                ],
                "boosterWallet": {
                    "balance": {
                        "type": "BOOSTER",
                        "amount": "20000000000",
                        "amountLeft": "12500000000",
                    }
                },
            }
        ),
    )
    assert result.ok
    assert [row["value_display"] for row in result.rows] == [
        "周剩余 60%",
        "5小时剩余 75%",
        "Extra Usage USD 125 / 200",
    ]


def test_kimi_code_named_window_without_weekly_summary_fails_closed() -> None:
    result = parse_provider_response(
        "kimi-code",
        200,
        encoded(
            {
                "limits": [
                    {
                        "name": "短窗口",
                        "window": {"duration": "1", "timeUnit": "TIME_UNIT_DAY"},
                        "detail": {"used": "12", "limit": "10"},
                    }
                ]
            }
        ),
    )
    assert not result.ok
    assert result.safe_error_code == "contract-error"


@pytest.mark.parametrize("remaining", [-0.0, "-0", "-0.0"])
def test_kimi_code_normalizes_signed_zero_as_depleted(remaining: object) -> None:
    result = parse_provider_response(
        "kimi-code",
        200,
        encoded(
            {
                "usage": {"remaining": remaining, "limit": 100},
                "limits": [
                    {
                        "window": {"duration": 5, "timeUnit": "TIME_UNIT_HOUR"},
                        "detail": {"remaining": 100, "limit": 100},
                    }
                ],
            }
        ),
    )
    assert result.ok
    assert result.rows[0]["value_display"] == "周剩余 0%"


def test_kimi_code_missing_five_hour_usage_fails_closed() -> None:
    result = parse_provider_response(
        "kimi-code",
        200,
        encoded({"usage": {"remaining": 100, "limit": 100}, "limits": []}),
    )
    assert not result.ok
    assert result.safe_error_code == "contract-error"


@pytest.mark.parametrize(
    "document",
    [
        {"limits": "bad"},
        {"usage": {"used": 1, "remaining": 9, "limit": 10}, "limits": []},
        {"usage": {"remaining": 11, "limit": 10}, "limits": []},
        {"limits": ["bad"]},
        {"limits": [{"window": {}, "detail": "bad"}]},
        {
            "limits": [
                {
                    "window": {"duration": 0, "timeUnit": "TIME_UNIT_HOUR"},
                    "detail": {"used": 1, "limit": 10},
                }
            ]
        },
        {
            "limits": [
                {
                    "name": "",
                    "window": {"duration": 1, "timeUnit": "TIME_UNIT_HOUR"},
                    "detail": {"used": 1, "limit": 10},
                }
            ]
        },
        {"limits": [], "boosterWallet": "bad"},
        {"limits": [], "boosterWallet": {"balance": {"type": "OTHER"}}},
        {
            "limits": [],
            "boosterWallet": {"balance": {"type": "BOOSTER", "amount": 0, "amountLeft": 0}},
        },
    ],
)
def test_kimi_code_malformed_shapes_fail_closed(document: object) -> None:
    result = parse_provider_response("kimi-code", 200, encoded(document))
    assert result.safe_error_code == "contract-error"


def test_kimi_code_missing_weekly_usage_fails_closed() -> None:
    result = parse_provider_response(
        "kimi-code",
        200,
        encoded(
            {
                "limits": [
                    {
                        "name": "general",
                        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {"limit": 100, "remaining": 100},
                    }
                ]
            }
        ),
    )
    assert not result.ok
    assert result.safe_error_code == "contract-error"


@pytest.mark.parametrize("provider", ["minimax-cn", "minimax-global"])
def test_minimax_token_plan_projection(provider: str) -> None:
    result = parse_provider_response(
        provider,
        200,
        encoded(
            {
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "model_name": "MiniMax-M2.7",
                        "current_interval_total_count": 100,
                        "current_interval_usage_count": 20,
                        "current_weekly_total_count": 1000,
                        "current_weekly_usage_count": 300,
                        "current_weekly_status": 1,
                    }
                ],
            }
        ),
    )
    assert result.ok
    assert [row["value_display"] for row in result.rows] == [
        "MiniMax-M2.7 · 5小时剩余 80%",
        "MiniMax-M2.7 · 周剩余 70%",
    ]


def test_minimax_normalizes_signed_zero_as_depleted() -> None:
    result = parse_provider_response(
        "minimax-cn",
        200,
        encoded(
            {
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "model_name": "general",
                        "current_interval_remaining_percent": "-0",
                        "current_weekly_status": 3,
                    }
                ],
            }
        ),
    )
    assert result.ok
    assert result.rows[0]["value_display"] == "general · 5小时剩余 0%"


@pytest.mark.parametrize("provider", ["glm-cn", "glm-global"])
def test_glm_official_usage_projection(provider: str) -> None:
    result = parse_provider_response(
        provider,
        200,
        encoded(
            {
                "data": {
                    "limits": [
                        {"type": "TOKENS_LIMIT", "percentage": 17},
                        {"type": "TIME_LIMIT", "percentage": 2},
                    ]
                }
            }
        ),
    )
    assert result.ok
    assert len(result.rows) == 2


@pytest.mark.parametrize("provider", ["glm-cn", "glm-global"])
def test_glm_http_200_authentication_envelope_requires_reauth(provider: str) -> None:
    result = parse_provider_response(
        provider,
        200,
        encoded({"code": 1000, "msg": "Authentication Failed", "success": False}),
    )
    assert (result.safe_error_code, result.retryable) == ("reauth-required", False)


def test_http_and_schema_errors_are_safe_and_body_bounded() -> None:
    assert parse_provider_response("deepseek", 401, "not-base64").safe_error_code == (
        "reauth-required"
    )
    assert parse_provider_response("deepseek", 429, "not-base64").retryable
    assert parse_provider_response("deepseek", 200, "not-base64").safe_error_code == (
        "contract-error"
    )
    assert parse_provider_response("deepseek", 200, "A" * 600_000).safe_error_code == (
        "contract-error"
    )


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, "provider-unavailable", False),
        (403, "reauth-required", False),
        (500, "provider-unavailable", True),
        (599, "provider-unavailable", True),
    ],
)
def test_http_error_classification(status: int, code: str, retryable: bool) -> None:
    result = parse_provider_response("deepseek", status, "ignored")
    assert (result.safe_error_code, result.retryable) == (code, retryable)


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"is_available": "yes", "balance_infos": []},
        {"is_available": True, "balance_infos": ["bad"]},
        {
            "is_available": True,
            "balance_infos": [{"currency": "TOO-LONG-CURRENCY", "total_balance": "1"}],
        },
        {
            "is_available": True,
            "balance_infos": [{"currency": "CNY", "total_balance": "NaN"}],
        },
        {
            "is_available": True,
            "balance_infos": [{"currency": "CNY", "total_balance": True}],
        },
    ],
)
def test_deepseek_malformed_shapes_fail_closed(document: object) -> None:
    assert parse_provider_response("deepseek", 200, encoded(document)).safe_error_code == (
        "contract-error"
    )


def test_deepseek_unavailable_marks_row_error() -> None:
    result = parse_provider_response(
        "deepseek",
        200,
        encoded(
            {
                "is_available": False,
                "balance_infos": [{"currency": "USD", "total_balance": "0"}],
            }
        ),
    )
    assert result.rows[0]["health"] == "error"


@pytest.mark.parametrize(
    ("provider", "document"),
    [
        ("kimi-cn", {"code": 1, "data": {}}),
        ("kimi-global", {"code": 0, "data": "bad"}),
        ("kimi-code", {"usage": {}, "limits": []}),
        ("minimax-cn", {"base_resp": {"status_code": 1}, "model_remains": []}),
        (
            "minimax-global",
            {"base_resp": {"status_code": 0}, "model_remains": [{"model_name": ""}]},
        ),
        ("glm-cn", {"data": {"limits": []}}),
        ("glm-global", {"data": {"limits": [{"type": "UNKNOWN", "percentage": 1}]}}),
    ],
)
def test_provider_specific_malformed_shapes_fail_closed(provider: str, document: object) -> None:
    assert parse_provider_response(provider, 200, encoded(document)).safe_error_code == (
        "contract-error"
    )


def test_minimax_server_percentages_and_unlimited_week() -> None:
    result = parse_provider_response(
        "minimax-global",
        200,
        encoded(
            {
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "model_name": "M2.7",
                        "current_interval_remaining_percent": 33.3,
                        "current_weekly_status": 3,
                    }
                ],
            }
        ),
    )
    assert result.ok
    assert "33.3%" in result.rows[0]["value_display"]
    assert "不限量" in result.rows[1]["value_display"]


def test_percentage_out_of_range_and_nonfinite_fail_closed() -> None:
    for value in (-1, 101, "Infinity"):
        result = parse_provider_response(
            "glm-cn",
            200,
            encoded({"data": {"limits": [{"type": "TOKENS_LIMIT", "percentage": value}]}}),
        )
        assert result.safe_error_code == "contract-error"


def test_invalid_base64_json_scalar_and_unknown_provider_fail_closed() -> None:
    assert parse_provider_response("deepseek", 200, encoded([])).safe_error_code == "contract-error"
    with pytest.raises(ValueError, match="unsupported"):
        parse_provider_response("unknown", 200, encoded({}))
