"""Write a release version into ./Cargo.toml, and ./Cargo.lock if there is one.

Cargo only accepts a literal `version`, so there is no setuptools_scm for it:
the committed Cargo.toml holds a 0.0.0 placeholder, and this runs just before a
build to write the tag's version in. It sets whichever of these exist:

    [package] version                     single-crate projects
    [workspace.package] version           workspaces, inherited by members
    [workspace.dependencies] path deps    internal pins, kept `=` if they were

In Cargo.lock it sets the version of every package of this repository that
has the version Cargo.toml had: those with no `source`, which registry and git
packages have. Without that the lock no longer matches the manifest, and
`cargo build --locked` refuses to run.

tomlkit rewrites only those values, so comments and layout survive, and the
lock stays byte for byte what cargo itself would write.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tomlkit
from tomlkit.items import Table

CARGO_TOML = Path("Cargo.toml")
CARGO_LOCK = Path("Cargo.lock")


def _table(parent: Table | tomlkit.TOMLDocument, key: str) -> Table | None:
    item = parent.get(key)
    return item if isinstance(item, Table) else None


def stamp(text: str, version: str) -> tuple[str, list[str], set[str]]:
    """The manifest with `version` written in, the fields set, and the
    versions they had."""
    doc = tomlkit.parse(text)
    stamped: list[str] = []
    old: set[str] = set()

    # `version.workspace = true` parses to a table, so the isinstance check
    # leaves an inheriting package alone.
    package = _table(doc, "package")
    if package is not None and isinstance(package.get("version"), str):
        old.add(str(package["version"]))
        package["version"] = version
        stamped.append("[package] version")

    workspace = _table(doc, "workspace")
    if workspace is not None:
        workspace_package = _table(workspace, "package")
        if workspace_package is not None and "version" in workspace_package:
            old.add(str(workspace_package["version"]))
            workspace_package["version"] = version
            stamped.append("[workspace.package] version")

        dependencies = _table(workspace, "dependencies")
        for name, dep in (dependencies or {}).items():
            if isinstance(dep, dict) and "path" in dep and "version" in dep:
                pin = "=" if str(dep["version"]).startswith("=") else ""
                dep["version"] = f"{pin}{version}"
                stamped.append(f"[workspace.dependencies] {name}")

    return tomlkit.dumps(doc), stamped, old


def stamp_lock(text: str, old: set[str], version: str) -> tuple[str, list[str]]:
    """The lock with `version` written into this repository's own packages
    that were at one of the `old` versions, and their names."""
    doc = tomlkit.parse(text)
    stamped: list[str] = []
    for package in doc.get("package", []):
        if "source" not in package and str(package["version"]) in old:
            package["version"] = version
            stamped.append(str(package["name"]))
    return tomlkit.dumps(doc), stamped


def main() -> None:
    version = sys.argv[1].removeprefix("v")
    text, stamped, old = stamp(CARGO_TOML.read_text(), version)
    if not stamped:
        raise SystemExit(f"error: no version field to stamp in {CARGO_TOML.resolve()}")
    CARGO_TOML.write_text(text)
    for field in stamped:
        print(f"{field} = {version}")
    if CARGO_LOCK.exists():
        text, packages = stamp_lock(CARGO_LOCK.read_text(), old, version)
        CARGO_LOCK.write_text(text)
        for name in packages:
            print(f"Cargo.lock {name} = {version}")


if __name__ == "__main__":
    main()
