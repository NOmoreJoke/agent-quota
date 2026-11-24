use tauri::{AppHandle, Manager, Window, WindowEvent};

pub(crate) const CLOSE_WINDOW_MENU_ID: &str = "quota-close-window";

pub(crate) fn application_menu(app: &AppHandle) -> tauri::Result<tauri::menu::Menu<tauri::Wry>> {
    #[cfg(not(target_os = "macos"))]
    return tauri::menu::Menu::default(app);

    #[cfg(target_os = "macos")]
    {
        use tauri::menu::{
            AboutMetadata, HELP_SUBMENU_ID, MenuBuilder, MenuItem, SubmenuBuilder,
            WINDOW_SUBMENU_ID,
        };
        // AppKit's predefined performClose: ignores borderless windows. Route both
        // menu entries through Tauri so our CloseRequested recovery also handles Cmd+W.
        let close = MenuItem::with_id(
            app,
            CLOSE_WINDOW_MENU_ID,
            "Close Window",
            true,
            Some("CmdOrCtrl+W"),
        )?;
        let package = app.package_info();
        let about = AboutMetadata {
            name: Some(package.name.clone()),
            version: Some(package.version.to_string()),
            copyright: app.config().bundle.copyright.clone(),
            authors: app.config().bundle.publisher.clone().map(|name| vec![name]),
            ..Default::default()
        };
        MenuBuilder::new(app)
            .items(&[
                &SubmenuBuilder::new(app, &package.name)
                    .about(Some(about))
                    .separator()
                    .services()
                    .separator()
                    .hide()
                    .hide_others()
                    .separator()
                    .quit()
                    .build()?,
                &SubmenuBuilder::new(app, "File").item(&close).build()?,
                &SubmenuBuilder::new(app, "Edit")
                    .undo()
                    .redo()
                    .separator()
                    .cut()
                    .copy()
                    .paste()
                    .select_all()
                    .build()?,
                &SubmenuBuilder::new(app, "View").fullscreen().build()?,
                &SubmenuBuilder::with_id(app, WINDOW_SUBMENU_ID, "Window")
                    .minimize()
                    .maximize()
                    .separator()
                    .item(&close)
                    .build()?,
                &SubmenuBuilder::with_id(app, HELP_SUBMENU_ID, "Help").build()?,
            ])
            .build()
    }
}

pub(crate) fn window_ready(app: &AppHandle) -> bool {
    let Some(window) = app.get_webview_window("main") else {
        return false;
    };
    window.is_visible().ok() == Some(true)
        && window.is_minimized().ok() == Some(false)
        && window.is_focused().ok() == Some(true)
}

pub(crate) fn restore_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

pub(crate) fn position_and_show_floating(app: &tauri::App) {
    if let Some(floating) = app.get_webview_window("floating") {
        if let Ok(Some(monitor)) = floating.primary_monitor() {
            let area = monitor.work_area();
            let scale = monitor.scale_factor();
            let _ = floating.set_position(tauri::PhysicalPosition::new(
                area.position.x + (f64::from(area.size.width) - 404.0 * scale).max(0.0) as i32,
                area.position.y + (24.0 * scale) as i32,
            ));
        }
        let _ = floating.show();
    }
}

pub(crate) fn handle_window_event(window: &Window, event: &WindowEvent) {
    if window.label() == "floating"
        && let WindowEvent::CloseRequested { api, .. } = event
    {
        api.prevent_close();
        restore_main_window(window.app_handle());
        let _ = window.hide();
    }
    if window.label() == "main"
        && let WindowEvent::CloseRequested { api, .. } = event
        && let Some(floating) = window.app_handle().get_webview_window("floating")
        && floating.show().is_ok()
    {
        api.prevent_close();
        let _ = window.hide();
    }
}
