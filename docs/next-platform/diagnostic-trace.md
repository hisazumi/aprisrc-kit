# Correlated localization, route and service diagnostics

Download `apris-diagnostic-trace.json` using **診断ログを保存** on `/console`,
or authenticated `GET /api/trace`. Export works after completion/failure and does
not renew leases, recover control, clear handover guards or move the robot. Data
is in memory for this server instance; export before restarting it.

Every record has a cursor and host-monotonic timestamp. The envelope carries a
traceId, schemaVersion, dropped count and complete flag. Context correlates
controlEpoch, runId/runEpoch, matching route ID/waypoint/action count/status,
localization evaluation, localization gate reason, guard ID and inhibition.
Revocation and terminal events retain the original run epoch after run release;
an old route is not attached to a different run's events.

Localization uses the safety gate's cached last evaluation, including map identity
and digest, localization/odometry epochs, odom/map poses, quality/error estimates
and provenance. Diagnostics do not advance estimator state. Record time differs
from sensor sampleTime and evaluation receivedTime; use all timestamps when
assessing freshness. Missing evaluations are null.

Recorded events include operator transitions (excluding heartbeat/snapshot),
localization samples at at most 2 Hz during a run, marker correction results,
route start/action requests, motion terminal/revocation/localization loss/route
terminal, and service start/question/answer/consume/speech/finish. Route action
records denote requests, not acceptance or completion. Service questions and
answers carry only question IDs and handover metadata; speech carries an index,
not text. No authentication token or dialogue body is recorded. Technical error
reasons remain diagnostic strings.

To investigate: select the finished service's runEpoch, order by cursor, find the
first failure/revocation and inspect the contemporaneous localization evaluation
and gate reason. Correlate route actions with motion terminals and the final
route terminal. A successful delivery consumes its receipt question only after
arrival. Stop-unconfirmed never means arrival or confirmed stopping, and speech
acceptance does not prove audio playback completion.

Storage is bounded to 512 entries and 180,000 bytes of serialized records. Entries
above 16,384 bytes or not JSON-serializable are dropped. Eviction and rejected
records increment dropped; complete becomes false. Cursor gaps and loss counts
must be checked before interpreting absence of an event. Even complete=true means
only that the selected diagnostic stream has no reported loss, not that all raw
sensor inputs or all causal history were captured.

This is simulator diagnostics, not physical stop qualification. There is no
upload, durable storage, automatic replay or motor-command replay API. M4 input
capture and reproducible replay remain separate work; this trace alone is not a
deterministic replay source.

Tests cover entry/byte limits, independent copies, explicit loss, authentication,
read-only export, no estimator evaluation during recording, browser download
without authority changes, and connected delivery completion/interruption with
run/route correlation and handover ordering.
