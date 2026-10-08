# Live rover playground

[日本語](hardware-playground.ja.md)

Status: software prototype tested with mocked live inputs and a disconnected WebSocket
adapter. No physical trial of this Playground UI has been performed. Existing rover and
person-following qualifications do not qualify this new UI.

The server's adapter selects the mode; the browser does not change the adapter or connect
directly to rover motors. A Simulator server retains its scene controls. A `websocket_rover`
server shows live camera observations and telemetry instead. `factory_http` is not supported
for live Playground trials. Marker guidance cannot start on a physical rover in this MVP;
marker observations can still be inspected.

## Later, with the rover

1. Follow [UGV02 self-test](../hardware/ugv02-self-test.md) and the
   [WebSocket firmware connection guide](../hardware/ugv02-websocket-firmware.md) first.
   Use matching rover ID/token and a private LAN; do not put tokens in URLs or Git.
2. Start the server with the existing `APRIS_ADAPTER=websocket_rover` configuration.
   Open `/lab?sample=follow` on the rover-mounted phone. Use HTTPS for a phone connecting
   by LAN address; see [Local HTTPS](../local-https.md).
3. Start **vision** with the appropriate camera. Allow camera access yourself. Confirm
   that the actual person is detected and an **accepted camera event** appears.
4. With rover connection and fresh telemetry, **Acquire control**. In a clear supervised
   test area, press **Confirm clear path · 30 s**. This is an operator confirmation, not
   automatic obstacle detection. The authoritative front state must become CLEAR.
5. Begin with `/lab?sample=greeting`: explicitly press **Start greeting** and verify a
   bounded turn and stop with wheels raised. Stop before selecting Follow helper, then
   confirm inputs/path again and explicitly press **Follow me**. Only after raised-wheel
   checks pass, perform a short floor trial with an operator able to stop it.
6. **Stop** cancels the current service. **Disable motion** revokes clearance.
   **Emergency stop** latches a server stop. Use these during qualification.

No service starts automatically when a camera, person, or rover reconnects. Clearance lasts
30 seconds and can be explicitly renewed. Camera stop/failure, a lost or stale person
observation, stale rover telemetry, disconnect, ownership loss, E-stop, non-CLEAR front
safety, or permission expiry removes readiness and cancels an active service.
After lost inputs, confirm the path again before starting a new trial. Browser heartbeat
refresh uses the existing server-owned clearance lease; browser suspension cannot keep it alive.
Do not use this as an unattended service or for general obstacle avoidance.

## What is visible

- Live camera image and existing upper-body detection box.
- Accepted camera person status, confidence, observation age, bearing and normalized image width.
- Accepted camera marker ID/status, observation age and relative x/y when supplied. This MVP
  displays marker values, not a QR overlay box on the video.
- Authoritative front safety and rover pose estimate.
- A rolling 12-second graph of rover-reported linear/angular velocity estimates. It is not
  externally measured motion; missing telemetry must not be interpreted as zero movement.
- The same real mission code and reported decision highlighting as the Simulator.
- Timestamped high-level move/turn requests, completion/failure, and stop reasons. These
  are not a plotted motor-command waveform or instruction-level debugger.
- Recent server observations, including rejection reasons, in a details disclosure.

Physical missions accept only server-published `camera` events. Recorded video, manual,
scenario and replay events do not trigger this mode's missions. Live camera input is still
validated by the server. No Simulator pose reset, synthetic obstacle CLEAR, synthetic person,
marker injection, or scene-editor operation is used in this mode. Runtime/firmware safety
remains authoritative.

## Without hardware

Continue using the [Simulator workshop](playground-workshop.md). Software tests mock camera
readiness, accepted observations, telemetry and motion responses to check arming, source
filtering, cancellation and permission expiry. They do not establish camera accuracy, Wi-Fi
latency, actual wheel direction, smoothness, or real stopping distance. Those require the
physical qualification above. A disconnected WebSocket server exposes the live UI with
service-start and motion-clearance controls disabled; it is not a fake connected rover.

Run `npm test`, `npm run typecheck`, and `npm run build` for the frontend checks.
