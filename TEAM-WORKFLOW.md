# Team Workflow

This project now uses one integration baseline plus multiple local workspaces.

The goal is:

- keep one shared "final version" baseline
- let each module evolve in its own workspace
- reduce cross-module drift
- make release and deployment easier to reason about

## 1. Main Branch Roles

### `codex/preview`

This is the integration baseline.

Use it for:

- checking the current combined final version
- preparing releases
- syncing the latest baseline into all module workspaces
- cross-module fixes that truly belong to the whole product

### `codex/release-YYYYMMDD[a-z]`

These are deployment snapshots.

Use them for:

- production deployment
- rollbacks
- preserving a known-good online version

Do not keep developing on release branches.

### Module branches

Current module workspaces:

- `codex/footprints`
- `codex/moments`
- `codex/music`
- `codex/books`
- `codex/videos`
- `codex/mobile-polish`

Use them for module-specific work.

### `codex/refactor-low-conflict`

Use this branch only for structural work:

- splitting large files
- reducing merge hotspots
- moving shared code into smaller modules

Do not use it for normal product features.

## 2. Workspace Map

Local workspaces:

- `CODE-preview` -> `codex/preview`
- `CODE` -> `codex/footprints`
- `CODE-moments` -> `codex/moments`
- `CODE-music` -> `codex/music`
- `CODE-books` -> `codex/books`
- `CODE-videos` -> `codex/videos`
- `CODE-mobile-polish` -> `codex/mobile-polish`
- `CODE-refactor-low-conflict` -> `codex/refactor-low-conflict`
- `CODE-app-shell` -> `codex/app-shell`

Important note:

- `CODE-app-shell` is intentionally separate from the normal sync flow because it is the iOS shell line, not a web module branch.

## 3. Daily Development Flow

When starting new work:

1. Open `CODE-preview`
2. Run `sync-all-modules.bat`
3. Open the module workspace you want to change
4. Make the change only in that module workspace
5. Commit in that module branch
6. If you want to see the integrated result, update `CODE-preview`

## 4. Release Flow

When the preview version looks correct:

1. Work in `CODE-preview`
2. Create a new release branch from the current final version
3. Push it
4. Deploy that release branch to the server

The local helper script already supports this:

- `publish-preview-release.bat`

## 5. Server Deployment Flow

Server pattern:

```bash
ssh root@178.104.86.101
cd /srv/moments/app
git fetch origin
git switch codex/release-YYYYMMDD[a-z] || git checkout -b codex/release-YYYYMMDD[a-z] origin/codex/release-YYYYMMDD[a-z]
BRANCH=codex/release-YYYYMMDD[a-z] bash scripts/update-production.sh
```

## 6. Important Rules

### Rule 1

Do not use `codex/preview` as a normal long-term feature branch.

### Rule 2

Before starting a new task in any module, sync the latest preview baseline into all module workspaces.

### Rule 3

If a task affects multiple modules or shared files heavily, either:

- do it in `codex/preview`, or
- do it in a short-lived feature branch created from the current preview baseline

### Rule 4

If a conflict is solved in preview and the solution should live long-term, sync or backport that fix into the owning module branch.

## 7. Recommended Future Direction

This project still uses multiple full local workspaces because that is easier for safe development right now.

The long-term goal should be:

- one shared baseline
- clearer module ownership
- more short-lived feature branches
- fewer permanent module-specific divergences

The current workflow is a transitional step toward a more standard team-style setup.
