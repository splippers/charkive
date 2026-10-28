# Filekive Platform Specification
> Digital Archaeology and Storage Curation
>
> **Charkive** is the engine.
> **Filekive** is the product suite.
>
> Taglines:
>
> - Burn Away the Fluff
> - Keep the Masters. Char the Rest.
> - Restore SANity.
> - None More Black.
> - Because Archives Should Not Hoard.

---

# Product Vision

Charkive is not a disk cleaner.

It is a policy-driven storage curation platform designed to identify non-user-generated data, duplicate content, abandoned artefacts, and historical clutter while preserving user content and archival masters.

Primary goals:

- Recover storage safely.
- Preserve user-created content.
- Provide reversible actions.
- Support SAN, NAS, archive, and removable-media workflows.
- Enable digital archaeology of backup collections.
- Never perform irreversible deletion without quarantine and retention.

Core philosophy:

> Nothing is deleted.
>
> Everything burns twice.

Workflow:

```text
Found
 ↓
SANitorium
 ↓
Retention
 ↓
Ash
```

---

# Product Structure

```text
Filekive
├── Charkive Core
├── Filekive SAN Edition
├── Filekive Archaeology
├── Home Edition
└── Enterprise Edition
```

---

# Charkive Core

## Purpose

Burn away the fluff.

Engine responsibilities:

```text
Scan
Classify
Protect
Quarantine
Restore
Report
```

Supported storage:

- Local disks
- External USB drives
- Old laptop drives in caddies
- NAS shares
- SAN volumes
- Mounted GlusterFS volumes
- Archaeological archives

---

# Classifications

Rather than simply:

```text
Delete
Review
Protect
```

Use:

```text
Protect
Review
Kindling
Combustible
```

Examples:

```text
Master Footage
Confidence: 100%
Classification: Protect
```

```text
Premiere Media Cache
Confidence: 99%
Classification: Combustible
```

```text
Auto Save Folder
Confidence: 76%
Classification: Review
```

---

# Filekive SAN Edition

## Target

Media production environments:

- Premiere Pro
- DaVinci Resolve
- Final Cut Pro
- Avid
- Shared storage
- NAS
- SAN
- GlusterFS

### Goal

Restore SANity.

Features:

- Cache identification
- Render pruning
- Proxy cleanup
- Sidecar validation
- Snapshot management
- Duplicate detection
- SAN-safe quarantine

---

# Filekive Archaeology

## Purpose

Historical archive analysis.

The key question is not:

> What can I delete?

It is:

> What is this collection and why do I have it?

Typical targets:

- USB dump collections
- Old laptop backups
- Profile backups
- Legacy OS backups
- Family media archives
- Backup generations

Outputs:

```text
ACER290 Backup
 Size: 6.3 GB

 Unique:
   2.4 GB

 Duplicated:
   3.9 GB

 Closest Match:
   charm-1TB/Desktop
```

```text
Photo Archive

 Located In:
  BACK/
  charm-1TB/
  OLDSYSTEM/

 Recommendation:
  Keep canonical copy
  Archive duplicates
```

---

# Scan Pipeline

```text
Inventory
 ↓
Classify
 ↓
Score Confidence
 ↓
Protect / Review / Kindling / Combustible
 ↓
SANitorium
 ↓
Retention
 ↓
Ash
```

---

# Inventory Engine

Directory walk:

```bash
find /mnt/root -type f -printf '%s\t%i\t%p\t%T@\n'
```

Store metadata:

- Path
- Size
- Inode
- mtime
- atime
- Extension
- Parent directory
- Link count
- Partial hash
- Classification
- Confidence score

Backend:

- SQLite
- PostgreSQL

---

# Partial Hash Strategy

```python
sha1(first_1MB + last_1MB)
```

Purpose:

- Rapid duplicate detection
- Reduced disk activity
- Archive-scale performance

Full hash only when required.

---

# Safe Categories

## Temp Files

Extensions:

```text
.tmp
.temp
.bak
.old
.crdownload
.partial
.autosave
```

Rule:

```text
mtime > 7 days
not inside sanctuary
```

