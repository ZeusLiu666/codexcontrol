"""Small, deterministic release helpers; never read application account data."""
from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
import re
import struct
import sys
import zipfile

PORTABLE_FILES = (
    "CodexControl.exe", "install.ps1", "README.md", "LICENSE",
    "THIRD_PARTY_NOTICES.txt",
)
RUNTIME_DISTRIBUTIONS = (
    "certifi", "charset-normalizer", "idna", "pillow", "pyinstaller",
    "pystray", "requests", "six", "urllib3",
)
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
NATIVE_LICENSE_SOURCES = {
    "bzip2.txt": "https://github.com/libarchive/bzip2/tree/bzip2-1.0.8",
    "Expat.txt": "https://github.com/libexpat/libexpat/tree/R_2_6_3",
    "InnoSetup.txt": "https://github.com/jrsoftware/issrc/tree/is-6_5_3",
    "libffi.txt": "https://github.com/libffi/libffi/tree/v3.4.4",
    "OpenSSL.txt": "https://github.com/openssl/openssl/tree/openssl-3.0.15",
    "Tcl.txt": "https://github.com/tcltk/tcl/tree/core-8-6-14",
    "xz.txt": "https://github.com/tukaani-project/xz/tree/v5.4.6",
    "zlib.txt": "https://github.com/madler/zlib/tree/v1.2.13",
}


def requirement_pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", line)
        if not match:
            raise ValueError("Release dependencies must use exact == version pins")
        pins[match[1]] = match[2]
    if not pins:
        raise ValueError("Release dependency pins are empty")
    return pins


def verify_dependencies(requirements: Path) -> None:
    if sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise RuntimeError("Build with 64-bit Python 3.12")
    for name, expected in requirement_pins(requirements).items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError(f"Dependency {name}: expected {expected}, found {actual}")
    print("Pinned release dependencies verified")


def version_resource(version: str, output: Path) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must have three numeric components")
    parts = tuple(int(part) for part in version.split(".")) + (0,)
    if any(part > 65535 for part in parts):
        raise ValueError("Version component exceeds Windows resource limits")
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo,
    )
    resource = VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts, mask=0x3F,
                          flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "CodexControl contributors"),
                StringStruct("FileDescription", "CodexControl for Windows"),
                StringStruct("FileVersion", version),
                StringStruct("InternalName", "CodexControl"),
                StringStruct("LegalCopyright", "CodexControl contributors"),
                StringStruct("OriginalFilename", "CodexControl.exe"),
                StringStruct("ProductName", "CodexControl"),
                StringStruct("ProductVersion", version),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(str(resource) + "\n", encoding="utf-8", newline="\n")


def portable_zip(source: Path, output: Path) -> None:
    if source.is_symlink() or source.is_junction() or not source.is_dir():
        raise ValueError("Portable payload must be an ordinary directory")
    actual = {entry.name for entry in source.iterdir()}
    if actual != set(PORTABLE_FILES):
        raise ValueError("Portable payload does not match the release file allowlist")
    for name in PORTABLE_FILES:
        path = source / name
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError("Portable payload must contain ordinary files only")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in PORTABLE_FILES:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.create_system = 0
            info.external_attr = 0x20
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (source / name).read_bytes(), compresslevel=9)


def third_party_notices(output: Path) -> None:
    sections = [
        "CodexControl for Windows - third-party notices\n"
        "This distribution includes the unmodified components listed below.\n"
        "Their copyrights and licenses belong to their respective authors.\n"
        "Application source and pinned rebuild instructions accompany the project.\n"
        "pystray source: https://github.com/moses-palmer/pystray/tree/v0.19.5\n"
        "You may replace the LGPL pystray component by rebuilding from source.\n"
    ]
    for name in RUNTIME_DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        files = sorted(
            (file for file in distribution.files or []
             if any(word in file.name.lower() for word in ("license", "copying", "notice"))
             and ".dist-info/" in file.as_posix()),
            key=lambda file: file.as_posix(),
        )
        if not files:
            raise RuntimeError(f"No bundled license found for {name}")
        sections.append(f"\n{'=' * 72}\n{name} {distribution.version}\n{'=' * 72}\n")
        for file in files:
            sections.append(f"\n{file.name}\n\n" + Path(distribution.locate_file(file)).read_text(encoding="utf-8", errors="replace"))
    # Support both python.org and Conda layouts without writing their local paths.
    runtime = Path(sys.base_prefix)
    python_license = next((path for path in (runtime / "LICENSE.txt", runtime / "LICENSE_PYTHON.txt") if path.is_file()), None)
    if python_license is None:
        raise RuntimeError("Python runtime license could not be located")
    sections.append("\n" + "=" * 72 + "\nPython runtime\n" + "=" * 72 + "\n")
    sections.append(python_license.read_text(encoding="utf-8", errors="replace"))
    tcl_licenses = sorted({
        path for prefix in (runtime / "tcl", runtime / "Library" / "lib")
        for path in prefix.glob("t[kc]l*/license.terms")
    })
    # Tk's directory is tk8.x, while Tcl's is tcl8.x.
    tcl_licenses += sorted({
        path for prefix in (runtime / "tcl", runtime / "Library" / "lib")
        for path in prefix.glob("tk*/license.terms")
    } - set(tcl_licenses))
    if not tcl_licenses:
        raise RuntimeError("Tcl/Tk runtime license could not be located")
    for path in tcl_licenses:
        sections.append("\n" + "=" * 72 + f"\n{path.parent.name} runtime\n" + "=" * 72 + "\n")
        sections.append(path.read_text(encoding="utf-8", errors="replace"))
    for name, source in NATIVE_LICENSE_SOURCES.items():
        path = Path(__file__).resolve().parent / "licenses" / name
        sections.append("\n" + "=" * 72 + f"\nBundled component: {name}\nUpstream: {source}\n" + "=" * 72 + "\n")
        sections.append(path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sections).replace("\r\n", "\n") + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-dependencies").add_argument("--requirements", type=Path, required=True)
    resource = sub.add_parser("version-resource")
    resource.add_argument("--version", required=True)
    resource.add_argument("--output", type=Path, required=True)
    archive = sub.add_parser("portable-zip")
    archive.add_argument("--source", type=Path, required=True)
    archive.add_argument("--output", type=Path, required=True)
    sub.add_parser("third-party-notices").add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify-dependencies":
        verify_dependencies(args.requirements)
    elif args.command == "version-resource":
        version_resource(args.version, args.output)
    elif args.command == "portable-zip":
        portable_zip(args.source, args.output)
    else:
        third_party_notices(args.output)


if __name__ == "__main__":
    main()
