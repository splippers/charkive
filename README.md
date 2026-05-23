Charkive: Burn Away the Fluff - Complete Roll-Up for MARVIN-SANDIEGO
Restore SANity. All tiers go to 11.

1. ORIGIN: GlusterFS SAN Curation
Goal: Identify/prune garbage on GlusterFS synced SAN without threatening user media.

Safe-to-Prune GlusterFS Targets:
1. Heal leftovers & trash:.glusterfs/landfill,.trashcan/ if trash translator enabled, /.shard/ orphans. Pre-check: gluster volume heal <volname> info and info split-brain. Only prune when heals = 0.
2. Duplicates/unreferenced: Use rhash, fdupes, rmlint from FUSE mount. Flag if hash+size match and one copy in /tmp, /cache vs user media dir.
3. Temp/cache/render: *.tmp, *.bak, Media Cache*, Adobe Premiere Pro Auto-Save/, CacheClip/,.DS_Store, Thumbs.db. Age: mtime > 30 days.
4. Orphaned sidecars/proxies:.xmp,.xml,.fcpevent with no parent.mov,.mxf,.braw. Proxies where source deleted.
5. Snapshots: gluster snapshot list + lvs. Keep N recent + tagged keep. Prune rest.

Never Auto-Delete:
Extensions:.mov,.mxf,.braw,.r3d,.ari,.dpx,.exr,.wav,.aif,.psd,.tiff,.cr2,.nef,.arw
Projects:.prproj,.drp,.fcpxml,.aep
Paths: /Archive, /Masters, /Originals, /Deliverables
Xattr: user.immutable=true

Core Logic:
1. Inventory: find /mnt/gluster/vol -type f -printf '%s\t%i\t%p\t%T@\n' > inventory.tsv -> SQLite/Postgres
2. Classify: Rules tag: Gluster Trash, Temp, Cache, Orphan Sidecar, Duplicate, User Media
3. Quarantine: Move to /mnt/gluster/vol/.quarantine/YYYY-MM-DD/path. Cron purges 14-30d
4. Gluster checks: All bricks online, heal info = 0, quorum ok before prune

GlusterFS Gotchas:
1. Never delete on bricks. Always FUSE mount /mnt/gluster/volname. Brick delete = split-brain.
2. GFID hardlinks in.glusterfs/ - do not touch unless landfill or quarantine.
3. After deleting millions of files: gluster volume rebalance <vol> start.
4. df lies. Use du --inode and group by extension.

