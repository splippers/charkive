# Charkive Roadmap

> **Keep the masters. Burn the fluff.**

## Vision

Charkive is a preservation-first data hygiene and storage-response system.

Today, Charkive finds likely disposable caches and scratch files, reports what it finds, and can move reviewed candidates into a recoverable SANitorium.

That remains valuable as a standalone capability.

The longer-term vision is broader:

> **Charkive becomes the Police, Fire Department, Sanitation Department, and preservation authority of FileCity.**

Charkive should be capable of examining storage wherever that storage lives, producing trustworthy structured findings, recommending safe responses, executing explicitly authorised actions, and verifying the outcome.

FileCity can visualise those findings.

Virtual Network Admin can provide infrastructure context.

BoreDOOM! or other interactive clients can turn appropriate findings into gameplay.

Charkive remains responsible for the underlying analysis and safe storage operations.

```text
REAL DATA
   ↓
CHARKIVE
   ↓
FINDINGS
   ↓
RECOMMENDED ACTIONS
   ↓
CONTROLLED RESPONSE
   ↓
VERIFICATION
   ↓
AUDIT / REPORT
```

---

# Current Foundation

Charkive already provides a deliberately conservative filesystem workflow.

Its implemented behaviour includes:

- Scanning ordinary local filesystems
- Scanning fixed disks
- Scanning USB and removable media
- Working with mounted GlusterFS exports
- Classifying files using configurable rules
- Protected extensions and sanctuary paths
- Optional partial hashing
- Scan history
- Dry-run sanitisation
- Reversible quarantine
- SANitorium inspection
- Restoration from the SANitorium
- CLI operation
- Web dashboard operation
- Gluster preflight checks
- Brick protection checks
- Typed acknowledgement for higher-risk candidate tiers

Charkive does not permanently delete files.

That is not merely a temporary limitation.

It expresses an important design principle:

> **When uncertainty exists, preservation wins.**

---

# Core Principle: Observation Before Action

Charkive should separate:

```text
OBSERVE
   ↓
CLASSIFY
   ↓
REPORT
   ↓
REVIEW
   ↓
PROPOSE
   ↓
AUTHORISE
   ↓
ACT
   ↓
VERIFY
```

Discovery should not imply destruction.

Classification should not imply action.

Recommendation should not imply authorisation.

Authorisation should not imply that an operation succeeded.

Every stage should remain meaningful independently.

---

# Core Principle: The Finding Is More Important Than the Metaphor

In future integrations, a Charkive finding might appear as:

```text
🚒 Fire alarm
🚓 Police investigation
🚛 Sanitation call
🏥 SANitorium admission
```

Those representations are useful, but they must never become the authoritative record.

Underneath them should be structured information describing the actual condition.

The metaphor exists to help humans understand the data.

The finding describes reality.

---

# 0.1: Structured Findings

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
```

The exact schema should evolve from real Charkive requirements rather than attempting to predict every future detector.

## Quick Win

Existing scan results can be converted into findings without changing Charkive's current classification behaviour.

## Success Criterion

> Another application can understand what Charkive discovered without parsing CLI output or scraping the web dashboard.

---

# 0.2: Findings API / Export

Make structured findings available outside Charkive.

Possible consumers include:

```text
Charkive Web
FileCity
Virtual Network Admin
BoreDOOM!
Automation
Future tools
```

Initially this can be read-only.

The important boundary is:

```text
FILESYSTEM
    ↓
CHARKIVE SCAN
    ↓
STRUCTURED FINDINGS
    ↓
OTHER SYSTEMS
```

External clients should not need to duplicate Charkive's classification logic.

## Success Criterion

> FileCity or another client can retrieve a genuine Charkive finding and display it meaningfully.

---

# 0.3: Stable Finding Categories

Introduce a small, stable vocabulary for findings.

Do not create hundreds of event types immediately.

Start from things Charkive genuinely understands.

Conceptually:

```text
storage.disposable_candidate
storage.protected
storage.quarantined
storage.restored
storage.preflight_warning
storage.preflight_failure
```

Additional categories should only appear when corresponding analysis actually exists.

This vocabulary becomes important because external clients should not depend upon Charkive's internal implementation details.

---

# 0.4: Severity and Confidence

Severity and confidence represent different concepts.

For example:

```text
Confidence:
How certain is Charkive about the classification?

