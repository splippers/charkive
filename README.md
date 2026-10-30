# Charkive

**Keep the masters. Burn the fluff.**

Charkive is a storage-health and preservation tool for identifying data that
may no longer deserve the space it occupies.

Today, Charkive finds likely disposable caches and scratch files, reports what
it finds, and can move selected candidates into a recoverable SANitorium. It
works on ordinary local filesystems, including fixed disks, USB disks, and
removable media, as well as GlusterFS exports mounted through FUSE. Gluster is
optional.

Charkive never permanently deletes files. Review a scan, preview the proposed
move, then quarantine. Files can be restored from the SANitorium.

The longer-term vision is broader: Charkive becomes a storage-health,
preservation, and response service capable of reporting problems to other
systems such as FileCity and Virtual Network Admin (VNA).

**Understand first. Quarantine second. Delete never.**

## Philosophy

Charkive starts from a simple principle:

> Valuable data and disposable data often live side by side, and software
> should not assume it knows which is which.

For that reason, Charkive favours:

- inspection before action
- dry runs before real moves
- quarantine instead of deletion
- explicit confirmation for higher-risk operations
- recoverability
- refusal to overwrite existing destinations
- stopping when important safety checks cannot be completed

Charkive is deliberately conservative.

The software can identify candidates and help the user act on them, but the
original data remains more important than a successful cleanup operation.

## Current capabilities

Charkive currently provides:

- Filesystem inventory and classification
- Configurable candidate rules
- Protected extensions and sanctuary paths
- Optional partial hashing
- Scan history
- Dry-run sanitisation
- Reversible quarantine in the SANitorium
- Restore operations
- Typed acknowledgement for higher-risk candidate tiers
- A local web console
- Optional GlusterFS health preflight checks
- Protection against scanning Charkive's own state
- Protection against overwriting existing quarantine or restore destinations

The currently implemented action is **reversible quarantine**.

Charkive does not permanently delete files.

## Install

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,web]"
```

The `web` extra installs the dashboard dependencies; omit it if you only need
the CLI.

## Use on a disk

Mount the disk first.

This applies to removable media too: verify that the mount is present before
running Charkive so an unplugged disk cannot be mistaken for an ordinary
directory.

```bash
findmnt /media/$USER/MY-DISK
charkive init /media/$USER/MY-DISK
charkive scan
charkive sanity
charkive sanitise --dry-run
```

Run these commands from the disk root, where `init` creates `.charkive.yml`.

If the config is elsewhere, pass it explicitly:

```bash
charkive --config /path/to/.charkive.yml
```

`init` requires an existing directory and will not create a missing
mountpoint. The generated configuration keeps scan and quarantine paths within
the selected root.

After reviewing the preview, run:

```bash
charkive sanitise
```

to move candidates into the SANitorium.

`megashyte` and `gigashyte` moves require typing an acknowledgement.

Restore a file with:

```bash
charkive sanitorium ls
charkive sanitorium quench 2026-W43/path/to/file
```

The week used in the restore path is shown by `sanitorium ls`.

`charkive sanitorium purge` is not implemented. Charkive does not
automatically expire or delete quarantined files.

## The SANitorium

The SANitorium is Charkive's reversible quarantine.

Candidates sent there have not been deleted. They have been moved aside so the
user can regain control of active storage while retaining the ability to
restore something that should have been kept.

This distinction is fundamental to Charkive.

The SANitorium is not a recycle bin with an automatic expiry timer. Charkive
does not currently purge it, and permanent deletion is not part of the
implemented cleanup workflow.

## Web console

Start the dashboard from the directory containing `.charkive.yml`:

```bash
charkive web
```

The dashboard opens on:

```text
http://127.0.0.1:8080
```

It shows scan history, protected and candidate data, the SANitorium, and a
read-only document-curation report.

The dashboard can:

- start a scan
- preview candidate moves
- quarantine candidates
- restore files

Higher-risk tiers require the same typed confirmation as the CLI.

The server only binds beyond localhost when `CHARKIVE_WEB_TOKEN` is set.

Remote access uses HTTP Basic authentication:

```text
username: charkive
password: <CHARKIVE_WEB_TOKEN>
```

Use a trusted network and HTTPS termination for remote access. Do not commit
the token.

Set:

```bash
CHARKIVE_READONLY=1
```

to disable real quarantine and restore operations.

## GlusterFS

For GlusterFS, use the mounted FUSE export, not a brick directory.

Set `gluster.volume` in `.charkive.yml` to enable heal and volume-status
preflight checks before reporting or moving candidates.

If those checks fail or return unrecognized output, Charkive stops rather than
proceeding.

For local disks and other filesystems, leave `gluster.volume` empty.

Brick protection checks configured forbidden paths and searches the selected
root and its parent directories for Gluster brick markers.

It does not reserve machine-specific mount paths such as `/SANDIEGO`.

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

Rules, protected extensions, sanctuary paths, and optional Gluster settings
live in `.charkive.yml`.

The repository config is a local development example, not a disk target.

## Charkive and FileCity

Charkive and FileCity have related but distinct responsibilities.

**FileCity** is concerned with understanding storage as a landscape: locations,
capacity, structure, relationships, movement, and eventually the spatial
visualisation of an entire data estate.

**Charkive** is concerned with the health of that landscape: preservation,
waste identification, safety, quarantine, and recovery.

The distinction is deliberately not "cloud versus local".

Both projects should ultimately be able to reason about storage regardless of
where that storage physically resides.

Neither project needs the other in order to remain useful. Integration should
add capability rather than create unnecessary dependency.

## Future direction: City Services

Within the wider FileCity and VNA vision, Charkive can become a source of
structured storage-health findings.

Those findings may eventually appear within a storage landscape as incidents
requiring attention.

The emerging metaphor is **City Services**:

- **Police** – investigate suspicious or inconsistent storage conditions
- **Fire** – highlight urgent storage-health incidents
- **Sanitation** – identify and manage likely disposable material
- **SANitorium** – provide recoverable quarantine and restoration

These are representations of underlying technical findings, not replacements
for them.

A burning building should always lead back to a real, inspectable reason.

## Future direction: structured findings

A useful next step for Charkive is to make its existing knowledge available in
a machine-readable form.

For example, future structured output could describe concepts such as:

```text
Observation
Candidate
Protected item
Finding
Severity
Recommendation
Quarantine state
Restore state
```

This would allow other software to consume Charkive's analysis without
reimplementing its filesystem knowledge.

Potential consumers include:

- FileCity
- Virtual Network Admin (VNA)
- Telemetry4Toddlers
- reporting systems
- future simulation and game clients

The structured representation must remain grounded in the underlying
filesystem evidence.

## Future direction: VNA

Charkive may eventually participate in the wider Virtual Network Admin
ecosystem as a specialist storage-health service.

Conceptually:

```text
REAL STORAGE
     |
     v
  CHARKIVE
     |
     | observations / findings
     v
    VNA
     |
     +----> FileCity
     |
     +----> Telemetry / explanation
     |
     +----> Reports
     |
     +----> Simulation / gameplay
