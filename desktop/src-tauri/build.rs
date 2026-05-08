fn main() {
    let manifest_dir = std::path::PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by Cargo"),
    );
    let repo_root = manifest_dir
        .parent()
        .and_then(std::path::Path::parent)
        .expect("desktop/src-tauri has a repository root");

    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();

    // Sidecar contract: enforced on Windows since M3. macOS support is M4-A.2;
    // until that lands the macOS branch only warns so cargo check / scaffold work
    // cleanly on developer machines without the sidecar pre-built.
    let (sidecar, build_hint) = match target_os.as_str() {
        "windows" => (
            repo_root
                .join("dist")
                .join("tagledger-server")
                .join("tagledger_server.exe"),
            "pwsh -File packaging/windows/build_backend.ps1",
        ),
        "macos" => (
            repo_root
                .join("dist-macos")
                .join("tagledger-server")
                .join("tagledger_server"),
            "packaging/macos/build_backend.sh (M4-A.2)",
        ),
        _ => {
            tauri_build::build();
            return;
        }
    };

    println!("cargo:rerun-if-changed={}", sidecar.display());
    if !sidecar.exists() {
        if target_os == "windows" {
            panic!(
                "Missing M2 sidecar bundle at {}. Run `{}` before building the desktop launcher.",
                sidecar.display(),
                build_hint
            );
        } else {
            // macOS scaffold mode: warn only. tauri bundle stage will still fail
            // when resources are wired in M4-A.2 if the bundle is missing.
            println!(
                "cargo:warning=macOS sidecar bundle missing at {}. Run `{}` before tauri build (M4-A.2 will enforce).",
                sidecar.display(),
                build_hint
            );
        }
    }

    tauri_build::build()
}
