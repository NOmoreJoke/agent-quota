fn main() {
    println!("cargo:rerun-if-env-changed=AQ_RESOURCE_MANIFEST_SHA256");
    if std::env::var("PROFILE").ok().as_deref() == Some("release") {
        let digest = std::env::var("AQ_RESOURCE_MANIFEST_SHA256")
            .expect("release build requires AQ_RESOURCE_MANIFEST_SHA256");
        assert!(
            digest.len() == 64 && digest.bytes().all(|byte| byte.is_ascii_hexdigit()),
            "AQ_RESOURCE_MANIFEST_SHA256 must be a SHA-256 hex digest"
        );
        println!("cargo:rustc-env=AQ_RESOURCE_MANIFEST_SHA256={digest}");
    }
    tauri_build::build();
}
