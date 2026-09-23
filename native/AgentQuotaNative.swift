import AppKit
import CryptoKit
import Foundation
import Security
import UniformTypeIdentifiers

private let service = "com.agentquota.desktop.credentials.v1"
private let legacyCredentialLabel = "Agent Quota credential reference"
private let maxRequestBytes = 4096
private let maxResponseBytes = 384 * 1024
private let maxProviderBodyBytes = 256 * 1024
private let kimiCodeOAuthHost = "auth.kimi.com"
private let kimiCodeOAuthClientID = "17e5f671-d194-4dfb-9706-5516cb48c098"

private enum ProviderAuthMode: Equatable {
    case bearer
    case raw
    case kimiCodeOAuth
    case volcAKSK(service: String, region: String, action: String, version: String, method: String)
    case aliyunRPC(action: String, version: String)
}

private struct ProviderDefinition {
    let id: String
    let label: String
    let host: String
    let path: String
    let authMode: ProviderAuthMode

    var endpoint: URL? {
        var components = URLComponents()
        components.scheme = "https"
        components.host = host
        components.path = path
        guard
            let url = components.url,
            url.scheme == "https",
            url.host == host,
            url.path == path,
            url.port == nil,
            url.user == nil,
            url.password == nil,
            url.query == nil,
            url.fragment == nil
        else { return nil }
        return url
    }
}

private let providers = [
    ProviderDefinition(id: "bailian-wallet", label: "阿里云账户余额（百炼）", host: "business.aliyuncs.com", path: "/", authMode: .aliyunRPC(action: "QueryAccountBalance", version: "2017-12-14")),
    ProviderDefinition(id: "deepseek", label: "DeepSeek", host: "api.deepseek.com", path: "/user/balance", authMode: .bearer),
    ProviderDefinition(id: "glm-cn", label: "GLM Coding Plan（中国区）", host: "open.bigmodel.cn", path: "/api/monitor/usage/quota/limit", authMode: .raw),
    ProviderDefinition(id: "glm-global", label: "GLM Coding Plan（国际区）", host: "api.z.ai", path: "/api/monitor/usage/quota/limit", authMode: .raw),
    ProviderDefinition(id: "kimi-cn", label: "Kimi API 余额（中国区）", host: "api.moonshot.cn", path: "/v1/users/me/balance", authMode: .bearer),
    ProviderDefinition(id: "kimi-global", label: "Kimi API 余额（国际区）", host: "api.moonshot.ai", path: "/v1/users/me/balance", authMode: .bearer),
    ProviderDefinition(id: "kimi-code", label: "Kimi Code Token Plan", host: "api.kimi.com", path: "/coding/v1/usages", authMode: .kimiCodeOAuth),
    ProviderDefinition(id: "minimax-cn", label: "MiniMax Token Plan（中国区）", host: "www.minimaxi.com", path: "/v1/token_plan/remains", authMode: .bearer),
    ProviderDefinition(id: "minimax-global", label: "MiniMax Token Plan（国际区）", host: "www.minimax.io", path: "/v1/token_plan/remains", authMode: .bearer),
    ProviderDefinition(id: "volc-wallet", label: "火山引擎账户余额", host: "open.volcengineapi.com", path: "/", authMode: .volcAKSK(service: "billing", region: "cn-beijing", action: "QueryBalanceAcct", version: "2022-01-01", method: "POST")),
    ProviderDefinition(id: "volc-plan", label: "火山方舟 Coding Plan", host: "ark.cn-beijing.volces.com", path: "/", authMode: .volcAKSK(service: "ark", region: "cn-beijing", action: "GetAFPUsage", version: "2024-01-01", method: "POST")),
]

// BEGIN GENERATED LAUNCH CREATE IDS
private let creatableProviderIDs = [
    "deepseek",
    "glm-cn",
    "kimi-cn",
    "kimi-code",
    "minimax-cn",
]
// END GENERATED LAUNCH CREATE IDS

private let creatableProviders = creatableProviderIDs.compactMap { id in
    providers.first { $0.id == id }
}

private struct CloudKeyBundle: Codable {
    let accessKeyID: String
    let secretAccessKey: String
}

private struct KimiCodeTokenBundle: Codable {
    let accessToken: String
    let refreshToken: String
    let expiresAt: Int64
    let scope: String
    let tokenType: String
    let expiresIn: Int64

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case expiresAt = "expires_at"
        case scope
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

private struct NativeRequest {
    let action: String
    let dialogPurpose: String?
    let operationIntent: String?
    let planSummary: String?
    let planDigest: String?
    let generation: Int64?
    let nonce: String?
    let opaqueReference: String?
    let provider: String?
    let exportContentBase64: String?
    let exportFilename: String?

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
            required = (value["dialogPurpose"] as? String) == "replace-credential-reference"
                ? ["action", "dialogPurpose", "opaqueReference", "provider"]
                : ["action", "dialogPurpose", "opaqueReference"]
        case "provider-fetch", "keychain-rename":
            required = ["action", "opaqueReference", "provider"]
        case "destructive":
            required = [
                "action", "generation", "nonce", "operationIntent", "planDigest", "planSummary",
            ]
        case "keychain-delete":
            required = ["action", "opaqueReference"]
        case "export-redacted":
            required = ["action", "exportContentBase64", "exportFilename"]
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
        provider = value["provider"] as? String
        exportContentBase64 = value["exportContentBase64"] as? String
        exportFilename = value["exportFilename"] as? String
        for item in [
            dialogPurpose, operationIntent, planSummary, planDigest, nonce, opaqueReference, provider,
        ].compactMap({ $0 }) where item.isEmpty || item.utf8.count > 256 {
            throw NativeFailure.invalidRequest
        }
        if let exportContentBase64,
           exportContentBase64.isEmpty || exportContentBase64.utf8.count > 3_072
        {
            throw NativeFailure.invalidRequest
        }
        if let exportFilename,
           exportFilename != "agent-quota-diagnostics.json"
        {
            throw NativeFailure.invalidRequest
        }
    }

    private static let allowedKeys: Set<String> = [
        "action", "dialogPurpose", "generation", "nonce", "opaqueReference",
        "operationIntent", "planDigest", "planSummary", "provider",
        "exportContentBase64", "exportFilename",
    ]
}

private struct NativeResponse: Encodable {
    let status: String
    let opaqueReference: String?
    let errorCode: String?
    let userPresenceToken: String?
    let provider: String?
    let httpStatus: Int?
    let bodyBase64: String?

    init(
        status: String,
        opaqueReference: String?,
        errorCode: String?,
        userPresenceToken: String?,
        provider: String? = nil,
        httpStatus: Int? = nil,
        bodyBase64: String? = nil
    ) {
        self.status = status
        self.opaqueReference = opaqueReference
        self.errorCode = errorCode
        self.userPresenceToken = userPresenceToken
        self.provider = provider
        self.httpStatus = httpStatus
        self.bodyBase64 = bodyBase64
    }
}

private enum NativeFailure: Error {
    case invalidRequest
    case keychain(OSStatus)
}

