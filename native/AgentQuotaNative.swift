import AppKit
import Foundation
import Security

private let service = "com.agentquota.desktop.credentials.v1"

private struct NativeRequest: Decodable {
    let action: String
    let dialogPurpose: String?
    let operationIntent: String?
}

private struct NativeResponse: Encodable {
    let status: String
    let opaqueReference: String?
    let errorCode: String?
}

private enum NativeFailure: Error {
    case invalidRequest
    case keychain(OSStatus)
}

private func emit(_ response: NativeResponse) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard let data = try? encoder.encode(response) else { exit(70) }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
}

private func keychainAdd(account: String, secret: inout [UInt8]) throws {
    defer { secret.resetBytes(in: secret.indices) }
    let data = Data(secret)
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
        kSecAttrLabel: "Agent Quota credential reference",
        kSecValueData: data,
    ]
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else { throw NativeFailure.keychain(status) }
}

private func keychainDelete(account: String) -> OSStatus {
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
    ]
    return SecItemDelete(query as CFDictionary)
}

@MainActor
private func credentialDialog(purpose: String) -> NativeResponse {
    NSApplication.shared.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.alertStyle = .informational
    alert.messageText = purpose == "replace-credential-reference" ? "替换本机凭据" : "添加本机凭据"
    alert.informativeText = "凭据只写入 macOS 钥匙串，不会进入网页界面、IPC 或日志。"
    alert.addButton(withTitle: "保存到钥匙串")
    alert.addButton(withTitle: "取消")

    let container = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 54))
    let secure = NSSecureTextField(frame: NSRect(x: 0, y: 18, width: 360, height: 28))
    secure.placeholderString = "API Key / Token"
    secure.setAccessibilityLabel("凭据")
    container.addSubview(secure)
    alert.accessoryView = container
    alert.window.initialFirstResponder = secure

    guard alert.runModal() == .alertFirstButtonReturn else {
        secure.stringValue = ""
        return NativeResponse(status: "cancelled", opaqueReference: nil, errorCode: nil)
    }
    var bytes = Array(secure.stringValue.utf8)
    secure.stringValue = ""
    guard !bytes.isEmpty, bytes.count <= 16_384 else {
        bytes.resetBytes(in: bytes.indices)
        return NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-secret")
    }
    let reference = "credential-\(UUID().uuidString.lowercased())"
    do {
        try keychainAdd(account: reference, secret: &bytes)
        let status = purpose == "replace-credential-reference"
            ? "reference-replaced"
            : "reference-created"
        return NativeResponse(status: status, opaqueReference: reference, errorCode: nil)
    } catch NativeFailure.keychain(let status) {
        let code: String
        switch status {
        case errSecDuplicateItem: code = "duplicate"
        case errSecInteractionNotAllowed, errSecAuthFailed: code = "keychain-locked"
        default: code = "keychain-write-failed"
        }
        return NativeResponse(status: "error", opaqueReference: nil, errorCode: code)
    } catch {
        return NativeResponse(status: "error", opaqueReference: nil, errorCode: "keychain-write-failed")
    }
}

@MainActor
private func destructiveDialog(intent: String) -> NativeResponse {
    NSApplication.shared.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.alertStyle = .critical
    alert.messageText = "确认\(intent)"
    alert.informativeText = "此窗口只确认意图；宿主会在提交前重新校验选择范围和版本。请输入 DELETE。"
    alert.addButton(withTitle: "取消")
    alert.addButton(withTitle: "确认")
    let confirmation = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 28))
    confirmation.placeholderString = "DELETE"
    confirmation.setAccessibilityLabel("破坏性操作确认文本")
    alert.accessoryView = confirmation
    alert.window.initialFirstResponder = confirmation
    let response = alert.runModal()
    let matched = confirmation.stringValue == "DELETE"
    confirmation.stringValue = ""
    guard response == .alertSecondButtonReturn, matched else {
        return NativeResponse(status: "cancelled", opaqueReference: nil, errorCode: nil)
    }
    return NativeResponse(status: "confirmed", opaqueReference: nil, errorCode: nil)
}

private func selfTestKeychain() -> Int32 {
    let account = "self-test-\(UUID().uuidString.lowercased())"
    var secret = Array("temporary-agent-quota-self-test".utf8)
    do {
        try keychainAdd(account: account, secret: &secret)
        let deleteStatus = keychainDelete(account: account)
        guard deleteStatus == errSecSuccess else { return 3 }
        emit(NativeResponse(status: "self-test-ok", opaqueReference: nil, errorCode: nil))
        return 0
    } catch {
        _ = keychainDelete(account: account)
        emit(NativeResponse(status: "self-test-failed", opaqueReference: nil, errorCode: nil))
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
                data.count <= 4096,
                let request = try? JSONDecoder().decode(NativeRequest.self, from: data)
            else {
                emit(NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-request"))
                exit(64)
            }
            let response: NativeResponse
            switch request.action {
            case "credential":
                guard let purpose = request.dialogPurpose else {
                    emit(NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-request"))
                    exit(64)
                }
                response = credentialDialog(purpose: purpose)
            case "destructive":
                guard let intent = request.operationIntent else {
                    emit(NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-request"))
                    exit(64)
                }
                response = destructiveDialog(intent: intent)
            default:
                response = NativeResponse(status: "error", opaqueReference: nil, errorCode: "invalid-request")
            }
            emit(response)
        }
    }
}
