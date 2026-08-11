"""Vendor exact upstream license evidence for crates missing packaged notices."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPDX_REPOSITORY = "https://github.com/spdx/license-list-data"
SPDX_REVISION = "5bf6d9610255540bfbee6890765a616042bf1e11"

SPECS: dict[tuple[str, str], dict[str, Any]] = {
    ("alloc-stdlib", "0.2.4"): {
        "repository": "https://github.com/dropbox/rust-alloc-no-stdlib",
        "commit": "ae42d22078b98549e987d2f03d12df7b984fde47",
        "path": "alloc-stdlib",
        "repo_notices": ["LICENSE"],
        "license_ids": ["BSD-3-Clause"],
    },
    ("block2", "0.6.2"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "b4167b582b2f75f9a1be75495c41b765344fd03c",
        "path": "crates/block2",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["MIT"],
    },
    ("dispatch2", "0.3.1"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "8852b424193ca41602281b3d7540d7c8ed51e49a",
        "path": "crates/dispatch2",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("objc2-app-kit", "0.3.2"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "7b1abfd750a2cacaea71d6a56ecfb83cb7de560b",
        "path": "framework-crates/objc2-app-kit",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("objc2-core-foundation", "0.3.2"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "7b1abfd750a2cacaea71d6a56ecfb83cb7de560b",
        "path": "framework-crates/objc2-core-foundation",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("objc2-encode", "4.1.0"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "8d214f5477365ffcbcbb7de058c86ed9a518efb7",
        "path": "crates/objc2-encode",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["MIT"],
    },
    ("objc2-exception-helper", "0.1.1"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "8d214f5477365ffcbcbb7de058c86ed9a518efb7",
        "path": "crates/objc2-exception-helper",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("objc2-foundation", "0.3.2"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "7b1abfd750a2cacaea71d6a56ecfb83cb7de560b",
        "path": "framework-crates/objc2-foundation",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["MIT"],
    },
    ("objc2-web-kit", "0.3.2"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "7b1abfd750a2cacaea71d6a56ecfb83cb7de560b",
        "path": "framework-crates/objc2-web-kit",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("objc2", "0.6.4"): {
        "repository": "https://github.com/madsmtm/objc2",
        "commit": "8852b424193ca41602281b3d7540d7c8ed51e49a",
        "path": "crates/objc2",
        "repo_notices": ["LICENSE.md"],
        "license_ids": ["MIT"],
    },
    ("selectors", "0.36.1"): {
        "repository": "https://github.com/servo/stylo",
        "commit": "635e1a19d02960588a00e189bd4bd5bdb150ec3d",
        "path": "selectors",
        "repo_notices": [],
        "license_ids": ["MPL-2.0"],
    },
    ("unic-char-property", "0.9.0"): {
        "repository": "https://github.com/open-i18n/rust-unic",
        "commit": "5878605364af97a3358368a6eaef02104af2e016",
        "path": "unic/char/property",
        "repo_notices": ["LICENSE-APACHE", "LICENSE-MIT"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("unic-char-range", "0.9.0"): {
        "repository": "https://github.com/open-i18n/rust-unic",
        "commit": "5878605364af97a3358368a6eaef02104af2e016",
        "path": "unic/char/range",
        "repo_notices": ["LICENSE-APACHE", "LICENSE-MIT"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("unic-common", "0.9.0"): {
        "repository": "https://github.com/open-i18n/rust-unic",
        "commit": "5878605364af97a3358368a6eaef02104af2e016",
        "path": "unic/common",
        "repo_notices": ["LICENSE-APACHE", "LICENSE-MIT"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("unic-ucd-ident", "0.9.0"): {
        "repository": "https://github.com/open-i18n/rust-unic",
        "commit": "8a6ce83063d90b91ae2ce59eddb803edd393fca9",
        "path": "unic/ucd/ident",
        "repo_notices": ["LICENSE-APACHE", "LICENSE-MIT"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
    ("unic-ucd-version", "0.9.0"): {
        "repository": "https://github.com/open-i18n/rust-unic",
        "commit": "5878605364af97a3358368a6eaef02104af2e016",
        "path": "unic/ucd/version",
        "repo_notices": ["LICENSE-APACHE", "LICENSE-MIT"],
        "license_ids": ["Apache-2.0", "MIT"],
    },
}


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(512 * 1024 + 1)
    if len(data) > 512 * 1024:
        raise ValueError(f"upstream source is oversized: {url}")
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text if text.endswith("\n") else text + "\n"


def source(url: str, revision: str) -> dict[str, str]:
    text = fetch(url)
    return {
        "source_uri": url,
        "source_revision": revision,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "text": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = []
    for (name, version), spec in sorted(SPECS.items()):
        repository = str(spec["repository"])
        commit = str(spec["commit"])
        raw_root = repository.replace("https://github.com/", "https://raw.githubusercontent.com/")
        metadata_url = f"{raw_root}/{commit}/{spec['path']}/Cargo.toml"
        notices = [source(f"{raw_root}/{commit}/{path}", commit) for path in spec["repo_notices"]]
        notices.extend(
            source(
                f"https://raw.githubusercontent.com/spdx/license-list-data/{SPDX_REVISION}/text/{identifier}.txt",
                SPDX_REVISION,
            )
            for identifier in spec["license_ids"]
        )
        entries.append(
            {
                "name": name,
                "version": version,
                "repository": repository,
                "vcs_commit": commit,
                "path_in_vcs": spec["path"],
                "license_ids": spec["license_ids"],
                "metadata": source(metadata_url, commit),
                "notices": notices,
            }
        )
    document = {
        "schema": "agent-quota-upstream-license-sources-v1",
        "spdx_repository": SPDX_REPOSITORY,
        "spdx_revision": SPDX_REVISION,
        "entry_count": len(entries),
        "entries": entries,
    }
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
