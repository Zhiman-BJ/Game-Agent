#!/usr/bin/env python3
"""Read-only byte comparison of two Godot projects; no engine or source parsing.

The caller supplies BEFORE/AFTER order. Projects must remain stationary during
the scan. Excluded names are omitted from manifests, but all tree entries are
still checked for symbolic links and special files.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


EXCLUDED_NAMES = frozenset({".git", ".godot", "__pycache__", ".DS_Store"})
KINDS = ("script", "scene", "resource", "project", "uid", "asset", "other")
ASSET_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".tga", ".gif",
    ".ico", ".exr", ".hdr", ".dds", ".ktx", ".ktx2", ".basis",
    ".wav", ".ogg", ".mp3", ".flac", ".aiff", ".aif", ".opus",
    ".ttf", ".otf", ".woff", ".woff2", ".fnt", ".font",
    ".glb", ".gltf", ".obj", ".fbx", ".blend", ".dae", ".mesh",
    ".mp4", ".webm", ".ogv", ".avi", ".mov",
})
LIMITATIONS = [
    "This report records file bytes only. It cannot prove semantic differences, "
    "sufficient ablation, runtime correctness, or task difficulty.",
    "BEFORE and AFTER follow the caller's arguments; direction is not inferred.",
    "No Godot engine, scene parser, or source parser is invoked. Extension-based "
    "classification is descriptive; paths, not renames, are compared.",
    "Excluded names are omitted from hashes at every depth. Symlinks and special "
    "files are rejected even inside excluded directories.",
    "Inputs must remain unchanged during scanning; this is not an atomic snapshot "
    "or a defense against concurrent hostile filesystem changes.",
]


class DeltaError(ValueError):
    """Invalid or unsafe input/output path."""


def classify(relative_path):
    path = Path(relative_path)
    if path.name == "project.godot":
        return "project"
    suffix = path.suffix.lower()
    for kind, suffixes in (
        ("script", {".gd", ".cs"}),
        ("scene", {".tscn", ".scn"}),
        ("resource", {".tres", ".res"}),
        ("uid", {".uid"}),
    ):
        if suffix in suffixes:
            return kind
    return "asset" if suffix in ASSET_SUFFIXES else "other"


def project_root(value):
    path = Path(value).expanduser()
    if path.is_symlink():
        raise DeltaError(f"Input root is a symlink: {path}")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise DeltaError(f"Input root is not a directory: {path}")
    project = root / "project.godot"
    if project.is_symlink() or not project.is_file():
        raise DeltaError(f"Input requires a regular project.godot file: {root}")
    return root


def hash_file(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise DeltaError(f"Special file is not allowed: {path}")
        digest = hashlib.sha256()
        size = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(stream.fileno())
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if signature(before) != signature(after) or size != before.st_size:
        raise DeltaError(f"File changed while being read: {path}")
    return {"size": size, "sha256": digest.hexdigest()}


def scan_project(root):
    files = {}

    def visit(directory, excluded=False):
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            mode = entry.stat(follow_symlinks=False).st_mode
            path = Path(entry.path)
            if stat.S_ISLNK(mode):
                raise DeltaError(f"Symlink is not allowed in input tree: {path}")
            omit = excluded or entry.name in EXCLUDED_NAMES
            if stat.S_ISDIR(mode):
                visit(path, omit)
            elif not stat.S_ISREG(mode):
                raise DeltaError(f"Special file is not allowed in input tree: {path}")
            elif not omit:
                files[path.relative_to(root).as_posix()] = hash_file(path)

    visit(root)
    files = dict(sorted(files.items()))
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "root": str(root),
        "file_count": len(files),
        "byte_count": sum(item["size"] for item in files.values()),
        "manifest_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "files": files,
    }


def compare_projects(before_root, after_root):
    before = scan_project(before_root)
    after = scan_project(after_root)
    changes = {kind: {status: [] for status in ("added", "deleted", "modified")}
               for kind in KINDS}
    summary = {"added": 0, "deleted": 0, "modified": 0, "unchanged": 0}
    by_kind = {kind: dict(summary) for kind in KINDS}
    for path in sorted(before["files"].keys() | after["files"].keys()):
        old = before["files"].get(path)
        new = after["files"].get(path)
        kind = classify(path)
        status = ("added" if old is None else "deleted" if new is None
                  else "unchanged" if old == new else "modified")
        summary[status] += 1
        by_kind[kind][status] += 1
        if status != "unchanged":
            changes[kind][status].append({"path": path, "before": old, "after": new})
    summary["by_kind"] = by_kind
    return {
        "schema_version": 1,
        "comparison": "byte-level SHA-256 and size by relative path",
        "excluded_names": sorted(EXCLUDED_NAMES),
        "limitations": LIMITATIONS,
        "before": before,
        "after": after,
        "summary": summary,
        "changes": changes,
    }


def validate_output(value, roots):
    path = Path(value).expanduser().absolute()
    # Check before resolve(), so symlink parents cannot disguise their target.
    for component in (path, *path.parents):
        if component.is_symlink():
            raise DeltaError(f"Output path must not contain a symlink: {component}")
    resolved = path.resolve()
    if any(resolved == root or root in resolved.parents for root in roots):
        raise DeltaError(f"Output must be outside both input trees: {resolved}")
    if resolved.exists() and not resolved.is_file():
        raise DeltaError(f"Output is not a regular file: {resolved}")
    return resolved


def write_report(output, report, roots):
    output = validate_output(output, roots)
    output.parent.mkdir(parents=True, exist_ok=True)
    output = validate_output(output, roots)
    temp_name = None
    try:
        # Replace, rather than truncate, an existing hard link to an input file.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=".project_delta-", suffix=".tmp",
                                         delete=False) as stream:
            temp_name = stream.name
            json.dump(report, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
        validate_output(output, roots)
        os.replace(temp_name, output)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", help="Caller-designated BEFORE Godot project")
    parser.add_argument("after", help="Caller-designated AFTER Godot project")
    parser.add_argument("--output", type=Path, help="Write full JSON outside both input trees")
    args = parser.parse_args(argv)
    try:
        roots = (project_root(args.before), project_root(args.after))
        output = validate_output(args.output, roots) if args.output is not None else None
        report = compare_projects(*roots)
        if output is None:
            print(json.dumps(report, indent=2, ensure_ascii=True))
        else:
            write_report(output, report, roots)
            counts = report["summary"]
            print("; ".join(f"{key}={counts[key]}" for key in
                            ("added", "deleted", "modified", "unchanged")))
            print(f"Full JSON: {output}")
            print(LIMITATIONS[0])
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(2, f"project_delta: error: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
