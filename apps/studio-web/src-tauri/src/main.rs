#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod runtime;

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use tauri::{Manager, State, TitleBarStyle, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

static TERMINATE_REQUESTED: AtomicBool = AtomicBool::new(false);

extern "C" fn terminate_signal(_signal: libc::c_int) {
    // The signal handler performs no allocation, locks or process operations.
    TERMINATE_REQUESTED.store(true, Ordering::SeqCst);
}

fn require_bootstrap(window: &WebviewWindow) -> Result<(), String> {
    let url = window
        .url()
        .map_err(|_| "Unable to verify the startup screen.")?;
    if runtime::is_bootstrap_origin(&url) {
        Ok(())
    } else {
        Err("Native runtime controls are available only to the bundled startup screen.".into())
    }
}

#[tauri::command]
fn runtime_status(
    window: WebviewWindow,
    runtime: State<'_, Arc<runtime::LocalRuntime>>,
) -> Result<runtime::RuntimeStatus, String> {
    require_bootstrap(&window)?;
    Ok(runtime.status())
}

#[tauri::command]
fn runtime_retry(
    window: WebviewWindow,
    runtime: State<'_, Arc<runtime::LocalRuntime>>,
) -> Result<runtime::RuntimeStatus, String> {
    require_bootstrap(&window)?;
    runtime.start();
    Ok(runtime.status())
}

#[tauri::command]
fn runtime_open(
    window: WebviewWindow,
    runtime: State<'_, Arc<runtime::LocalRuntime>>,
) -> Result<(), String> {
    require_bootstrap(&window)?;
    let origin = runtime.ready_origin()?;
    window
        .navigate(origin)
        .map_err(|_| String::from("The workspace could not be opened. Please retry."))?;
    runtime.record_open();
    Ok(())
}

fn main() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            runtime_status,
            runtime_retry,
            runtime_open
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // Follow macOS's normal close-window behavior. The app and its
                // owned runtime stay available for a later Dock click.
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .setup(|app| {
            let resource_dir = app.path().resource_dir()?;
            let runtime = Arc::new(runtime::LocalRuntime::new(resource_dir.join("frontend")));
            app.manage(runtime.clone());
            let window = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::App("index.html?desktop=boot".into()),
            )
            .title("Chemistry Studio")
            .inner_size(1280.0, 860.0)
            .min_inner_size(800.0, 600.0)
            .center()
            .title_bar_style(TitleBarStyle::Overlay)
            .hidden_title(true)
            .initialization_script("window.__CHEMISTRY_DESKTOP__ = true;")
            .on_navigation(|url| {
                if runtime::is_internal_navigation(url) {
                    return true;
                }
                // Ordinary research citations open in the user's browser.
                // This accepts web URLs only, never paths or shell text.
                if matches!(url.scheme(), "http" | "https")
                    && url.username().is_empty()
                    && url.password().is_none()
                {
                    let _ = std::process::Command::new("/usr/bin/open")
                        .arg(url.as_str())
                        .spawn();
                }
                false
            })
            .build()?;
            window.show()?;
            app.set_menu(tauri::menu::Menu::default(app.handle())?)?;
            // Make ordinary process termination follow the same ownership-safe
            // cleanup as Command-Q. SIGKILL still follows the operating system.
            unsafe {
                libc::signal(
                    libc::SIGTERM,
                    terminate_signal as *const () as libc::sighandler_t,
                );
                libc::signal(
                    libc::SIGINT,
                    terminate_signal as *const () as libc::sighandler_t,
                );
            }
            let handle = app.handle().clone();
            std::thread::spawn(move || loop {
                if TERMINATE_REQUESTED.swap(false, Ordering::SeqCst) {
                    handle.exit(0);
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(150));
            });
            runtime.start();
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Chemistry Studio could not create its native window");
    app.run(|app, event| {
        if let tauri::RunEvent::Reopen { .. } = event {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }
        if matches!(
            event,
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
        ) {
            app.state::<Arc<runtime::LocalRuntime>>().shutdown();
        }
    });
}
