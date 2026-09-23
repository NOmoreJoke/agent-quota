#ifndef AGENT_QUOTA_KEYCHAIN_METADATA_H
#define AGENT_QUOTA_KEYCHAIN_METADATA_H

#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>
#include <stdbool.h>

CF_ASSUME_NONNULL_BEGIN

// The existing macOS login-keychain items use SecAccess ACLs. Keep the deprecated
// API boundary here; migrating to the data-protection keychain is a separate change.
OSStatus AQKeychainCreateAccess(CFStringRef label, SecAccessRef _Nullable * _Nonnull CF_RETURNS_RETAINED access);
OSStatus AQKeychainBeginNoninteractive(bool *previouslyAllowed);
OSStatus AQKeychainRestoreInteraction(bool previouslyAllowed);
OSStatus AQKeychainCopyAccessRenamingDescription(
    CFTypeRef item, CFStringRef oldDescription, CFStringRef newDescription,
    SecAccessRef _Nullable * _Nonnull CF_RETURNS_RETAINED access, bool *changed);
OSStatus AQKeychainSetAccess(CFTypeRef item, SecAccessRef access);

// Used only by the temporary-credential self-test. Does not retrieve secret data.
CFArrayRef _Nullable AQKeychainCopyACLSnapshot(CFTypeRef item, OSStatus *status)
    CF_RETURNS_RETAINED;
OSStatus AQKeychainOpenForSelfTest(
    const char *path, SecKeychainRef _Nullable * _Nonnull CF_RETURNS_RETAINED keychain);
OSStatus AQKeychainCreateForSelfTest(
    const char *path, CFDataRef password,
    SecKeychainRef _Nullable * _Nonnull CF_RETURNS_RETAINED keychain);
OSStatus AQKeychainDeleteForSelfTest(SecKeychainRef keychain);

CF_ASSUME_NONNULL_END
#endif
