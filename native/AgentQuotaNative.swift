import AppKit
import Foundation
import Security

private let service = "com.agentquota.desktop.credentials.v1"
private let maxRequestBytes = 4096

private struct NativeRequest {
    let action: String
    let dialogPurpose: String?
    let operationIntent: String?
    let planSummary: String?
    let planDigest: String?
    let generation: Int64?
    let nonce: String?
    let opaqueReference: String?
    let retainedReferences: [String]?

    init(data: Data) throws {
        guard
            data.count <= maxRequestBytes,
            let value = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            value.keys.allSatisfy({ Self.allowedKeys.contains($0) }),
            let action = value["action"] as? String,
            action.utf8.count <= 32
        else {
            throw NativeFailure.invalidRequest
        }
        let required: Set<String>
        switch action {
        case "credential":
            required = ["action", "dialogPurpose"]
        case "destructive":
            required = [
                "action", "generation", "nonce", "operationIntent", "planDigest", "planSummary",
            ]
        case "keychain-delete":
            required = ["action", "opaqueReference"]
        case "keychain-prune":
            required = ["action", "retainedReferences"]
        default:
            throw NativeFailure.invalidRequest
        }
        guard Set(value.keys) == required else { throw NativeFailure.invalidRequest }
        self.action = action
        dialogPurpose = value["dialogPurpose"] as? String
        operationIntent = value["operationIntent"] as? String
        planSummary = value["planSummary"] as? String
        planDigest = value["planDigest"] as? String
        if let number = value["generation"] as? NSNumber {
            guard
                CFGetTypeID(number) != CFBooleanGetTypeID(),
                !CFNumberIsFloatType(number)
            else {
                throw NativeFailure.invalidRequest
            }
            generation = number.int64Value
        } else {
            generation = nil
        }
        nonce = value["nonce"] as? String
        opaqueReference = value["opaqueReference"] as? String
        retainedReferences = value["retainedReferences"] as? [String]
        for item in [
            dialogPurpose, operationIntent, planSummary, planDigest, nonce, opaqueReference,
        ].compactMap({ $0 }) where item.isEmpty || item.utf8.count > 256 {
            throw NativeFailure.invalidRequest
        }
        if action == "keychain-prune" {
            guard
                let references = retainedReferences,
                references.count <= 64,
                Set(references).count == references.count,
                references.allSatisfy(isCredentialReference)
            else {
                throw NativeFailure.invalidRequest
            }
        }
    }

    private static let allowedKeys: Set<String> = [
        "action", "dialogPurpose", "generation", "nonce", "opaqueReference",
        "operationIntent", "planDigest", "planSummary", "retainedReferences",
    ]
}

private struct NativeResponse: Encodable {
    let status: String
    let opaqueReference: String?
    let errorCode: String?
    let userPresenceToken: String?
}

private enum NativeFailure: Error {
    case invalidRequest
    case keychain(OSStatus)
}

private func emit(_ response: NativeResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(response), data.count <= maxRequestBytes else { exit(70) }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
}

private func withSecretData<T>(
    _ secret: inout [UInt8],
    operation: (NSData) throws -> T
) rethrows -> T {
    defer { secret.resetBytes(in: secret.indices) }
    return try secret.withUnsafeMutableBytes { buffer in
        let data = NSData(bytesNoCopy: buffer.baseAddress!, length: buffer.count, freeWhenDone: false)
        return try operation(data)
    }
}

private func keychainAdd(account: String, secret: inout [UInt8]) throws {
    try withSecretData(&secret) { data in
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
            kSecAttrLabel: "Agent Quota credential reference",
            kSecAttrAccessible: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            kSecValueData: data,
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw NativeFailure.keychain(status) }
    }
}

private func keychainRead(account: String) throws -> Data {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
        kSecMatchLimit: kSecMatchLimitOne,
        kSecReturnData: true,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else {
        throw NativeFailure.keychain(status)
    }
    return data
}

private func keychainUpdate(account: String, secret: inout [UInt8]) throws {
    try withSecretData(&secret) { data in
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
        ]
        let status = SecItemUpdate(
            query as CFDictionary,
            [kSecValueData: data] as CFDictionary
        )
        guard status == errSecSuccess else { throw NativeFailure.keychain(status) }
    }
}

private func keychainDelete(account: String) -> OSStatus {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
    ]
    return SecItemDelete(query as CFDictionary)
}

private func keychainErrorCode(_ status: OSStatus) -> String {
    switch status {
    case errSecDuplicateItem:
        return "duplicate"
    case errSecInteractionNotAllowed, errSecAuthFailed:
        return "keychain-locked"
    default:
        return "keychain-write-failed"
    }
}

