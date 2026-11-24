import AppKit
import CryptoKit
import Foundation
import Security
import UniformTypeIdentifiers

let service = "com.agentquota.desktop.credentials.v1"
let legacyCredentialLabel = "Agent Quota credential reference"
let maxRequestBytes = 4096
let maxResponseBytes = 384 * 1024
let maxProviderBodyBytes = 256 * 1024
let kimiCodeOAuthHost = "auth.kimi.com"
let kimiCodeOAuthClientID = "17e5f671-d194-4dfb-9706-5516cb48c098"
let antigravityOAuthAuthHost = "accounts.google.com"
let antigravityOAuthTokenHost = "oauth2.googleapis.com"
let antigravityCloudCodePrimaryHost = "daily-cloudcode-pa.googleapis.com"
let antigravityCloudCodeFallbackHost = "cloudcode-pa.googleapis.com"

enum ProviderAuthMode: Equatable {
    case bearer
    case raw
    case kimiCodeOAuth
    case antigravityOAuth
    case volcAKSK(service: String, region: String, action: String, version: String, method: String)
    case aliyunRPC(action: String, version: String)
}

struct ProviderDefinition {
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

let providers = [
    ProviderDefinition(id: "antigravity", label: "Google Antigravity", host: "daily-cloudcode-pa.googleapis.com", path: "/v1internal:fetchAvailableModels", authMode: .antigravityOAuth),
    ProviderDefinition(id: "bailian-wallet", label: "阿里云账户余额（百炼）", host: "business.aliyuncs.com", path: "/", authMode: .aliyunRPC(action: "QueryAccountBalance", version: "2017-12-14")),
    ProviderDefinition(id: "deepseek", label: "DeepSeek", host: "api.deepseek.com", path: "/user/balance", authMode: .bearer),
    ProviderDefinition(id: "glm-cn", label: "GLM Coding Plan（中国区）", host: "open.bigmodel.cn", path: "/api/monitor/usage/quota/limit", authMode: .raw),
    ProviderDefinition(id: "glm-global", label: "GLM Coding Plan（国际区）", host: "api.z.ai", path: "/api/monitor/usage/quota/limit", authMode: .raw),
    ProviderDefinition(id: "kimi-cn", label: "Kimi API 余额（中国区）", host: "api.moonshot.cn", path: "/v1/users/me/balance", authMode: .bearer),
    ProviderDefinition(id: "kimi-global", label: "Kimi API 余额（国际区）", host: "api.moonshot.ai", path: "/v1/users/me/balance", authMode: .bearer),
    ProviderDefinition(id: "kimi-code", label: "Kimi Code Token Plan", host: "api.kimi.com", path: "/coding/v1/usages", authMode: .kimiCodeOAuth),
    ProviderDefinition(id: "minimax-cn", label: "MiniMax Token Plan（中国区）", host: "www.minimaxi.com", path: "/v1/token_plan/remains", authMode: .bearer),
    ProviderDefinition(id: "minimax-global", label: "MiniMax Token Plan（国际区）", host: "www.minimax.io", path: "/v1/token_plan/remains", authMode: .bearer),
    ProviderDefinition(id: "volc-wallet", label: "火山引擎账户余额", host: "open.volcengineapi.com", path: "/", authMode: .volcAKSK(service: "billing", region: "cn-beijing", action: "QueryBalanceAcct", version: "2022-01-01", method: "GET")),
    ProviderDefinition(id: "volc-plan", label: "火山方舟 Coding Plan", host: "ark.cn-beijing.volces.com", path: "/", authMode: .volcAKSK(service: "ark", region: "cn-beijing", action: "GetAFPUsage", version: "2024-01-01", method: "POST")),
]

// BEGIN GENERATED LAUNCH CREATE IDS
let creatableProviderIDs = [
    "antigravity",
    "deepseek",
    "glm-cn",
    "kimi-cn",
    "kimi-code",
    "minimax-cn",
]
// END GENERATED LAUNCH CREATE IDS

let creatableProviders = creatableProviderIDs.compactMap { id in
    providers.first { $0.id == id }
}

struct CloudKeyBundle: Codable {
    let accessKeyID: String
    let secretAccessKey: String
}

struct KimiCodeTokenBundle: Codable {
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

struct AntigravityTokenBundle: Codable {
    let accessToken: String
    let refreshToken: String
    let expiresAt: Int64
    let projectID: String
    let clientID: String
    let clientSecret: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case expiresAt = "expires_at"
        case projectID = "project_id"
        case clientID = "client_id"
        case clientSecret = "client_secret"
    }
}

struct NativeRequest {
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

struct NativeResponse: Encodable {
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

enum NativeFailure: Error {
    case invalidRequest
    case keychain(OSStatus)
}


func requiresDualCloudSecret(_ mode: ProviderAuthMode) -> Bool {
    switch mode {
    case .volcAKSK, .aliyunRPC:
        return true
    case .bearer, .raw, .kimiCodeOAuth, .antigravityOAuth:
        return false
    }
}


func emit(_ response: NativeResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(response), data.count <= maxResponseBytes else { exit(70) }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
}


func isSafeCredential(_ value: String) -> Bool {
    let bytes = value.utf8
    return !bytes.isEmpty && bytes.count <= 16_384 && bytes.allSatisfy { 0x21...0x7E ~= $0 }
}


func providerDefinition(_ id: String) -> ProviderDefinition? {
    providers.first { $0.id == id }
}


func isCredentialReference(_ reference: String) -> Bool {
    reference.count == 47
        && reference.hasPrefix("credential-")
        && UUID(uuidString: String(reference.dropFirst("credential-".count))) != nil
}