Quick Wins:
1. Trashcan auto-expire: gluster volume set <vol> features.trash on + cron purge.trashcan/* >30d.
2. Cache sweeper: Register project roots. */Cache/* not accessed 45d -> quarantine.

2. PIVOT: Treat as Plain SAN Filesystem
Ignore Gluster internals. Files not mounted exposing Gluster compliments.

Safe-to-Prune Media SAN Categories:
1. Render & cache dirs:
   Premiere: Media Cache/, Media Cache Files/, Peak Files/, Adobe Premiere Pro Auto-Save/
   Resolve: CacheClip/, ProxyMedia/, GalleryStills/
   FCP: Render Files/, Transcoded Media/, Analysis Files/
   Avid: Avid MediaFiles/MXF/1/Creating/, Attic/
   OS:.DS_Store, Thumbs.db,._*,.Spotlight-V100
   Safe if: atime > 14d or project not touched 30d
2. Temp/intermediate: *.tmp, *.temp, *.bak, *.old, *.crdownload, *.partial, ~$*, *.autosave, Untitled*
   Rule: mtime > 7d AND not in /Masters, /Originals, /Deliverables
3. Orphaned sidecars:.xmp,.xml,.fcpevent,.cube,.look with no parent clip
4. Duplicates outside masters: sha1 match where A in /Projects/Footage/, B in /Temp, /Downloads, /Cache. Never auto-dedupe two files both under /Archive
5. Old exports/versions: *_v01.mov...*_v13.mov where v13 exists. /Exports/, /Renders/ with mtime > 90d. Keep newest 2.

Never Auto-Delete List:
Core:.mov,.mp4,.mxf,.braw,.r3d,.ari,.dpx,.exr,.cin,.wav,.aif,.flac,.psd,.psb,.tiff,.cr2,.cr3,.nef,.arw,.raf
Projects:.prproj,.aep,.drp,.fcpxml,.xml,.aaf,.edl,.avp,.cube,.3dl
Paths: /Archive, /Masters, /Originals, /Delivery, /Final, /Camera, /RAID, /Ingest
Flag: xattr user.immutable=true

App Logic v2:
1. Scan: Walk tree, store path, size, mtime, atime, hash_partial, extension, parent_dir, is_sidecar. hash_partial = sha1 first+last 1MB.
2. Rule Engine YAML:
- name: Premiere Cache
  match_path: "*/Media Cache/*"
  match_age_days: 30
  action: quarantine
  risk: low
- name: Orphan XMP
  match_ext:.xmp
  require_no_sibling: [.mov,.mxf,.braw,.r3d]
  action: quarantine
- name: Master Media
  match_ext: [.mov,.mxf,.braw]
  match_path: ["/Masters/*", "/Archive/*"]
  action: protect
3. Quarantine: Move to /.quarantine/YYYY-WW/ preserving path + manifest.json. 30d retention.
4. Report: Output TB by category. Protected TB. Require admin approve.

Python Scanner:
import os, hashlib, time
from pathlib import Path
PROTECT_DIRS = {'/Archive', '/Masters', '/Originals', '/Deliverables'}
TEMP_EXT = {'.tmp', '.temp', '.bak', '.pek', '.cfa'}
MEDIA_EXT = {'.mov', '.mxf', '.braw', '.r3d', '.wav', '.dpx', '.exr'}
def partial_hash(path):
    h = hashlib.sha1()
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        h.update(f.read(1_048_576))
        if size > 2_097_152:
            f.seek(-1_048_576, 2)
            h.update(f.read(1_048_576))
    return h.hexdigest()
def classify(path: Path):
    str_path = str(path)
    if any(str_path.startswith(p) for p in PROTECT_DIRS):
        return 'protect'
    if path.suffix.lower() in TEMP_EXT:
        return 'quarantine_temp'
    if 'Cache' in path.parts and path.stat().st_atime < time.time() - 30*86400:
        return 'quarantine_cache'
    if path.suffix.lower() == '.xmp' and not any(path.with_suffix(ext).exists() for ext in MEDIA_EXT):
        return 'quarantine_orphan'
    return 'review'

SAN Gotchas:
1. Atime lies: Many SANs mount noatime. Use mtime of parent project folder.
2. Hardlinks: Check stat.st_nlink > 1. Skip unless all links in temp dirs.

3. REBRAND: Splippers-Archive to Charkive/Charchive
Tagline: Burn away the fluff

Charkive = CLI/core engine. Charchive = product suite.
Taglines: "Keep the master, char the rest", "Because archives should not hoard"

CLI Verbs:
charkive scan /mnt/san
charkive ember list
charkive ignite
charkive ash
charkive quench <path>
charkive status

.charkive.yml:
sanctuary:
    - /Archive/**
    - /Masters/**
    - /Originals/**
  extensions: [.mov,.braw,.r3d,.mxf,.dpx,.wav]
kindling:
    - path: "*/Media Cache/**"
    age_days: 30
    - path: "*/Render Files/**"
    age_days: 14
    - ext: [.tmp,.bak,.pek,.cfa]
    age_days: 7
quarantine:
  path: /.charkive/quarantine
  retention_days: 30

Module Names: scanner.py->kindling.py, rules.py->fire_codes.py, mover.py->ember.py, deleter.py->ash.py, restore.py->quench.py

4. PRIVATE CASE: Sandboxed /mnt/MARVIN-SANDIEGO
Treat as entire universe. Never peek outside.

.charkive.yml:
version: 1
root: /mnt/MARVIN-SANDIEGO
sandbox: true
quarantine:
  path: /mnt/MARVIN-SANDIEGO/.charkive/quarantine
  retention_days: 30
sanctuary:
    - /Archive/**
    - /Masters/**
    - /Originals/**
    - /Camera/**
    - /Deliverables/**
kindling:
    - path: "*/Media Cache*/**"
    age_days: 30
    - path: "*/Render Files/**"
    age_days: 14
    - ext: [.tmp,.bak,.pek,.cfa,.ims,.old]
    age_days: 7

CLI:
charkive init /mnt/MARVIN-SANDIEGO
charkive scan
charkive ember list --top 50
charkive ignite --dry-run
charkive ignite

Safety Checks:
1. Realpath jail: os.path.realpath(f).startswith(ROOT) on every file
2. No symlinks out: Resolve + check, or skip
3. Quarantine inside root: Abort if not under root
4. Read-only scan: DB ro, no writes until ignite

Report:
Charkive scan complete for /mnt/MARVIN-SANDIEGO
Fluff found: 3.1TB in 418,293 files
  Cache: 2.2TB ████████████████░░░░ 71%
  Temps: 540GB ████░░░░░░░░░░░░░░░░ 17%
  Orphans: 260GB ██░░░░░░░░░░░░░░░░░░ 8%
  Dupes: 100GB █░░░░░░░░░░░░░░░░░░░ 3%
Protected: 62.4TB - sanctuary rules honored
Quarantine: /mnt/MARVIN-SANDIEGO/.charkive/quarantine

5. SAN PUN NOMENCLATURE
SANitorium - Quarantine: /mnt/MARVIN-SANDIEGO/.charkive/sanitorium/
SANity - Health check: charkive sanity
SANitise - Quarantine fluff: alias for ignite
SANitary - Clean dir status: SANitary ✓
SANitor - Daemon: charkive sanitor --watch /mnt/MARVIN-SANDIEGO
SANdwich - Before/after report: charkive sandwich --last-run

Updated CLI:
charkive scan
charkive sanity
charkive sanitise --dry-run
charkive sanitise
charkive sanitorium ls
charkive sanitorium purge
charkive sanitorium quench <id>
charkive sanitor --daemon
charkive status

.charkive.yml with SAN terms:
sanitorium:
  path:.charkive/sanitorium
  retention_days: 30
sanctuary:
    - /Archive/**
sanity_rules:
    - name: render_cache
    path: "*/Render Files/**"
    age_days: 14
    sanity: low-risk
sanitor:
  schedule: "0 2 * * 0"
  auto_sanitise: false
  sandwich_reports: true

SANdwich Report:
Charkive SANity Report for /mnt/MARVIN-SANDIEGO
SANitary Status: 62.4TB protected, 3.1TB ready for SANitise
SANdwich Preview:
  Cache 2.2TB -> SANitorium
  Temps 540GB -> SANitorium
Files remain recoverable for 30 days. SANity guaranteed.

Module Renames: scanner.py->sanity.py, quarantine.py->sanitorium.py, deleter.py->ash.py, daemon.py->sanitor.py, report.py->sandwich.py

6. SHYTE TIERS
Shyte - Light metadata trim..DS_Store, Thumbs.db, orphan.xmp,.pek <1MB. Risk: Negligible. --tier shyte
Kiloshyte - Medium trim. Render cache, Media Cache Files/, auto-saves, dupes in /Temp, 1MB–1GB. Risk: Low. --tier kiloshyte
Megashyte - Heavy trim. Full Render Files/ folders, old proxies, v01-v12 stacks, abandoned projects >1GB. Risk: Medium. --tier megashyte

Config:
sanity_rules:
    - name: shyte_ds_store
    tier: shyte
    match: [.DS_Store, Thumbs.db]
    - name: kiloshyte_adobe_cache
    tier: kiloshyte
    path: "*/Media Cache*/**"
    age_days: 30
    - name: megashyte_render_folders
    tier: megashyte
    path: "*/Render Files/**"
    min_size: 1GB
    age_days: 14
    require_confirm: true

CLI: charkive sanity --tier kiloshyte, charkive sanitise --tier megashyte

Report:
Shyte: 4.2GB 180,421 files Metadata cruft
Kiloshyte: 2.1TB 201,884 files Cache + temps
Megashyte: 960GB 1,988 files Renders + versions
Total burnable: 3.06TB -> SANitorium

Guardrails:
Shyte: Auto-run ok, 7d retention. Kiloshyte: Y/n, 30d. Megashyte: Type MEGASHYTE, 60d.

7. SPINAL TAP EDITION: This One Goes to Eleven
Gigashyte - Nuke whole dead project. /Projects/Client_2019/ untouched 3 years, 4TB. Confirm: THESE GO TO ELEVEN [11]

Tier Table: Shyte [1], Kiloshyte [5], Megashyte [10], Gigashyte [11]

Config:
spinal_tap_mode: true
sanity_rules:
    - name: gigashyte_dead_projects
    tier: gigashyte
    path: "/Projects/**"
    atime_days: 1095
    min_size: 100GB
    confirm_phrase: "THESE GO TO ELEVEN"
    warning: "This folder is a Stonehenge-sized monument to forgotten renders"

CLI: charkive sanitise --tier gigashyte -> Prompts for THESE GO TO ELEVEN

Spinal Tap Nouns:
SANitorium = The Stonehenge, charkive sanity = Smell the Glove Check, --dry-run = Jazz Odyssey Preview, charkive sanitor --daemon = Nigel's Amp, Retention expiry = Spontaneous Combustion, Log = The Black Album

Status Output:
Charkive v1.0.0 "Smell the Glove"
Amp Levels:
  Shyte [ 1] █ 4.2GB 💩
  Kiloshyte [ 5] █████ 2.1TB 🗑️
  Megashyte [10] ██████████ 960GB 🔥
  Gigashyte [11] ███████████ 4.3TB 🔥🔥🔥 Dead projects
SANitary Status: 62.4TB protected, 7.36TB burnable

Easter Eggs:
charkive --version -> "All tiers go to 11."
charkive sanitise --tier 11 -> "Did you mean --tier gigashyte? Our amps don't have numbers."

8. GLUSTERFS BACKEND COMPATIBILITY
Yes, via FUSE mount only. Never point at bricks.

Correct: mount -t glusterfs marvin-storage:/sandiego /mnt/MARVIN-SANDIEGO -> charkive init /mnt/MARVIN-SANDIEGO
Wrong: Pointing Charkive at /SANDIEGO raw brick = split-brain.

Gluster Benefits: Replication handles SANitorium moves. Quotas update on FUSE ops. Snapshots: gluster snapshot create snap-pre-gigashyte sandiego

Gluster Gotchas:
1. Heal pending: sanity runs gluster volume heal sandiego info. Abort if >0 entries.
2. Shards: Ignore **/.shard/** unless sharding off.
3. Landfill: **/.glusterfs/landfill/** is safe shyte tier.
4. Split-brain: Check getfattr -n trusted.afr.dirty. Skip affected dirs.
5. Rebalance: Post-SANitise hook: gluster volume rebalance sandiego start if >10k files moved.
6. Quorum: Abort if bricks down.

.charkive.yml Gluster:
gluster:
  volume: sandiego
  pre_sanity_checks:
        - heal_pending: abort_if_true
        - quorum: abort_if_lost
        - split_brain: skip_affected_dirs
  post_sanitise_hooks:
        - rebalance: if_files_moved > 10000

Gluster Preflight sanity.py:
def gluster_preflight(volume: str) -> bool:
    heal = subprocess.run(["gluster", "volume", "heal", volume, "info"], capture_output=True, text=True)
    if "Number of entries: 0" not in heal.stdout:
        raise RuntimeError("Gluster heal pending. SANity aborted.")
    status = subprocess.run(["gluster", "volume", "status", volume], capture_output=True, text=True)
    if "Y" not in status.stdout:
        raise RuntimeError("Gluster quorum not met. Cannot SANitise safely.")
    return True

Workflow:
mount -t glusterfs marvin-storage:/sandiego /mnt/MARVIN-SANDIEGO
gluster snapshot create pre-gigashyte sandiego
charkive sanity --tier gigashyte
charkive sanitise --tier kiloshyte
charkive sanitise --tier gigashyte # type THESE GO TO ELEVEN
gluster volume rebalance sandiego start

9. CRITICAL: Raw Brick at /SANDIEGO
Rule: Bricks are lava. Charkive must NEVER scan /SANDIEGO directly.

Brick Firewall sanity.py:
FORBIDDEN_PATHS = {"/SANDIEGO", "/bricks", "/.glusterfs"}
def is_brick(path: Path) -> bool:
    resolved = path.resolve()
    if str(resolved) in FORBIDDEN_PATHS: return True
    if (resolved / ".glusterfs").exists(): return True
    try:
        attrs = os.listxattr(resolved)
        if any(a.startswith(b"trusted.glusterfs") for a in attrs): return True
    except: pass
    return False
def charkive_init(root: str):
    if is_brick(Path(root).resolve()):
        raise RuntimeError(f"🧱 BRICK DETECTED: {root}\nCharkive refuses to scan raw bricks. Mount the volume first.")

Correct vs Wrong:
/SANDIEGO = Raw brick -> NO - Brick jail triggers
/mnt/MARVIN-SANDIEGO = FUSE mount -> YES - This is the way

Config:
root: /mnt/MARVIN-SANDIEGO # FUSE mount ONLY
brick_protection:
  enabled: true
  forbidden_paths: [/SANDIEGO, /bricks/**]
  abort_message: "These amps don't work on raw bricks. Mount the volume first."

Error on Brick:
charkive init /SANDIEGO
🧱 BRICK DETECTED: /SANDIEGO
Charkive refuses to scan raw bricks. This would cause split-brain.
Error: Aborting before your archive becomes Spinal Tap's drummer.

10. SANDIEGO ARCHAEOLOGY: Backup Dig & Cross-Backup Dedup
Target: /mnt/SANDIEGO/Archive/ — old system images, USB stick dumps, family media spread across backup generations.

The Archive is 178G and consists of multiple generations of backup dumps that contain overlapping content. Unlike media render caches (which are ephemeral), Archive cruft is historical — old laptop backups, USB stick contents, full Windows user profiles. The goal is to surface duplicates across backup lineages so Jon can decide what to keep and what to char.

Real-world Archive profile (2026-05-23):
- BACK/ (87G): Old USB stick dumps — Videos (27G), DAD'S BACKUP (27G), Rachael Davis (8.9G), ACER290 laptop (6.3G), My Documents (4.4G), RAEJON+MP3s (4.3G), OLDXP (2.3G), more
- charm-1TB/ (54G): Full Windows user profile for a machine called "charm" — Desktop (26G), Music (14G), Apple/ (10G), AppData (2.4G), Pictures (2.2G)
- OLDSYSTEM/ (18G): Old home directory backup
- Music/ (8G): MP3 collection (also present in other backup dirs)
- OLD DVDs FROM PREHISTORY/ (8.7G): DVD rips circa 2003
- TM290/ (2.4G): ThinkPad system backup
- jmd/ (89M), SERV101/ (64M): Old profiles

Safe-to-Archive categories:
1. Full system images / user profiles: Entire Desktop folders, AppData, full Music trees duplicated across BACK/, charm-1TB/, OLDSYSTEM/ — identify by partial hash, flag for review
2. USB stick snowflakes: Each BACK/ subdir is a unique USB stick dump — unique files (e.g. a single photo only on one stick) belong in a consolidated archive; duplicates across sticks should be deduped
3. Ancient ISOs: Custom_HBCD15_1.iso, UBCD310.iso, HB CD 13.iso — probably obsolete (2005-era tools), flag age + check if still relevant
4. Old OS roots: SERV101/ (bin/dev/etc/lib), TM290/ (home), OLDSYSTEM/ (home) — full Linux filesystem backups from defunct hardware

Config:
sanity_rules:
    - name: archive_dup_cross_backup
    tier: kiloshyte
    match: "/Archive/**"
    dedup_scope: cross_backup     # compare files across BACK/, charm-1TB/, OLDSYSTEM/, TM290/
    hash_partial: true
    action: flag_for_review
    risk: medium
    - name: archive_ancient_iso
    tier: kiloshyte
    match: "*.iso"
    match_path: "/Archive/**"
    age_days: 3650
    action: flag
    - name: archive_os_root
    tier: megashyte
    match_path: "/Archive/**/home/**"
    age_days: 3650
    action: flag_for_review
    - name: archive_system_profile
    tier: megashyte
    match_path: ["**/Desktop/**", "**/AppData/**", "**/NTUSER.DAT*"]
    match_path_archive: "/Archive/**"
    action: flag_system_profile