Severity:
How important is the condition to the operator?
```

A detector might have:

```text
confidence = high
severity = low
```

because Charkive is very confident that something is disposable, but the item is tiny and insignificant.

Conversely, a condition could be operationally important while its diagnosis remains uncertain.

Keeping these concepts separate will make future automation safer.

---

# 0.5: Evidence

Findings should retain evidence sufficient to explain themselves.

The objective is that a user can ask:

> Why did Charkive flag this?

and receive a meaningful answer.

Evidence might derive from:

- classification rules
- file metadata
- paths
- extension matches
- size
- age or scan observations where available
- detector output
- filesystem checks
- configured protection rules

The evidence model should grow alongside actual detectors.

Avoid black-box classification where possible.

---

# Phase 1: Separate Detection From Response

The current workflow already supports an important distinction:

```text
scan
   ↓
review
   ↓
sanitise --dry-run
   ↓
sanitise
```

Preserve and strengthen this separation.

Long term, Charkive should be able to say:

```text
I found this.

Here is why.

Here is what I recommend.

Here is what I can safely do.

I have not done it yet.
```

This boundary becomes increasingly important when findings are surfaced through FileCity, Virtual Network Admin, or gameplay clients.

---

# Phase 2: Actions as Explicit Capabilities

Model Charkive actions separately from findings.

For example:

```text
Finding
   ↓
Recommended Action
   ↓
Available Charkive Operation
```

An operation might eventually describe:

```text
action
target
risk
requires_confirmation
dry_run_supported
reversible
expected_result
```

Charkive should remain the authority on whether a particular Charkive operation is safe and valid.

External clients request operations.

They do not reimplement Charkive's safeguards.

---

# Phase 3: Verification

A command completing is not sufficient evidence that the intended outcome occurred.

The eventual operation lifecycle should be:

```text
PROPOSE
   ↓
PREVIEW
   ↓
AUTHORISE
   ↓
EXECUTE
   ↓
VERIFY
   ↓
AUDIT
```

For reversible quarantine, verification should establish that Charkive's expected post-operation state exists.

Likewise, restoration should not be considered complete until its result is established.

## Principle

> **Act carefully, then check your work.**

---

# Phase 4: SANitorium as a First-Class Concept

The SANitorium is more than an amusing name.

It represents a core Charkive philosophy:

> **Questionable data should be isolated before it is destroyed.**

The SANitorium should therefore remain a first-class object in both Charkive and its integrations.

A quarantined object should retain enough information to answer:

```text
What was moved?
Where did it come from?
Why was it moved?
When was it moved?
Which scan/finding led to it?
Can it be restored?
Where would restoration place it?
```

The goal is traceable reversibility.

---

# Phase 5: FileCity Integration

Charkive should become FileCity's storage-health and response service rather than merely its local-filesystem counterpart.

Conceptually:

```text
STORAGE
   ↓
CHARKIVE
   ↓
FINDINGS
   ↓
FILECITY
   ↓
VISUAL CONDITION
```

FileCity should consume Charkive's structured output.

It should not need to understand Charkive's internal scanning implementation.

---

# Charkive as City Services

Within FileCity, Charkive findings and operations can be represented through municipal services.

The metaphor should remain derived from real Charkive state.

## Sanitation Department

This is the closest representation of Charkive's current functionality.

Likely disposable data can be represented as requiring sanitation review.

Once authorised for quarantine:

```text
SOURCE BUILDING
      ↓
CHARKIVE ACTION
      ↓
SANITATION VEHICLE
      ↓
SANITORIUM
```

The vehicle is the metaphor.

The actual operation remains a Charkive filesystem action.

---

# SANitorium District

FileCity can represent quarantined material as residing in a dedicated SANitorium facility or district.

The important semantic distinction is:

```text
Gone        ≠ quarantined
Deleted     ≠ quarantined
Destroyed   ≠ quarantined
```

Instead:

```text
Original location
       ↓
Controlled move
       ↓
SANitorium
       ↓