@MainActor
private func prepareApplication() {
    let application = NSApplication.shared
    application.setActivationPolicy(.accessory)
    application.finishLaunching()
    application.activate(ignoringOtherApps: true)
}

@MainActor
private func credentialDialog(purpose: String) -> NativeResponse {
    guard ["create-credential-reference", "replace-credential-reference"].contains(purpose) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    prepareApplication()
    let alert = NSAlert()
    alert.alertStyle = .informational
    alert.messageText = purpose == "replace-credential-reference" ? "替换本机凭据" : "添加本机凭据"
    alert.informativeText = "凭据只写入 macOS 钥匙串，不进入网页、Tauri IPC、日志或参数。"
    alert.addButton(withTitle: "保存到钥匙串")
    alert.addButton(withTitle: "取消")

    let container = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 54))
    let secure = NSSecureTextField(frame: NSRect(x: 0, y: 18, width: 360, height: 28))
    secure.placeholderString = "API Key / Token"
    secure.setAccessibilityLabel("本机安全凭据")
    container.addSubview(secure)
    alert.accessoryView = container
    alert.window.initialFirstResponder = secure

    var lostFocus = false
    let observer = NotificationCenter.default.addObserver(
        forName: NSApplication.didResignActiveNotification,
        object: NSApplication.shared,
        queue: .main
    ) { _ in lostFocus = true }
    defer { NotificationCenter.default.removeObserver(observer) }
    guard alert.runModal() == .alertFirstButtonReturn, !lostFocus else {
        secure.stringValue = ""
        return NativeResponse(
            status: "cancelled", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    }
    var bytes = Array(secure.stringValue.utf8)
    secure.stringValue = ""
    guard !bytes.isEmpty, bytes.count <= 16_384 else {
        bytes.resetBytes(in: bytes.indices)
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-secret",
            userPresenceToken: nil
        )
    }
    let reference = "credential-\(UUID().uuidString.lowercased())"
    do {
        try keychainAdd(account: reference, secret: &bytes)
        return NativeResponse(
            status: purpose == "replace-credential-reference"
                ? "reference-replaced" : "reference-created",
            opaqueReference: reference,
            errorCode: nil,
            userPresenceToken: nil
        )
    } catch NativeFailure.keychain(let status) {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: keychainErrorCode(status),
            userPresenceToken: nil
        )
    } catch {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "keychain-write-failed",
            userPresenceToken: nil
        )
    }
}

