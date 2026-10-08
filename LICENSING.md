# Licensing and third-party source

The root [MIT license](LICENSE) covers original APRISRC Kit application/server code,
protocol definitions, tests, scripts and documentation, except where a file carries a
different notice. It does not relicense the vendored firmware or third-party dependencies.

## Firmware

`firmware/upstream/ugv_base_ros_smooth/` contains a modified derivative of
[JuzzyDee/ugv_base_ros_smooth](https://github.com/JuzzyDee/ugv_base_ros_smooth), based on
[Waveshare ugv_base_ros](https://github.com/waveshareteam/ugv_base_ros).
The bundled upstream README identifies Copyright (C) 2024 Waveshare and GPL version 3
or later. Its [GPL text](firmware/upstream/ugv_base_ros_smooth/LICENSE), original notices
and source comments are retained. APRIS modifications in this derivative are distributed
under those GPL terms, not the root MIT license. The bundled SCServo source and examples
remain part of the upstream tree with their existing notices.

Imported motion-control baseline: JuzzyDee commit `1db990a`; upstream Waveshare v0.96
baseline recorded as `2e7df97`. APRIS changes include encoder estimation/control tuning,
WebSocket protocol support, leased/bounded movement, safety checks, and a reduced serial
provisioning profile. PlatformIO configuration pins build dependencies. No compiled firmware
binary, original private Git history, local credentials or flash backups are shipped here.

The upstream firmware README describes the vendor firmware, not all capabilities of the
APRIS profile. Build/provision using [the APRIS guide](docs/hardware/ugv02-websocket-firmware.md).
Before distributing a compiled firmware image, satisfy the applicable GPL source and notice
requirements and the licenses of its build dependencies.

## Dependencies and optional integrations

npm, Python and PlatformIO dependencies retain their own licenses; installing them does
not place them under MIT. Their manifests/lockfiles identify the dependencies. Browser
perception also loads external model/runtime assets; review the relevant provider terms
when packaging or redistributing those assets offline.

The initial public release does not bundle the separate PhysiCode provider contracts,
fixtures or supervisor, so its cross-repository contract suite is not included. The original
APRIS compatibility/bridge implementation and its self-contained tests remain in the server;
external integration is not part of this release's supported getting-started path.
