# -*- mode: python ; coding: utf-8 -*-
"""
LOKI Agent — Optimized PyInstaller Specification File (loki.spec)

Optimizes standalone executable footprint, compilation duration, and startup speed:
1. Prunes `litellm.proxy` (~50MB of Next.js frontend chunks, Prisma schemas, FastAPI proxy routes).
2. Filters out developer & testing dependencies (pytest, unittest, doctest).
3. Excludes unused GUI frameworks and dev tools (tkinter, tcl, pydoc, idlelib, pdb).
4. Excludes runtime build/packaging tools (pip, setuptools, wheel).
5. Collects Playwright driver binaries and LiteLLM core completion submodules without dead weight.
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

repo_root = Path(os.path.abspath(SPECPATH))

# --- 1. Targeted Dependency Harvesting ---

# Playwright: requires browser driver bindings and runtime assets
playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")

# Rich & Typer: terminal formatting and CLI infrastructure
rich_datas, rich_binaries, rich_hidden = collect_all("rich")
typer_datas, typer_binaries, typer_hidden = collect_all("typer")

# LiteLLM: Surgical harvest of core completions & providers
# Retains Python submodules while omitting tests and benchmarks
litellm_submodules = [
    mod for mod in collect_submodules("litellm")
    if "test" not in mod
    and "benchmark" not in mod
]

# Harvest data files (model pricing, provider configs) while strictly omitting 860+ web UI assets
litellm_datas = [
    (src, dst) for src, dst in collect_data_files("litellm")
    if "proxy" not in src
    and "_experimental" not in src
    and "out" not in src
]

# LOKI's own artifact templates (repro scripts, HTML report), read via importlib.resources
loki_template_datas = [(str(repo_root / "src" / "loki" / "templates"), "loki/templates")]

# Combined datas, binaries, and hidden imports
datas = playwright_datas + rich_datas + typer_datas + litellm_datas + loki_template_datas
binaries = playwright_binaries + rich_binaries + typer_binaries

hiddenimports = (
    playwright_hidden
    + rich_hidden
    + typer_hidden
    + litellm_submodules
    + [
        "loki.cli",
        "loki.config",
        "loki.models",
        "loki.safety",
        "loki.templates",
        "loki.ai.brain",
        "loki.ai.chat",
        "loki.ai.llm",
        "loki.engine.api_chaos",
        "loki.engine.browser",
        "loki.engine.ci",
        "loki.engine.detectors",
        "loki.engine.devices",
        "loki.engine.healer",
        "loki.engine.html_reporter",
        "loki.engine.infra_chaos",
        "loki.engine.recorder",
        "loki.engine.replayer",
        "loki.engine.reporter",
        "loki.engine.sandbox",
        "loki.engine.scanner",
        "loki.engine.scrubber",
        "loki.engine.updater",
        "loki.personas.adversary",
        "loki.personas.base",
        "loki.personas.network_tormentor",
        "loki.personas.novice_chaotic",
        "loki.personas.rage_clicker",
        "loki.personas.registry",
        "loki.personas.swarm",
        "loki.services.heal",
        "loki.services.run",
        "PIL",
        "yaml",
        "psutil",
        "prompt_toolkit",
        "tenacity",
    ]
)

# --- 2. Comprehensive Dead-Weight Exclusions ---

excludes = [
    # LiteLLM heavy web proxy servers & ASGI runtimes
    "fastapi",
    "starlette",
    "uvicorn",
    # Testing suites & runners
    "pytest",
    "_pytest",
    "unittest",
    "doctest",
    "test",
    # Packaging & build-time tools
    "pip",
    "setuptools",
    "distutils",
    "wheel",
    "pkg_resources.tests",
    # GUI and debug utilities
    "tkinter",
    "Tkinter",
    "_tkinter",
    "tcl",
    "turtle",
    "idlelib",
    "pydoc",
    "pdb",
    # Heavy scientific / interactive suites
    "matplotlib",
    "scipy",
    "IPython",
    "notebook",
    "jupyter",
    "PIL.ImageQt",
    "PIL.ImageTk",
]

# --- 3. Analysis & Build Configuration ---

a = Analysis(
    ["loki_entry.py"],
    pathex=[str(repo_root / "src"), str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- 4. Windows Executable Metadata & Icon ---

import re

init_text = (repo_root / "src" / "loki" / "__init__.py").read_text(encoding="utf-8")
version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_text)
version_str = version_match.group(1) if version_match else "1.0.0"
version_nums = [int(n) for n in re.findall(r"\d+", version_str)[:4]]
while len(version_nums) < 4:
    version_nums.append(0)
version_tuple = tuple(version_nums[:4])

win_version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32 import versioninfo

    win_version_info = versioninfo.VSVersionInfo(
        ffi=versioninfo.FixedFileInfo(
            filevers=version_tuple,
            prodvers=version_tuple,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            versioninfo.StringFileInfo(
                [
                    versioninfo.StringTable(
                        "040904B0",
                        [
                            versioninfo.StringStruct("CompanyName", "Elabsurdo984"),
                            versioninfo.StringStruct(
                                "FileDescription",
                                "LOKI - Autonomous AI Testing & Synthetic Chaos Agent",
                            ),
                            versioninfo.StringStruct("FileVersion", version_str),
                            versioninfo.StringStruct("InternalName", "loki"),
                            versioninfo.StringStruct(
                                "LegalCopyright",
                                "Copyright (c) Elabsurdo984. MIT License.",
                            ),
                            versioninfo.StringStruct("OriginalFilename", "loki.exe"),
                            versioninfo.StringStruct("ProductName", "LOKI Chaos Agent"),
                            versioninfo.StringStruct("ProductVersion", version_str),
                        ],
                    )
                ]
            ),
            versioninfo.VarFileInfo([versioninfo.VarStruct("Translation", [1033, 1200])]),
        ],
    )

icon_path = str(repo_root / "assets" / "logo.ico") if (repo_root / "assets" / "logo.ico").exists() else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="loki",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=win_version_info,
    icon=icon_path,
)
