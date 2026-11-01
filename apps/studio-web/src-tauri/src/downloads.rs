//! Private destinations for native artifact and citation downloads.
//!
//! WebKit's completion callback omits the destination path on macOS. Track one
//! in-flight request per URL, download into a private staging directory, then
//! publish with create_new so an existing human-reviewed file is never replaced.

#[cfg(unix)]
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::{
    collections::HashMap,
    fs::{self, DirBuilder, File, OpenOptions},
    io,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};

static NEXT_DOWNLOAD: AtomicU64 = AtomicU64::new(0);

fn invalid() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidInput,
        "Invalid application download path",
    )
}

fn decode_segment(raw: &str) -> io::Result<String> {
    let mut decoded = Vec::with_capacity(raw.len());
    let bytes = raw.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' {
            if i + 2 >= bytes.len() {
                return Err(invalid());
            }
            let pair = std::str::from_utf8(&bytes[i + 1..i + 3]).map_err(|_| invalid())?;
            decoded.push(u8::from_str_radix(pair, 16).map_err(|_| invalid())?);
            i += 3;
        } else {
            decoded.push(bytes[i]);
            i += 1;
        }
    }
    let value = String::from_utf8(decoded).map_err(|_| invalid())?;
    if value.is_empty()
        || matches!(value.as_str(), "." | "..")
        || value
            .chars()
            .any(|c| c.is_control() || matches!(c, '/' | '\\' | '%'))
    {
        return Err(invalid());
    }
    Ok(value)
}

fn safe_basename(name: &str) -> io::Result<String> {
    if name.is_empty()
        || name
            .chars()
            .any(|c| c.is_control() || matches!(c, '/' | '\\'))
    {
        return Err(invalid());
    }
    let clean: String = name
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_') {
                c
            } else {
                '_'
            }
        })
        .take(180)
        .collect();
    let clean = clean.trim_matches('.');
    if clean.is_empty() {
        return Err(invalid());
    }
    Ok(clean.to_string())
}

fn uuid_component(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, byte)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                byte == b'-'
            } else {
                byte.is_ascii_hexdigit()
            }
        })
}

#[derive(Debug, PartialEq)]
struct ArtifactRoute {
    category: &'static str,
    job: String,
    basename: String,
}

fn artifact_route(path: &str) -> io::Result<Option<ArtifactRoute>> {
    let parts: Vec<_> = path.trim_start_matches('/').split('/').collect();
    if parts.len() < 2 || parts[0] != "api" {
        return Ok(None);
    }
    let category = match parts[1] {
        "learning-workspace" => "learning",
        "simulations" => "simulations",
        _ => return Ok(None),
    };
    if parts.get(2) != Some(&"jobs") {
        return Ok(None);
    }
    if parts.len() < 6 || parts[4] != "artifacts" || !uuid_component(parts[3]) {
        return Err(invalid());
    }
    let decoded: Vec<_> = parts[5..]
        .iter()
        .map(|part| decode_segment(part))
        .collect::<io::Result<_>>()?;
    Ok(Some(ArtifactRoute {
        category,
        job: parts[3].to_ascii_lowercase(),
        basename: safe_basename(decoded.last().ok_or_else(invalid)?)?,
    }))
}

fn private_child(parent: &Path, component: &str) -> io::Result<PathBuf> {
    let path = parent.join(component);
    let mut builder = DirBuilder::new();
    #[cfg(unix)]
    builder.mode(0o700);
    match builder.create(&path) {
        Ok(()) => (),
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => (),
        Err(error) => return Err(error),
    }
    let metadata = fs::symlink_metadata(&path)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid());
    }
    #[cfg(unix)]
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700))?;
    Ok(path)
}

struct PendingDownload {
    directory: PathBuf,
    staging: PathBuf,
    basename: String,
}

pub struct DownloadStore {
    downloads: PathBuf,
    pending: Mutex<HashMap<String, PendingDownload>>,
}

impl DownloadStore {
    pub fn new(downloads: PathBuf) -> Self {
        Self {
            downloads,
            pending: Mutex::new(HashMap::new()),
        }
    }