```

Charkive should remain independently usable even if those integrations never
exist.

## Reality first, metaphor second

Future visualisations, simulations, or games must not become Charkive's source
of truth.

The intended flow is:

```text
REAL FILESYSTEM
      |
      v
   CHARKIVE
      |
      v
STRUCTURED FINDING
      |
      v
VISUALISATION / GAME / REPORT
```

If gameplay or another client represents a cache problem as a fire, rubbish
pile, police incident, or other metaphor, the user must still be able to reach
the actual technical evidence behind it.

Likewise, game actions should not silently become destructive filesystem
operations.

A future game session might investigate a real Charkive finding and produce a
real recommendation or report while leaving the underlying storage untouched.

## Product ideas

Potential longer-term directions include:

- Structured storage-health APIs
- Common VNA finding formats
- FileCity health overlays
- Cross-device and cross-location analysis
- Storage growth and capacity warnings
- Duplicate analysis
- Archive archaeology
- Historical health reports
- Generalised or pseudonymised findings for training environments
- SysMedic snapshot ingestion
- Procedurally generated maintenance scenarios
- Read-only BoreDOOM/VNA missions based on real Charkive findings
- Vendor-neutral storage-health reporting

These are product directions, not claims about the current release.

## Not currently implemented

The current release does not implement:

- archive archaeology
- duplicate cleanup for arbitrary media
- automatic retention purges
- permanent deletion
- FileCity integration
- VNA integration
- game-generated remediation
- general infrastructure monitoring

The implemented action remains reversible quarantine.

## Development

Run the test suite with:

```bash
python -m pytest
```

The scanner:

- skips symlinks
- keeps its SQLite state under `.charkive/`
- excludes its own state directory from scans
- moves candidates rather than deleting them
- never overwrites existing restore or quarantine destinations

## Status

Charkive is under active development.

The current application is a conservative filesystem inspection and reversible
quarantine tool.

Its longer-term direction is to become a storage-health, preservation, and
response service which can operate independently or contribute trustworthy
findings to the wider FileCity and VNA ecosystem.

## License

MIT. Use freely, fork wildly, save disks.
