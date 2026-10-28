# Charkive

**Keep the masters. Burn the fluff.**

Charkive finds likely disposable caches and scratch files, reports what it finds, and can move selected candidates into a recoverable SANitorium. It works on ordinary local filesystems—including fixed disks, USB disks, and removable media—as well as GlusterFS exports mounted through FUSE. Gluster is optional.

Charkive never permanently deletes files. Review a scan, preview the proposed move, then quarantine; files can be restored from the SANitorium.

## Install

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,web]"
```

The `web` extra installs the dashboard dependencies; omit it if you only need the CLI.

## Use on a disk

Mount the disk first. This applies to removable media too: verify the mount is present before running Charkive, so an unplugged disk cannot be mistaken for an ordinary directory.

```bash
findmnt /media/$USER/MY-DISK
charkive init /media/$USER/MY-DISK
charkive scan
charkive sanity
charkive sanitise --dry-run
```

Run these commands from the disk root, where `init` creates `.charkive.yml`. If the config is elsewhere, pass it with `--config /path/to/.charkive.yml`. `init` requires an existing directory and will not create a missing mountpoint. The generated config keeps scan and quarantine paths within the selected root.

After reviewing the preview, run `charkive sanitise` to move candidates into the SANitorium. `megashyte` and `gigashyte` moves require typing an acknowledgement. Restore a file with:

```bash
charkive sanitorium ls
charkive sanitorium quench 2026-W43/path/to/file
```

The week in the restore path is shown by `sanitorium ls`. `charkive sanitorium purge` is not implemented; Charkive does not automatically expire or delete quarantined files.

## Web console

Start the dashboard from the directory containing `.charkive.yml`:

```bash
charkive web
```

The dashboard opens on `http://127.0.0.1:8080`. It shows scan history, protected and candidate data, the SANitorium, and a read-only document-curation report. The dashboard can start a scan, preview candidate moves, quarantine them, and restore files. Higher-risk tiers require the same typed confirmation as the CLI.

The server only binds beyond localhost when `CHARKIVE_WEB_TOKEN` is set. Remote access uses HTTP Basic authentication: username `charkive`, password the token. Use a trusted network and HTTPS termination for remote access; do not commit the token. Set `CHARKIVE_READONLY=1` to disable real quarantine and restore operations.

## GlusterFS

For Gluster, use the mounted FUSE export—not a brick directory. Set `gluster.volume` in `.charkive.yml` to enable heal and volume-status preflight checks before reporting or moving candidates. If those checks fail or return unrecognized output, Charkive stops rather than proceeding. For local disks and other filesystems, leave `gluster.volume` empty.

Brick protection checks configured forbidden paths and searches the selected root and its parent directories for Gluster brick markers. It does not reserve machine-specific mount paths such as `/SANDIEGO`.

## Commands

| Command | Purpose |
|---|---|
| `charkive init ROOT` | Create a sandboxed config for an existing directory or mounted filesystem |
| `charkive scan` | Inventory files and classify them against configured rules |
| `charkive scan --hash` | Also calculate partial hashes for files |
| `charkive sanity` | Report the latest scan and run configured Gluster preflight checks |
| `charkive sanitise --dry-run` | Preview candidate files to quarantine |
| `charkive sanitise` | Move candidates into the SANitorium |
| `charkive status` | Show the latest scan summary |
| `charkive sanitorium ls` | List quarantined files |
| `charkive sanitorium quench PATH` | Restore a quarantined file |
| `charkive web` | Start the local web console |

Rules, protected extensions, sanctuary paths, and optional Gluster settings live in `.charkive.yml`. The repository config is a local development example, not a disk target.

The current release does not implement archive archaeology, duplicate cleanup for arbitrary media, automatic retention purges, or permanent deletion. Those remain product ideas; the implemented action is reversible quarantine.

## Development

```bash
python -m pytest
```

The scanner skips symlinks, keeps its SQLite state under `.charkive/`, and does not include its own state directory in scans. Candidate files are moved—not deleted—and existing restore or quarantine destinations are never overwritten.

## License

MIT. Use freely, fork wildly, save disks.