private final class PasteSecureTextField: NSSecureTextField {
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let modifiers = event.modifierFlags.intersection([.command, .option, .control, .shift])
        if event.type == .keyDown,
           modifiers == [.command],
           event.charactersIgnoringModifiers?.lowercased() == "v",
           let editor = currentEditor()
        {
            editor.paste(nil)
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

@MainActor
private final class DestructiveConfirmationGate: NSObject {
    weak var confirmButton: NSButton?

    @objc func update(_ checkbox: NSButton) {
        confirmButton?.isEnabled = checkbox.state == .on
    }
}

private func emit(_ response: NativeResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(response), data.count <= maxResponseBytes else { exit(70) }
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

private func credentialKeychainLabel(reference: String, provider: ProviderDefinition) -> String? {
    guard isCredentialReference(reference) else { return nil }
    // This suffix identifies a local credential, not an account name or part of its secret.
    let identifier = reference.dropFirst("credential-".count).prefix(8).lowercased()
    return "Agent Quota · \(provider.label) · \(identifier)"
}

private func keychainAdd(
    account: String, provider: ProviderDefinition, secret: inout [UInt8],
    keychain: SecKeychain? = nil
) throws {
    guard let label = credentialKeychainLabel(reference: account, provider: provider) else {
        secret.resetBytes(in: secret.indices)
        throw NativeFailure.invalidRequest
    }
    try keychainAdd(account: account, label: label, secret: &secret, keychain: keychain)
}

private func keychainAdd(
    account: String, label: String, secret: inout [UInt8], keychain: SecKeychain? = nil
) throws {
    try withSecretData(&secret) { data in
        // macOS permission dialogs use the ACL descriptor, which is separate from the label
        // shown in Keychain Access. A nil trusted list keeps the default: this creating app.
        var access: SecAccess?
        let accessStatus = AQKeychainCreateAccess(label as CFString, &access)
        guard accessStatus == errSecSuccess, let access else {
            throw NativeFailure.keychain(accessStatus)
        }
        var query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
            kSecAttrLabel: label,
            kSecAttrAccess: access,
            kSecAttrAccessible: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            kSecValueData: data,
        ]
        if let keychain { query[kSecUseKeychain] = keychain }
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw NativeFailure.keychain(status) }
    }
}

private func keychainAttributes(account: String, keychain: SecKeychain? = nil) throws -> [CFString: Any] {
    var query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
        kSecMatchLimit: kSecMatchLimitOne,
        kSecReturnAttributes: true,
        kSecReturnRef: true,
    ]
    if let keychain { query[kSecMatchSearchList] = [keychain] }
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let attributes = result as? [CFString: Any] else {
        throw NativeFailure.keychain(status == errSecSuccess ? errSecInternalComponent : status)
    }
    return attributes
}

private enum CredentialLabelMigration: Equatable {
    case renamed
    case unchanged
    case customLabelPreserved
    case labelUpdateDeferred(OSStatus)
    case failed(OSStatus)
}

@discardableResult
private func migrateCredentialKeychainLabel(
    account: String, provider: ProviderDefinition, keychain: SecKeychain? = nil
) -> CredentialLabelMigration {
    guard let label = credentialKeychainLabel(reference: account, provider: provider) else {
        return .failed(errSecParam)
    }
    // Called only by explicit keychain-rename maintenance. Legacy ACL writes may prompt even
    // with optional interaction disabled; never call this function from a refresh operation.
    do {
        let attributes = try keychainAttributes(account: account, keychain: keychain)
        guard let currentLabel = attributes[kSecAttrLabel] as? String,
              currentLabel == legacyCredentialLabel || currentLabel == label
        else { return .customLabelPreserved }
        guard let item = attributes[kSecValueRef] else { return .failed(errSecInternalComponent) }
        var access: SecAccess?
        var changedDescription = false
        let accessStatus = AQKeychainCopyAccessRenamingDescription(
            item as CFTypeRef, legacyCredentialLabel as CFString, label as CFString,
            &access, &changedDescription
        )
        guard accessStatus == errSecSuccess, let access else { return .failed(accessStatus) }
        guard currentLabel != label || changedDescription else { return .unchanged }
        // Authorize the ACL description change first. SecItemUpdate is not atomic across
        // label and ACL writes on the legacy keychain, so do not submit them together.
        if changedDescription {
            let status = AQKeychainSetAccess(item as CFTypeRef, access)
            guard status == errSecSuccess else { return .failed(status) }
        }
        guard currentLabel != label else { return .renamed }
        var query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
            kSecAttrLabel: currentLabel,
            kSecMatchItemList: [item],
        ]
        if let keychain { query[kSecMatchSearchList] = [keychain] }
        let updateStatus = SecItemUpdate(
            query as CFDictionary, [kSecAttrLabel: label] as CFDictionary
        )
        // A later retry accepts the old label with the already updated ACL description.
        return updateStatus == errSecSuccess ? .renamed : .labelUpdateDeferred(updateStatus)
    } catch NativeFailure.keychain(let status) {
        return .failed(status)
    } catch {
        return .failed(errSecInternalComponent)
    }
}

private func renameCredentialReference(_ reference: String, provider id: String) -> NativeResponse {
    guard isCredentialReference(reference), let definition = providerDefinition(id) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    // Explicit maintenance action only. It never requests secret data; the system may ask the
    // user to authorize editing this item's metadata. Normal refresh never enables this UI.
    let result = migrateCredentialKeychainLabel(
        account: reference, provider: definition
    )
    let status: String
    let errorCode: String?
    switch result {
    case .renamed:
        status = "renamed"
        errorCode = nil
    case .unchanged:
        status = "unchanged"
        errorCode = nil
    case .customLabelPreserved:
        status = "unchanged"
        errorCode = "custom-label-preserved"
    case .labelUpdateDeferred:
        status = "deferred"
        errorCode = "keychain-label-update-pending"
    case .failed(let code):
        status = [errSecInteractionNotAllowed, errSecAuthFailed, errSecUserCanceled].contains(code)
            ? "deferred" : "error"
        errorCode = code == errSecItemNotFound ? "not-found" : "keychain-metadata-update-failed"
    }
    return NativeResponse(
        status: status, opaqueReference: nil, errorCode: errorCode,
        userPresenceToken: nil, provider: id
    )
}

private func keychainRead(account: String, keychain: SecKeychain? = nil) throws -> Data {
    var query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
        kSecMatchLimit: kSecMatchLimitOne,
        kSecReturnData: true,
    ]
    if let keychain { query[kSecMatchSearchList] = [keychain] }
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else {
        throw NativeFailure.keychain(status)
    }
    return data
}

private func keychainUpdate(
    account: String, secret: inout [UInt8], keychain: SecKeychain? = nil
) throws {
    try withSecretData(&secret) { data in
        var query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
        ]
        if let keychain { query[kSecMatchSearchList] = [keychain] }
        let status = SecItemUpdate(
            query as CFDictionary,
            [kSecValueData: data] as CFDictionary
        )
        guard status == errSecSuccess else { throw NativeFailure.keychain(status) }
    }
}

private func keychainDelete(account: String, keychain: SecKeychain? = nil) -> OSStatus {
    var query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
    ]
    if let keychain { query[kSecMatchSearchList] = [keychain] }
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

private func isSafeCredential(_ value: String) -> Bool {
    let bytes = value.utf8
    return !bytes.isEmpty && bytes.count <= 16_384 && bytes.allSatisfy { 0x21...0x7E ~= $0 }
}

