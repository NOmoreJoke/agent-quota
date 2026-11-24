import AppKit
import CryptoKit
import Foundation
import Security
import UniformTypeIdentifiers

func selfTestCredentialLabels() -> Int32 {
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


func selfTestKeychainMetadata(provider: ProviderDefinition, keychain: SecKeychain) throws -> Int32 {
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

func selfTestKeychain(path: String? = nil) -> Int32 {
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

func selfTestProviderMinimization() -> Int32 {
    guard
        creatableProviders.map(\.id) == creatableProviderIDs,
        Set(creatableProviderIDs).count == 5
    else { return 9 }
    let samples = [
        ("deepseek", #"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"1","granted_balance":"0","topped_up_balance":"1","account_id":"sensitive"}],"user":{"email":"sensitive"}}"#),
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
        walletSigned.method == "GET",
        walletSigned.body == nil,
        walletSigned.headers["Content-Type"] == nil,
        walletSigned.headers["Authorization"]?.hasSuffix(
            "Signature=45433d0b80f6e188625d2186b504f4510b5f14606220a322bf334cc189cd34e4"
        ) == true
    else { return 14 }
    guard
        isKimiCodeReauthResponse(status: 401, body: Data()),
        isKimiCodeReauthResponse(status: 403, body: Data()),
        isKimiCodeReauthResponse(
            status: 400,
            body: Data(#"{"error":"invalid_grant","error_description":"The provided authorization grant is invalid"}"#.utf8)
        ),
        isKimiCodeReauthResponse(status: 400, body: Data(#"{"error":"expired_token"}"#.utf8)),
        !isKimiCodeReauthResponse(status: 400, body: Data(#"{"error":"invalid_request"}"#.utf8)),
        !isKimiCodeReauthResponse(status: 500, body: Data(#"{"error":"invalid_grant"}"#.utf8)),
        !isKimiCodeReauthResponse(status: 200, body: Data(#"{"error":"invalid_grant"}"#.utf8))
    else { return 15 }
    return 0
}

@main
struct AgentQuotaNative {
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
        if arguments.count == 3 && arguments[1] == "--self-test-minimize-stdin" {
            let input = FileHandle.standardInput.readDataToEndOfFile()
            guard
                input.count <= maxProviderBodyBytes,
                let minimized = minimizedProviderBody(provider: arguments[2], status: 200, body: input)
            else { exit(65) }
            FileHandle.standardOutput.write(minimized)
            exit(0)
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