Recoverable
```

Restoration can be represented as the return journey.

---

# Fire Department

Over time, Charkive may gain detectors for urgent storage conditions.

Where genuine detectors exist, FileCity may represent appropriate high-severity findings as fire-service incidents.

The metaphor could communicate:

> Something here needs prompt attention.

A user investigating the incident should be led directly to the underlying Charkive finding.

```text
🚒 INCIDENT
     ↓
Affected storage
     ↓
Finding
     ↓
Evidence
     ↓
Recommended response
```

The fire itself must never be fabricated merely to make the city entertaining.

---

# Police Department

Some findings may represent conditions requiring investigation rather than immediate remediation.

These can potentially map to a police metaphor.

Conceptually:

```text
🚓 Investigation
      ↓
Finding
      ↓
Evidence
      ↓
User assessment
```

Again, the visual metaphor remains subordinate to the structured finding.

---

# City Services Rule

> **No sirens without evidence.**

If Charkive triggers a visible FileCity incident, there must be a real underlying finding.

If the condition disappears, is resolved, or is found to be incorrect, the world representation should reflect the real state.

---

# Phase 6: Storage Independence

Charkive currently operates on ordinary mounted filesystems, including local storage and mounted GlusterFS exports.

Long term, its conceptual model should avoid assuming that useful storage-health analysis must always be tied to one particular filesystem implementation.

However, do not distort the existing safe filesystem scanner merely to achieve theoretical universality.

Instead:

```text
Charkive Core Concepts
        │
        ├── Scanner / Detector
        ├── Finding
        ├── Evidence
        ├── Recommendation
        └── Action
```

can gradually become independent from:

```text
specific storage implementation
```

The existing local/mounted-filesystem implementation remains the first and authoritative implementation.

---

# Phase 7: FileCity Storage Context

FileCity provides spatial context that Charkive does not need to own.

Charkive might report:

```text
/path/to/cache
28 GB
candidate
```

FileCity might know that this corresponds to:

```text
DISTRICT:
Eddie

BUILDING:
Projects

FLOOR:
Temporary Data
```

Charkive need not understand districts, buildings or floors.

That division is intentional.

```text
CHARKIVE
knows condition
     +
FILECITY
knows geography
     =
UNDERSTANDABLE INCIDENT
```

---

# Phase 8: Virtual Network Admin Integration

Virtual Network Admin may provide infrastructure context around Charkive findings.

The longer-term relationship is:

```text
VNA
Infrastructure truth
      │
      ├─────────────┐
      ↓             ↓
  Charkive       FileCity
  analysis       geography
      │             │
      └──────┬──────┘
             ↓
       Digital Twin
```

For example, VNA may identify the machine or infrastructure containing a storage location.

Charkive may identify a condition within that storage.

FileCity may show where that condition exists spatially.

No one repository has to own all three responsibilities.

---

# Phase 9: Events

Charkive should eventually emit structured events when meaningful state changes occur.

Possible event categories derived from actual implemented behaviour might include:

```text
scan.completed
finding.created
quarantine.previewed
quarantine.completed
restore.completed
preflight.failed
```

Additional event types can be introduced as functionality expands.

These events allow clients to respond to Charkive activity without constantly polling and comparing complete reports.

---

# Phase 10: Historical State

Charkive already maintains scan history.

That history may eventually allow storage conditions to be examined over time.

Useful questions include:

```text
What changed between scans?

Did candidate data increase?

Did a condition disappear?

Was something quarantined?

Was something restored?
```

FileCity could eventually use this information to visualise change.

VNA might use it as part of an operational timeline.

Historical analysis should remain grounded in recorded Charkive state rather than inferred fictional history.

---

# Phase 11: Broader Detectors

The current product should not pretend to implement analysis that remains only a product idea.

Future detector work can be added incrementally.

Potential areas may include:

- storage growth
- duplicate analysis
- abandoned temporary data
- archive-health conditions
- capacity-related findings
- inconsistent or unusual storage patterns
- other evidence-based storage hygiene checks

Each new detector should preferably provide:

```text
finding
evidence
confidence
severity
recommended action
```

not merely a boolean warning.

---

# Duplicate Analysis

Duplicate cleanup should remain distinct from simple duplicate detection.

Finding two identical objects does not answer:

```text
Which is the master?
Which is expendable?
Are both intentionally retained?
Are they backups?
Do metadata differences matter?
Can either be safely quarantined?
```

The preservation-first principle applies.

> **Duplicate does not automatically mean disposable.**

Any future duplicate-response functionality should therefore require evidence and explicit policy rather than assuming that identical content authorises removal.

---

# Phase 12: Document and Data Curation

Charkive's broader preservation mission can eventually extend beyond obvious cache and scratch detection.

The question becomes:

> Which material appears important enough to protect, curate, consolidate, or preserve deliberately?

This complements sanitation.

```text
SANITATION
What might safely leave active storage?