CLI:
charkive archaeology               # scan Archive for cross-backup dupes
charkive archaeology --dig BACK    # deep-dig a single backup dir
charkive archaeology --report      # generate a digestible report of what overlaps where
charkive archaeological_find <sha1> # find all copies of a given file across Archive

Architecture:
The Archive contains same-inode hardlinks — top-level dirs (BACK/, charm-1TB/, Music/, etc.) are the SAME inodes as those inside Archive/. Charkive must detect and report this, not double-count.

Report format:
Charkive Archaeological Dig: /mnt/SANDIEGO/Archive
┌──────────────────────────────┬────────────┬─────────────────┐
│ Backup Set                    │ Size       │ Unique Content  │
├──────────────────────────────┼────────────┼─────────────────┤
│ BACK/                         │ 87G        │ 52G (estimate)  │
│ charm-1TB/                    │ 54G        │ 41G             │
│ OLDSYSTEM/                    │ 18G        │ 18G             │
│ Music/                        │ 8G         │ 1.2G            │
│ ...                           │            │                 │
├──────────────────────────────┼────────────┼─────────────────┤
│ Overlap:                      │            │ ~47G            │
└──────────────────────────────┴────────────┴─────────────────┘

TL;DR
- Charkive burns fluff, keeps masters. SANitorium quarantines. SANity checks safety.
- Shyte tiers: Shyte/Kiloshyte/Megashyte/Gigashyte. Confirm phrases for 10 and 11.
- MARVIN-SANDIEGO: Sandboxed at /mnt/MARVIN-SANDIEGO. Never scan /SANDIEGO brick.
- Gluster: Works via FUSE. Add heal/quorum/split-brain preflight. Brick jail mandatory.
- Archive Archaeology: Cross-backup dedup for /mnt/SANDIEGO/Archive/ — identify duplicates across old backup generations, flag system profiles, surface what's unique vs duplicated.
- Tagline: None more black. All tiers go to 11. Restore SANity. [1][5][10][11]
