import AppKit
import CryptoKit
import Foundation
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

