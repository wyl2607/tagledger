fn main() {
    let manifest_dir = std::path::PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by Cargo"),
    );
    let sidecar = manifest_dir
        .parent()
        .and_then(std::path::Path::parent)
        .expect("desktop/src-tauri has a repository root")
        .join("dist")
        .join("tagledger-server")
        .join("tagledger_server.exe");

    println!("cargo:rerun-if-changed={}", sidecar.display());
    if !sidecar.exists() {
        panic!(
            "Missing M2 sidecar bundle at {}. Run `pwsh -File packaging/windows/build_backend.ps1` before building the desktop launcher.",
            sidecar.display()
        );
    }

    tauri_build::build()
}
