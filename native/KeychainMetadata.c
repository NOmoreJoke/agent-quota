#include "KeychainMetadata.h"

// Apple provides no replacement for editing the ACL descriptors on an existing
// login-keychain item. Suppress this category only inside this small legacy bridge.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

OSStatus AQKeychainCreateAccess(CFStringRef label, SecAccessRef *access) {
    // NULL means only the app creating the item, not every application.
    return SecAccessCreate(label, NULL, access);
}

OSStatus AQKeychainBeginNoninteractive(bool *previouslyAllowed) {
    Boolean previous = false;
    OSStatus status = SecKeychainGetUserInteractionAllowed(&previous);
    if (status != errSecSuccess) return status;
    *previouslyAllowed = previous;
    return SecKeychainSetUserInteractionAllowed(false);
}

OSStatus AQKeychainRestoreInteraction(bool previouslyAllowed) {
    return SecKeychainSetUserInteractionAllowed(previouslyAllowed);
}

OSStatus AQKeychainOpenForSelfTest(const char *path, SecKeychainRef *keychain) {
    return SecKeychainOpen(path, keychain);
}

OSStatus AQKeychainCreateForSelfTest(const char *path, CFDataRef password, SecKeychainRef *keychain) {
    return SecKeychainCreate(path, (UInt32)CFDataGetLength(password),
                            CFDataGetBytePtr(password), false, NULL, keychain);
}

OSStatus AQKeychainDeleteForSelfTest(SecKeychainRef keychain) {
    return SecKeychainDelete(keychain);
}

OSStatus AQKeychainSetAccess(CFTypeRef item, SecAccessRef access) {
    if (CFGetTypeID(item) != SecKeychainItemGetTypeID()) return errSecParam;
    return SecKeychainItemSetAccess((SecKeychainItemRef)item, access);
}

static OSStatus copyAccessAndACLs(CFTypeRef item, SecAccessRef *access, CFArrayRef *acls) {
    *access = NULL;
    *acls = NULL;
    OSStatus status;
    if (CFGetTypeID(item) == SecKeychainItemGetTypeID()) {
        status = SecKeychainItemCopyAccess((SecKeychainItemRef)item, access);
    } else if (CFGetTypeID(item) == SecAccessGetTypeID()) {
        *access = (SecAccessRef)CFRetain(item); // In-memory migration snapshot in self-tests.
        status = errSecSuccess;
    } else {
        return errSecParam;
    }
    if (status == errSecSuccess && !*access) status = errSecInternalComponent;
    if (status == errSecSuccess) status = SecAccessCopyACLList(*access, acls);
    if (status == errSecSuccess && !*acls) status = errSecInternalComponent;
    if (status != errSecSuccess && *access) {
        CFRelease(*access);
        *access = NULL;
    }
    return status;
}

OSStatus AQKeychainCopyAccessRenamingDescription(
    CFTypeRef item, CFStringRef oldDescription, CFStringRef newDescription,
    SecAccessRef *access, bool *changed
) {
    CFArrayRef acls = NULL;
    *changed = false;
    OSStatus status = copyAccessAndACLs(item, access, &acls);
    if (status != errSecSuccess) return status;
    for (CFIndex i = 0; i < CFArrayGetCount(acls); i++) {
        SecACLRef acl = (SecACLRef)CFArrayGetValueAtIndex(acls, i);
        CFArrayRef applications = NULL;
        CFStringRef description = NULL;
        SecKeychainPromptSelector prompt;
        status = SecACLCopyContents(acl, &applications, &description, &prompt);
        if (status == errSecSuccess && description && CFEqual(description, oldDescription)) {
            // Preserve NULL vs empty app lists, all application requirements, flags, and
            // authorizations. In particular, never replace owner or partition ACLs.
            status = SecACLSetContents(acl, applications, newDescription, prompt);
            if (status == errSecSuccess) *changed = true;
        }
        if (applications) CFRelease(applications);
        if (description) CFRelease(description);
        if (status != errSecSuccess) break;
    }
    CFRelease(acls);
    if (status != errSecSuccess) {
        CFRelease(*access);
        *access = NULL;
        *changed = false;
    }
    return status;
}

CFArrayRef AQKeychainCopyACLSnapshot(CFTypeRef item, OSStatus *status) {
    SecAccessRef access = NULL;
    CFArrayRef acls = NULL;
    *status = copyAccessAndACLs(item, &access, &acls);
    if (*status != errSecSuccess) return NULL;
    CFMutableArrayRef result = CFArrayCreateMutable(NULL, 0, &kCFTypeArrayCallBacks);
    for (CFIndex i = 0; i < CFArrayGetCount(acls); i++) {
        SecACLRef acl = (SecACLRef)CFArrayGetValueAtIndex(acls, i);
        CFArrayRef applications = NULL;
        CFStringRef description = NULL;
        SecKeychainPromptSelector prompt;
        *status = SecACLCopyContents(acl, &applications, &description, &prompt);
        if (*status != errSecSuccess) {
            if (applications) CFRelease(applications);
            if (description) CFRelease(description);
            break;
        }
        CFMutableArrayRef appData = NULL;
        if (applications) {
            appData = CFArrayCreateMutable(NULL, 0, &kCFTypeArrayCallBacks);
            for (CFIndex a = 0; a < CFArrayGetCount(applications); a++) {
                CFDataRef data = NULL;
                *status = SecTrustedApplicationCopyData(
                    (SecTrustedApplicationRef)CFArrayGetValueAtIndex(applications, a), &data);
                if (*status != errSecSuccess) break;
                CFArrayAppendValue(appData, data);
                CFRelease(data);
            }
        }
        CFArrayRef authorizations = SecACLCopyAuthorizations(acl);
        uint32_t flags = prompt;
        CFNumberRef flagNumber = CFNumberCreate(NULL, kCFNumberSInt32Type, &flags);
        const void *keys[] = { CFSTR("description"), CFSTR("applications"),
                              CFSTR("authorizations"), CFSTR("prompt_flags") };
        const void *values[] = { description ? (CFTypeRef)description : kCFNull,
                                appData ? (CFTypeRef)appData : kCFNull,
                                authorizations, flagNumber };
        if (*status == errSecSuccess && authorizations) {
            CFDictionaryRef entry = CFDictionaryCreate(NULL, keys, values, 4,
                &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
            CFArrayAppendValue(result, entry);
            CFRelease(entry);
        } else if (*status == errSecSuccess) {
            *status = errSecInternalComponent;
        }
        CFRelease(flagNumber);
        if (authorizations) CFRelease(authorizations);
        if (appData) CFRelease(appData);
        if (applications) CFRelease(applications);
        if (description) CFRelease(description);
        if (*status != errSecSuccess) break;
    }
    CFRelease(acls);
    CFRelease(access);
    if (*status != errSecSuccess) {
        CFRelease(result);
        return NULL;
    }
    return result;
}

#pragma clang diagnostic pop
