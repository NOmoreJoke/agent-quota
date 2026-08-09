# Security Policy

## Reporting

Report vulnerabilities privately through GitHub Security Advisories for this repository. Do not
open a public issue containing credentials, account details, Provider responses, or exploit data.

Include the affected version/commit, reproducible steps, impact, and the smallest safe test case.
Never include API keys, tokens, cookies, Keychain exports, or real account payloads.

## Supported releases

Only releases explicitly marked as supported in GitHub Releases receive security fixes. Local
unsigned development packages are test artifacts and are not public releases.

## Security boundary

Agent Quota stores secret values in the macOS Keychain. Release bundles must contain no runtime
account state. A normal upgrade preserves the current macOS user's own Application Support data;
removal requires the app's explicit purge flow.