    pub fn requested(&self, key: &str, path: &str, suggested: &str) -> io::Result<PathBuf> {
        if !self.downloads.is_absolute() {
            return Err(invalid());
        }
        let route = artifact_route(path)?;
        let mut pending = self
            .pending
            .lock()
            .map_err(|_| io::Error::other("Download state unavailable"))?;
        // macOS provides only the original URL at completion; avoid ambiguous
        // completion pairing for overlapping requests to that exact same URL.
        if pending.contains_key(key) || pending.len() >= 64 {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "Download already in progress",
            ));
        }
        let app = private_child(&self.downloads, "Chemistry Studio")?;
        let artifacts = private_child(&app, "Artifacts")?;
        let (directory, basename) = if let Some(route) = route {
            let category = private_child(&artifacts, route.category)?;
            (private_child(&category, &route.job)?, route.basename)
        } else {
            (
                private_child(&artifacts, "Exports")?,
                safe_basename(suggested)?,
            )
        };
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| invalid())?
            .as_nanos();
        let counter = NEXT_DOWNLOAD.fetch_add(1, Ordering::Relaxed);
        let staging = private_child(&directory, &format!(".incoming-{stamp}-{counter}"))?;
        let destination = staging.join("content");
        pending.insert(
            key.to_string(),
            PendingDownload {
                directory,
                staging,
                basename,
            },
        );
        Ok(destination)
    }

    pub fn finished(&self, key: &str, success: bool) -> io::Result<Option<PathBuf>> {
        let pending = self
            .pending
            .lock()
            .map_err(|_| io::Error::other("Download state unavailable"))?
            .remove(key);
        let Some(pending) = pending else {
            return Ok(None);
        };
        let source = pending.staging.join("content");
        if !success {
            // Keep any partial bytes for review, but do not leave empty folders.
            let _ = fs::remove_dir(&pending.staging);
            return Ok(None);
        }
        let metadata = fs::symlink_metadata(&source)?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(invalid());
        }
        #[cfg(unix)]
        fs::set_permissions(&source, fs::Permissions::from_mode(0o600))?;
        let name = Path::new(&pending.basename);
        let stem = name
            .file_stem()
            .and_then(|v| v.to_str())
            .ok_or_else(invalid)?;
        let extension = name
            .extension()
            .and_then(|v| v.to_str())
            .map(|v| format!(".{v}"))
            .unwrap_or_default();
        for count in 0..10_000 {
            let filename = if count == 0 {
                pending.basename.clone()
            } else {
                format!("{stem} ({count}){extension}")
            };
            let destination = pending.directory.join(filename);
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            options.mode(0o600);
            let mut output = match options.open(&destination) {
                Ok(file) => file,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error),
            };
            let copy = File::open(&source).and_then(|mut input| io::copy(&mut input, &mut output));
            if let Err(error) = copy.and_then(|_| output.sync_all()) {
                let _ = fs::remove_file(&destination);
                return Err(error);
            }
            fs::remove_file(&source)?;
            let _ = fs::remove_dir(&pending.staging);
            return Ok(Some(destination));
        }
        Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "Too many duplicate artifact names",
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const JOB: &str = "8afbb515-043a-40a1-858a-dda41da1364e";
    fn route(name: &str) -> String {
        format!("/api/learning-workspace/jobs/{JOB}/artifacts/{name}")
    }
    fn temp() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "chem-download-{stamp}-{}",
            NEXT_DOWNLOAD.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        path
    }
    #[test]
    fn routes_only_valid_jobs_and_rejects_encoded_path_escape() {
        let parsed = artifact_route(&route("output/checkpoint/adapter.safetensors"))
            .unwrap()
            .unwrap();
        assert_eq!(parsed.category, "learning");
        assert_eq!(parsed.job, JOB);
        assert_eq!(parsed.basename, "adapter.safetensors");
        assert_eq!(
            artifact_route(&format!(
                "/api/simulations/jobs/{JOB}/artifacts/seed-1/eq3.log"
            ))
            .unwrap()
            .unwrap()
            .category,
            "simulations"
        );
        for raw in [
            route("../secret"),
            route("%2e%2e/secret"),
            route("%252e%252e/secret"),
            route("%2fsecret"),
            route("%5csecret"),
            route("a/%00bad"),
        ] {
            assert!(artifact_route(&raw).is_err(), "{raw}");
        }
        assert!(artifact_route("/api/learning-workspace/jobs/not-a-uuid/artifacts/x").is_err());
    }
    #[test]
    fn preserves_existing_bytes_and_finishes_in_private_job_folder() {
        let base = temp();
        let store = DownloadStore::new(base.clone());
        let first = store
            .requested("one", &route("manifest.json"), "ignored.json")
            .unwrap();
        fs::write(&first, b"first").unwrap();
        let first = store.finished("one", true).unwrap().unwrap();
        assert_eq!(
            first,
            base.join("Chemistry Studio/Artifacts/learning")
                .join(JOB)
                .join("manifest.json")
        );
        let second = store
            .requested("two", &route("manifest.json"), "ignored.json")
            .unwrap();
        fs::write(&second, b"second").unwrap();
        let second = store.finished("two", true).unwrap().unwrap();
        assert_eq!(second.file_name().unwrap(), "manifest (1).json");
        assert_eq!(fs::read(&first).unwrap(), b"first");
        assert_eq!(fs::read(&second).unwrap(), b"second");
        #[cfg(unix)]
        {
            assert_eq!(
                fs::metadata(first.parent().unwrap())
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o700
            );
            assert_eq!(
                fs::metadata(&first).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        fs::remove_dir_all(base).unwrap();
    }
    #[test]
    fn serializes_identical_urls_and_routes_other_internal_exports() {
        let base = temp();
        let store = DownloadStore::new(base.clone());
        let file = store
            .requested("one", "/api/library/citations/export", "citations.bib")
            .unwrap();
        assert!(store
            .requested("one", &route("manifest.json"), "manifest.json")
            .is_err());
        fs::write(file, b"citation").unwrap();
        let final_path = store.finished("one", true).unwrap().unwrap();
        assert_eq!(
            final_path,
            base.join("Chemistry Studio/Artifacts/Exports/citations.bib")
        );
        fs::remove_dir_all(base).unwrap();
    }
    #[test]
    #[cfg(unix)]
    fn refuses_app_folder_symlinks() {
        use std::os::unix::fs::symlink;
        let base = temp();
        let outside = temp();
        symlink(&outside, base.join("Chemistry Studio")).unwrap();
        let store = DownloadStore::new(base.clone());
        assert!(store
            .requested("one", &route("manifest.json"), "manifest.json")
            .is_err());
        fs::remove_dir_all(base).unwrap();
        fs::remove_dir_all(outside).unwrap();
    }
}