@MainActor
private func prepareApplication() {
    let application = NSApplication.shared
    application.setActivationPolicy(.accessory)
    application.finishLaunching()
    if application.mainMenu?.items.contains(where: { $0.title == "Edit" }) != true {
        let mainMenu = application.mainMenu ?? NSMenu()
        let editMenuItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit")
        let pasteItem = NSMenuItem(
            title: "Paste",
            action: #selector(NSText.paste(_:)),
            keyEquivalent: "v"
        )
        pasteItem.keyEquivalentModifierMask = [.command]
        editMenu.addItem(pasteItem)
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)
        application.mainMenu = mainMenu
    }
    application.activate(ignoringOtherApps: true)
}

private func providerDefinition(_ id: String) -> ProviderDefinition? {
    providers.first { $0.id == id }
}

@MainActor
private func credentialDialog(
    purpose: String,
    reference: String,
    provider requestedProvider: String?
) -> NativeResponse {
    guard
        ["create-credential-reference", "replace-credential-reference"].contains(purpose),
        isCredentialReference(reference)
    else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    prepareApplication()
    let alert = NSAlert()
    alert.alertStyle = .informational
    alert.messageText = purpose == "replace-credential-reference" ? "替换本机凭据" : "添加本机凭据"
    alert.informativeText = purpose == "replace-credential-reference"
        ? "替换已配置 Provider 的凭据；凭据只写入 macOS 钥匙串。"
        : "仅可添加当前 5 项 Provider；API Key/Token 可直接粘贴，Kimi Code 使用官方 OAuth。凭据只写入 macOS 钥匙串。"
    alert.addButton(withTitle: "继续")
    alert.addButton(withTitle: "取消")

    let container = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 122))
    let selector = NSPopUpButton(frame: NSRect(x: 0, y: 88, width: 360, height: 28))
    for item in creatableProviders { selector.addItem(withTitle: item.label) }
    selector.isHidden = purpose == "replace-credential-reference"
    container.addSubview(selector)
    let secure = PasteSecureTextField(frame: NSRect(x: 0, y: 52, width: 360, height: 28))
    secure.placeholderString = "API Key / Token / AccessKey ID（Kimi Code 留空）"
    secure.setAccessibilityLabel("本机安全凭据")
    let secureMenu = NSMenu()
    secureMenu.addItem(
        withTitle: "Paste",
        action: #selector(NSText.paste(_:)),
        keyEquivalent: ""
    )
    secure.menu = secureMenu
    container.addSubview(secure)
    let cloudSecret = PasteSecureTextField(frame: NSRect(x: 0, y: 18, width: 360, height: 28))
    cloudSecret.placeholderString = "SecretKey（仅火山签名接口）"
    cloudSecret.setAccessibilityLabel("云接口 SecretKey")
    cloudSecret.menu = secureMenu
    cloudSecret.isHidden = purpose == "create-credential-reference"
    container.addSubview(cloudSecret)
    alert.accessoryView = container
    alert.window.initialFirstResponder = secure

    // The modal result is captured before normal helper deactivation. Treating
    // didResignActive as cancellation races every successful modal teardown.
    guard alert.runModal() == .alertFirstButtonReturn else {
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        return NativeResponse(
            status: "cancelled", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    }
    let selectedProvider = purpose == "replace-credential-reference"
        ? requestedProvider
        : creatableProviders.indices.contains(selector.indexOfSelectedItem)
            ? creatableProviders[selector.indexOfSelectedItem].id
            : nil
    guard let selectedProvider, let definition = providerDefinition(selectedProvider) else {
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-provider",
            userPresenceToken: nil
        )
    }
    var bytes: [UInt8]
    if definition.authMode == .kimiCodeOAuth {
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        let login = kimiCodeOAuthCredential()
        guard let credential = login.credential else {
            return NativeResponse(
                status: login.errorCode == nil ? "cancelled" : "error",
                opaqueReference: nil,
                errorCode: login.errorCode,
                userPresenceToken: nil
            )
        }
        bytes = credential
    } else if case .volcAKSK = definition.authMode {
        let accessKeyID = secure.stringValue
        let secretAccessKey = cloudSecret.stringValue
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        guard isSafeCredential(accessKeyID), isSafeCredential(secretAccessKey),
              let encoded = try? JSONEncoder().encode(
                  CloudKeyBundle(accessKeyID: accessKeyID, secretAccessKey: secretAccessKey)
              )
        else {
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "invalid-secret",
                userPresenceToken: nil
            )
        }
        bytes = Array(encoded)
    } else if case .aliyunRPC = definition.authMode {
        let accessKeyID = secure.stringValue
        let secretAccessKey = cloudSecret.stringValue
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        guard isSafeCredential(accessKeyID), isSafeCredential(secretAccessKey),
              let encoded = try? JSONEncoder().encode(
                  CloudKeyBundle(accessKeyID: accessKeyID, secretAccessKey: secretAccessKey)
              )
        else {
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "invalid-secret",
                userPresenceToken: nil
            )
        }
        bytes = Array(encoded)
    } else {
        bytes = Array(secure.stringValue.utf8)
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        guard let value = String(bytes: bytes, encoding: .utf8), isSafeCredential(value) else {
            bytes.resetBytes(in: bytes.indices)
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "invalid-secret",
                userPresenceToken: nil
            )
        }
    }
    do {
        try keychainAdd(account: reference, provider: definition, secret: &bytes)
        return NativeResponse(
            status: purpose == "replace-credential-reference"
                ? "reference-replaced" : "reference-created",
            opaqueReference: reference,
            errorCode: nil,
            userPresenceToken: nil,
            provider: selectedProvider
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

private final class BoundedProviderDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let limit: Int
    private let semaphore: DispatchSemaphore
    private let lock = NSLock()
    private var completed = false
    private var body = Data()
    private var response: HTTPURLResponse?
    private var error: Error?
    private var exceededLimit = false

    init(limit: Int, semaphore: DispatchSemaphore) {
        self.limit = limit
        self.semaphore = semaphore
    }

    private func complete(error: Error? = nil) {
        lock.lock()
        let shouldSignal = !completed
        if shouldSignal {
            completed = true
            self.error = error
        }
        lock.unlock()
        if shouldSignal { semaphore.signal() }
    }

    func snapshot() -> (body: Data, response: HTTPURLResponse?, error: Error?, exceededLimit: Bool) {
        lock.lock()
        defer { lock.unlock() }
        return (body, response, error, exceededLimit)
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        guard let httpResponse = response as? HTTPURLResponse else {
            completionHandler(.cancel)
            complete()
            return
        }
        lock.lock()
        self.response = httpResponse
        lock.unlock()
        let expected = response.expectedContentLength
        if expected > Int64(limit) {
            lock.lock()
            exceededLimit = true
            lock.unlock()
            completionHandler(.cancel)
            complete()
            return
        }
        completionHandler(.allow)
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive data: Data
    ) {
        lock.lock()
        let exceedsLimit = data.count > limit - body.count
        if exceedsLimit {
            exceededLimit = true
        } else {
            body.append(data)
        }
        lock.unlock()
        if exceedsLimit {
            dataTask.cancel()
            complete()
            return
        }
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        complete(error: error)
    }
}

private struct BoundedHTTPResult {
    let status: Int
    let body: Data
}

private func fixedHTTPSURL(host: String, path: String) -> URL? {
    var components = URLComponents()
    components.scheme = "https"
    components.host = host
    components.path = path
    guard
        let url = components.url,
        url.scheme == "https",
        url.host == host,
        url.path == path,
        url.port == nil,
        url.user == nil,
        url.password == nil,
        url.query == nil,
        url.fragment == nil
    else { return nil }
    return url
}

private func boundedHTTPRequest(
    url: URL,
    method: String,
    headers: [String: String],
    body: Data? = nil,
    timeout: TimeInterval = 15
) -> BoundedHTTPResult? {
    var request = URLRequest(
        url: url,
        cachePolicy: .reloadIgnoringLocalAndRemoteCacheData,
        timeoutInterval: timeout
    )
    request.httpMethod = method
    request.httpBody = body
    for (name, value) in headers {
        request.setValue(value, forHTTPHeaderField: name)
    }
    request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")

    let configuration = URLSessionConfiguration.ephemeral
    configuration.urlCache = nil
    configuration.urlCredentialStorage = nil
    configuration.httpCookieStorage = nil
    configuration.httpShouldSetCookies = false
    configuration.connectionProxyDictionary = [:]
    configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
    configuration.timeoutIntervalForRequest = timeout
    configuration.timeoutIntervalForResource = timeout + 5
    let semaphore = DispatchSemaphore(value: 0)
    let delegate = BoundedProviderDelegate(limit: maxProviderBodyBytes, semaphore: semaphore)
    let delegateQueue = OperationQueue()
    delegateQueue.maxConcurrentOperationCount = 1
    let session = URLSession(
        configuration: configuration,
        delegate: delegate,
        delegateQueue: delegateQueue
    )
    let task = session.dataTask(with: request)
    task.resume()
    guard semaphore.wait(timeout: .now() + timeout + 6) == .success else {
        task.cancel()
        session.invalidateAndCancel()
        return nil
    }
    session.finishTasksAndInvalidate()
    let snapshot = delegate.snapshot()
    guard
        snapshot.error == nil,
        !snapshot.exceededLimit,
        let response = snapshot.response,
        response.url == url,
        !snapshot.body.isEmpty,
        snapshot.body.count <= maxProviderBodyBytes
    else { return nil }
    return BoundedHTTPResult(status: response.statusCode, body: snapshot.body)
}

private func formBody(_ fields: [(String, String)]) -> Data? {
    var components = URLComponents()
    components.queryItems = fields.map { URLQueryItem(name: $0.0, value: $0.1) }
    return components.percentEncodedQuery?.data(using: .utf8)
}

private func jsonObject(_ data: Data) -> [String: Any]? {
    try? JSONSerialization.jsonObject(with: data) as? [String: Any]
}

private func positiveInt64(_ value: Any?) -> Int64? {
    if let number = value as? NSNumber,
       CFGetTypeID(number) != CFBooleanGetTypeID(),
       !CFNumberIsFloatType(number),
       number.int64Value > 0
    {
        return number.int64Value
    }
    if let string = value as? String, let number = Int64(string), number > 0 {
        return number
    }
    return nil
}

private func kimiCodeTokenBundle(_ document: [String: Any]) -> KimiCodeTokenBundle? {
    let now = Int64(Date().timeIntervalSince1970)
    guard
        let accessToken = document["access_token"] as? String,
        isSafeCredential(accessToken),
        let refreshToken = document["refresh_token"] as? String,
        isSafeCredential(refreshToken),
        let expiresIn = positiveInt64(document["expires_in"]),
        expiresIn <= Int64.max - now
    else { return nil }
    return KimiCodeTokenBundle(
        accessToken: accessToken,
        refreshToken: refreshToken,
        expiresAt: now + expiresIn,
        scope: document["scope"] as? String ?? "",
        tokenType: document["token_type"] as? String ?? "Bearer",
        expiresIn: expiresIn
    )
}

private func encodedKimiCodeTokenBundle(_ bundle: KimiCodeTokenBundle) -> [UInt8]? {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(bundle), data.count <= 32_768 else { return nil }
    return Array(data)
}

@MainActor
private func kimiCodeOAuthCredential() -> (credential: [UInt8]?, errorCode: String?) {
    guard
        let authorizationURL = fixedHTTPSURL(
            host: kimiCodeOAuthHost,
            path: "/api/oauth/device_authorization"
        ),
        let authorizationBody = formBody([("client_id", kimiCodeOAuthClientID)]),
        let authorization = boundedHTTPRequest(
            url: authorizationURL,
            method: "POST",
            headers: [
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            ],
            body: authorizationBody,
            timeout: 30
        ),
        authorization.status == 200,
        let document = jsonObject(authorization.body),
        let userCode = document["user_code"] as? String,
        !userCode.isEmpty,
        userCode.utf8.count <= 64,
        let deviceCode = document["device_code"] as? String,
        !deviceCode.isEmpty,
        deviceCode.utf8.count <= 1024,
        let verificationString = document["verification_uri_complete"] as? String,
        let verificationURL = URL(string: verificationString),
        verificationURL.scheme == "https",
        ["auth.kimi.com", "www.kimi.com"].contains(verificationURL.host),
        verificationURL.user == nil,
        verificationURL.password == nil,
        verificationURL.port == nil
    else { return (nil, "provider-unavailable") }

    guard NSWorkspace.shared.open(verificationURL) else {
        return (nil, "provider-unavailable")
    }
    let alert = NSAlert()
    alert.alertStyle = .informational
    alert.messageText = "登录 Kimi Code"
    alert.informativeText = "已在浏览器打开官方授权页。完成登录并确认授权后，返回这里继续。\n设备码：\(userCode)"
    alert.addButton(withTitle: "我已完成授权")
    alert.addButton(withTitle: "取消")
    guard alert.runModal() == .alertFirstButtonReturn else { return (nil, nil) }

    guard
        let tokenURL = fixedHTTPSURL(host: kimiCodeOAuthHost, path: "/api/oauth/token")
    else { return (nil, "provider-unavailable") }
    let interval = min(max(positiveInt64(document["interval"]) ?? 5, 1), 10)
    let authorizationLifetime = min(max(positiveInt64(document["expires_in"]) ?? 300, 45), 1_800)
    let deadline = Date().addingTimeInterval(TimeInterval(authorizationLifetime))
    while Date() < deadline {
        guard let tokenBody = formBody([
            ("client_id", kimiCodeOAuthClientID),
            ("device_code", deviceCode),
            ("grant_type", "urn:ietf:params:oauth:grant-type:device_code"),
        ]), let response = boundedHTTPRequest(
            url: tokenURL,
            method: "POST",
            headers: [
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            ],
            body: tokenBody,
            timeout: 30
        ), let tokenDocument = jsonObject(response.body)
        else { return (nil, "provider-unavailable") }
        if response.status == 200,
           let bundle = kimiCodeTokenBundle(tokenDocument),
           let encoded = encodedKimiCodeTokenBundle(bundle)
        {
            return (encoded, nil)
        }
        let error = tokenDocument["error"] as? String
        if error == "access_denied" || error == "expired_token" {
            return (nil, "not-authorized")
        }
        guard error == "authorization_pending" || error == "slow_down" else {
            return (nil, "provider-unavailable")
        }
        Thread.sleep(forTimeInterval: TimeInterval(interval))
    }
    return (nil, "timeout")
}

private enum KimiCodeCredentialResolution {
    case ready(String)
    case reauthRequired
    case keychainLocked
    case unavailable
}

private func resolveKimiCodeCredential(reference: String, secret: Data) -> KimiCodeCredentialResolution {
    let decoder = JSONDecoder()
    guard var bundle = try? decoder.decode(KimiCodeTokenBundle.self, from: secret) else {
        return .reauthRequired
    }
    if bundle.expiresAt <= Int64(Date().timeIntervalSince1970) + 60 {
        guard
            let tokenURL = fixedHTTPSURL(host: kimiCodeOAuthHost, path: "/api/oauth/token"),
            let body = formBody([
                ("client_id", kimiCodeOAuthClientID),
                ("grant_type", "refresh_token"),
                ("refresh_token", bundle.refreshToken),
            ]),
            let response = boundedHTTPRequest(
                url: tokenURL,
                method: "POST",
                headers: [
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                ],
                body: body,
                timeout: 30
            )
        else { return .unavailable }
        if response.status == 401 || response.status == 403 {
            return .reauthRequired
        }
        guard
            response.status == 200,
            let document = jsonObject(response.body),
            let refreshed = kimiCodeTokenBundle(document),
            let encoded = encodedKimiCodeTokenBundle(refreshed)
        else { return .unavailable }
        var bytes = encoded
        do {
            try keychainUpdate(account: reference, secret: &bytes)
        } catch NativeFailure.keychain(let status)
            where status == errSecInteractionNotAllowed || status == errSecAuthFailed
        {
            return .keychainLocked
        } catch {
            return .unavailable
        }
        bundle = refreshed
    }
    return .ready(bundle.accessToken)
}

private func selected(_ document: [String: Any], _ keys: [String]) -> [String: Any] {
    Dictionary(uniqueKeysWithValues: keys.compactMap { key in
        document[key].map { (key, $0) }
    })
}

private func selectedArray(_ value: Any?, _ keys: [String], maximum: Int) -> [[String: Any]]? {
    guard let items = value as? [Any], items.count <= maximum else { return nil }
    var result: [[String: Any]] = []
    for item in items {
        guard let document = item as? [String: Any] else { return nil }
        result.append(selected(document, keys))
    }
    return result
}

private func minimizedProviderDocument(provider: String, document: [String: Any]) -> [String: Any]? {
    if provider == "deepseek" {
        guard let balances = selectedArray(
            document["balance_infos"],
            ["currency", "total_balance"],
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
        return [
            "base_resp": selected(base, ["status_code"]),
            "model_remains": models,
        ]
    }
    if provider == "glm-cn" || provider == "glm-global" {
        if document["success"] as? Bool == false {
            return selected(document, ["success", "code"])
        }
        let data = document["data"] as? [String: Any] ?? document
        guard let limits = selectedArray(data["limits"], ["type", "percentage"], maximum: 16)
        else { return nil }
        var result = selected(document, ["code", "success"])
        result["data"] = ["limits": limits]
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

private func minimizedProviderBody(provider: String, status: Int, body: Data) -> Data? {
    if status != 200 { return Data("{}".utf8) }
    guard
        let document = jsonObject(body),
        let projectionSource = minimizedProviderDocument(provider: provider, document: document),
        JSONSerialization.isValidJSONObject(projectionSource)
    else { return nil }
    return try? JSONSerialization.data(withJSONObject: projectionSource, options: [.sortedKeys])
}

private func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func hmacSHA256(key: Data, message: String) -> Data {
    Data(HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: SymmetricKey(data: key)))
}

private func volcSignedRequest(
    definition: ProviderDefinition,
    accessKeyID: String,
    secretAccessKey: String,
    now: Date = Date()
) -> (url: URL, method: String, headers: [String: String], body: Data?)? {
    guard case let .volcAKSK(service, region, action, version, method) = definition.authMode else {
        return nil
    }
    let body = method == "POST" ? Data("{}".utf8) : nil
    let payloadHash = sha256Hex(body ?? Data())
    let query = "Action=\(action)&Version=\(version)"
    guard let url = URL(string: "https://\(definition.host)/?\(query)") else { return nil }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyyMMdd'T'HHmmss'Z'"
    let xDate = formatter.string(from: now)
    formatter.dateFormat = "yyyyMMdd"
    let shortDate = formatter.string(from: now)
    let signedHeaders = "host;x-content-sha256;x-date"
    let canonicalHeaders = "host:\(definition.host)\nx-content-sha256:\(payloadHash)\nx-date:\(xDate)\n"
    let canonicalRequest = "\(method)\n/\n\(query)\n\(canonicalHeaders)\n\(signedHeaders)\n\(payloadHash)"
    let scope = "\(shortDate)/\(region)/\(service)/request"
    let stringToSign = "HMAC-SHA256\n\(xDate)\n\(scope)\n\(sha256Hex(Data(canonicalRequest.utf8)))"
    let dateKey = hmacSHA256(key: Data(secretAccessKey.utf8), message: shortDate)
    let regionKey = hmacSHA256(key: dateKey, message: region)
    let serviceKey = hmacSHA256(key: regionKey, message: service)
    let signingKey = hmacSHA256(key: serviceKey, message: "request")
    let signature = hmacSHA256(key: signingKey, message: stringToSign)
        .map { String(format: "%02x", $0) }.joined()
    return (
        url,
        method,
        [
            "Accept": "application/json",
            "Authorization": "HMAC-SHA256 Credential=\(accessKeyID)/\(scope), SignedHeaders=\(signedHeaders), Signature=\(signature)",
            "Content-Type": "application/json; charset=utf-8",
            "Host": definition.host,
            "X-Content-Sha256": payloadHash,
            "X-Date": xDate,
        ],
        body
    )
}

private func aliyunPercentEncode(_ value: String) -> String {
    var allowed = CharacterSet.alphanumerics
    allowed.insert(charactersIn: "-_.~")
    return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? ""
}

private func aliyunSignedURL(
    definition: ProviderDefinition,
    accessKeyID: String,
    secretAccessKey: String,
    now: Date = Date(),
    nonce: String = UUID().uuidString
) -> URL? {
    guard case let .aliyunRPC(action, version) = definition.authMode else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.formatOptions = [.withInternetDateTime]
    var parameters = [
        "AccessKeyId": accessKeyID,
        "Action": action,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": nonce,
        "SignatureVersion": "1.0",
        "Timestamp": formatter.string(from: now),
        "Version": version,
    ]
    let canonical = parameters.sorted { $0.key < $1.key }
        .map { "\(aliyunPercentEncode($0.key))=\(aliyunPercentEncode($0.value))" }
        .joined(separator: "&")
    let stringToSign = "GET&%2F&\(aliyunPercentEncode(canonical))"
    let key = SymmetricKey(data: Data("\(secretAccessKey)&".utf8))
    parameters["Signature"] = Data(
        HMAC<Insecure.SHA1>.authenticationCode(for: Data(stringToSign.utf8), using: key)
    ).base64EncodedString()
    let query = parameters.sorted { $0.key < $1.key }
        .map { "\(aliyunPercentEncode($0.key))=\(aliyunPercentEncode($0.value))" }
        .joined(separator: "&")
    return URL(string: "https://\(definition.host)/?\(query)")
}

private func providerFetch(reference: String, provider id: String) -> NativeResponse {
    guard
        isCredentialReference(reference),
        let definition = providerDefinition(id),
        definition.endpoint != nil
    else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    let secret: Data
    do {
        secret = try keychainRead(account: reference)
    } catch NativeFailure.keychain(let status) {
        if status == errSecItemNotFound {
            return NativeResponse(
                status: "provider-response", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil, provider: id, httpStatus: 401,
                bodyBase64: Data("{}".utf8).base64EncodedString()
            )
        }
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: keychainErrorCode(status),
            userPresenceToken: nil, provider: id
        )
    } catch {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "keychain-read-failed",
            userPresenceToken: nil, provider: id
        )
    }
    var credential = ""
    var requestURL: URL
    var requestMethod = "GET"
    var requestHeaders: [String: String] = [:]
    var requestBody: Data?
    switch definition.authMode {
    case .kimiCodeOAuth:
        switch resolveKimiCodeCredential(reference: reference, secret: secret) {
        case .ready(let accessToken):
            credential = accessToken
        case .reauthRequired:
            return NativeResponse(
                status: "provider-response", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil, provider: id, httpStatus: 401,
                bodyBase64: Data("{}".utf8).base64EncodedString()
            )
        case .keychainLocked:
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "keychain-locked",
                userPresenceToken: nil, provider: id
            )
        case .unavailable:
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
                userPresenceToken: nil, provider: id
            )
        }
        guard let endpoint = definition.endpoint else {
            return NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-request", userPresenceToken: nil, provider: id)
        }
        requestURL = endpoint
        requestHeaders = [
            "Accept": "application/json",
            "Accept-Language": "en-US,en",
            "Authorization": "Bearer \(credential)",
        ]
    case .bearer, .raw:
        guard let value = String(data: secret, encoding: .utf8), isSafeCredential(value) else {
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "invalid-secret",
                userPresenceToken: nil, provider: id
            )
        }
        credential = value
        guard let endpoint = definition.endpoint else {
            return NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-request", userPresenceToken: nil, provider: id)
        }
        requestURL = endpoint
        requestHeaders = [
            "Accept": "application/json",
            "Accept-Language": "en-US,en",
            "Authorization": definition.authMode == .raw ? credential : "Bearer \(credential)",
        ]
    case .volcAKSK:
        guard
            let bundle = try? JSONDecoder().decode(CloudKeyBundle.self, from: secret),
            isSafeCredential(bundle.accessKeyID), isSafeCredential(bundle.secretAccessKey),
            let signed = volcSignedRequest(
                definition: definition,
                accessKeyID: bundle.accessKeyID,
                secretAccessKey: bundle.secretAccessKey
            )
        else {
            return NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-secret", userPresenceToken: nil, provider: id)
        }
        requestURL = signed.url
        requestMethod = signed.method
        requestHeaders = signed.headers
        requestBody = signed.body
    case .aliyunRPC:
        guard
            let bundle = try? JSONDecoder().decode(CloudKeyBundle.self, from: secret),
            isSafeCredential(bundle.accessKeyID), isSafeCredential(bundle.secretAccessKey),
            let signedURL = aliyunSignedURL(
                definition: definition,
                accessKeyID: bundle.accessKeyID,
                secretAccessKey: bundle.secretAccessKey
            )
        else {
            return NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-secret", userPresenceToken: nil, provider: id)
        }
        requestURL = signedURL
        requestHeaders = ["Accept": "application/json"]
    }
    guard let response = boundedHTTPRequest(
        url: requestURL,
        method: requestMethod,
        headers: requestHeaders,
        body: requestBody
    ) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
            userPresenceToken: nil, provider: id
        )
    }
    guard let minimizedBody = minimizedProviderBody(
        provider: id,
        status: response.status,
        body: response.body
    ) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "contract-error",
            userPresenceToken: nil, provider: id
        )
    }
    return NativeResponse(
        status: "provider-response", opaqueReference: nil, errorCode: nil,
        userPresenceToken: nil, provider: id, httpStatus: response.status,
        bodyBase64: minimizedBody.base64EncodedString()
    )
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
    let confirmButton = alert.buttons[1]
    confirmButton.isEnabled = false
    let confirmation = NSButton(
        checkboxWithTitle: "我已核对范围，并确认该操作可能不可恢复。",
        target: nil,
        action: nil
    )
    confirmation.state = .off
    confirmation.setAccessibilityLabel("确认破坏性操作范围")
    let gate = DestructiveConfirmationGate()
    gate.confirmButton = confirmButton
    confirmation.target = gate
    confirmation.action = #selector(DestructiveConfirmationGate.update(_:))
    alert.accessoryView = confirmation

    let response = alert.runModal()
    guard
        response == .alertSecondButtonReturn,
        confirmation.state == .on,
        confirmButton.isEnabled
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