---

## Cache Directories

Premiere:

```text
Media Cache/
Media Cache Files/
Peak Files/
Adobe Premiere Pro Auto-Save/
```

Resolve:

```text
CacheClip/
ProxyMedia/
GalleryStills/
```

FCP:

```text
Render Files/
Transcoded Media/
Analysis Files/
```

Avid:

```text
Avid MediaFiles/MXF/1/Creating/
Attic/
```

Rule:

```text
Unused > 14-45 days
```

---

## Orphan Sidecars

Potential candidates:

```text
.xmp
.xml
.fcpevent
```

Only if media parent absent:

```text
.mov
.mxf
.braw
.r3d
.ari
```

---

## Duplicate Detection

Tools:

```text
rhash
fdupes
rmlint
```

Rules:

- Compare via mountpoint.
- Never compare against raw bricks.
- Never auto-dedupe archive masters.

---

## Historical Versions

Examples:

```text
_v01.mov
_v02.mov
...
_v13.mov
```

Rule:

```text
Keep newest two.
Review older revisions.
```

---

# Sanctuary System

Protected locations:

```yaml
sanctuary:
  - /Archive/**
  - /Masters/**
  - /Originals/**
  - /Camera/**
  - /Deliverables/**
  - /Final/**
```

Protected media:

```text
.mov
.mp4
.mxf
.braw
.r3d
.ari
.dpx
.exr
.wav
.aif
.flac
.psd
.psb
.tiff
.cr2
.cr3
.nef
.arw
.raf
```

Protected projects:

```text
.prproj
.aep
.drp
.fcpxml
.aaf
.edl
.avp
.cube
.3dl
```

Protected attributes:

```text
user.immutable=true
```

---

# SANitorium

Quarantine system.

Structure:

```text
/.charkive/sanitorium/YYYY-WW/
```

Preserves original path hierarchy.

Example:

```text
/.charkive/sanitorium/2026-W21/
```

Each item receives:

```json
{
  "original_path": "...",
  "classification": "...",
  "confidence": 98,
  "quarantined": "...",
  "rule": "premiere_cache"
}
```

Retention:

```text
Shyte       7 days
Kiloshyte  30 days
Megashyte  60 days
Gigashyte  90 days
```

---

# Tier System

## Shyte [1]

Metadata cruft.

Examples:

```text
.DS_Store
Thumbs.db
orphan .xmp
small .pek
```

Risk:

```text
Negligible
```

Auto-approval:

```text
Allowed
```

---

## Kiloshyte [5]

Temporary and cache data.

Examples:

```text
Media Cache
Auto Saves
Temp directories
Duplicate downloads
```

Risk:

```text
Low
```

Confirmation:

```text
Y/N
```

---

## Megashyte [10]

Large removable artefacts.

Examples:

```text
Render Files
Proxy Media
Version Stacks
Abandoned Deliverables
```

Risk:

```text
Medium
```

Confirmation:

```text
Type: MEGASHYTE
```

---

## Gigashyte [11]

Dead project retirement.

Examples:

```text
Client project untouched > 3 years
Size > 100 GB
```

Risk:

```text
High
```

Confirmation:

```text
THESE GO TO ELEVEN
```

Warning:

```text
This folder is a Stonehenge-sized monument
to forgotten renders.
```

---

# Spinal Tap Edition

Version:

```text
Charkive v1.0.0
"None More Black"
```

Banner:

```text
All tiers go to 11.
```

Mappings:

```text
SANitorium      = The Stonehenge
sanity          = Smell the Glove Check
--dry-run       = Jazz Odyssey Preview
sanitor daemon  = Nigel's Amp
retention purge = Spontaneous Combustion
log file        = The Black Album
```

Examples:

```bash
charkive --version
```

Output:

```text
All tiers go to 11.
```

---

# CLI

## Primary Commands

```bash
charkive init
charkive sanity
charkive sanitise
charkive quench
charkive status
```

## SAN Commands

```bash
charkive sanity
charkive sanitise --dry-run
charkive sanitise
charkive sanitor --daemon
charkive sanitorium ls
charkive sanitorium purge
charkive sanitorium quench
```

