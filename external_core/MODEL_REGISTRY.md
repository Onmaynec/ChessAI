# Model Registry & Naming — v0.9.3.5.3
Read-only shared model catalog. Dashboard Models tab, named PPO sessions, Vision
model selector, manual Bot Lab and Multi-Engine Lab use the same names and content
revisions. A checkpoint is not a run. PPO resume continues the original latest.pt
and optimizer. The catalog never replaces, renames, deletes, or promotes weights.
Technical IDs remain stable on disk. SHA-256 exact byte duplicates and historical
aliases are hidden by default, visible in the dashboard archive. A different
checkpoint may contain identical tensors but different metadata; not assumed equal.
Candidate provenance comes from completed training_report.json (schema, selected
epoch, model_config), no claims of verified Elo. PPO/legacy release number may be
unknown, displayed revision is actual file hash, not trainer version. External
revision is installation manifest hash; integrity is checked by UCI loader at launch.
The new candidate Vision namespace model_catalog_sessions/<sha256> is independent
of existing neural/UCI recovery. Stop the session before switching candidate or UCI.
Existing Vision authorization and computer-only constraints unchanged. Catalog scans
read bytes once per file stat revision, so opening/refreshing may cause temporary
disk load. No torch deserialization in catalog. Refresh Vision selection after a
candidate finishes; the hash represents catalog scan time, not a live PPO iteration.
Install with Vision, dashboard and local match labs closed; active standalone
Scaling may continue, but avoid launching games/training concurrently.
For a safe cleanup audit, run python -B -m neural.model_catalog --output
model_inventory.json from the project root. It writes a read-only inventory and
refuses overwrite. No physical removal until local inventory reviewed, training
stopped, and all active sources/recovery references accounted for.
