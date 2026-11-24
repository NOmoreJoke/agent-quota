import AppKit
import CryptoKit
import Foundation
import Security
import UniformTypeIdentifiers

func selected(_ document: [String: Any], _ keys: [String]) -> [String: Any] {
    Dictionary(uniqueKeysWithValues: keys.compactMap { key in
        document[key].map { (key, $0) }
    })
}

func selectedArray(_ value: Any?, _ keys: [String], maximum: Int) -> [[String: Any]]? {
    guard let items = value as? [Any], items.count <= maximum else { return nil }
    var result: [[String: Any]] = []
    for item in items {
        guard let document = item as? [String: Any] else { return nil }
        result.append(selected(document, keys))
    }
    return result
}

func isSafeFiniteNumber(_ value: Any?) -> Bool {
    if let number = value as? NSNumber {
        return CFGetTypeID(number) != CFBooleanGetTypeID() && number.doubleValue.isFinite
    }
    if let text = value as? String, !text.isEmpty, text.utf8.count <= 64, let number = Double(text) {
        return number.isFinite
    }
    return false
}

func boundedShortString(_ value: Any?, maximumBytes: Int) -> String? {
    guard let text = value as? String, !text.isEmpty, text.utf8.count <= maximumBytes else {
        return nil
    }
    return text
}

