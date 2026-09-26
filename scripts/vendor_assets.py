"""Download pinned third-party assets for the offline desktop viewer.

Usage::

    uv run python scripts/vendor_assets.py

Fetches Mermaid, KaTeX and IBM Plex Mono from the npm registry, checks each
tarball against the registry's published SHA-512 integrity hash, and copies
only the files the viewer needs into
``src/md_viewer_desktop/resources/``. Re-running is safe; files are
overwritten. Bump a version here, re-run, and commit the result.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src" / "md_viewer_desktop" / "resources"
REGISTRY = "https://registry.npmjs.org"


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    # tarball member (relative to "package/") -> destination under RESOURCES
    files: dict[str, str] = field(default_factory=dict)
    # (tarball dir prefix, suffix, destination dir) copied wholesale
    globs: tuple[tuple[str, str, str], ...] = ()


PLEX_WEIGHTS = ("Regular", "Medium", "SemiBold", "Italic")

PACKAGES = (
    Package(
        name="mermaid",
        # Same major as view.html loads (mermaid@10); UMD build for a plain <script>.
        version="10.9.3",
        files={
            "dist/mermaid.min.js": "vendor/mermaid/mermaid.min.js",
            "LICENSE": "vendor/mermaid/LICENSE",
        },
    ),
    Package(
        name="katex",
        version="0.16.22",
        files={
            "dist/katex.min.js": "vendor/katex/katex.min.js",
            "dist/katex.min.css": "vendor/katex/katex.min.css",
            "dist/contrib/auto-render.min.js": "vendor/katex/auto-render.min.js",
            "LICENSE": "vendor/katex/LICENSE",
        },
        # QtWebEngine always supports WOFF2, so skip the woff/ttf fallbacks.
        globs=(("dist/fonts/", ".woff2", "vendor/katex/fonts"),),
    ),
    Package(
        name="@ibm/plex-mono",
        version="1.1.0",
        files={
            **{
                # WOFF (zlib) for QFontDatabase: the npm package ships no TTF, and
                # FreeType reads WOFF everywhere, unlike WOFF2 (needs brotli).
                f"fonts/complete/woff/IBMPlexMono-{w}.woff": f"fonts/IBMPlexMono-{w}.woff"
                for w in PLEX_WEIGHTS
            },
            **{
                f"fonts/complete/woff2/IBMPlexMono-{w}.woff2": f"fonts/IBMPlexMono-{w}.woff2"
                for w in PLEX_WEIGHTS
            },
            "LICENSE.txt": "fonts/OFL.txt",
        },
    ),
)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "md-viewer-vendor"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _verify(data: bytes, integrity: str, label: str) -> None:
    algorithm, _, expected = integrity.partition("-")
    if algorithm != "sha512":
        raise SystemExit(f"{label}: unsupported integrity algorithm {algorithm!r}")
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if actual != expected:
        raise SystemExit(f"{label}: integrity check failed")


def vendor(package: Package) -> list[Path]:
    label = f"{package.name}@{package.version}"
    meta = json.loads(_get(f"{REGISTRY}/{package.name}/{package.version}"))
    dist = meta["dist"]
    tarball = _get(dist["tarball"])
    _verify(tarball, dist["integrity"], label)

    written: list[Path] = []
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        members = {
            m.name.removeprefix("package/"): m for m in archive.getmembers() if m.isfile()
        }
        wanted = dict(package.files)
        for prefix, suffix, dest_dir in package.globs:
            for name in members:
                if name.startswith(prefix) and name.endswith(suffix):
                    wanted[name] = f"{dest_dir}/{name.rsplit('/', 1)[-1]}"

        for source, dest in sorted(wanted.items()):
            member = members.get(source)
            if member is None:
                raise SystemExit(f"{label}: {source} not found in tarball")
            target = RESOURCES / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            assert extracted is not None
            with extracted, target.open("wb") as handle:
                shutil.copyfileobj(extracted, handle)
            written.append(target)

    print(f"{label}: {len(written)} files")
    return written


def main() -> int:
    for package in PACKAGES:
        vendor(package)
    versions = {p.name: p.version for p in PACKAGES}
    (RESOURCES / "vendor").mkdir(parents=True, exist_ok=True)
    (RESOURCES / "vendor" / "VERSIONS.json").write_text(
        json.dumps(versions, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