@MainActor
private func exportRedacted(contentBase64: String, filename: String) -> NativeResponse {
    guard
        filename == "agent-quota-diagnostics.json",
        let content = Data(base64Encoded: contentBase64),
        content.count <= 2_048,
        let document = try? JSONSerialization.jsonObject(with: content) as? [String: Any],
        Set(document.keys) == [
            "account_count", "lifecycle_counts", "quota", "scheduler", "schema", "security",
        ]
    else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-request",
            userPresenceToken: nil
        )
    }
    prepareApplication()
    let panel = NSSavePanel()
    panel.title = "导出脱敏诊断"
    panel.nameFieldStringValue = filename
    panel.allowedContentTypes = [.json]
    panel.canCreateDirectories = true
    guard panel.runModal() == .OK, let destination = panel.url else {
        return NativeResponse(
            status: "cancelled", opaqueReference: nil, errorCode: nil,
            userPresenceToken: nil
        )
    }
    do {
        try content.write(to: destination, options: .atomic)
        return NativeResponse(
            status: "exported", opaqueReference: nil, errorCode: nil,
            userPresenceToken: nil
        )
    } catch {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "export-write-failed",
            userPresenceToken: nil
        )
    }
}

private func selfTestCredentialLabels() -> Int32 {
    let reference = "credential-a1234567-0000-4000-8000-000000000001"
    let secondReference = "credential-b1234567-0000-4000-8000-000000000001"
    guard let deepseek = providerDefinition("deepseek"), let kimi = providerDefinition("kimi-code")
    else { return 20 }
    guard
        credentialKeychainLabel(reference: reference, provider: deepseek)
            == "Agent Quota · DeepSeek · a1234567",
        credentialKeychainLabel(reference: "credential-A1234567-0000-4000-8000-000000000001", provider: deepseek)
            == "Agent Quota · DeepSeek · a1234567",
        credentialKeychainLabel(reference: reference.uppercased(), provider: deepseek) == nil,
        credentialKeychainLabel(reference: "credential-a1234567-invalid", provider: deepseek) == nil,
        credentialKeychainLabel(reference: "secret-not-a-reference", provider: deepseek) == nil,
        credentialKeychainLabel(reference: secondReference, provider: deepseek)
            != credentialKeychainLabel(reference: reference, provider: deepseek),
        credentialKeychainLabel(reference: reference, provider: kimi)
            != credentialKeychainLabel(reference: reference, provider: deepseek),
        providers.allSatisfy({ provider in
            credentialKeychainLabel(reference: reference, provider: provider)
                == "Agent Quota · \(provider.label) · a1234567"
        })
    else { return 21 }
    let validRequest = #"{"action":"keychain-rename","opaqueReference":"credential-a1234567-0000-4000-8000-000000000001","provider":"deepseek"}"#
    guard (try? NativeRequest(data: Data(validRequest.utf8)))?.action == "keychain-rename" else { return 37 }
    let invalidRequests = [
        #"{"action":"keychain-rename","opaqueReference":"credential-a1234567-0000-4000-8000-000000000001"}"#,
        #"{"action":"keychain-rename","opaqueReference":"credential-a1234567-0000-4000-8000-000000000001","provider":"deepseek","label":"override"}"#,
        #"{"action":"keychain-rename","opaqueReference":"credential-a1234567-0000-4000-8000-000000000001","provider":"deepseek","service":"override"}"#,
        #"{"action":"keychain-rename","opaqueReference":"credential-a1234567-0000-4000-8000-000000000001","provider":"deepseek","dialogPurpose":"replace-credential-reference"}"#,
    ]
    guard invalidRequests.allSatisfy({ (try? NativeRequest(data: Data($0.utf8))) == nil }) else { return 38 }
    return 0
}

