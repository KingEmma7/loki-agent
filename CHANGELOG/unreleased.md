# Unreleased

## Added
- **CLI Alias**: Added `loki-chaos` entry point alongside `loki`.
- **Windows Installer (`installer/`)**:
  - Inno Setup wizard (`loki-setup-windows-amd64.exe`) with custom install path, automatic `PATH` setup, desktop/Start Menu shortcuts, folder right-click "Open LOKI Chaos here", and optional Playwright Chromium setup.
  - PE publisher metadata on the Windows binary and a code-signing workflow (`installer/sign_windows.ps1`).

## Changed
- **Branding**: Unified product display name as **LOKI Chaos** across CLI output, HTML reports, reproduction templates, installer, and documentation.
- **Selective CI (`.github/workflows/loki.yml`)**: jobs are path-filtered so only the relevant ones (tests, security, packaging, chaos) run for a given change, with a fast push matrix.
- **Release workflow**: the PyPI publish job now runs in the `pypi` environment.
- `loki init` now suggests `loki run <url>` instead of `python -m loki.cli run <url>`.
- The scaffolded `.loki/config.yaml` uses `ai.model: gemini/gemini-flash-latest`, identical to the bundled default, and no longer counts as a customized AI connection.

## Documentation
- README: PyPI install instructions, `--browser`, `--seed` and `--api-chaos` documented, accurate repository tree, multi-browser badge, and `loki infra pause` marked as experimental.
- `SECURITY.md`: supported version is now `v1.10.x`.