func minimizedProviderDocument(provider: String, document: [String: Any]) -> [String: Any]? {
    if provider == "antigravity" {
        var result: [String: Any] = [:]
        if let tier = boundedShortString(document["tier"], maximumBytes: 48) {
            result["tier"] = tier
        }
        if isSafeFiniteNumber(document["aiCredits"]), let credits = document["aiCredits"] {
            result["aiCredits"] = credits
        }
        if let rawBuckets = document["buckets"] as? [Any] {
            guard rawBuckets.count <= 16 else { return nil }
            var sanitizedBuckets: [[String: Any]] = []
            for item in rawBuckets {
                guard
                    let bucket = item as? [String: Any],
                    let bucketID = boundedShortString(bucket["id"], maximumBytes: 64),
                    isSafeFiniteNumber(bucket["remainingFraction"])
                else { return nil }
                var entry: [String: Any] = [
                    "id": bucketID,
                    "remainingFraction": bucket["remainingFraction"] as Any,
                ]
                if let window = boundedShortString(bucket["window"], maximumBytes: 16) {
                    entry["window"] = window
                }
                if let resetTime = boundedShortString(bucket["resetTime"], maximumBytes: 48) {
                    entry["resetTime"] = resetTime
                }
                sanitizedBuckets.append(entry)
            }
            result["buckets"] = sanitizedBuckets
        }
        let nonEmptyBuckets = (result["buckets"] as? [[String: Any]])?.isEmpty == false
        guard nonEmptyBuckets || result["aiCredits"] != nil else { return nil }
        return result
    }
    if provider == "deepseek" {
        guard let balances = selectedArray(
            document["balance_infos"],
            ["currency", "granted_balance", "topped_up_balance", "total_balance"],
            maximum: 16
        ) else { return nil }
        var result = selected(document, ["is_available"])
        result["balance_infos"] = balances
        return result
    }
    if provider == "kimi-cn" || provider == "kimi-global" {
        guard let data = document["data"] as? [String: Any] else { return nil }
        var result = selected(document, ["code"])
        result["data"] = selected(data, ["available_balance", "cash_balance", "voucher_balance"])
        return result
    }
    if provider == "kimi-code" {
        guard
            let usage = document["usage"] as? [String: Any],
            let sourceLimits = document["limits"] as? [Any],
            sourceLimits.count <= 16
        else { return nil }
        let limits: [[String: Any]] = sourceLimits.compactMap { item in
            guard
                let limit = item as? [String: Any],
                let window = limit["window"] as? [String: Any],
                let detail = limit["detail"] as? [String: Any]
            else { return nil }
            var sanitized = selected(limit, ["name"])
            sanitized["window"] = selected(window, ["duration", "timeUnit"])
            sanitized["detail"] = selected(detail, ["limit", "used", "remaining"])
            return sanitized
        }
        guard limits.count == sourceLimits.count else { return nil }
        var result: [String: Any] = [
            "limits": limits,
            "usage": selected(usage, ["limit", "used", "remaining"]),
        ]
        if let wallet = document["boosterWallet"] as? [String: Any],
           let balance = wallet["balance"] as? [String: Any]
        {
            result["boosterWallet"] = [
                "balance": selected(balance, ["type", "amount", "amountLeft"]),
            ]
        }
        return result
    }
    if provider == "minimax-cn" || provider == "minimax-global" {
        guard
            let base = document["base_resp"] as? [String: Any],
            let models = selectedArray(
                document["model_remains"],
                [
                    "model_name", "current_interval_remaining_percent",
                    "current_interval_total_count", "current_interval_usage_count",
                    "current_weekly_remaining_percent", "current_weekly_total_count",
                    "current_weekly_usage_count", "current_weekly_status",
                ],
                maximum: 32
            )
        else { return nil }
        var result: [String: Any] = [
            "base_resp": selected(base, ["status_code"]),
            "model_remains": models,
        ]
        for extraKey in ["extra_remains", "boost_remains", "package_remains", "wallet_remains"] {
            if let extra = document[extraKey] as? [String: Any] {
                result[extraKey] = selected(
                    extra,
                    [
                        "remaining", "remain", "total", "limit", "used",
                        "available", "balance", "remaining_percent", "unit", "currency", "name",
                    ]
                )
            }
        }
        return result
    }
    if provider == "glm-cn" || provider == "glm-global" {
        if document["success"] as? Bool == false {
            return selected(document, ["success", "code"])
        }
        let data = document["data"] as? [String: Any] ?? document
        guard let limits = selectedArray(
            data["limits"],
            [
                "type", "unit", "number", "percentage", "usage",
                "currentValue", "remaining", "limitValue", "nextResetTime",
            ],
            maximum: 16
        )
        else { return nil }
        var sanitizedData: [String: Any] = ["limits": limits]
        if let level = boundedShortString(data["level"], maximumBytes: 32) {
            sanitizedData["level"] = level
        }
        for extraKey in ["extra", "extraPackage", "boostPack", "fuelPack"] {
            if let extra = data[extraKey] as? [String: Any] {
                sanitizedData[extraKey] = selected(
                    extra,
                    ["remaining", "total", "limit", "used", "balance", "available", "unit", "currency", "type"]
                )
            }
        }
        var result = selected(document, ["code", "success"])
        result["data"] = sanitizedData
        return result
    }
    if provider == "volc-wallet" {
        guard let result = document["Result"] as? [String: Any] else { return nil }
        return [
            "Result": selected(
                result,
                ["ArrearsBalance", "AvailableBalance", "CashBalance", "CreditLimit", "FreezeAmount"]
            ),
        ]
    }
    if provider == "volc-plan" {
        guard let result = document["Result"] as? [String: Any] else { return nil }
        var sanitized = selected(result, ["PlanType"])
        for key in ["AFPFiveHour", "AFPWeekly"] {
            guard let window = result[key] as? [String: Any] else { return nil }
            sanitized[key] = selected(window, ["Quota", "Used", "SubscribeTime", "ResetTime"])
        }
        return ["Result": sanitized]
    }
    if provider == "bailian-wallet" {
        guard let data = document["Data"] as? [String: Any] else { return nil }
        var result = selected(document, ["Code", "Success"])
        result["Data"] = selected(
            data,
            ["AvailableAmount", "AvailableCashAmount", "CreditAmount", "Currency", "MybankCreditAmount", "QuotaLimit"]
        )
        return result
    }
    return nil
}

func minimizedProviderBody(provider: String, status: Int, body: Data) -> Data? {
    if status != 200 { return Data("{}".utf8) }
    guard
        let document = jsonObject(body),
        let projectionSource = minimizedProviderDocument(provider: provider, document: document),
        JSONSerialization.isValidJSONObject(projectionSource)
    else { return nil }
    return try? JSONSerialization.data(withJSONObject: projectionSource, options: [.sortedKeys])
}