private func keychainACLSnapshot(account: String, keychain: SecKeychain? = nil) throws -> [[String: Any]] {
    let attributes = try keychainAttributes(account: account, keychain: keychain)
    guard let item = attributes[kSecValueRef] else {
        throw NativeFailure.keychain(errSecInternalComponent)
    }
    var status: OSStatus = errSecSuccess
    guard let snapshot = AQKeychainCopyACLSnapshot(item as CFTypeRef, &status) as? [[String: Any]],
          status == errSecSuccess
    else { throw NativeFailure.keychain(status) }
    return snapshot
}

private func selfTestKeychainMetadata(provider: ProviderDefinition, keychain: SecKeychain) throws -> Int32 {
    // Every query targets one fresh random reference in an isolated test keychain. Do not
    // execute an ACL write: even a legacy noninteractive update may start SecurityAgent.
    let legacy = "credential-\(UUID().uuidString.lowercased())"
    let partial = "credential-\(UUID().uuidString.lowercased())"
    let custom = "credential-\(UUID().uuidString.lowercased())"
    let current = "credential-\(UUID().uuidString.lowercased())"
    let accounts = [legacy, partial, custom, current]
    defer { for account in accounts { _ = keychainDelete(account: account, keychain: keychain) } }
    let testSecret = Data("temporary-agent-quota-metadata-self-test".utf8)
    for account in accounts {
        let label = credentialKeychainLabel(reference: account, provider: provider)!
        let storedLabel = account == custom ? "User custom credential name"
            : account == legacy ? legacyCredentialLabel : label
        var access: SecAccess?
        let descriptor = account == current ? label : legacyCredentialLabel
        let status = AQKeychainCreateAccess(descriptor as CFString, &access)
        guard status == errSecSuccess, let access else { return 29 }
        let addStatus = SecItemAdd([
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
            kSecAttrLabel: storedLabel,
            kSecAttrAccess: access,
            kSecAttrAccessible: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            kSecValueData: testSecret,
            kSecUseKeychain: keychain,
        ] as CFDictionary, nil)
        guard addStatus == errSecSuccess else { return 30 }
    }
    for account in accounts {
        let beforeAttributes = try keychainAttributes(account: account, keychain: keychain)
        let beforeACL = try keychainACLSnapshot(account: account, keychain: keychain)
        let label = credentialKeychainLabel(reference: account, provider: provider)!
        guard let item = beforeAttributes[kSecValueRef] else { return 23 }
        var plannedAccess: SecAccess?
        var changed = false
        let planStatus = AQKeychainCopyAccessRenamingDescription(
            item as CFTypeRef, legacyCredentialLabel as CFString, label as CFString,
            &plannedAccess, &changed
        )
        guard planStatus == errSecSuccess, let plannedAccess else { return 24 }
        var snapshotStatus: OSStatus = errSecSuccess
        guard let plannedACL = AQKeychainCopyACLSnapshot(plannedAccess, &snapshotStatus) as? [[String: Any]],
              snapshotStatus == errSecSuccess
        else { return 25 }
        let expectedACL = beforeACL.map { entry -> [String: Any] in
            var result = entry
            if result["description"] as? String == legacyCredentialLabel {
                result["description"] = label
            }
            return result
        }
        // Verify the public app data (paths), authorization tags, prompt flags, and every
        // nonmatching descriptor. The bridge reuses the trusted-app objects; this snapshot
        // does not claim to serialize their private code-signing requirements.
        guard NSArray(array: plannedACL).isEqual(to: expectedACL), changed == (account != current)
        else { return 26 }
        // Only the two no-write branches may call the actual maintenance function in tests.
        if account == custom || account == current {
            let migration = migrateCredentialKeychainLabel(account: account, provider: provider, keychain: keychain)
            let expectedMigration: CredentialLabelMigration = account == custom ? .customLabelPreserved : .unchanged
            guard migration == expectedMigration else { return 31 }
        }
        let afterAttributes = try keychainAttributes(account: account, keychain: keychain)
        guard NSArray(array: try keychainACLSnapshot(account: account, keychain: keychain)).isEqual(to: beforeACL),
              afterAttributes[kSecAttrLabel] as? String == beforeAttributes[kSecAttrLabel] as? String,
              afterAttributes[kSecAttrAccount] as? String == account,
              afterAttributes[kSecAttrService] as? String == service,
              (afterAttributes[kSecAttrAccessible] as? String)
                == (beforeAttributes[kSecAttrAccessible] as? String),
              try keychainRead(account: account, keychain: keychain) == testSecret
        else { return 32 }
    }
    return 0
}

