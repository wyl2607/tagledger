mod lan_ip;
mod sidecar;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .manage(sidecar::SidecarManager::default())
        .invoke_handler(tauri::generate_handler![
            sidecar::get_state,
            sidecar::start_sidecar,
            sidecar::stop_sidecar,
            sidecar::restart_sidecar,
            sidecar::regenerate_pair_token,
            sidecar::open_data_dir,
            sidecar::open_log_dir,
            sidecar::list_lan_ips,
            sidecar::select_lan_ip,
        ])
        .build(tauri::generate_context!())
        .expect("error while building TagLedger launcher")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                sidecar::stop_on_exit(app);
            }
        });
}
