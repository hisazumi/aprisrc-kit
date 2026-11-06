"""Bounded lifecycle for the one fixed simulator service executable."""

import asyncio
import os
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


class ServiceProcess:
    def __init__(self, port, token, service_getter, *, node=None, origin="http://127.0.0.1:8766"):
        self.origin = origin
        self.port = port
        self.token = token
        self.service_getter = service_getter
        self.node = node or shutil.which("node") or "node"
        self.job = None
        self.task = None

    @property
    def active(self):
        return self.task is not None and not self.task.done()

    def snapshot(self):
        if not self.job:
            return None
        return {k: self.job[k] for k in ("id", "status", "reason", "runEpoch")} | {
            "active": self.active
        }

    def launch(self):
        if self.active:
            raise ValueError("service-process-busy")
        job = dict(
            id=uuid.uuid4().hex,
            status="starting",
            reason="",
            runEpoch=None,
            stop=asyncio.Event(),
            operatorId=self.port.operator_id,
        )
        self.job = job
        self.task = asyncio.create_task(self._run(job))
        return self.snapshot()

    def request_stop(self):
        if self.job and self.active:
            self.job["status"] = "stopping"
            self.job["stop"].set()

    async def _run(self, job):
        process = None
        drain = None
        stopped = None
        exited = None
        tail = bytearray()
        try:
            env = dict(
                os.environ,
                APRIS_CONSOLE_TOKEN=self.token,
                APRIS_LAUNCH_ID=job["id"],
                APRIS_CONSOLE_ORIGIN=self.origin,
            )
            process = await asyncio.create_subprocess_exec(
                self.node,
                str(ROOT / "apps/runner-prototype/console-service.ts"),
                cwd=ROOT,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            async def read_output():
                while data := await process.stdout.read(4096):
                    tail.extend(data)
                    if len(tail) > 4096:
                        del tail[:-4096]

            drain = asyncio.create_task(read_output())
            exited = asyncio.create_task(process.wait())
            stopped = asyncio.create_task(job["stop"].wait())
            await asyncio.wait({exited, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if job["stop"].is_set() and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(asyncio.shield(exited), 0.7)
                except TimeoutError:
                    process.kill()
            await asyncio.wait_for(asyncio.shield(exited), 1)
            await asyncio.wait_for(drain, 1)
            job["status"] = (
                "interrupted"
                if job["stop"].is_set()
                else "completed"
                if process.returncode == 0
                else "failed"
            )
            job["reason"] = (
                "operator-stop"
                if job["stop"].is_set()
                else "service-completed"
                if process.returncode == 0
                else f"node-exit-{process.returncode}"
            )
        except Exception as error:
            job["status"] = "failed"
            job["reason"] = f"{type(error).__name__}: {error}"[:256]
        finally:
            if process and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except TimeoutError:
                    job["reason"] = "process-exit-unconfirmed"
            for task in (drain, stopped, exited):
                if task and not task.done():
                    task.cancel()
            # Never revoke a newer run from an old process completion.
            async with self.port.lock:
                if job["runEpoch"] and self.port.session == job["runEpoch"]:
                    self.port._revoke("service-host-exited")
                service = self.service_getter()
                if service and service["runEpoch"] == job["runEpoch"] and service["result"] is None:
                    service["result"] = dict(
                        status="interrupted" if job["stop"].is_set() else "failed",
                        reason=job["reason"],
                    )
                    service["prompt"] = service["answered"] = None

    async def close(self):
        self.request_stop()
        if self.task:
            await self.task
