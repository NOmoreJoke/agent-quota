"""Official provider manifests and fail-closed response projection."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

MAX_PROVIDER_BODY_BYTES: Final = 256 * 1024
PROVIDER_IDS: Final = frozenset(
    {
        "deepseek",
        "bailian-wallet",
        "glm-cn",
        "glm-global",
        "kimi-cn",
        "kimi-code",
        "kimi-global",
        "minimax-cn",
        "minimax-global",
        "volc-plan",
        "volc-wallet",
    }
)


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    display_name: str
    credential_type: str
    endpoint: str
    authorization: str
    evidence_url: str


@dataclass(frozen=True)
class ProviderResult:
    rows: tuple[dict[str, str], ...]
    safe_error_code: str | None = None
    retryable: bool = False

    @property
    def ok(self) -> bool:
        return self.safe_error_code is None


MANIFESTS: Final = {
    "bailian-wallet": ProviderManifest(
        "bailian-wallet",
        "阿里云账户余额 (百炼)",
        "access-key-id+secret-key",
        "https://business.aliyuncs.com/?Action=QueryAccountBalance&Version=2017-12-14",
        "aliyun-rpc-hmac-sha1",
        "https://help.aliyun.com/zh/user-center/developer-reference/api-bssopenapi-2017-12-14-queryaccountbalance",
    ),
    "deepseek": ProviderManifest(
        "deepseek",
        "DeepSeek",
        "api-key",
        "https://api.deepseek.com/user/balance",
        "bearer",
        "https://api-docs.deepseek.com/api/get-user-balance/",
    ),
    "kimi-cn": ProviderManifest(
        "kimi-cn",
        "Kimi (中国区)",
        "api-key-cn",
        "https://api.moonshot.cn/v1/users/me/balance",
        "bearer",
        "https://platform.kimi.com/docs/api/balance",
    ),
    "kimi-global": ProviderManifest(
        "kimi-global",
        "Kimi (国际区)",
        "api-key-global",
        "https://api.moonshot.ai/v1/users/me/balance",
        "bearer",
        "https://platform.kimi.ai/docs/api/overview",
    ),
    "kimi-code": ProviderManifest(
        "kimi-code",
        "Kimi Code Token Plan",
        "oauth-device-code",
        "https://api.kimi.com/coding/v1/usages",
        "oauth-bearer-refreshable",
        "https://github.com/MoonshotAI/kimi-code/blob/main/packages/oauth/src/managed-usage.ts",
    ),
    "minimax-cn": ProviderManifest(
        "minimax-cn",
        "MiniMax Token Plan (中国区)",
        "token-plan-key-cn",
        "https://www.minimaxi.com/v1/token_plan/remains",
        "bearer",
        "https://platform.minimaxi.com/docs/token-plan/faq",
    ),
    "minimax-global": ProviderManifest(
        "minimax-global",
        "MiniMax Token Plan (国际区)",
        "token-plan-key-global",
        "https://www.minimax.io/v1/token_plan/remains",
        "bearer",
        "https://platform.minimax.io/docs/token-plan/faq",
    ),
    "glm-cn": ProviderManifest(
        "glm-cn",
        "GLM Coding Plan (中国区)",
        "coding-plan-auth-token-cn",
        "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
        "raw-authorization",
        "https://docs.z.ai/devpack/extension/usage-query-plugin",
    ),
    "glm-global": ProviderManifest(
        "glm-global",
        "GLM Coding Plan (国际区)",
        "coding-plan-auth-token-global",
        "https://api.z.ai/api/monitor/usage/quota/limit",
        "raw-authorization",
        "https://docs.z.ai/devpack/extension/usage-query-plugin",
    ),
    "volc-wallet": ProviderManifest(
        "volc-wallet",
        "火山引擎账户余额",
        "access-key-id+secret-key",
        "https://open.volcengineapi.com/?Action=QueryBalanceAcct&Version=2022-01-01",
        "volc-hmac-sha256",
        "https://www.volcengine.com/docs/6269/1223898",
    ),
    "volc-plan": ProviderManifest(
        "volc-plan",
        "火山方舟 Coding Plan",
        "access-key-id+secret-key",
        "https://ark.cn-beijing.volces.com/?Action=GetAFPUsage&Version=2024-01-01",
        "volc-hmac-sha256",
        "https://api.volcengine.com/api-explorer/?action=GetAFPUsage&groupName=Agent+Plan+API&serviceCode=ark&version=2024-01-01",
    ),
}


def manifest(provider_id: str) -> ProviderManifest:
    try:
        return MANIFESTS[provider_id]
    except KeyError as error:
        raise ValueError("unsupported provider") from error


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise ValueError("invalid decimal")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("invalid decimal") from error
    if not number.is_finite() or abs(number) > Decimal("1e30"):
        raise ValueError("invalid decimal")
    return number


def _number_display(value: object) -> str:
    number = _decimal(value)
    rendered = format(number, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _percentage(value: object) -> str:
    number = _decimal(value)
    if not Decimal(0) <= number <= Decimal(100):
        raise ValueError("invalid percentage")
    if number == 0:
        number = Decimal(0)
    return f"{_number_display(number)}%"


def _row(provider_id: str, suffix: str, kind: str, value: str) -> dict[str, str]:
    if not value or len(value.encode()) > 128:
        raise ValueError("provider display value is invalid")
    return {
        "capability_ref": f"cap-{provider_id}-{suffix}",
        "display_kind": kind,
        "health": "ok",
        "value_display": value,
    }


def _decode_json(body_base64: str) -> dict[str, object]:
    if not isinstance(body_base64, str) or len(body_base64) > MAX_PROVIDER_BODY_BYTES * 2:
        raise ValueError("provider body is oversized")
    try:
        raw = base64.b64decode(body_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("provider body encoding mismatch") from error
    if not 1 <= len(raw) <= MAX_PROVIDER_BODY_BYTES:
        raise ValueError("provider body size mismatch")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("provider JSON mismatch") from error
    if not isinstance(document, dict):
        raise ValueError("provider JSON shape mismatch")
    return document


def _deepseek(document: dict[str, object]) -> tuple[dict[str, str], ...]:
    available = document.get("is_available")
    balances = document.get("balance_infos")
    if not isinstance(available, bool) or not isinstance(balances, list) or not balances:
        raise ValueError("DeepSeek response mismatch")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(balances[:16]):
        if not isinstance(item, dict):
            raise ValueError("DeepSeek balance mismatch")
        currency = item.get("currency")
        if not isinstance(currency, str) or not 1 <= len(currency) <= 8:
            raise ValueError("DeepSeek currency mismatch")
        total = _number_display(item.get("total_balance"))
        row = _row("deepseek", f"balance-{index}", "balance", f"{currency} {total} 可用")
        if not available:
            row["health"] = "error"
        rows.append(row)
    return tuple(rows)


def _kimi(document: dict[str, object], provider_id: str) -> tuple[dict[str, str], ...]:
    data = document.get("data")
    if document.get("code") != 0 or not isinstance(data, dict):
        raise ValueError("Kimi response mismatch")
    fields = (
        ("available_balance", "available", "可用余额"),
        ("cash_balance", "cash", "现金余额"),
        ("voucher_balance", "voucher", "代金券余额"),
    )
    return tuple(
        _row(provider_id, suffix, "balance", f"CNY {_number_display(data.get(field))} {label}")
        for field, suffix, label in fields
    )


def _remaining_percentage(used: object, limit: object) -> str:
    used_number = _decimal(used)
    limit_number = _decimal(limit)
    if used_number < 0 or limit_number <= 0:
        raise ValueError("invalid usage limit")
    remaining = max(
        Decimal(0), min(Decimal(100), (limit_number - used_number) * 100 / limit_number)
    )
    return _percentage(remaining)


def _usage_remaining_percentage(detail: dict[str, object]) -> str:
    limit = _decimal(detail.get("limit"))
    if limit <= 0:
        raise ValueError("invalid usage limit")
    used = detail.get("used")
    remaining = detail.get("remaining")
    if (used is None) == (remaining is None):
        raise ValueError("ambiguous usage counters")
    if remaining is not None:
        remaining_number = _decimal(remaining)
        if not Decimal(0) <= remaining_number <= limit:
            raise ValueError("invalid remaining usage")
        return _percentage(remaining_number * 100 / limit)
    return _remaining_percentage(used, limit)


def _kimi_code(document: dict[str, object]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    summary = document.get("usage")
    if isinstance(summary, dict):
        rows.append(
            _row(
                "kimi-code",
                "weekly",
                "window",
                f"周剩余 {_usage_remaining_percentage(summary)}",
            )
        )

    limits = document.get("limits")
    if not isinstance(limits, list):
        raise ValueError("Kimi Code limits mismatch")
    unit_labels = {
        "TIME_UNIT_MINUTE": "分钟",
        "TIME_UNIT_HOUR": "小时",
        "TIME_UNIT_DAY": "天",
        "TIME_UNIT_WEEK": "周",
    }
    for index, item in enumerate(limits[:16]):
        if not isinstance(item, dict):
            raise ValueError("Kimi Code limit mismatch")
        window = item.get("window")
        detail = item.get("detail")
        if not isinstance(window, dict) or not isinstance(detail, dict):
            raise ValueError("Kimi Code limit detail mismatch")
        duration = _decimal(window.get("duration"))
        unit = window.get("timeUnit")
        if duration <= 0 or duration != duration.to_integral_value() or unit not in unit_labels:
            raise ValueError("Kimi Code window mismatch")
        if unit == "TIME_UNIT_MINUTE" and duration >= 60 and duration % 60 == 0:
            duration /= 60
            unit = "TIME_UNIT_HOUR"
        name = item.get("name")
        if name is not None and (not isinstance(name, str) or not 1 <= len(name.encode()) <= 32):
            raise ValueError("Kimi Code limit name mismatch")
        label = name or f"{_number_display(duration)}{unit_labels[unit]}"
        rows.append(
            _row(
                "kimi-code",
                f"limit-{index}",
                "window",
                f"{label}剩余 {_usage_remaining_percentage(detail)}",
            )
        )

    wallet = document.get("boosterWallet")
    if wallet is not None:
        if not isinstance(wallet, dict):
            raise ValueError("Kimi Code wallet mismatch")
        balance = wallet.get("balance")
        if not isinstance(balance, dict) or balance.get("type") != "BOOSTER":
            raise ValueError("Kimi Code wallet balance mismatch")
        amount = _decimal(balance.get("amount"))
        amount_left = _decimal(balance.get("amountLeft"))
        if amount <= 0 or amount_left < 0:
            raise ValueError("Kimi Code wallet amount mismatch")
        # Official service encodes currency units as fixed-point 1e6 cents.
        total_cents = amount / Decimal(1_000_000)
        left_cents = amount_left / Decimal(1_000_000)
        left_display = _number_display(left_cents / 100)
        total_display = _number_display(total_cents / 100)
        rows.append(
            _row(
                "kimi-code",
                "extra-usage",
                "balance",
                f"Extra Usage USD {left_display} / {total_display}",
            )
        )

    if not rows:
        raise ValueError("Kimi Code usage is absent")
    return tuple(rows)


def _minimax(document: dict[str, object], provider_id: str) -> tuple[dict[str, str], ...]:
    base = document.get("base_resp")
    models = document.get("model_remains")
    if (
        not isinstance(base, dict)
        or base.get("status_code") != 0
        or not isinstance(models, list)
        or not models
    ):
        raise ValueError("MiniMax response mismatch")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(models[:32]):
        if not isinstance(item, dict):
            raise ValueError("MiniMax model mismatch")
        name = item.get("model_name")
        if not isinstance(name, str) or not 1 <= len(name.encode()) <= 48:
            raise ValueError("MiniMax model name mismatch")
        interval = item.get("current_interval_remaining_percent")
        if interval is None:
            total = _decimal(item.get("current_interval_total_count"))
            used = _decimal(item.get("current_interval_usage_count"))
            interval = Decimal(0) if total <= 0 else (total - used) * 100 / total
        rows.append(
            _row(
                provider_id,
                f"model-{index}-5h",
                "window",
                f"{name} · 5小时剩余 {_percentage(interval)}",
            )
        )
        weekly_status = item.get("current_weekly_status")
        if weekly_status == 3:
            weekly_display = "不限量"
        else:
            weekly = item.get("current_weekly_remaining_percent")
            if weekly is None:
                total = _decimal(item.get("current_weekly_total_count"))
                used = _decimal(item.get("current_weekly_usage_count"))
                weekly = Decimal(0) if total <= 0 else (total - used) * 100 / total
            weekly_display = _percentage(weekly)
        rows.append(
            _row(
                provider_id,
                f"model-{index}-weekly",
                "window",
                f"{name} · 周剩余 {weekly_display}",
            )
        )
    return tuple(rows)


def _glm(document: dict[str, object], provider_id: str) -> tuple[dict[str, str], ...]:
    data = document.get("data", document)
    if not isinstance(data, dict):
        raise ValueError("GLM response mismatch")
    limits = data.get("limits")
    if not isinstance(limits, list) or not limits:
        raise ValueError("GLM limits mismatch")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(limits[:16]):
        if not isinstance(item, dict) or item.get("type") not in {"TOKENS_LIMIT", "TIME_LIMIT"}:
            continue
        kind = str(item["type"])
        label = "5小时已用" if kind == "TOKENS_LIMIT" else "MCP月度已用"
        rows.append(
            _row(
                provider_id,
                f"limit-{index}",
                "window",
                f"{label} {_percentage(item.get('percentage'))}",
            )
        )
    if not rows:
        raise ValueError("GLM supported limits are absent")
    return tuple(rows)


def _volc_wallet(document: dict[str, object]) -> tuple[dict[str, str], ...]:
    result = document.get("Result")
    if not isinstance(result, dict):
        raise ValueError("Volcengine wallet response mismatch")
    fields = (
        ("AvailableBalance", "available", "可用余额"),
        ("CashBalance", "cash", "现金余额"),
        ("CreditLimit", "credit", "信控额度"),
        ("FreezeAmount", "frozen", "冻结金额"),
        ("ArrearsBalance", "arrears", "欠费金额"),
    )
    return tuple(
        _row("volc-wallet", suffix, "balance", f"CNY {_number_display(result.get(field))} {label}")
        for field, suffix, label in fields
    )


def _volc_plan(document: dict[str, object]) -> tuple[dict[str, str], ...]:
    result = document.get("Result")
    if not isinstance(result, dict):
        raise ValueError("Volcengine plan response mismatch")
    rows: list[dict[str, str]] = []
    for key, suffix, label in (
        ("AFPFiveHour", "5h", "5小时剩余"),
        ("AFPWeekly", "weekly", "周剩余"),
    ):
        window = result.get(key)
        if not isinstance(window, dict):
            raise ValueError("Volcengine plan window mismatch")
        rows.append(
            _row(
                "volc-plan",
                suffix,
                "window",
                f"{label} {_remaining_percentage(window.get('Used'), window.get('Quota'))}",
            )
        )
    return tuple(rows)


def _bailian_wallet(document: dict[str, object]) -> tuple[dict[str, str], ...]:
    data = document.get("Data")
    if (
        document.get("Success") is not True
        or str(document.get("Code")) != "200"
        or not isinstance(data, dict)
    ):
        raise ValueError("Alibaba Cloud wallet response mismatch")
    currency = data.get("Currency")
    if currency not in {"CNY", "USD", "JPY"}:
        raise ValueError("Alibaba Cloud currency mismatch")
    fields = (
        ("AvailableAmount", "available", "可用额度"),
        ("AvailableCashAmount", "cash", "现金余额"),
        ("CreditAmount", "credit", "信控额度"),
        ("MybankCreditAmount", "mybank", "网商银行额度"),
    )
    return tuple(
        _row(
            "bailian-wallet",
            suffix,
            "balance",
            f"{currency} {_number_display(data.get(field))} {label}",
        )
        for field, suffix, label in fields
    )


def _provider_error(document: dict[str, object], provider_id: str) -> ProviderResult | None:
    # GLM returns authentication failures as HTTP 200 JSON envelopes. Classify
    # only the observed stable machine code; unknown envelopes remain contract
    # errors instead of trusting provider-controlled prose.
    if (
        provider_id.startswith("glm-")
        and document.get("success") is False
        and document.get("code") == 1000
    ):
        return ProviderResult((), "reauth-required", False)
    return None


def parse_provider_response(
    provider_id: str,
    http_status: int,
    body_base64: str,
) -> ProviderResult:
    manifest(provider_id)
    if http_status in {401, 403}:
        return ProviderResult((), "reauth-required", False)
    if http_status == 429 or 500 <= http_status <= 599:
        return ProviderResult((), "provider-unavailable", True)
    if http_status != 200:
        return ProviderResult((), "provider-unavailable", False)
    try:
        document = _decode_json(body_base64)
        if provider_error := _provider_error(document, provider_id):
            return provider_error
        if provider_id == "bailian-wallet":
            rows = _bailian_wallet(document)
        elif provider_id == "deepseek":
            rows = _deepseek(document)
        elif provider_id == "kimi-code":
            rows = _kimi_code(document)
        elif provider_id.startswith("kimi-"):
            rows = _kimi(document, provider_id)
        elif provider_id.startswith("minimax-"):
            rows = _minimax(document, provider_id)
        elif provider_id.startswith("glm-"):
            rows = _glm(document, provider_id)
        elif provider_id == "volc-wallet":
            rows = _volc_wallet(document)
        elif provider_id == "volc-plan":
            rows = _volc_plan(document)
        else:  # pragma: no cover - manifest closes this branch
            raise ValueError("unsupported provider")
        return ProviderResult(rows)
    except ValueError:
        return ProviderResult((), "contract-error", False)
