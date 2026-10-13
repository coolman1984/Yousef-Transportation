"""One-time config.json adjustments when the installed program is updated (never touches the data databases)."""


def migrate_config(cfg):
    """Apply in-place migrations. Returns True when config.json should be rewritten."""
    changed = False
    # Before the desktop shell, some pilot builds stored this experimental flag.
    if cfg.pop('edge_webview', None) is not None:
        changed = True
    if cfg.pop('force_system_browser', None) is not None:
        changed = True
    # ui_mode: "window" (default for TripOrders.exe) or "browser" (legacy / troubleshooting).
    mode = cfg.get('ui_mode')
    if mode is not None and mode not in ('window', 'browser'):
        cfg['ui_mode'] = 'window'
        changed = True
    return changed