## Archaeology Commands

```bash
charkive archaeology
charkive archaeology --report
charkive archaeology --dig BACK
charkive archaeological_find
```

---

# Suggested Internal Modules

```text
kindling.py
fire_codes.py
ember.py
ash.py
quench.py
```

SAN flavour:

```text
sanity.py
sanitorium.py
sanitor.py
sandwich.py
ash.py
```

---

# MARVIN-SANDIEGO Sandbox

Root:

```text
/mnt/MARVIN-SANDIEGO
```

Principle:

```text
Treat sandbox as the entire universe.
Never inspect outside root.
```

Configuration:

```yaml
version: 1

root: /mnt/MARVIN-SANDIEGO

sandbox: true

quarantine:
  path: /mnt/MARVIN-SANDIEGO/.charkive/sanitorium
  retention_days: 30
```

Required safeguards:

- Realpath jail
- Symlink escape prevention
- Root confinement
- Read-only scan mode

Validation:

```python
os.path.realpath(path).startswith(ROOT)
```

---

# GlusterFS Support

Supported:

✅ Mounted FUSE volumes

Unsupported:

❌ Raw bricks

Core rule:

> Bricks are lava.

Never scan:

```text
/SANDIEGO
/bricks
/.glusterfs
```

Always scan:

```text
/mnt/MARVIN-SANDIEGO
```

Mount first:

```bash
mount -t glusterfs marvin-storage:/sandiego /mnt/MARVIN-SANDIEGO
```

Then:

```bash
charkive init /mnt/MARVIN-SANDIEGO
```

---

# Gluster Preflight

Before sanitise:

```text
All bricks online
Quorum valid
Heal entries = 0
No active split-brain
```

Checks:

```bash
gluster volume heal sandiego info
gluster volume status sandiego
```

Abort conditions:

```text
Heal pending
Brick offline
Quorum failure
```

---

# Gluster Safe Targets

Potential candidates:

```text
.glusterfs/landfill/
.trashcan/
Orphan shards
```

Only after:

```text
heal = 0
split-brain = 0
```

---

# Brick Firewall

Mandatory protection.

```text
Raw brick access forbidden.
```

Error:

```text
🧱 BRICK DETECTED

Charkive refuses to scan raw bricks.

Mount the volume first.

Error:
Aborting before your archive becomes
Spinal Tap's drummer.
```

---

# Archive Archaeology

Target:

```text
/mnt/SANDIEGO/Archive
```

Purpose:

Cross-generation backup analysis.

Example archive sets:

```text
BACK/
charm-1TB/
OLDSYSTEM/
TM290/
Music/
OLD DVDs FROM PREHISTORY/
```

Questions answered:

- Which files are unique?
- Which files are duplicated?
- Which backups overlap?
- Which system images are obsolete?
- Which folders contain irreplaceable content?

---

# Archaeology Report

Example:

```text
Charkive Archaeological Dig

┌─────────────────────────────┬────────┬──────────┐
│ Backup Set                  │ Size   │ Unique   │
├─────────────────────────────┼────────┼──────────┤
│ BACK/                       │ 87G    │ 52G      │
│ charm-1TB/                  │ 54G    │ 41G      │
│ OLDSYSTEM/                  │ 18G    │ 18G      │
│ Music/                      │ 8G     │ 1.2G     │
└─────────────────────────────┴────────┴──────────┘

Overlap:
  ~47 GB
```

---

# Design Principle

Every action must answer:

```text
What was found?
Why was it classified?
What rule matched?
How confident are we?
Can it be restored?
```

Trust is more important than reclaimed space.

Success metrics:

```text
TB Recovered
Files Protected
Restores Performed
False Positives Avoided
Files Lost: 0
```

---

# Vision Statement

Filekive is a storage curation and digital archaeology platform that helps users understand, organise, quarantine, and safely retire redundant data while preserving irreplaceable content.

It is designed for archives, creative workflows, old drive migrations, SAN storage, backup collections, and historical data preservation.

Final principle:

> Keep the masters.
>
> Char the rest.
