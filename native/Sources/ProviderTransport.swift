import AppKit
import CryptoKit
import Foundation
import Network
import Security
import UniformTypeIdentifiers

final class BoundedProviderDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
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

struct BoundedHTTPResult {
    let status: Int
    let body: Data
}

func fixedHTTPSURL(host: String, path: String) -> URL? {
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

func boundedHTTPRequest(
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

func formBody(_ fields: [(String, String)]) -> Data? {
    var components = URLComponents()
    components.queryItems = fields.map { URLQueryItem(name: $0.0, value: $0.1) }
    return components.percentEncodedQuery?.data(using: .utf8)
}

func jsonObject(_ data: Data) -> [String: Any]? {
    try? JSONSerialization.jsonObject(with: data) as? [String: Any]
}

func positiveInt64(_ value: Any?) -> Int64? {
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

func kimiCodeTokenBundle(_ document: [String: Any]) -> KimiCodeTokenBundle? {
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

func encodedKimiCodeTokenBundle(_ bundle: KimiCodeTokenBundle) -> [UInt8]? {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(bundle), data.count <= 32_768 else { return nil }
    return Array(data)
}

@MainActor
func kimiCodeOAuthCredential() -> (credential: [UInt8]?, errorCode: String?) {
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
    let authorizationLifetime = min(max(positiveInt64(document["expires_in"]) ?? 180, 45), 180)
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

enum KimiCodeCredentialResolution {
    case ready(String)
    case reauthRequired
    case keychainLocked
    case unavailable
}

func isKimiCodeReauthResponse(status: Int, body: Data) -> Bool {
    if status == 401 || status == 403 {
        return true
    }
    guard status == 400, let document = jsonObject(body), let error = document["error"] as? String else {
        return false
    }
    return ["invalid_grant", "invalid_token", "expired_token", "access_denied"].contains(error)
}

func resolveKimiCodeCredential(reference: String, secret: Data) -> KimiCodeCredentialResolution {
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
        if isKimiCodeReauthResponse(status: response.status, body: response.body) {
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

func randomBase64URL(byteCount: Int) -> String? {
    var bytes = [UInt8](repeating: 0, count: byteCount)
    guard SecRandomCopyBytes(kSecRandomDefault, byteCount, &bytes) == errSecSuccess else {
        return nil
    }
    return Data(bytes).base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}

func pkceCodeChallenge(verifier: String) -> String {
    Data(SHA256.hash(data: Data(verifier.utf8))).base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}

final class LoopbackOAuthServer: @unchecked Sendable {
    private let expectedState: String
    private let lock = NSLock()
    private let queue = DispatchQueue(label: "com.agentquota.oauth.loopback")
    private var listener: NWListener?
    private var portValue: UInt16?
    private var codeValue: String?
    private var errorValue: String?
    private let readySemaphore = DispatchSemaphore(value: 0)
    private let callbackSemaphore = DispatchSemaphore(value: 0)
    private var didSignalReady = false
    private var didSignalCallback = false

    init(expectedState: String) {
        self.expectedState = expectedState
    }

    func start() -> UInt16? {
        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = NWEndpoint.hostPort(host: .ipv4(.loopback), port: .any)
        guard let listener = try? NWListener(using: parameters) else { return nil }
        lock.lock()
        self.listener = listener
        lock.unlock()
        listener.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                self.lock.lock()
                self.portValue = listener.port?.rawValue
                let shouldSignal = !self.didSignalReady
                self.didSignalReady = true
                self.lock.unlock()
                if shouldSignal { self.readySemaphore.signal() }
            case .failed, .cancelled:
                self.lock.lock()
                let shouldSignal = !self.didSignalReady
                self.didSignalReady = true
                self.lock.unlock()
                if shouldSignal { self.readySemaphore.signal() }
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            self?.handleConnection(connection)
        }
        listener.start(queue: queue)
        guard readySemaphore.wait(timeout: .now() + 5) == .success else {
            stop()
            return nil
        }
        lock.lock()
        let boundPort = portValue
        lock.unlock()
        return boundPort
    }

    private func handleConnection(_ connection: NWConnection) {
        connection.start(queue: queue)
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16_384) { [weak self] data, _, _, _ in
            guard let self else {
                connection.cancel()
                return
            }
            var statusLine = "HTTP/1.1 400 Bad Request"
            var message = "Invalid OAuth callback request."
            if let data,
               let text = String(data: data, encoding: .utf8),
               let firstLine = text.components(separatedBy: "\r\n").first
            {
                let parts = firstLine.split(separator: " ", omittingEmptySubsequences: true)
                if parts.count >= 2, parts[0] == "GET",
                   let components = URLComponents(string: "http://127.0.0.1" + String(parts[1])),
                   components.path == "/oauth-callback"
                {
                    let items = Dictionary(
                        (components.queryItems ?? []).map { ($0.name, $0.value ?? "") },
                        uniquingKeysWith: { first, _ in first }
                    )
                    if items["state"] == self.expectedState {
                        if let code = items["code"], !code.isEmpty {
                            self.recordResult(code: code, error: nil)
                            statusLine = "HTTP/1.1 200 OK"
                            message = "Authorization complete — you may close this browser tab and return to Agent Quota."
                        } else if let error = items["error"], !error.isEmpty {
                            self.recordResult(code: nil, error: error)
                            statusLine = "HTTP/1.1 200 OK"
                            message = "Authorization cancelled or denied — you may close this browser tab."
                        }
                    }
                }
            }
            let html = "<!doctype html><html><meta charset=\"utf-8\"><body><p>\(message)</p></body></html>"
            let raw = "\(statusLine)\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n\(html)"
            connection.send(content: Data(raw.utf8), completion: .contentProcessed { _ in
                connection.cancel()
            })
        }
    }

    private func recordResult(code: String?, error: String?) {
        lock.lock()
        if codeValue == nil && errorValue == nil {
            codeValue = code
            errorValue = error
            let shouldSignal = !didSignalCallback
            didSignalCallback = true
            lock.unlock()
            if shouldSignal { callbackSemaphore.signal() }
            Task { @MainActor in
                if NSApp.modalWindow != nil {
                    NSApp.abortModal()
                }
            }
        } else {
            lock.unlock()
        }
    }

    func result() -> (code: String?, error: String?) {
        lock.lock()
        defer { lock.unlock() }
        return (codeValue, errorValue)
    }

    func waitShort(seconds: TimeInterval = 2) -> (code: String?, error: String?) {
        _ = callbackSemaphore.wait(timeout: .now() + seconds)
        return result()
    }

    func stop() {
        lock.lock()
        let active = listener
        listener = nil
        lock.unlock()
        active?.cancel()
    }
}

func antigravityManualCallbackCode(_ rawInput: String, expectedState: String) -> String? {
    let trimmed = rawInput.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty, trimmed.utf8.count <= 4096 else { return nil }
    if trimmed.hasPrefix("http://") || trimmed.hasPrefix("https://"),
       let components = URLComponents(string: trimmed)
    {
        let items = Dictionary(
            (components.queryItems ?? []).map { ($0.name, $0.value ?? "") },
            uniquingKeysWith: { first, _ in first }
        )
        if let state = items["state"], state != expectedState {
            return nil
        }
        guard let code = items["code"], !code.isEmpty, isSafeCredential(code) else { return nil }
        return code
    }
    guard isSafeCredential(trimmed) else { return nil }
    return trimmed
}

func antigravityTokenBundle(
    from document: [String: Any],
    existingRefreshToken: String? = nil,
    projectID: String = "",
    clientID: String,
    clientSecret: String
) -> AntigravityTokenBundle? {
    let now = Int64(Date().timeIntervalSince1970)
    guard
        let accessToken = document["access_token"] as? String,
        isSafeCredential(accessToken),
        let expiresIn = positiveInt64(document["expires_in"]),
        expiresIn <= Int64.max - now
    else { return nil }
    let refreshToken = (document["refresh_token"] as? String) ?? existingRefreshToken ?? ""
    guard isSafeCredential(refreshToken) else { return nil }
    return AntigravityTokenBundle(
        accessToken: accessToken,
        refreshToken: refreshToken,
        expiresAt: now + expiresIn,
        projectID: projectID,
        clientID: clientID,
        clientSecret: clientSecret
    )
}

func encodedAntigravityTokenBundle(_ bundle: AntigravityTokenBundle) -> [UInt8]? {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(bundle), data.count <= 32_768 else { return nil }
    return Array(data)
}

@MainActor
func antigravityOAuthCredential(
    clientIDOverride: String,
    clientSecretOverride: String
) -> (credential: [UInt8]?, errorCode: String?) {
    let clientID = clientIDOverride.isEmpty ? antigravityDefaultOAuthClientID : clientIDOverride
    let clientSecret = clientSecretOverride.isEmpty ? antigravityDefaultOAuthClientSecret : clientSecretOverride
    guard isSafeCredential(clientID) else {
        return (nil, "oauth-client-unconfigured")
    }
    guard
        let verifier = randomBase64URL(byteCount: 32),
        let state = randomBase64URL(byteCount: 24)
    else { return (nil, "provider-unavailable") }
    let challenge = pkceCodeChallenge(verifier: verifier)

    let server = LoopbackOAuthServer(expectedState: state)
    defer { server.stop() }
    guard let port = server.start() else {
        return (nil, "provider-unavailable")
    }
    let redirectURI = "http://127.0.0.1:\(port)/oauth-callback"
    var authComponents = URLComponents()
    authComponents.scheme = "https"
    authComponents.host = antigravityOAuthAuthHost
    authComponents.path = "/o/oauth2/auth"
    authComponents.queryItems = [
        URLQueryItem(name: "client_id", value: clientID),
        URLQueryItem(name: "redirect_uri", value: redirectURI),
        URLQueryItem(name: "response_type", value: "code"),
        URLQueryItem(name: "scope", value: "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/cclog https://www.googleapis.com/auth/experimentsandconfigs"),
        URLQueryItem(name: "access_type", value: "offline"),
        URLQueryItem(name: "prompt", value: "consent"),
        URLQueryItem(name: "include_granted_scopes", value: "true"),
        URLQueryItem(name: "code_challenge", value: challenge),
        URLQueryItem(name: "code_challenge_method", value: "S256"),
        URLQueryItem(name: "state", value: state),
    ]
    guard
        let authURL = authComponents.url,
        authURL.scheme == "https",
        authURL.host == antigravityOAuthAuthHost,
        NSWorkspace.shared.open(authURL)
    else { return (nil, "provider-unavailable") }

    let alert = NSAlert()
    alert.alertStyle = .informational
    alert.messageText = "登录 Google Antigravity"
    alert.informativeText = "已在浏览器打开官方 Google 授权页。完成授权后本窗口会自动继续；若浏览器未自动回跳，可粘贴回调 URL 后点击继续。"
    let callbackField = NSTextField(frame: NSRect(x: 0, y: 0, width: 340, height: 26))
    callbackField.placeholderString = "可选：手动粘贴完整回调 URL 或授权码"
    alert.accessoryView = callbackField
    alert.addButton(withTitle: "我已完成授权")
    alert.addButton(withTitle: "取消")
    let modalResponse = alert.runModal()
    let manualText = callbackField.stringValue
    callbackField.stringValue = ""

    var authCode = server.result().code
    if let callbackError = server.result().error {
        return (nil, callbackError == "access_denied" ? "not-authorized" : "provider-unavailable")
    }
    if authCode == nil {
        if modalResponse == .alertSecondButtonReturn {
            return (nil, nil)
        }
        if let parsedManual = antigravityManualCallbackCode(manualText, expectedState: state) {
            authCode = parsedManual
        } else {
            let late = server.waitShort(seconds: 3)
            if let lateError = late.error {
                return (nil, lateError == "access_denied" ? "not-authorized" : "provider-unavailable")
            }
            authCode = late.code
        }
    }
    guard let code = authCode,
          let tokenURL = fixedHTTPSURL(host: antigravityOAuthTokenHost, path: "/token")
    else { return (nil, "not-authorized") }

    var fields = [
        ("code", code),
        ("client_id", clientID),
        ("redirect_uri", redirectURI),
        ("grant_type", "authorization_code"),
        ("code_verifier", verifier),
    ]
    if !clientSecret.isEmpty {
        fields.append(("client_secret", clientSecret))
    }
    guard
        let body = formBody(fields),
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
    else { return (nil, "provider-unavailable") }
    if isKimiCodeReauthResponse(status: response.status, body: response.body) {
        return (nil, "not-authorized")
    }
    guard
        response.status == 200,
        let tokenDocument = jsonObject(response.body),
        let bundle = antigravityTokenBundle(
            from: tokenDocument,
            clientID: clientID,
            clientSecret: clientSecret
        ),
        let encoded = encodedAntigravityTokenBundle(bundle)
    else { return (nil, "provider-unavailable") }
    return (encoded, nil)
}

enum OAuthRefreshFailure: Error {
    case reauthRequired
    case keychainLocked
    case unavailable
}

func refreshAntigravityBundle(reference: String, bundle: AntigravityTokenBundle) -> Result<AntigravityTokenBundle, OAuthRefreshFailure> {
    guard let tokenURL = fixedHTTPSURL(host: antigravityOAuthTokenHost, path: "/token") else {
        return .failure(.unavailable)
    }
    var fields = [
        ("client_id", bundle.clientID),
        ("grant_type", "refresh_token"),
        ("refresh_token", bundle.refreshToken),
    ]
    if !bundle.clientSecret.isEmpty {
        fields.append(("client_secret", bundle.clientSecret))
    }
    guard
        let body = formBody(fields),
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
    else { return .failure(.unavailable) }
    if isKimiCodeReauthResponse(status: response.status, body: response.body) {
        return .failure(.reauthRequired)
    }
    guard
        response.status == 200,
        let document = jsonObject(response.body),
        let refreshed = antigravityTokenBundle(
            from: document,
            existingRefreshToken: bundle.refreshToken,
            projectID: bundle.projectID,
            clientID: bundle.clientID,
            clientSecret: bundle.clientSecret
        ),
        let encoded = encodedAntigravityTokenBundle(refreshed)
    else { return .failure(.unavailable) }
    var bytes = encoded
    do {
        try keychainUpdate(account: reference, secret: &bytes)
    } catch NativeFailure.keychain(let status)
        where status == errSecInteractionNotAllowed || status == errSecAuthFailed
    {
        return .failure(.keychainLocked)
    } catch {
        return .failure(.unavailable)
    }
    return .success(refreshed)
}

func cloudCodeRequest(path: String, accessToken: String, payload: [String: Any]) -> BoundedHTTPResult? {
    guard let body = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
        return nil
    }
    let headers = [
        "Accept": "application/json",
        "Authorization": "Bearer \(accessToken)",
        "Content-Type": "application/json",
        "User-Agent": "antigravity/1.104.0 darwin/arm64",
    ]
    let hosts = [antigravityCloudCodePrimaryHost, antigravityCloudCodeFallbackHost]
    var lastResponse: BoundedHTTPResult?
    for host in hosts {
        guard let url = fixedHTTPSURL(host: host, path: path) else { continue }
        guard let response = boundedHTTPRequest(
            url: url,
            method: "POST",
            headers: headers,
            body: body,
            timeout: 20
        ) else { continue }
        if response.status < 500 {
            return response
        }
        lastResponse = response
    }
    return lastResponse
}

func numericDouble(_ value: Any?) -> Double? {
    if let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() {
        let doubleValue = number.doubleValue
        return doubleValue.isFinite ? doubleValue : nil
    }
    if let text = value as? String, let doubleValue = Double(text), doubleValue.isFinite {
        return doubleValue
    }
    return nil
}

func extractAntigravityAICredits(tierObject: [String: Any]?) -> Double? {
    guard let credits = tierObject?["availableCredits"] as? [[String: Any]] else {
        return nil
    }
    var sum = 0.0
    var found = false
    for item in credits {
        guard (item["creditType"] as? String) == "GOOGLE_ONE_AI",
              let amount = numericDouble(item["creditAmount"]),
              amount >= 0
        else { continue }
        sum += amount
        found = true
    }
    return found ? sum : nil
}

func inferAntigravityGroupAndWindow(id: String, bucketType: String?, quotaGroup: String?) -> (group: String, window: String) {
    let loweredGroup = (quotaGroup ?? "").lowercased()
    let loweredID = id.lowercased()
    let group: String
    if loweredGroup.contains("gemini") || loweredID.contains("gemini") {
        group = "gemini"
    } else if loweredGroup.contains("3p") || loweredID.contains("claude") || loweredID.contains("sonnet") || loweredID.contains("opus") || loweredID.contains("gpt") || loweredID.contains("3p") {
        group = "3p"
    } else {
        group = "general"
    }
    let window: String
    if bucketType == "SHORT_TERM" || loweredID.contains("5h") || loweredID.contains("short") {
        window = "5h"
    } else if bucketType == "LONG_TERM" || loweredID.contains("week") || loweredID.contains("7d") || loweredID.contains("long") {
        window = "weekly"
    } else {
        window = "5h"
    }
    return (group, window)
}

func extractCloudCodeBucketsFromModels(_ document: [String: Any]) -> [[String: Any]] {
    guard let models = document["models"] as? [String: Any] else { return [] }
    var bestByKey: [String: (fraction: Double, resetTime: String?, group: String, window: String)] = [:]
    for (modelID, rawModel) in models {
        guard let model = rawModel as? [String: Any] else { continue }
        let quotaInfo = model["quotaInfo"] as? [String: Any]
        var candidateEntries: [[String: Any]] = []
        if let quotaBuckets = (quotaInfo?["quotaBuckets"] as? [[String: Any]]) ?? (model["quotaBuckets"] as? [[String: Any]]) {
            candidateEntries.append(contentsOf: quotaBuckets)
        } else if let quotaInfo {
            candidateEntries.append(quotaInfo)
        }
        for entry in candidateEntries {
            guard let fraction = numericDouble(entry["remainingFraction"]), fraction >= 0, fraction <= 1 else {
                continue
            }
            let inferred = inferAntigravityGroupAndWindow(
                id: modelID,
                bucketType: entry["quotaBucketType"] as? String,
                quotaGroup: (entry["quotaGroup"] as? String) ?? (quotaInfo?["quotaGroup"] as? String)
            )
            let key = "\(inferred.group)-\(inferred.window)"
            let reset = entry["resetTime"] as? String
            if let existing = bestByKey[key] {
                if fraction < existing.fraction {
                    bestByKey[key] = (fraction, reset ?? existing.resetTime, inferred.group, inferred.window)
                }
            } else {
                bestByKey[key] = (fraction, reset, inferred.group, inferred.window)
            }
        }
    }
    let priority = ["gemini-5h": 0, "gemini-weekly": 1, "3p-5h": 2, "3p-weekly": 3]
    return bestByKey.keys
        .sorted { (priority[$0] ?? 99, $0) < (priority[$1] ?? 99, $1) }
        .prefix(16)
        .map { key in
            let item = bestByKey[key]!
            var out: [String: Any] = [
                "id": key,
                "window": item.window,
                "remainingFraction": item.fraction,
            ]
            if let resetTime = item.resetTime, !resetTime.isEmpty {
                out["resetTime"] = resetTime
            }
            return out
        }
}

func extractCloudCodeBucketsFromSummary(_ document: [String: Any]) -> [[String: Any]] {
    guard let groups = document["groups"] as? [[String: Any]] else { return [] }
    var rows: [[String: Any]] = []
    for group in groups {
        let groupID = group["groupId"] as? String
        guard let buckets = group["buckets"] as? [[String: Any]] else { continue }
        for bucket in buckets {
            guard
                let bucketID = (bucket["bucketId"] as? String) ?? (bucket["id"] as? String),
                !bucketID.isEmpty,
                let fraction = numericDouble(bucket["remainingFraction"]),
                fraction >= 0, fraction <= 1
            else { continue }
            let inferred = inferAntigravityGroupAndWindow(
                id: bucketID,
                bucketType: bucket["quotaBucketType"] as? String,
                quotaGroup: groupID
            )
            var out: [String: Any] = [
                "id": bucketID,
                "window": (bucket["window"] as? String) ?? inferred.window,
                "remainingFraction": fraction,
            ]
            if let resetTime = bucket["resetTime"] as? String, !resetTime.isEmpty {
                out["resetTime"] = resetTime
            }
            rows.append(out)
            if rows.count >= 16 { return rows }
        }
    }
    return rows
}

func antigravityFetch(reference: String, provider id: String, secret: Data) -> NativeResponse {
    guard var bundle = try? JSONDecoder().decode(AntigravityTokenBundle.self, from: secret) else {
        return NativeResponse(
            status: "provider-response", opaqueReference: nil, errorCode: nil,
            userPresenceToken: nil, provider: id, httpStatus: 401,
            bodyBase64: Data("{}".utf8).base64EncodedString()
        )
    }
    if bundle.expiresAt <= Int64(Date().timeIntervalSince1970) + 300 {
        switch refreshAntigravityBundle(reference: reference, bundle: bundle) {
        case .success(let refreshed):
            bundle = refreshed
        case .failure(.reauthRequired):
            return NativeResponse(
                status: "provider-response", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil, provider: id, httpStatus: 401,
                bodyBase64: Data("{}".utf8).base64EncodedString()
            )
        case .failure(.keychainLocked):
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "keychain-locked",
                userPresenceToken: nil, provider: id
            )
        case .failure:
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
                userPresenceToken: nil, provider: id
            )
        }
    }
    let loadPayload: [String: Any] = [
        "metadata": [
            "ideName": "antigravity",
            "ideType": "ANTIGRAVITY",
            "platform": "DARWIN_ARM64",
            "updateChannel": "stable",
            "pluginType": "GEMINI",
        ],
        "mode": "FULL_ELIGIBILITY_CHECK",
    ]
    guard var loadResponse = cloudCodeRequest(
        path: "/v1internal:loadCodeAssist",
        accessToken: bundle.accessToken,
        payload: loadPayload
    ) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
            userPresenceToken: nil, provider: id
        )
    }
    if loadResponse.status == 401 {
        switch refreshAntigravityBundle(reference: reference, bundle: bundle) {
        case .success(let refreshed):
            bundle = refreshed
            guard let retried = cloudCodeRequest(
                path: "/v1internal:loadCodeAssist",
                accessToken: bundle.accessToken,
                payload: loadPayload
            ) else {
                return NativeResponse(
                    status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
                    userPresenceToken: nil, provider: id
                )
            }
            loadResponse = retried
        case .failure(.reauthRequired):
            return NativeResponse(
                status: "provider-response", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil, provider: id, httpStatus: 401,
                bodyBase64: Data("{}".utf8).base64EncodedString()
            )
        case .failure(.keychainLocked):
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "keychain-locked",
                userPresenceToken: nil, provider: id
            )
        case .failure:
            return NativeResponse(
                status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
                userPresenceToken: nil, provider: id
            )
        }
    }
    if loadResponse.status == 401 || loadResponse.status == 403 {
        return NativeResponse(
            status: "provider-response", opaqueReference: nil, errorCode: nil,
            userPresenceToken: nil, provider: id, httpStatus: loadResponse.status,
            bodyBase64: Data("{}".utf8).base64EncodedString()
        )
    }
    guard loadResponse.status == 200, let loadDocument = jsonObject(loadResponse.body) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
            userPresenceToken: nil, provider: id
        )
    }
    let discoveredProject = (loadDocument["cloudaicompanionProject"] as? String)
        ?? ((loadDocument["cloudaicompanionProject"] as? [String: Any])?["id"] as? String)
        ?? bundle.projectID
    let projectPayload: [String: Any] = discoveredProject.isEmpty ? [:] : ["project": discoveredProject]
    let paidTier = loadDocument["paidTier"] as? [String: Any]
    let currentTier = loadDocument["currentTier"] as? [String: Any]
    let tier = (paidTier?["id"] as? String) ?? (currentTier?["id"] as? String)
    let aiCredits = extractAntigravityAICredits(tierObject: paidTier) ?? extractAntigravityAICredits(tierObject: currentTier)

    guard let modelsResponse = cloudCodeRequest(
        path: "/v1internal:fetchAvailableModels",
        accessToken: bundle.accessToken,
        payload: projectPayload
    ) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
            userPresenceToken: nil, provider: id
        )
    }
    if modelsResponse.status == 401 || modelsResponse.status == 403 {
        return NativeResponse(
            status: "provider-response", opaqueReference: nil, errorCode: nil,
            userPresenceToken: nil, provider: id, httpStatus: modelsResponse.status,
            bodyBase64: Data("{}".utf8).base64EncodedString()
        )
    }
    guard modelsResponse.status == 200, let modelsDocument = jsonObject(modelsResponse.body) else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "provider-unavailable",
            userPresenceToken: nil, provider: id
        )
    }
    var buckets = extractCloudCodeBucketsFromModels(modelsDocument)
    if let summaryResponse = cloudCodeRequest(
        path: "/v1internal:retrieveUserQuotaSummary",
        accessToken: bundle.accessToken,
        payload: projectPayload
    ) {
        if summaryResponse.status == 401 || summaryResponse.status == 403 {
            return NativeResponse(
                status: "provider-response", opaqueReference: nil, errorCode: nil,
                userPresenceToken: nil, provider: id, httpStatus: summaryResponse.status,
                bodyBase64: Data("{}".utf8).base64EncodedString()
            )
        }
        if summaryResponse.status == 200,
           let summaryDocument = jsonObject(summaryResponse.body)
        {
            let summaryBuckets = extractCloudCodeBucketsFromSummary(summaryDocument)
            if !summaryBuckets.isEmpty {
                buckets = summaryBuckets
            }
        }
    }
    var combined: [String: Any] = ["buckets": buckets]
    if let tier, !tier.isEmpty {
        combined["tier"] = tier
    }
    if let aiCredits {
        combined["aiCredits"] = aiCredits
    }
    guard
        let rawData = try? JSONSerialization.data(withJSONObject: combined, options: [.sortedKeys]),
        let minimizedBody = minimizedProviderBody(provider: id, status: 200, body: rawData)
    else {
        return NativeResponse(
            status: "error", opaqueReference: nil, errorCode: "contract-error",
            userPresenceToken: nil, provider: id
        )
    }
    return NativeResponse(
        status: "provider-response", opaqueReference: nil, errorCode: nil,
        userPresenceToken: nil, provider: id, httpStatus: 200,
        bodyBase64: minimizedBody.base64EncodedString()
    )
}


func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func hmacSHA256(key: Data, message: String) -> Data {
    Data(HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: SymmetricKey(data: key)))
}

func volcSignedRequest(
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
    var headers = [
        "Accept": "application/json",
        "Authorization": "HMAC-SHA256 Credential=\(accessKeyID)/\(scope), SignedHeaders=\(signedHeaders), Signature=\(signature)",
        "Host": definition.host,
        "X-Content-Sha256": payloadHash,
        "X-Date": xDate,
    ]
    if body != nil {
        headers["Content-Type"] = "application/json; charset=utf-8"
    }
    return (
        url,
        method,
        headers,
        body
    )
}

func aliyunPercentEncode(_ value: String) -> String {
    var allowed = CharacterSet.alphanumerics
    allowed.insert(charactersIn: "-_.~")
    return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? ""
}

func aliyunSignedURL(
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

func providerFetch(reference: String, provider id: String) -> NativeResponse {
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
    case .antigravityOAuth:
        return antigravityFetch(reference: reference, provider: id, secret: secret)
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

