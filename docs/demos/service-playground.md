# Service playground

[日本語](service-playground.ja.md)

The Playground is APRISRC Kit's sample development view. Greeting, following and marker
guidance illustrate reusable APIs; they are not required challenge services. Participants
develop their own service policy and user experience; see [Purpose and scope](../positioning.md).

Status: Simulator MVP with an experimental [live rover mode](hardware-playground.md).
The live mode has software tests but has not been physically qualified.

First visit? Use the [20-30 minute hands-on guide](playground-workshop.md) for startup,
repeatable scenes, and two small before/after improvement exercises. This page is the controls reference.

Start the development environment using the [quickstart](../challenger-quickstart.md), then
open `/lab?sample=greeting`. No camera, phone, physical rover, or API key is required.

1. Press **Start greeting**. Control acquisition is automatic.
2. Select **On the left**. Watch the rover face the visitor and read or hear its greeting.
3. Change **Greeting**, then start again. The service speaks the new text.
4. Set **Maximum turn** to zero, choose **On the right**, and start again. The service greets
   without turning. Restore 15 degrees and compare.
5. Choose **Outside view** and start. The service waits for a visitor. **Stop** cancels it;
   after 30 seconds without detection, the observation wait reports a timeout.

The service experience, simulated visitor, real mission source, and reported steps appear in
one workspace. Highlighting follows Mission reports and marks the observation wait, turn,
or greeting statement; it is not a debugger or instruction-level execution trace.

Preview controls change only this browser's next run. To keep the settings, edit
`apps/pwa/src/config/greetingStarter.ts`. To change the behavior, edit
`apps/pwa/src/missions/challengerStarter.ts`. These are the same defaults and mission used by
the registered Person greeting starter. Reloading restores file settings; it discards browser
preview settings. Source edits use Vite reload, so stop a running trial before editing.

## Try the follow helper

Select **Follow helper**, or open `/lab?sample=follow` directly.

1. Press **Follow me**. If nobody is present, the scene places a person in front of the rover.
2. Observe the rover approach and then keep its distance.
3. Press **Walk ahead**. The person walks a gentle 12-second route; the rover follows.
4. Press **Stand still**. The rover catches up and holds its distance.
5. Choose **Outside view** during motion. The mission stops and reports target loss.
6. After stopping, change **Following distance** to Near or Far and repeat. These options
   change the camera-frame width thresholds; they are not calibrated physical metre values.

This runs the existing `carryHelperMission` and `runFollowMe` in `missions/comeHere.ts`,
including target-loss and stale-observation stops. The code panel displays the real tracking
loop and scrolls to its reported decision. Distance presets are shown from the same source;
edit that file to change them permanently.

The Simulator harness declares this empty test area CLEAR before starting and refreshes it
while the follow service runs. This is synthetic free-space input, not obstacle sensing.
Simulator scene controls are unavailable with physical adapters. Sensor failure, loss of control, E-stop, or Stop
cancels the current run; switching examples is disabled until the run ends.

## Try marker guidance

Select **Marker guide**, or open `/lab?sample=receptionist`. Choose Entrance or Desk and
press **Guide me**. The visitor is supplied automatically; the existing reception mission
searches for the selected marker, approaches it, and announces arrival. Desk takes longer
because it is farther from the starting position.
The mission allows at most 32 approach steps, then checks the final observation. Initial search
turns in place until measured rotation reaches a full circle (at most 36 short turns). If no
destination marker is found, it stops and asks for repositioning; it never searches by driving.

### Design a test scene

In **Test scene**, choose **In view**, **Behind rover**, or **Not visible**. Edit the rover's
start x/y and heading, visitor x/y, and Entrance/Desk x/y in metres. The map previews these
positions before starting. **Guide me** resets the rover to that scene on every run.
The visitor must be in view to trigger the service; a visitor outside view causes a wait.
Initial marker visibility and path blockage are scene settings; the controls beside the map
can still change them during a run. Position editing is locked until the service stops.

**Save scene** stores one scene in this browser. **Load scene** restores it after reload or
edits; it does not start motion. Saving does not alter source files or share the scene.
Only marker guidance has this editor in the MVP; greeting/following retain their visitor controls.
Simulator marker positions are updated with the scene, independently of physical course defaults.

- **Other marker** exposes the other configured marker. The mission ignores its ID while
  searching. Switch to **Correct marker** to let the mission find its destination; detection
  still depends on whether the marker is inside the simulated field of view.
- **Hide marker** during approach produces target loss and a stop. Restore **Correct marker**
  and start again to repeat.
- **Path blocked** supplies a latched BLOCKED observation. Forward motion stops. Uncheck it
  and restart after the simulated path is clear.

Every guidance run resets the Simulator course pose to the scene's start, stops any old motion
and scenario, and clears Simulator fault settings. It preserves control ownership and E-stop.
Markers use the configured course coordinates and a 70-degree field of view; their relative
position changes with the rover's actual simulated pose. Arrival is determined by the same
mission's 0.45 m target with a 0.02 m arrival tolerance, not by a timed scenario completion. This is geometric perception
input, not QR image recognition or route planning. Markers hidden by the scene controls are
dimmed on the map even if their physical position remains known.

The code panel shows `runMobileReceptionist`; configuration and approach constants are
available beside it. Change `config/courseMarkers.ts` and the matching server course-marker
configuration together when editing marker IDs or course positions. Hardware guidance is
still unverified; no printing or physical equipment is needed for this Playground.

The simulated visitor is a geometric observation source, not virtual camera recognition.
The mission uses the public Mission API and keeps server ownership, cancellation, speed
limits, and emergency stop unchanged. This greeting example performs a single bounded turn;
it does not continuously track a visitor or offer the following service's target-loss behavior.
Use the regular Lab for other missions, emergency-stop recovery, and advanced diagnostics.

This prototype evaluates whether users can connect a service experience to editable code.
Physical marker guidance remains a separate, unverified hardware trial.
