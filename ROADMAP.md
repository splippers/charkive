# Charkive Roadmap

**Keep the masters. Burn the fluff.**

## Vision

Charkive is a storage hygiene, preservation, investigation, and data-archaeology
system.

Today, Charkive scans local and mounted filesystems, identifies likely
disposable caches and scratch data, and can move selected candidates into a
recoverable SANitorium.

The long-term vision is broader.

Charkive should help users distinguish between:

- data that is probably disposable
- data that is clearly important
- data that may be historically meaningful
- data whose apparent history cannot be trusted
- data that requires investigation
- data that should be protected before any cleanup occurs

Charkive should not only ask:

> **What is probably fluff?**

It should also ask:

> **What might matter?**

Within FileCity and the wider Virtual Network Admin (VNA) ecosystem, Charkive
can provide storage-health, preservation, and archaeological findings that
other tools can explain, visualise, generalise, or turn into playable work.

Its governing principle remains:

> **Understand first. Preserve the evidence. Quarantine second. Delete never.**

---

# Core Principles

## Keep the masters

Charkive should identify and protect important source material before
considering cleanup.

Age, inactivity, unfamiliarity, duplication, poor organisation, or an
apparently strange timestamp do not make a file disposable.

---

## Burn the fluff

Charkive should identify material that is likely to be reproducible,
temporary, cached, generated, or otherwise disposable.

Classification must remain explainable and reviewable.

---

## Old does not mean worthless

Dormant data can be historically significant.

An old directory containing apparently forgotten files may represent a
project, event, period of work, collection, or personal history.

Charkive should become increasingly cautious when storage contains patterns
that suggest meaningful historical activity.

---

## Recorded metadata is evidence, not truth

Filesystem timestamps, embedded timestamps, filenames, and directory
locations can all be misleading.

Charkive should preserve original evidence while allowing competing
interpretations to be recorded separately.

---

## Quarantine before destruction

Charkive does not permanently delete user files.

Candidates selected for removal are moved into the recoverable SANitorium,
where they remain available for review and restoration.

---

## Reality before metaphor

A fire engine, police investigation, archaeological site, warning colour,
preservation order, or SANitorium animation is a representation.

The underlying observation, finding, evidence, and uncertainty remain
authoritative.

---

# Current Foundation

Charkive already provides:

- Local filesystem scanning and classification
- Support for fixed disks, USB disks, removable media, and mounted filesystems
- Optional GlusterFS-aware safety checks
- Protected extensions and sanctuary paths
- Partial hashing during scans
- Dry-run sanitisation
- Reversible quarantine through the SANitorium
- Restoration from quarantine
- Higher-risk candidate tiers requiring explicit typed acknowledgement
- Collision protection for quarantine and restore destinations
- SQLite-backed scan state
- CLI and web interfaces
- Read-only web operation
- Scan history
- Document-curation reporting

This existing behaviour remains the foundation of the project.

The roadmap extends it rather than replacing it.

---

# NOW: Make Existing Knowledge Portable

The immediate priority is not autonomous cleanup or 3D integration.

It is making Charkive's existing knowledge structured, traceable, historical,
and useful to other applications.

## 0.1: Structured Findings

Introduce a structured representation of findings produced by a scan.

A finding should be able to describe:

- where something was observed
- what was observed
- why it is noteworthy
- which rule, detector, or process produced the finding
- its classification
- its severity
- the evidence supporting it
- the degree of confidence
- the action Charkive can offer
- whether any real filesystem change occurred

An illustrative finding might resemble:

```json
{
  "schema": "charkive.finding/0.1",
  "id": "finding-example",
  "scan_id": "scan-example",
  "category": "storage.disposable_candidate",
  "severity": "notice",
  "confidence": 0.92,
  "path": "example/path",
  "classification": "candidate",
  "evidence": [],
  "recommended_action": "review_for_quarantine",
  "production_changed": false
}