@MainActor
private func destructiveDialog(_ request: NativeRequest) -> NativeResponse {
    let allowedIntents = [
        "cascade", "delete", "destructive-config-diff", "disable", "purge",
    ]
    guard
        let intent = request.operationIntent,
        allowedIntents.contains(intent),
        let summary = request.planSummary,
        let digest = request.planDigest,
        digest.count == 64,
        digest.allSatisfy({ $0.isHexDigit }),
        let generation = request.generation,
        generation >= 0,
        let nonce = request.nonce,
        nonce.count == 32,
        nonce.allSatisfy({ $0.isHexDigit })
    else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    prepareApplication()
    let alert = NSAlert()
    alert.alertStyle = .critical
    alert.messageText = "确认破坏性操作：\(intent)"
    alert.informativeText = "\(summary)\nGeneration \(generation) · Plan \(digest.prefix(12))"
    alert.addButton(withTitle: "取消")
    alert.addButton(withTitle: "确认执行")
    let confirmation = NSButton(
        checkboxWithTitle: "我已核对范围，并确认该操作可能不可恢复。",
        target: nil,
        action: nil
    )
    confirmation.setAccessibilityLabel("确认破坏性操作范围")
    alert.accessoryView = confirmation

    var lostFocus = false
    let observer = NotificationCenter.default.addObserver(
        forName: NSApplication.didResignActiveNotification,
        object: NSApplication.shared,
        queue: .main
    ) { _ in lostFocus = true }
    defer { NotificationCenter.default.removeObserver(observer) }
    let response = alert.runModal()
    guard
        response == .alertSecondButtonReturn,
        confirmation.state == .on,
        !lostFocus
    else {
        return NativeResponse(
            status: "cancelled", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    }
    return NativeResponse(
        status: "confirmed",
        opaqueReference: nil,
        errorCode: nil,
        userPresenceToken: UUID().uuidString.lowercased()
    )
}

private func isCredentialReference(_ reference: String) -> Bool {
    reference.count == 47
        && reference.hasPrefix("credential-")
        && UUID(uuidString: String(reference.dropFirst("credential-".count))) != nil
}

private func deleteReference(_ reference: String) -> NativeResponse {
    guard isCredentialReference(reference) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    let status = keychainDelete(account: reference)
    if status == errSecSuccess {
        return NativeResponse(
            status: "deleted", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    }
    if status == errSecItemNotFound {
        return NativeResponse(
            status: "not-found", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    }
    return NativeResponse(
        status: "error", opaqueReference: nil, errorCode: keychainErrorCode(status),
        userPresenceToken: nil
    )
}

private func keychainAccounts() throws -> [String] {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecMatchLimit: kSecMatchLimitAll,
        kSecReturnAttributes: true,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound {
        return []
    }
    guard status == errSecSuccess else {
        throw NativeFailure.keychain(status)
    }
    let rows: [Any]
    if let values = result as? [Any] {
        rows = values
    } else if let value = result {
        rows = [value]
    } else {
        rows = []
    }
    return rows.compactMap { row in
        (row as? [String: Any])?[kSecAttrAccount as String] as? String
    }
}

private func pruneReferences(retaining retainedReferences: [String]) -> NativeResponse {
    let retained = Set(retainedReferences)
    do {
        for reference in try keychainAccounts()
        where isCredentialReference(reference) && !retained.contains(reference) {
            let status = keychainDelete(account: reference)
            guard status == errSecSuccess || status == errSecItemNotFound else {
                throw NativeFailure.keychain(status)
            }
        }
        return NativeResponse(
            status: "pruned", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    } catch NativeFailure.keychain(let status) {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: keychainErrorCode(status),
            userPresenceToken: nil
        )
    } catch {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "keychain-write-failed",
            userPresenceToken: nil
        )
    }
}

private func selfTestKeychain() -> Int32 {
    let account = "self-test-\(UUID().uuidString.lowercased())"
    let retainedReference = "credential-\(UUID().uuidString.lowercased())"
    let orphanReference = "credential-\(UUID().uuidString.lowercased())"
    var first = Array("temporary-agent-quota-self-test-a".utf8)
    var second = Array("temporary-agent-quota-self-test-b".utf8)
    var retainedSecret = Array("temporary-agent-quota-retained".utf8)
    var orphanSecret = Array("temporary-agent-quota-orphan".utf8)
    defer { _ = keychainDelete(account: account) }
    defer { _ = keychainDelete(account: retainedReference) }
    defer { _ = keychainDelete(account: orphanReference) }
    do {
        try keychainAdd(account: account, secret: &first)
        guard try keychainRead(account: account) == Data(
            "temporary-agent-quota-self-test-a".utf8
        ) else { return 3 }
        try keychainUpdate(account: account, secret: &second)
        guard try keychainRead(account: account) == Data(
            "temporary-agent-quota-self-test-b".utf8
        ) else { return 4 }
        guard keychainDelete(account: account) == errSecSuccess else { return 5 }
        do {
            _ = try keychainRead(account: account)
            return 6
        } catch NativeFailure.keychain(let status) where status == errSecItemNotFound {}
        try keychainAdd(account: retainedReference, secret: &retainedSecret)
        try keychainAdd(account: orphanReference, secret: &orphanSecret)
        guard pruneReferences(retaining: [retainedReference]).status == "pruned" else {
            return 7
        }
        _ = try keychainRead(account: retainedReference)
        do {
            _ = try keychainRead(account: orphanReference)
            return 8
        } catch NativeFailure.keychain(let status) where status == errSecItemNotFound {}
        emit(
            NativeResponse(
                status: "self-test-ok", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil
            )
        )
        return 0
    } catch {
        emit(
            NativeResponse(
                status: "self-test-failed", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil
            )
        )
        return 2
    }
}

@main
private struct AgentQuotaNative {
    @MainActor
    static func main() {
        if CommandLine.arguments == [CommandLine.arguments[0], "--self-test-keychain"] {
            exit(selfTestKeychain())
        }
        autoreleasepool {
            guard
                let line = readLine(strippingNewline: true),
                let data = line.data(using: .utf8),
                let request = try? NativeRequest(data: data)
            else {
                emit(
                    NativeResponse(
                        status: "error", opaqueReference: nil, errorCode: "invalid-request",
                        userPresenceToken: nil
                    )
                )
                exit(64)
            }
            let response: NativeResponse
            switch request.action {
            case "credential":
                guard let purpose = request.dialogPurpose else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = credentialDialog(purpose: purpose)
            case "destructive":
                response = destructiveDialog(request)
            case "keychain-delete":
                guard let reference = request.opaqueReference else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = deleteReference(reference)
            case "keychain-prune":
                guard let references = request.retainedReferences else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = pruneReferences(retaining: references)
            default:
                response = NativeResponse(
                    status: "error", opaqueReference: nil, errorCode: "invalid-request",
                    userPresenceToken: nil
                )
            }
            emit(response)
        }
    }
}
