"""Authenticated local-mailbox gateway. No ROS or remote bounded-motion API.

JSON RPC: {id, method, params} -> {id, result} or {id, error: {code, message}}.
acquire returns {nonce}; state and drive return {state, nonce}; other results are null.
Nonces are opaque, connection/ownership scoped, single-use; lifetime is profile-specific.
Only successful drive renews ownership. Stop failure requires gateway restart.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hmac
import json
import math
import os
import secrets
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from .ironx_adapter import IronXAdapter
from .ironx_profile import load_profile

LEASE_SECONDS = 0.3


class GatewayError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(eq=False)
class Session:
    nonces: dict[str, tuple[float, int]] = field(default_factory=dict)
    connected: bool = True


class IronXGateway:
    def __init__(self, adapter, token: str, *, clock=time.monotonic):
        if not token or token.strip() != token or not token.isascii():
            raise ValueError("A nonempty ASCII bearer token is required")
        self.adapter = adapter
        self.profile = load_profile()
        self.token = token
        self.clock = clock
        self.owner = None
        self.deadline = 0.0
        self.epoch = 0
        self.stopping = 0
        self.fault = None
        self.ready = False
        self.estopped = False
        self._mutations = asyncio.Lock()
        self._stops = asyncio.Lock()
        self._active = None

    def authenticate(self, connection, request):
        values = request.headers.get_all("Authorization")
        if len(values) != 1 or not hmac.compare_digest(
            values[0].encode(), ("Bearer " + self.token).encode()
        ):
            response = connection.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        return None

    async def initialize(self):
        await self._halt(revoke=True)
        self.ready = True

    def _available(self):
        if self.fault:
            raise GatewayError("stop_unconfirmed", "Stop unconfirmed; restart gateway")
        if not self.ready or self.stopping:
            raise GatewayError("stopping", "Stop confirmation in progress")

    def _owned(self, session):
        self._available()
        if self.owner is not session or not session.connected:
            raise GatewayError("not_owner", "Connection does not own control")
        if self.clock() >= self.deadline:
            raise GatewayError("lease_expired", "Drive lease expired")

    def _nonce(self, session):
        now = self.clock()
        session.nonces = {
            key: value
            for key, value in session.nonces.items()
            if value[0] > now and value[1] == self.epoch
        }
        if len(session.nonces) >= 128:
            del session.nonces[next(iter(session.nonces))]
        nonce = secrets.token_urlsafe(24)
        session.nonces[nonce] = (now + self.profile.nonce_s, self.epoch)
        return nonce

    async def _halt(self, *, revoke=False, emergency=None, clear=False):
        # Close admission before yielding; stops bypass and cancel ordinary mutations.
        self.stopping += 1
        self.epoch += 1
        if revoke:
            self.owner = None
        if emergency is not None:
            self.estopped = True
        active = self._active
        if active is not None and active is not asyncio.current_task():
            active.cancel()
        try:
            async with self._stops:
                if emergency is not None:
                    self.estopped = True
                    await self.adapter.emergency_stop(emergency)
                elif clear:
                    await self.adapter.clear_emergency_stop()
                    self.estopped = False
                else:
                    await self.adapter.stop()
                async with self._mutations:
                    pass
        except BaseException:
            self.fault = "stop_unconfirmed"
            self.owner = None
            raise
        finally:
            self.stopping -= 1

    async def expire(self):
        if self.owner is not None and self.clock() >= self.deadline and not self.stopping:
            await self._halt(revoke=True)

    async def watchdog(self):
        while True:
            await asyncio.sleep(0.01)
            with contextlib.suppress(Exception):
                await self.expire()

    async def disconnect(self, session):
        session.connected = False
        session.nonces.clear()
        if self.owner is session:
            await self._halt(revoke=True)
        elif self.stopping:
            # A release already revoked ownership but must finish confirmation.
            async with self._stops:
                pass

    async def dispatch(self, session, method, params):
        if not session.connected:
            raise GatewayError("disconnected", "Connection closed")
        if method == "state":
            if params:
                raise GatewayError("invalid_params", "state takes no parameters")
            state = await self.adapter.state()
            anomalies = []
            if self.fault:
                anomalies.append("gateway_stop_unconfirmed")
            if self.stopping or not self.ready:
                anomalies.append("gateway_stopping")
            if self.estopped:
                anomalies.append("gateway_emergency_stop")
            if anomalies:
                quality = state.pose_quality.model_copy(
                    update={
                        "anomalies": [*state.pose_quality.anomalies, *anomalies],
                    }
                )
                state = state.model_copy(update={"connected": False, "pose_quality": quality})
            return {"state": state.model_dump(mode="json"), "nonce": self._nonce(session),
                    "profile": self.profile.name}
        if method == "drive":
            epoch = self.epoch
            try:
                return await self._drive(session, params, epoch)
            except Exception:
                if self.owner is session and self.epoch == epoch:
                    await self._halt(revoke=True)
                raise
        if method == "emergency_stop":
            if set(params) - {"reason"} or not isinstance(params.get("reason", "remote"), str):
                raise GatewayError("invalid_params", "reason must be a string")
            await self._halt(revoke=True, emergency=params.get("reason", "remote"))
            return None
        if params:
            raise GatewayError("invalid_params", "Method takes no parameters")
        if method == "stop":
            if self.owner is session:
                await self._halt()
            return None
        if method == "release":
            if self.owner is not session:
                raise GatewayError("not_owner", "Connection does not own control")
            await self._halt(revoke=True)
            return None
        if method == "clear_emergency_stop":
            self._available()
            if self.owner is not None and self.owner is not session:
                raise GatewayError("not_owner", "Another connection owns control")
            await self._halt(clear=True)
            return None
        if method == "acquire":
            async with self._mutations:
                self._available()
                if not session.connected:
                    raise GatewayError("disconnected", "Connection closed")
                if self.owner is not None:
                    self._owned(session)
                else:
                    self.owner = session
                    self.epoch += 1
                    self.deadline = self.clock() + self.profile.ownership_s
                return {"nonce": self._nonce(session), "profile": self.profile.name}
        raise GatewayError("method_not_found", "Unknown method")

    async def _drive(self, session, params, epoch):
        async with self._mutations:
            self._owned(session)
            if epoch != self.epoch or self.estopped:
                raise GatewayError("superseded", "Command superseded by stop")
            if set(params) != {"nonce", "vx", "vy", "wz", "ttl_ms"}:
                raise GatewayError("invalid_params", "Expected nonce, vx, vy, wz, ttl_ms")
            nonce = params["nonce"]
            challenge = session.nonces.pop(nonce, None) if isinstance(nonce, str) else None
            if challenge is None or challenge[1] != self.epoch:
                raise GatewayError("invalid_nonce", "Unknown or consumed nonce")
            remaining = challenge[0] - self.clock()
            if remaining <= 0:
                raise GatewayError("expired_nonce", "Nonce expired")
            values = [params[key] for key in ("vx", "vy", "wz", "ttl_ms")]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise GatewayError("invalid_params", "Drive values must be finite numbers")
            vx, vy, wz, ttl = values
            if vy != 0 or abs(vx) > 0.15 or abs(wz) > 0.2 or ttl <= 0:
                raise GatewayError("invalid_params", "Invalid differential drive or speed limit")
            # Charge transport time since the challenge was issued to command TTL too.
            issued = challenge[0] - self.profile.nonce_s
            ttl = min(ttl, self.profile.local_command_ms)
            ttl = math.floor(min(challenge[0], issued + ttl / 1000) * 1000 - self.clock() * 1000)
            if ttl < 1:
                raise GatewayError("expired_nonce", "Insufficient nonce lifetime")
            self._active = asyncio.current_task()
            try:
                async with asyncio.timeout(remaining):
                    await self.adapter.drive(vx, vy, wz, ttl_ms=ttl)
                self._owned(session)
                if epoch != self.epoch:
                    raise GatewayError("superseded", "Command superseded by stop")
                self.deadline = self.clock() + self.profile.ownership_s
            except asyncio.CancelledError:
                raise GatewayError("superseded", "Command cancelled by stop") from None
            finally:
                self._active = None
        return await self.dispatch(session, "state", {})

    async def respond(self, session, raw):
        request_id = None
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise GatewayError("invalid_request", "Expected request object")
            request_id = request.get("id")
            if type(request_id) not in (str, int) or not isinstance(request.get("method"), str):
                request_id = None
                raise GatewayError("invalid_request", "Expected string/integer id and method")
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise GatewayError("invalid_params", "params must be an object")
            result = await self.dispatch(session, request["method"], params)
            return {"id": request_id, "result": result}
        except Exception as exc:
            code = exc.code if isinstance(exc, GatewayError) else "adapter_error"
            if isinstance(exc, (ValueError, TypeError)):
                code = "invalid_request"
            if self.fault:
                code = "stop_unconfirmed"
            return {"id": request_id, "error": {"code": code, "message": str(exc)}}

    async def handler(self, websocket):
        session = Session()
        pending = set()

        async def reply(raw):
            response = await self.respond(session, raw)
            with contextlib.suppress(ConnectionClosed):
                await websocket.send(json.dumps(response, allow_nan=False))

        try:
            async for raw in websocket:
                if len(pending) >= 32:
                    await websocket.close(code=1008, reason="Too many pending requests")
                    break
                task = asyncio.create_task(reply(raw))
                pending.add(task)
                task.add_done_callback(pending.discard)
        finally:
            # Stop is independent of telemetry requests and socket send completion.
            with contextlib.suppress(Exception):
                await self.disconnect(session)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--start-estopped", action="store_true",
                        help="Require explicit stop reset after gateway startup")
    for flag, env in (
        ("state-file", "APRIS_ROS2_STATE_FILE"),
        ("command-file", "APRIS_IRONX_COMMAND_FILE"),
        ("bridge-state-file", "APRIS_IRONX_BRIDGE_STATE_FILE"),
    ):
        parser.add_argument("--" + flag, type=Path, default=os.environ.get(env))
    args = parser.parse_args(argv)
    paths = [args.state_file, args.command_file, args.bridge_state_file]
    if any(path is None for path in paths):
        parser.error("All three local mailbox paths are required")
    if len({path.resolve() for path in paths}) != 3:
        parser.error("Mailbox paths must be distinct")
    if not os.environ.get("APRIS_IRONX_GATEWAY_TOKEN"):
        parser.error("APRIS_IRONX_GATEWAY_TOKEN is required")
    return args


async def run(args):
    adapter = IronXAdapter(args.state_file, args.command_file, args.bridge_state_file)
    gateway = IronXGateway(adapter, os.environ["APRIS_IRONX_GATEWAY_TOKEN"])
    await adapter.start()
    try:
        await gateway.initialize()
        if args.start_estopped:
            await gateway._halt(revoke=True, emergency="Gateway maintenance startup")
        async with serve(
            gateway.handler,
            args.host,
            args.port,
            process_request=gateway.authenticate,
            max_size=16384,
            max_queue=16,
        ):
            watcher = asyncio.create_task(gateway.watchdog())
            try:
                await asyncio.Future()
            finally:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
    finally:
        await adapter.close()


def main():
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