CURATION
What deserves deliberate preservation?
```

These are different decisions.

Charkive should treat them differently.

---

# Phase 13: BoreDOOM! Integration

BoreDOOM! can eventually turn genuine Charkive findings into interactive missions.

Conceptually:

```text
REAL STORAGE
     ↓
CHARKIVE SCAN
     ↓
REAL FINDING
     ↓
MISSION
     ↓
PLAYER INVESTIGATION
     ↓
PROPOSED ACTION
     ↓
CHARKIVE VALIDATION
     ↓
EXECUTION
     ↓
VERIFICATION
     ↓
MISSION COMPLETE
```

The mission is not arbitrary game content.

It represents real work that Charkive believes deserves attention.

---

# Gameplay Safety Boundary

BoreDOOM!, FileCity, BeamNG, or any other renderer must not bypass Charkive safeguards.

A game client should not translate:

```text
Player presses FIRE button
```

directly into:

```text
rm -rf ...
```

Instead:

```text
PLAYER ACTION
     ↓
REQUEST
     ↓
CHARKIVE
     ↓
VALIDATION
     ↓
PREVIEW / CONFIRMATION IF REQUIRED
     ↓
CONTROLLED OPERATION
     ↓
VERIFICATION
     ↓
RESULT
```

The game is an interface.

Charkive remains the safety authority for Charkive operations.

---

# Gameplay as Work

The ultimate integration changes what "playing" means.

A player might receive:

```text
🚨 CHARKIVE CALL

Storage condition detected
Location: Archive District
Severity: Warning
```

They travel to the represented location.

They inspect the issue.

They obtain the real finding.

They examine evidence.

They select an appropriate permitted response.

Charkive performs or previews the legitimate operation.

The result is verified.

The incident clears.

The user has not merely gained imaginary points.

They have completed genuine storage administration.

> **Gameplay becomes an interface to useful work.**

---

# Renderer Independence

Charkive must not depend upon FileCity, BeamNG, BoreDOOM!, Unreal, Unity, or any other visualisation technology.

Its output should be structured enough that multiple clients can consume the same information.

```text
                  CHARKIVE
                     │
             Structured Findings
                     │
       ┌─────────────┼─────────────┐
       ↓             ↓             ↓
      CLI          Web UI       FileCity
                                   │
                             World Model
                                   │
                           ┌───────┴───────┐
                           ↓               ↓
                        BeamNG          BoreDOOM!
```

Charkive remains useful if every experimental renderer disappears tomorrow.

That is an important architectural test.

---

# Safety Philosophy

Charkive should continue to prefer reversible actions.

The hierarchy should generally favour:

```text
OBSERVE
over
MODIFY

PREVIEW
over
EXECUTE

QUARANTINE
over
DELETE

VERIFY
over
ASSUME

REPORT
over
HIDE
```

Where permanent destruction is not required, it should not be introduced simply for convenience.

The SANitorium remains the embodiment of this principle.

---

# Explainability

A Charkive recommendation should be understandable.

Where possible, users should be able to answer:

```text
Why was this found?

What evidence supports it?

How confident is Charkive?

How important is it?

What does Charkive recommend?

What will happen if I accept?

Is the action reversible?

What actually happened afterward?
```

The more autonomous Charkive eventually becomes, the more important these questions become.

---

# Auditability

Real actions should leave a durable record.

An audit trail should eventually establish:

```text
Finding
   ↓
Proposed action
   ↓
Preview
   ↓
Authorisation
   ↓
Execution
   ↓
Verification
   ↓