private func selfTestKeychain(path: String? = nil) -> Int32 {
    guard let provider = providerDefinition("deepseek") else { return 20 }
    let nameStatus = selfTestCredentialLabels()
    guard nameStatus == 0 else { return nameStatus }
    var wasInteractionAllowed = false
    guard AQKeychainBeginNoninteractive(&wasInteractionAllowed) == errSecSuccess else { return 27 }
    defer { _ = AQKeychainRestoreInteraction(wasInteractionAllowed) }
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "agent-quota-keychain-self-test-\(UUID().uuidString.lowercased())", isDirectory: true
    )
    var openedKeychain: SecKeychain?
    if let path {
        guard path.hasPrefix("/"), AQKeychainOpenForSelfTest(path, &openedKeychain) == errSecSuccess
        else { return 33 }
    } else {
        do { try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false) }
        catch { return 34 }
        let password = Data(UUID().uuidString.utf8)
        let status = AQKeychainCreateForSelfTest(
            directory.appendingPathComponent("isolated.keychain-db").path,
            password as CFData, &openedKeychain
        )
        guard status == errSecSuccess else {
            try? FileManager.default.removeItem(at: directory)
            return 35
        }
    }
    guard let keychain = openedKeychain else { return 36 }
    defer {
        if path == nil {
            _ = AQKeychainDeleteForSelfTest(keychain)
            try? FileManager.default.removeItem(at: directory)
        }
    }
    let account = "credential-\(UUID().uuidString.lowercased())"
    var first = Array("temporary-agent-quota-self-test-a".utf8)
    var second = Array("temporary-agent-quota-self-test-b".utf8)
    defer { _ = keychainDelete(account: account, keychain: keychain) }
    do {
        try keychainAdd(account: account, provider: provider, secret: &first, keychain: keychain)
        let label = credentialKeychainLabel(reference: account, provider: provider)!
        let attributes = try keychainAttributes(account: account, keychain: keychain)
        let snapshot = try keychainACLSnapshot(account: account, keychain: keychain)
        guard attributes[kSecAttrLabel] as? String == label,
              snapshot.contains(where: { $0["description"] as? String == label }),
              !snapshot.contains(where: { $0["description"] as? String == legacyCredentialLabel })
        else { return 28 }
        guard try keychainRead(account: account, keychain: keychain) == Data(
            "temporary-agent-quota-self-test-a".utf8
        ) else { return 3 }
        try keychainUpdate(account: account, secret: &second, keychain: keychain)
        guard try keychainRead(account: account, keychain: keychain) == Data(
            "temporary-agent-quota-self-test-b".utf8
        ) else { return 4 }
        guard keychainDelete(account: account, keychain: keychain) == errSecSuccess else { return 5 }
        do {
            _ = try keychainRead(account: account, keychain: keychain)
            return 6
        } catch NativeFailure.keychain(let status) where status == errSecItemNotFound {}
        let metadataStatus = try selfTestKeychainMetadata(provider: provider, keychain: keychain)
        guard metadataStatus == 0 else { return metadataStatus }
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

private func selfTestProviderMinimization() -> Int32 {
    guard
        creatableProviders.map(\.id) == creatableProviderIDs,
        Set(creatableProviderIDs).count == 5
    else { return 9 }
    let samples = [
        ("deepseek", #"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"1","account_id":"sensitive"}],"user":{"email":"sensitive"}}"#),
        ("bailian-wallet", #"{"Code":"200","Success":true,"RequestId":"sensitive","Data":{"AvailableAmount":"100","AvailableCashAmount":"90","CreditAmount":"10","MybankCreditAmount":"0","Currency":"CNY","AccountID":"sensitive"}}"#),
        ("kimi-cn", #"{"code":0,"data":{"available_balance":1,"cash_balance":1,"voucher_balance":0,"account_id":"sensitive"},"user":{"email":"sensitive"}}"#),
        ("kimi-code", #"{"usage":{"limit":"10","remaining":"9","userId":"sensitive"},"limits":[{"window":{"duration":300,"timeUnit":"TIME_UNIT_MINUTE","region":"sensitive"},"detail":{"limit":"10","remaining":"9","businessId":"sensitive"}}],"authentication":{"scope":"sensitive"},"user":{"email":"sensitive"}}"#),
        ("minimax-cn", #"{"base_resp":{"status_code":0,"trace_id":"sensitive"},"model_remains":[{"model_name":"general","current_interval_remaining_percent":90,"current_weekly_remaining_percent":80,"current_weekly_status":1,"account_id":"sensitive"}],"user":{"email":"sensitive"}}"#),
        ("glm-cn", #"{"code":200,"success":true,"data":{"limits":[{"type":"TOKENS_LIMIT","percentage":1,"account_id":"sensitive"}],"user":{"email":"sensitive"}}}"#),
        ("volc-wallet", #"{"ResponseMetadata":{"RequestId":"sensitive"},"Result":{"AccountID":210000001,"AvailableBalance":"77.01","CashBalance":"83.01","CreditLimit":"0.01","FreezeAmount":"5.01","ArrearsBalance":"1.01"}}"#),
        ("volc-plan", #"{"ResponseMetadata":{"RequestId":"sensitive"},"Result":{"PlanType":"AFP","AFPFiveHour":{"Quota":1000,"Used":250,"SubscribeTime":1,"ResetTime":2,"AccountID":"sensitive"},"AFPWeekly":{"Quota":8000,"Used":2000,"SubscribeTime":1,"ResetTime":2}}}"#),
    ]
    for (provider, source) in samples {
        guard
            let minimized = minimizedProviderBody(
                provider: provider,
                status: 200,
                body: Data(source.utf8)
            ),
            let output = String(data: minimized, encoding: .utf8),
            !output.contains("sensitive")
        else { return 10 }
    }
    guard
        minimizedProviderBody(provider: "kimi-code", status: 401, body: Data("secret".utf8))
            == Data("{}".utf8),
        isSafeCredential("valid-token_123"),
        !isSafeCredential("injected\r\nHeader: value")
    else { return 11 }
    var components = DateComponents()
    components.calendar = Calendar(identifier: .gregorian)
    components.timeZone = TimeZone(secondsFromGMT: 0)
    components.year = 2026
    components.month = 8
    components.day = 11
    components.hour = 1
    components.minute = 2
    components.second = 3
    guard
        let date = components.date,
        let definition = providerDefinition("volc-plan"),
        let signed = volcSignedRequest(
            definition: definition,
            accessKeyID: "AKTEST",
            secretAccessKey: "secret-test",
            now: date
        ),
        signed.method == "POST",
        signed.body == Data("{}".utf8),
        signed.headers["X-Date"] == "20260811T010203Z",
        signed.headers["Authorization"]?.hasSuffix(
            "Signature=5f7d529b3da7006b514b96c46fb6fac1057502509b27eb13cfb766e94ce7b662"
        ) == true
    else { return 12 }
    guard
        let aliyunDefinition = providerDefinition("bailian-wallet"),
        let aliyunURL = aliyunSignedURL(
            definition: aliyunDefinition,
            accessKeyID: "testid",
            secretAccessKey: "testsecret",
            now: date,
            nonce: "nonce-test"
        ),
        aliyunURL.absoluteString.contains("Signature=tQPS4ljhN8dSSmBREFGdrt4RugM%3D"),
        aliyunURL.absoluteString.contains("Timestamp=2026-08-11T01%3A02%3A03Z")
    else { return 13 }
    guard
        let walletDefinition = providerDefinition("volc-wallet"),
        let walletSigned = volcSignedRequest(
            definition: walletDefinition,
            accessKeyID: "AKTEST",
            secretAccessKey: "secret-test",
            now: date
        ),
        walletSigned.method == "POST",
        walletSigned.body == Data("{}".utf8),
        walletSigned.headers["Authorization"]?.hasSuffix(
            "Signature=6688c394846c619523648413a14245ac671d5540e2b055ed40bcf553e4b16faa"
        ) == true
    else { return 14 }
    return 0
}

@main
private struct AgentQuotaNative {
    @MainActor
    static func main() {
        let arguments = ProcessInfo.processInfo.arguments
        if (2...3).contains(arguments.count) && arguments[1] == "--self-test-keychain" {
            exit(selfTestKeychain(path: arguments.count == 3 ? arguments[2] : nil))
        }
        if arguments.count == 2 && arguments[1] == "--self-test-credential-labels" {
            exit(selfTestCredentialLabels())
        }
        if arguments.count == 2 && arguments[1] == "--self-test-provider-minimization" {
            exit(selfTestProviderMinimization())
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
                guard let purpose = request.dialogPurpose, let reference = request.opaqueReference else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = credentialDialog(
                    purpose: purpose,
                    reference: reference,
                    provider: request.provider
                )
            case "provider-fetch":
                guard let reference = request.opaqueReference, let provider = request.provider else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = providerFetch(reference: reference, provider: provider)
            case "keychain-rename":
                guard let reference = request.opaqueReference, let provider = request.provider else {
                    emit(NativeResponse(
                        status: "error", opaqueReference: nil, errorCode: "invalid-request",
                        userPresenceToken: nil
                    ))
                    exit(64)
                }
                response = renameCredentialReference(reference, provider: provider)
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
            case "export-redacted":
                guard
                    let content = request.exportContentBase64,
                    let filename = request.exportFilename
                else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = exportRedacted(contentBase64: content, filename: filename)
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
