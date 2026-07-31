use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};

#[derive(Debug, thiserror::Error)]
pub enum ResourceError {
    #[error("resource manifest is unavailable")]
    Manifest,
    #[error("resource manifest digest mismatch")]
    ManifestDigest,
    #[error("resource manifest contract mismatch")]
    Contract,
    #[error("resource path is unsafe")]
    UnsafePath,
    #[error("resource metadata mismatch")]
    Metadata,
    #[error("resource digest mismatch")]
    Digest,
    #[error("resource closure mismatch")]
    Closure,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    artifact_class: String,
    entries: Vec<Entry>,
    schema: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    bytes: u64,
    mode: u32,
    path: String,
    sha256: String,
}

pub struct ValidatedResources {
    pub native: PathBuf,
    pub sidecar: PathBuf,
}

fn digest_bytes(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn digest_file(file: &mut File) -> Result<String, ResourceError> {
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read = file.read(&mut buffer).map_err(|_| ResourceError::Digest)?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn safe_relative(path: &str) -> bool {
    let path = Path::new(path);
    !path.as_os_str().is_empty()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn same_identity(left: &Metadata, right: &Metadata) -> bool {
    left.dev() == right.dev()
        && left.ino() == right.ino()
        && left.len() == right.len()
        && left.mode() == right.mode()
        && left.uid() == right.uid()
}

fn validate_entry(root: &Path, entry: &Entry) -> Result<(), ResourceError> {
    if !safe_relative(&entry.path)
        || entry.sha256.len() != 64
        || !entry.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(ResourceError::Contract);
    }
    let path = root.join(&entry.path);
    let path_metadata = fs::symlink_metadata(&path).map_err(|_| ResourceError::Metadata)?;
    if path_metadata.file_type().is_symlink() || !path_metadata.is_file() {
        return Err(ResourceError::UnsafePath);
    }
    let canonical = path.canonicalize().map_err(|_| ResourceError::UnsafePath)?;
    if !canonical.starts_with(root) {
        return Err(ResourceError::UnsafePath);
    }
    let mode = path_metadata.permissions().mode() & 0o7777;
    let effective_uid = unsafe { libc::geteuid() };
    if path_metadata.len() != entry.bytes
        || mode != entry.mode
        || mode & 0o022 != 0
        || (!matches!(path_metadata.uid(), 0) && path_metadata.uid() != effective_uid)
    {
        return Err(ResourceError::Metadata);
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&path)
        .map_err(|_| ResourceError::Metadata)?;
    let opened_metadata = file.metadata().map_err(|_| ResourceError::Metadata)?;
    if !same_identity(&path_metadata, &opened_metadata) || digest_file(&mut file)? != entry.sha256 {
        return Err(ResourceError::Digest);
    }
    let final_metadata = fs::symlink_metadata(&path).map_err(|_| ResourceError::Metadata)?;
    if !same_identity(&opened_metadata, &final_metadata) {
        return Err(ResourceError::Metadata);
    }
    Ok(())
}

fn collect_files(
    root: &Path,
    directory: &Path,
    output: &mut BTreeSet<String>,
) -> Result<(), ResourceError> {
    for item in fs::read_dir(directory).map_err(|_| ResourceError::Closure)? {
        let item = item.map_err(|_| ResourceError::Closure)?;
        let path = item.path();
        let metadata = fs::symlink_metadata(&path).map_err(|_| ResourceError::Closure)?;
        if metadata.file_type().is_symlink() {
            return Err(ResourceError::UnsafePath);
        }
        if metadata.is_dir() {
            collect_files(root, &path, output)?;
        } else if metadata.is_file() {
            output.insert(
                path.strip_prefix(root)
                    .map_err(|_| ResourceError::UnsafePath)?
                    .to_string_lossy()
                    .into_owned(),
            );
        } else {
            return Err(ResourceError::UnsafePath);
        }
    }
    Ok(())
}

pub fn validate(
    root: &Path,
    expected_manifest_digest: &str,
) -> Result<ValidatedResources, ResourceError> {
    let root = root.canonicalize().map_err(|_| ResourceError::UnsafePath)?;
    let manifest_path = root.join("resource-manifest.json");
    let metadata = fs::symlink_metadata(&manifest_path).map_err(|_| ResourceError::Manifest)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(ResourceError::Manifest);
    }
    let mut manifest_file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&manifest_path)
        .map_err(|_| ResourceError::Manifest)?;
    let opened_metadata = manifest_file
        .metadata()
        .map_err(|_| ResourceError::Manifest)?;
    if !same_identity(&metadata, &opened_metadata) {
        return Err(ResourceError::Manifest);
    }
    let mut bytes = Vec::new();
    manifest_file
        .read_to_end(&mut bytes)
        .map_err(|_| ResourceError::Manifest)?;
    let final_metadata =
        fs::symlink_metadata(&manifest_path).map_err(|_| ResourceError::Manifest)?;
    if !same_identity(&opened_metadata, &final_metadata) {
        return Err(ResourceError::Manifest);
    }
    if digest_bytes(&bytes) != expected_manifest_digest {
        return Err(ResourceError::ManifestDigest);
    }
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|_| ResourceError::Contract)?;
    if manifest.schema != "agent-quota-resource-manifest-v1"
        || manifest.artifact_class != "local unsigned development package"
        || manifest.entries.is_empty()
    {
        return Err(ResourceError::Contract);
    }
    let mut expected = BTreeSet::new();
    for entry in &manifest.entries {
        if !expected.insert(entry.path.clone()) {
            return Err(ResourceError::Contract);
        }
        validate_entry(&root, entry)?;
    }
    let mut actual = BTreeSet::new();
    collect_files(&root, &root.join("native-helper"), &mut actual)?;
    collect_files(&root, &root.join("sidecar"), &mut actual)?;
    if actual != expected {
        return Err(ResourceError::Closure);
    }
    let native =
        PathBuf::from("native-helper/AgentQuotaNative.app/Contents/MacOS/AgentQuotaNative");
    let sidecar = PathBuf::from("sidecar/agent-quota-sidecar");
    if !expected.contains(native.to_string_lossy().as_ref())
        || !expected.contains(sidecar.to_string_lossy().as_ref())
    {
        return Err(ResourceError::Contract);
    }
    Ok(ValidatedResources {
        native: root.join(native),
        sidecar: root.join(sidecar),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};
    use std::os::unix::fs::symlink;

    fn fixture() -> (tempfile::TempDir, String) {
        let directory = tempfile::tempdir().unwrap();
        let root = directory.path();
        let native =
            root.join("native-helper/AgentQuotaNative.app/Contents/MacOS/AgentQuotaNative");
        let sidecar = root.join("sidecar/agent-quota-sidecar");
        fs::create_dir_all(native.parent().unwrap()).unwrap();
        fs::create_dir_all(sidecar.parent().unwrap()).unwrap();
        fs::write(&native, b"native").unwrap();
        fs::write(&sidecar, b"sidecar").unwrap();
        for path in [&native, &sidecar] {
            let mut permissions = fs::metadata(path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(path, permissions).unwrap();
        }
        let entries: Vec<Value> = [&native, &sidecar]
            .iter()
            .map(|path| {
                let metadata = fs::metadata(path).unwrap();
                let mut file = File::open(path).unwrap();
                json!({
                    "bytes": metadata.len(),
                    "mode": metadata.permissions().mode() & 0o7777,
                    "path": path.strip_prefix(root).unwrap().to_string_lossy(),
                    "sha256": digest_file(&mut file).unwrap()
                })
            })
            .collect();
        let bytes = serde_json::to_vec(&json!({
            "artifact_class": "local unsigned development package",
            "entries": entries,
            "schema": "agent-quota-resource-manifest-v1"
        }))
        .unwrap();
        fs::write(root.join("resource-manifest.json"), &bytes).unwrap();
        (directory, digest_bytes(&bytes))
    }

    #[test]
    fn accepts_closed_pinned_resource_tree() {
        let (directory, digest) = fixture();
        let resources = validate(directory.path(), &digest).unwrap();
        assert!(
            resources
                .native
                .ends_with("Contents/MacOS/AgentQuotaNative")
        );
        assert!(resources.sidecar.ends_with("sidecar/agent-quota-sidecar"));
    }

    #[test]
    fn rejects_tamper_and_extra_file() {
        let (directory, digest) = fixture();
        fs::write(
            directory.path().join("sidecar/agent-quota-sidecar"),
            b"tampered",
        )
        .unwrap();
        assert!(matches!(
            validate(directory.path(), &digest),
            Err(ResourceError::Metadata | ResourceError::Digest)
        ));

        let (directory, digest) = fixture();
        fs::write(directory.path().join("sidecar/injected"), b"injected").unwrap();
        assert!(matches!(
            validate(directory.path(), &digest),
            Err(ResourceError::Closure)
        ));
    }

    #[test]
    fn rejects_manifest_and_resource_symlinks() {
        let (directory, digest) = fixture();
        let manifest = directory.path().join("resource-manifest.json");
        let moved = directory.path().join("manifest-real.json");
        fs::rename(&manifest, &moved).unwrap();
        symlink(&moved, &manifest).unwrap();
        assert!(matches!(
            validate(directory.path(), &digest),
            Err(ResourceError::Manifest)
        ));

        let (directory, digest) = fixture();
        let sidecar = directory.path().join("sidecar/agent-quota-sidecar");
        let moved = directory.path().join("sidecar/sidecar-real");
        fs::rename(&sidecar, &moved).unwrap();
        symlink(&moved, &sidecar).unwrap();
        assert!(matches!(
            validate(directory.path(), &digest),
            Err(ResourceError::UnsafePath)
        ));
    }
}
