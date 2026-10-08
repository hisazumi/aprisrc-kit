[日本語](mobile-receptionist.ja.md)

# Mobile Receptionist demo

Status: **Implemented in the shared Service App; supervised UGV02 walkthrough pending**

For first-time desktop trials use the [Playground workshop](playground-workshop.md).
This page covers a separate Service App flow. Its physical marker approach is unverified;
Live Playground intentionally disables that mission. Do not use this path to bypass its gate.

This service greets a visible visitor, accepts an allowlisted destination, finds the configured
destination marker, approaches it in bounded steps, and announces arrival. It demonstrates a
multi-input service built only from the public Mission API.

## Run the deterministic demo in the Service App

```bash
npm run dev
```

Open `http://localhost:5173/app?service=receptionist`, then:

1. Confirm that the status says **Simulator connected**.
2. Press **Run simulated service**. The app acquires control, starts the Mission, and starts the
   deterministic scenario in that order.
3. Observe the mission greet the visitor, ignore the kitchen marker, align to entrance marker
   1, approach it in bounded steps, and stop at arrival.
4. Check that the app shows **Destination reached** and the rover velocity is zero in the
   Operator Console.

The Service App performs the required Mission-before-scenario ordering. The scenario also
establishes a fresh `CLEAR` front-obstacle state for its explicitly simulated area. `/lab`
remains available for inspecting individual events and faults, but it is not a separate service
application.

The same mission can be started from **Human interaction** with **Guide me** or a request such
as `Guide me to the entrance`. Natural-language input supplies `desk`, `kitchen`, or `entrance`;
starting the mission from the mission selector uses `entrance` by default.

## Service boundary

The mission uses only:

- `onPerson()` and `onMarker()` observations
- `turn()` and `move()` bounded motion
- `stop()` for arrival and every unsafe exit
- `say()` for visitor feedback
- the read-only authoritative front-obstacle snapshot

It does not access Simulator controls, wheel velocities, command TTL, or the Rover protocol.
Wrong marker IDs are ignored. A lost or stale destination marker stops active motion.
Arrival targets 0.45 m with a 0.02 m tolerance to avoid moves below the motion completion tolerance.
Forward movement occurs only while the authoritative front state is `CLEAR`; `BLOCKED` and `UNKNOWN`
both stop the service.

## Configure destinations

Participant-facing marker labels and destination keys are in
`apps/pwa/src/config/courseMarkers.ts`. Matching course poses for server-side pose correction
are in `apps/server/config/course-markers.json`.

The reference mapping is:

| Destination | Marker ID |
|---|---:|
| Entrance | 1 |
| Desk | 2 |
| Kitchen | 3 |

Keep IDs unique and update both files together. Service code selects a destination key and does
not hard-code physical coordinates.

Printable A4 markers are available for
[Entrance](../../output/pdf/apris-marker-1-entrance-a4.pdf) and
[Desk](../../output/pdf/apris-marker-2-desk-a4.pdf). Print at **100% / Actual size**. The black
QR area is 160 mm wide; do not use **Fit to page**. Mount the full sheet flat and vertical with
its white border unobstructed.

## Run the same app with UGV02

Start the Local Server with `APRIS_ADAPTER=websocket_rover` and open the same
`/app?service=receptionist` URL on the mounted phone. **Start receptionist** first uses the front
camera to confirm a visitor, then requests the rear camera while finding the destination QR
marker. Forward movement requires **Allow movement for 30 s**; revoking it or letting it expire
returns the authoritative forward state to `UNKNOWN`.

The Simulator scenario is a deterministic input harness, not a physical navigation system.
Before a floor trial, verify marker 1 with the wheels raised, then perform a short supervised
approach. Printed marker size, camera range, stopping distance, and the course layout remain
physical test variables.
