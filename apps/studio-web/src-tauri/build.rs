fn main() {
    // This first local package deliberately uses the installed Python runtime.
    // Bind its location at build time; the webview never supplies filesystem paths.
    let workspace = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("workspace root must exist when packaging");
    println!(
        "cargo:rustc-env=CHEMISTRY_WORKSPACE={}",
        workspace.display()
    );
    // The marker is non-secret and fixed in this binary. A service started by
    // another release must never be mistaken for this bundle's API/interface.
    for path in [
        "../dist",
        "../../../services/studio-api/src",
        "../../../packages/contracts/schema.graphql",
    ] {
        println!("cargo:rerun-if-changed={path}");
    }
    let build_nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("build clock must be after the epoch")
        .as_nanos();
    println!(
        "cargo:rustc-env=CHEMISTRY_DESKTOP_BUILD_ID=chemistry-studio-{}-{build_nonce}",
        env!("CARGO_PKG_VERSION")
    );
    tauri_build::build();
}