Outcome
```

Interactive or game clients must not make operations less auditable.

They should ideally make operational history easier to understand.

---

# Quick-Win Roadmap

## Slice 1: Structured Findings

Turn existing scan classifications into a stable machine-readable finding representation.

Do not redesign the scanner first.

Use what Charkive already knows.

### Success

> Existing Charkive knowledge can be consumed without parsing human-oriented output.

---

## Slice 2: Findings Export / API

Expose those findings through a simple read-only machine interface.

### Success

> Another local application can retrieve genuine Charkive findings.

---

## Slice 3: FileCity Proof of Concept

Have FileCity consume one genuine Charkive finding.

For example:

```text
Charkive finding
      ↓
FileCity storage object
      ↓
Visible indicator
      ↓
Inspect
      ↓
Actual Charkive evidence
```

No emergency vehicles are required yet.

### Success

> The city can show a real storage condition discovered by Charkive.

---

## Slice 4: SANitorium Visualisation

Expose enough quarantine information for FileCity to represent the SANitorium.

### Success

> A quarantined object can be traced from its original storage context into the SANitorium representation.

---

## Slice 5: One Visible Sanitation Operation

Take one genuine Charkive quarantine operation and expose its lifecycle.

```text
Candidate
   ↓
Preview
   ↓
Authorise
   ↓
Move
   ↓
Verify
   ↓
SANitorium
```

FileCity may eventually visualise this as a sanitation vehicle journey.

### Success

> A playful visual representation corresponds exactly to a real, verified Charkive operation.

---

## Slice 6: One Health Incident

Choose one genuine condition that deserves attention and represent it as an incident.

The underlying Charkive finding remains visible.

### Success

```text
REAL CONDITION
      ↓
CHARKIVE FINDING
      ↓
FILECITY INCIDENT
      ↓
USER INSPECTION
```

This proves the Police/Fire concept without needing to build an entire emergency-services simulation.

---

## Slice 7: One Controlled External Action

Allow an authorised external client to request one low-risk Charkive operation through a controlled interface.

Preserve:

- validation
- dry-run behaviour where appropriate
- confirmations
- reversibility
- verification
- audit information

### Success

> FileCity or another client can request a legitimate Charkive operation without bypassing Charkive's safeguards.

---

## Slice 8: First Gameplay Mission

Expose one genuine Charkive finding to BoreDOOM! or another experimental gameplay client.

The player investigates it.

The player chooses a permitted response.

Charkive remains responsible for validating and executing the real operation.

### Success

```text
REAL FINDING
   ↓
GAME MISSION
   ↓
PLAYER DECISION
   ↓
SAFE CHARKIVE ACTION
   ↓
VERIFIED REAL RESULT
   ↓
MISSION COMPLETE
```

At this point the wider vision has become real.

---

# Medium-Term Direction

Charkive should evolve from:

> A tool that scans filesystems for likely disposable data.

toward:

> A storage-health and preservation service capable of producing explainable findings and performing controlled, reversible responses.

This should happen without sacrificing the simplicity and usefulness of the standalone CLI.

A user who does not care about FileCity, VNA, BoreDOOM!, multiplayer, or 3D visualisation should still have an excellent Charkive experience.

That constraint is healthy.

---

# Long-Term Vision

Charkive becomes the preservation, hygiene and emergency-response authority for a larger digital estate.

Its scanners and detectors observe real storage.

Its findings explain what deserves attention.

Its evidence explains why.

Its response layer offers controlled action.

Its safety model prevents visual or gameplay clients from bypassing important safeguards.

Its verification layer determines what actually happened.

Its audit trail remembers it.

FileCity can turn those findings into geography and visible incidents.

Virtual Network Admin can connect them to wider infrastructure state.

BoreDOOM! can turn genuine operational work into multiplayer gameplay.

But Charkive itself remains grounded in something much simpler:

```text
FIND THE FLUFF
      ↓
PROTECT THE MASTERS
      ↓
EXPLAIN THE EVIDENCE
      ↓
ACT CAREFULLY
      ↓
KEEP IT RECOVERABLE
      ↓
VERIFY THE RESULT
```

The visual world may show fire engines, police cars, sanitation trucks and the SANitorium.

Underneath them are real findings, real data and real operations.

## North Star

> **Keep the masters. Burn the fluff. But never burn what you can't get back.**
