import AppKit
import Foundation
import Security

private let service = "com.agentquota.desktop.credentials.v1"
private let maxRequestBytes = 4096
private let maxResponseBytes = 384 * 1024
private let maxProviderBodyBytes = 256 * 1024
private let kimiCodeOAuthHost = "auth.kimi.com"
private let kimiCodeOAuthClientID = "17e5f671-d194-4dfb-9706-5516cb48c098"

private enum ProviderAuthMode: Equatable {
    case bearer
    case raw
    case kimiCodeOAuth
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
    ProviderDefinition(id: "deepseek", label: "DeepSeek", host: "api.deepseek.com", path: "/user/balance", authMode: .bearer),
    ProviderDefinition(id: "glm-cn", label: "GLM Coding Plan（中国区）", host: "open.bigmodel.cn", path: "/api/monitor/usage/quota/limit", authMode: .raw),
    ProviderDefinition(id: "glm-global", label: "GLM Coding Plan（国际区）", host: "api.z.ai", path: "/api/monitor/usage/quota/limit", authMode: .raw),
    ProviderDefinition(id: "kimi-cn", label: "Kimi API 余额（中国区）", host: "api.moonshot.cn", path: "/v1/users/me/balance", authMode: .bearer),
    ProviderDefinition(id: "kimi-global", label: "Kimi API 余额（国际区）", host: "api.moonshot.ai", path: "/v1/users/me/balance", authMode: .bearer),
    ProviderDefinition(id: "kimi-code", label: "Kimi Code Token Plan", host: "api.kimi.com", path: "/coding/v1/usages", authMode: .kimiCodeOAuth),
    ProviderDefinition(id: "minimax-cn", label: "MiniMax Token Plan（中国区）", host: "www.minimaxi.com", path: "/v1/token_plan/remains", authMode: .bearer),
    ProviderDefinition(id: "minimax-global", label: "MiniMax Token Plan（国际区）", host: "www.minimax.io", path: "/v1/token_plan/remains", authMode: .bearer),
]

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
                ? ["action", "dialogPurpose", "provider"]
                : ["action", "dialogPurpose"]
        case "provider-fetch":
            required = ["action", "opaqueReference", "provider"]
        case "destructive":
            required = [
                "action", "generation", "nonce", "operationIntent", "planDigest", "planSummary",
            ]
        case "keychain-delete":
            required = ["action", "opaqueReference"]
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
        for item in [
            dialogPurpose, operationIntent, planSummary, planDigest, nonce, opaqueReference, provider,
        ].compactMap({ $0 }) where item.isEmpty || item.utf8.count > 256 {
            throw NativeFailure.invalidRequest
        }
    }

    private static let allowedKeys: Set<String> = [
        "action", "dialogPurpose", "generation", "nonce", "opaqueReference",
        "operationIntent", "planDigest", "planSummary", "provider",
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
private func credentialDialog(purpose: String, provider requestedProvider: String?) -> NativeResponse {
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
    alert.informativeText = "API Key/Token 可直接粘贴；Kimi Code 使用官方 OAuth 设备登录。凭据只写入 macOS 钥匙串。"
    alert.addButton(withTitle: "继续")
    alert.addButton(withTitle: "取消")

    let container = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 88))
    let selector = NSPopUpButton(frame: NSRect(x: 0, y: 54, width: 360, height: 28))
    for item in providers { selector.addItem(withTitle: item.label) }
    selector.isHidden = purpose == "replace-credential-reference"
    container.addSubview(selector)
    let secure = PasteSecureTextField(frame: NSRect(x: 0, y: 18, width: 360, height: 28))
    secure.placeholderString = "API Key / Token（Kimi Code 留空）"
    secure.setAccessibilityLabel("本机安全凭据")
    let secureMenu = NSMenu()
    secureMenu.addItem(
        withTitle: "Paste",
        action: #selector(NSText.paste(_:)),
        keyEquivalent: ""
    )
    secure.menu = secureMenu
    container.addSubview(secure)
    alert.accessoryView = container
    alert.window.initialFirstResponder = secure

    // The modal result is captured before normal helper deactivation. Treating
    // didResignActive as cancellation races every successful modal teardown.
    guard alert.runModal() == .alertFirstButtonReturn else {
        secure.stringValue = ""
        return NativeResponse(
            status: "cancelled", opaqueReference: nil, errorCode: nil, userPresenceToken: nil
        )
    }
    let selectedProvider = purpose == "replace-credential-reference"
        ? requestedProvider
        : providers[selector.indexOfSelectedItem].id
    guard let selectedProvider, let definition = providerDefinition(selectedProvider) else {
        secure.stringValue = ""
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "invalid-provider",
            userPresenceToken: nil
        )
    }
    var bytes: [UInt8]
    if definition.authMode == .kimiCodeOAuth {
        secure.stringValue = ""
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
    } else {
        bytes = Array(secure.stringValue.utf8)
        secure.stringValue = ""
        guard let value = String(bytes: bytes, encoding: .utf8), isSafeCredential(value) else {
            bytes.resetBytes(in: bytes.indices)
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "invalid-secret",
                userPresenceToken: nil
            )
        }
    }
    let reference = "credential-\(UUID().uuidString.lowercased())"
    do {
        try keychainAdd(account: reference, secret: &bytes)
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

private func providerFetch(reference: String, provider id: String) -> NativeResponse {
    guard
        isCredentialReference(reference),
        let definition = providerDefinition(id),
        let url = definition.endpoint
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
    let credential: String
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
    case .bearer, .raw:
        guard let value = String(data: secret, encoding: .utf8), isSafeCredential(value) else {
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "invalid-secret",
                userPresenceToken: nil, provider: id
            )
        }
        credential = value
    }
    let authorization = definition.authMode == .raw ? credential : "Bearer \(credential)"
    guard let response = boundedHTTPRequest(
        url: url,
        method: "GET",
        headers: [
            "Accept": "application/json",
            "Accept-Language": "en-US,en",
            "Authorization": authorization,
        ]
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

private func selfTestKeychain() -> Int32 {
    let account = "self-test-\(UUID().uuidString.lowercased())"
    var first = Array("temporary-agent-quota-self-test-a".utf8)
    var second = Array("temporary-agent-quota-self-test-b".utf8)
    defer { _ = keychainDelete(account: account) }
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
    let samples = [
        ("deepseek", #"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"1","account_id":"sensitive"}],"user":{"email":"sensitive"}}"#),
        ("kimi-cn", #"{"code":0,"data":{"available_balance":1,"cash_balance":1,"voucher_balance":0,"account_id":"sensitive"},"user":{"email":"sensitive"}}"#),
        ("kimi-code", #"{"usage":{"limit":"10","remaining":"9","userId":"sensitive"},"limits":[{"window":{"duration":300,"timeUnit":"TIME_UNIT_MINUTE","region":"sensitive"},"detail":{"limit":"10","remaining":"9","businessId":"sensitive"}}],"authentication":{"scope":"sensitive"},"user":{"email":"sensitive"}}"#),
        ("minimax-cn", #"{"base_resp":{"status_code":0,"trace_id":"sensitive"},"model_remains":[{"model_name":"general","current_interval_remaining_percent":90,"current_weekly_remaining_percent":80,"current_weekly_status":1,"account_id":"sensitive"}],"user":{"email":"sensitive"}}"#),
        ("glm-cn", #"{"code":200,"success":true,"data":{"limits":[{"type":"TOKENS_LIMIT","percentage":1,"account_id":"sensitive"}],"user":{"email":"sensitive"}}}"#),
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
    return 0
}

@main
private struct AgentQuotaNative {
    @MainActor
    static func main() {
        if CommandLine.arguments == [CommandLine.arguments[0], "--self-test-keychain"] {
            exit(selfTestKeychain())
        }
        if CommandLine.arguments == [CommandLine.arguments[0], "--self-test-provider-minimization"] {
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
                guard let purpose = request.dialogPurpose else {
                    emit(
                        NativeResponse(
                            status: "error", opaqueReference: nil, errorCode: "invalid-request",
                            userPresenceToken: nil
                        )
                    )
                    exit(64)
                }
                response = credentialDialog(purpose: purpose, provider: request.provider)
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
