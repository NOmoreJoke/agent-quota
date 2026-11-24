import AppKit
import CryptoKit
import Foundation
import Security
import UniformTypeIdentifiers

final class PasteSecureTextField: NSSecureTextField {
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
final class DestructiveConfirmationGate: NSObject {
    weak var confirmButton: NSButton?

    @objc func update(_ checkbox: NSButton) {
        confirmButton?.isEnabled = checkbox.state == .on
    }
}


@MainActor
final class CredentialSelectorGate: NSObject {
    let providers: [ProviderDefinition]
    weak var secureField: NSSecureTextField?
    weak var cloudSecretField: NSSecureTextField?

    init(
        providers: [ProviderDefinition],
        secureField: NSSecureTextField,
        cloudSecretField: NSSecureTextField
    ) {
        self.providers = providers
        self.secureField = secureField
        self.cloudSecretField = cloudSecretField
    }

    func apply(definition: ProviderDefinition?) {
        guard let definition else { return }
        if definition.authMode == .kimiCodeOAuth || definition.authMode == .workbuddyCNOAuth {
            secureField?.stringValue = ""
            cloudSecretField?.stringValue = ""
            secureField?.isHidden = true
            cloudSecretField?.isHidden = true
        } else if definition.authMode == .antigravityOAuth {
            secureField?.stringValue = ""
            cloudSecretField?.stringValue = ""
            secureField?.isHidden = false
            secureField?.placeholderString = "OAuth Client ID（可留空使用默认）"
            cloudSecretField?.isHidden = false
            cloudSecretField?.placeholderString = "OAuth Client Secret（可选）"
        } else if requiresDualCloudSecret(definition.authMode) {
            secureField?.isHidden = false
            secureField?.placeholderString = "AccessKey ID"
            cloudSecretField?.isHidden = false
            cloudSecretField?.placeholderString = "SecretAccessKey"
        } else {
            cloudSecretField?.stringValue = ""
            secureField?.isHidden = false
            secureField?.placeholderString = "API Key / Auth Token"
            cloudSecretField?.isHidden = true
        }
    }

    @objc func selectionChanged(_ sender: NSPopUpButton) {
        let index = sender.indexOfSelectedItem
        guard providers.indices.contains(index) else { return }
        apply(definition: providers[index])
    }
}


@MainActor
func prepareApplication() {
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


@MainActor
func credentialDialog(
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
        : "仅可添加当前 \(creatableProviders.count) 项已核验 Provider；API Key/Token 可直接粘贴，Kimi Code、Antigravity 与 WorkBuddy 使用官方 OAuth。凭据只写入 macOS 钥匙串。"
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
    cloudSecret.placeholderString = "SecretAccessKey（仅云签名接口）"
    cloudSecret.setAccessibilityLabel("云接口 SecretKey")
    cloudSecret.menu = secureMenu
    container.addSubview(cloudSecret)
    let selectorGate = CredentialSelectorGate(
        providers: creatableProviders,
        secureField: secure,
        cloudSecretField: cloudSecret
    )
    selector.target = selectorGate
    selector.action = #selector(CredentialSelectorGate.selectionChanged(_:))
    let initialDefinition = purpose == "replace-credential-reference"
        ? requestedProvider.flatMap(providerDefinition)
        : creatableProviders.first
    selectorGate.apply(definition: initialDefinition)
    alert.accessoryView = container
    if !secure.isHidden {
        alert.window.initialFirstResponder = secure
    }

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
    } else if definition.authMode == .antigravityOAuth {
        let clientIDOverride = secure.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        let clientSecretOverride = cloudSecret.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        let login = antigravityOAuthCredential(
            clientIDOverride: clientIDOverride,
            clientSecretOverride: clientSecretOverride
        )
        guard let credential = login.credential else {
            return NativeResponse(
                status: login.errorCode == nil ? "cancelled" : "error",
                opaqueReference: nil,
                errorCode: login.errorCode,
                userPresenceToken: nil
            )
        }
        bytes = credential
    } else if definition.authMode == .workbuddyCNOAuth {
        secure.stringValue = ""
        cloudSecret.stringValue = ""
        let login = workbuddyCNOAuthCredential()
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


@MainActor
func destructiveDialog(_ request: NativeRequest) -> NativeResponse {
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


@MainActor
func exportRedacted(contentBase64: String, filename: String) -> NativeResponse {
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

