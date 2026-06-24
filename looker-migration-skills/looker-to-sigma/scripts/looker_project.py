#!/usr/bin/env python3
"""looker_project.py — pull a Looker project's LookML over the REST API (no local
Git checkout) and resolve a project/explore's warehouse connection target.

Motivation (2026-06-18 postmortem follow-up): migrate-looker.py required
`--lookml-dir` (a local checkout of the LookML repo). This adds an API path so a
migration can run from just a project id, and lets the orchestrator AUTO-DERIVE
the `--source-swap` by asking Looker what DB.SCHEMA the project's connection
actually targets (the postmortem's #3 was hand-patching CSA.TJ → the Sigma
connection's schema).

Uses looker_api.py for auth (reads ~/.looker/looker.ini). Two capabilities:

  pull <project_id> <out_dir>
      Switch the API session to the `dev` workspace, list the project's files,
      and write every .lkml (model + views + dashboard) under <out_dir> mirroring
      its path. Requires the API user to have DEVELOP permission on the project
      (Looker only serves raw LookML in dev mode — `can.show_raw`). If that's
      missing the command exits non-zero with an actionable message (clone the
      Git repo and use --lookml-dir instead).

  connection <model> <explore>
      Print the warehouse target of the explore's connection as DB.SCHEMA (from
      GET /connections/{name}). This works in PRODUCTION (no develop permission)
      and is what migrate-looker.py uses for --auto-source-swap.

Both are importable: pull_project(), explore_connection_target().
"""
import json, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import looker_api


def _ok(code):
    return 200 <= code < 300


def list_models(project_id=None):
    """Models (optionally filtered to a project) — to resolve which model/explore
    belongs to a project when the caller only knows the project id."""
    code, models = looker_api.call("GET", "/lookml_models")
    if not _ok(code) or not isinstance(models, list):
        return []
    if project_id:
        models = [m for m in models if m.get("project_name") == project_id]
    return models


def explore_connection_target(model, explore):
    """Return (connection_name, DB, SCHEMA) for an explore, or (None, None, None).
    Production-safe (no develop permission needed)."""
    code, ex = looker_api.call(
        "GET", f"/lookml_models/{model}/explores/{urllib.parse.quote(explore)}"
        "?fields=connection_name")
    if not _ok(code) or not isinstance(ex, dict):
        return None, None, None
    conn = ex.get("connection_name")
    if not conn:
        # Fall back to the model's connection.
        code, m = looker_api.call("GET", f"/lookml_models/{urllib.parse.quote(model)}"
                                  "?fields=name,allowed_db_connection_names")
        conn = (m.get("allowed_db_connection_names") or [None])[0] if isinstance(m, dict) else None
    if not conn:
        return None, None, None
    code, c = looker_api.call("GET", f"/connections/{urllib.parse.quote(conn)}"
                              "?fields=name,database,schema")
    if not _ok(code) or not isinstance(c, dict):
        return conn, None, None
    return conn, c.get("database"), c.get("schema")


def pull_project(project_id, out_dir):
    """Pull all .lkml files of a project to out_dir via the API. Returns the list
    of written paths. Raises RuntimeError with an actionable message if the API
    user can't read raw LookML (no develop permission / project not dev-enabled)."""
    # Looker serves raw LookML only in the dev workspace.
    looker_api.call("PATCH", "/session", {"workspace_id": "dev"})
    code, files = looker_api.call("GET", f"/projects/{urllib.parse.quote(project_id)}/files")
    if not _ok(code) or not isinstance(files, list):
        raise RuntimeError(f"could not list files for project {project_id!r} "
                           f"(HTTP {code}: {str(files)[:160]})")
    lkml = [f for f in files if str(f.get("path", "")).endswith(".lkml")]
    if not lkml:
        raise RuntimeError(f"project {project_id!r} exposes no .lkml files over the API")
    written, blocked = [], []
    for f in lkml:
        fid = f.get("id") or f.get("path")
        code, resp = looker_api.call(
            "GET", f"/projects/{urllib.parse.quote(project_id)}/files/file"
            f"?file_id={urllib.parse.quote(fid, safe='')}")
        content = resp.get("content") if isinstance(resp, dict) else resp
        if not content:
            if isinstance(resp, dict) and resp.get("can", {}).get("show_raw") is False:
                blocked.append(f.get("path"))
            continue
        dest = os.path.join(out_dir, f["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as fh:
            fh.write(content)
        written.append(f["path"])
    if blocked and not written:
        raise RuntimeError(
            f"Looker returned metadata but no raw LookML for project {project_id!r} "
            f"(can.show_raw=false on {len(blocked)} file(s)). The API user needs "
            "DEVELOP permission on this project (raw LookML is only served in the dev "
            "workspace). Clone the Git repo and pass --lookml-dir instead.")
    return written


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: looker_project.py pull <project_id> <out_dir> | "
                 "connection <model> <explore>")
    cmd = sys.argv[1]
    if cmd == "pull":
        project_id, out_dir = sys.argv[2], sys.argv[3]
        try:
            written = pull_project(project_id, out_dir)
        except RuntimeError as e:
            sys.exit(f"FATAL: {e}")
        print(f"pulled {len(written)} LookML file(s) from project {project_id} → {out_dir}")
        for p in written:
            print("  ", p)
    elif cmd == "connection":
        model, explore = sys.argv[2], sys.argv[3]
        conn, db, schema = explore_connection_target(model, explore)
        if db and schema:
            print(f"{db}.{schema}")
        else:
            sys.exit(f"could not resolve connection target (connection={conn})")
    else:
        sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main()
