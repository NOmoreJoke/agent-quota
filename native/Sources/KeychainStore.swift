import AppKit
import CryptoKit
import Foundation
import Security
import UniformTypeIdentifiers

func withSecretData<T>(
    _ secret: inout [UInt8],
    operation: (NSData) throws -> T
) rethrows -> T {
    defer { secret.resetBytes(in: secret.indices) }
    return try secret.withUnsafeMutableBytes { buffer in
        let data = NSData(bytesNoCopy: buffer.baseAddress!, length: buffer.count, freeWhenDone: false)
        return try operation(data)
    }
}

func credentialKeychainLabel(reference: String, provider: ProviderDefinition) -> String? {
    guard isCredentialReference(reference) else { return nil }
    // This suffix identifies a local credential, not an account name or part of its secret.
    let identifier = reference.dropFirst("credential-".count).prefix(8).lowercased()
    return "Agent Quota · \(provider.label) · \(identifier)"
}

func keychainAdd(
    account: String, provider: ProviderDefinition, secret: inout [UInt8],
    keychain: SecKeychain? = nil
) throws {
    guard let label = credentialKeychainLabel(reference: account, provider: provider) else {
        secret.resetBytes(in: secret.indices)
        throw NativeFailure.invalidRequest
    }
    try keychainAdd(account: account, label: label, secret: &secret, keychain: keychain)
}

func keychainAdd(
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

func keychainAttributes(account: String, keychain: SecKeychain? = nil) throws -> [CFString: Any] {
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

enum CredentialLabelMigration: Equatable {
    case renamed
    case unchanged
    case customLabelPreserved
    case labelUpdateDeferred(OSStatus)
    case failed(OSStatus)
}

@discardableResult
func migrateCredentialKeychainLabel(
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

func renameCredentialReference(_ reference: String, provider id: String) -> NativeResponse {
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

func keychainRead(account: String, keychain: SecKeychain? = nil) throws -> Data {
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

func keychainUpdate(
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

func keychainDelete(account: String, keychain: SecKeychain? = nil) -> OSStatus {
    var query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
    ]
    if let keychain { query[kSecMatchSearchList] = [keychain] }
    return SecItemDelete(query as CFDictionary)
}

func keychainErrorCode(_ status: OSStatus) -> String {
    switch status {
    case errSecDuplicateItem:
        return "duplicate"
    case errSecInteractionNotAllowed, errSecAuthFailed:
        return "keychain-locked"
    default:
        return "keychain-write-failed"
    }
}


func deleteReference(_ reference: String) -> NativeResponse {
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


func keychainACLSnapshot(account: String, keychain: SecKeychain? = nil) throws -> [[String: Any]] {
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

