"""Profile-selected Chrome, extensions, and component sources."""

PLATFORM_SOURCE_OVERRIDES = {
    "darwin-arm64": {
        "chrome/browser/media/router/discovery/discovery_network_list_wifi_linux.cc": "chrome/browser/media/router/discovery/discovery_network_list_posix.cc",
    },
    "windows-amd64": {
        "chrome/browser/media/router/discovery/discovery_network_list_wifi_linux.cc": "chrome/browser/media/router/discovery/discovery_network_list_win.cc",
    },
    "windows-arm64": {
        "chrome/browser/media/router/discovery/discovery_network_list_wifi_linux.cc": "chrome/browser/media/router/discovery/discovery_network_list_win.cc",
    },
}

SOURCE_GROUPS = {
    "//chrome/utility:utility": [
        "chrome/utility/services.cc",
    ],
    "//chrome/renderer/extensions:extensions": [
        "chrome/renderer/extensions/api/chrome_extensions_renderer_api_provider.cc",
    ],
    "//extensions/renderer:renderer": [
        "extensions/renderer/worker_thread_dispatcher.cc",
        "extensions/renderer/bindings/api_binding.cc",
    ],
    "//chrome/renderer:renderer": [
        "chrome/renderer/accessibility/phrase_segmentation/dependency_tree.cc",
        "chrome/renderer/chrome_content_renderer_client.cc",
    ],
    "//chrome/browser/media/router/discovery:discovery": [
        "chrome/browser/media/router/discovery/discovery_network_list_wifi_linux.cc",
    ],
    "//chrome/browser/extensions/api/notifications:notifications": [
        "chrome/browser/extensions/api/notifications/extension_notification_display_helper.cc",
    ],
    "//chrome/browser/ui:ui": [
        "chrome/browser/ui/browser.cc",
        "chrome/browser/ui/views/frame/browser_view.cc",
        "chrome/browser/ui/webui/new_tab_page/new_tab_page_ui.cc",
    ],
    "//chrome/browser/ui/views/toolbar:impl": [
        "chrome/browser/ui/views/toolbar/toolbar_view.cc",
    ],
    "//components/password_manager/core/browser:browser": [
        "components/password_manager/core/browser/password_manager.cc",
    ],
    "//components/omnibox/browser:browser": [
        "components/omnibox/browser/autocomplete_controller.cc",
    ],
}
