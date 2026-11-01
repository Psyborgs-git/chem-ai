"""Outbound, authenticated worker for a self-hosted CPU/CUDA training machine.

Run ``python -m workers.training.workspace_worker --api https://studio.example
--backends transformers,chemprop --work-dir /private/training`` with an existing
user session token in STUDIO_WORKER_TOKEN. The token never enters trainer env.
Imported model IDs can be mapped to paths with repeated --model ID=/local/path.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any

from studio.domain.learning.workspace_runtime.dispatcher import _environment, _events, _kill

MAX_BYTES = 256 * 1024 * 1024


class Client:
    def __init__(self, base: str, token: str) -> None:
        parsed = urllib.parse.urlsplit(base)
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "\\" in base
            or any(character.isspace() for character in base)
        ):
            raise ValueError(
                "Worker API URL must have a plain host without credentials, query or fragment"
            )
        decoded_path = urllib.parse.unquote(urllib.parse.unquote(parsed.path))
        if any(part in {".", ".."} for part in decoded_path.split("/")):
            raise ValueError("Worker API URL cannot contain path traversal")
        _port = parsed.port  # Validate the port syntax before accepting the origin.
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("Use HTTPS for a remote Studio server")
        self.base, self.token = base.rstrip("/") + "/api/learning-workspace", token

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(
                self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
            ) -> None:
                raise ValueError("Worker API redirects are not allowed")

        # Session tokens never follow redirects or an environment-configured proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(
        self,
        path: str,
        payload: Any = None,
        *,
        data: bytes | None = None,
        content_type: str = "application/json",
    ) -> Any:
        if payload is not None:
            data = json.dumps(payload).encode()
        request = urllib.request.Request(  # noqa: S310 — origin validated; redirects/proxies denied
            self.base + path,
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": content_type,
            },
        )
        with self.opener.open(request, timeout=90) as response:
            value = response.read(MAX_BYTES + 1)
            if len(value) > MAX_BYTES:
                raise ValueError("Worker response exceeds transfer limit")
            return (
                json.loads(value) if "json" in response.headers.get("Content-Type", "") else value
            )

    def upload(self, identifier: str, metadata: dict[str, Any], artifacts: bytes) -> Any:
        boundary = uuid.uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()
            + json.dumps(metadata).encode()
            + (
                f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                'filename="artifacts.zip"\r\nContent-Type: application/zip\r\n\r\n'
            ).encode()
            + artifacts
            + f"\r\n--{boundary}--\r\n".encode()
        )
        return self.request(
            f"/worker/jobs/{identifier}/complete",
            data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )


def _archive(directory: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        total = 0
        for path in directory.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            total += path.stat().st_size
            if total > MAX_BYTES:
                raise ValueError(
                    "Artifacts exceed 256 MiB; use smaller adapters/checkpoint retention"
                )
            archive.write(path, str(path.relative_to(directory)))
    return buffer.getvalue()


def _restore(content: bytes, directory: Path) -> None:
    if not content:
        return
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
            raise ValueError("Checkpoint archive exceeds transfer limit")
        for item in archive.infolist():
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise ValueError("Unsafe checkpoint member")
            if not item.is_dir():
                target = directory / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))


def run_job(
    client: Client, lease: dict[str, Any], worker_id: str, root: Path, models: dict[str, str]
) -> None:
    identifier, request = str(uuid.UUID(lease["jobId"])), lease["request"]
    directory = root / identifier
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    done, cancel = threading.Event(), threading.Event()

    def heartbeat() -> None:
        while not done.is_set():
            try:
                response = client.request(
                    f"/worker/jobs/{identifier}/heartbeat",
                    {"workerId": worker_id, "events": _events(directory)},
                )
                if response["cancelRequested"]:
                    cancel.set()
            except Exception:
                # Losing authentication/lease stops training rather than creating an orphan run.
                cancel.set()
            done.wait(15)

    pulse = threading.Thread(target=heartbeat, daemon=True)
    pulse.start()
    try:
        model = request.get("model")
        if model:
            details = model.get("details", {})
            location = models.get(model["id"]) or models.get(details.get("baseModelId", ""))
            if not location and model.get("repo"):
                from huggingface_hub import snapshot_download

                location = snapshot_download(
                    repo_id=model["repo"],
                    allow_patterns=[
                        "*.json",
                        "*.safetensors",
                        "*.model",
                        "*.txt",
                        "*.tiktoken",
                        "LICENSE*",
                    ],
                )
            private_model = directory / "input-model"
            if details.get("trainingJobId"):
                private_model.mkdir(exist_ok=True)
                content = client.request(
                    f"/worker/jobs/{identifier}/model?workerId={urllib.parse.quote(worker_id)}"
                )
                _restore(content, private_model)
                if model["backend"] == "chemprop":
                    location = str(private_model)
                elif model["backend"] == "reinvent":
                    candidate = next(iter(private_model.glob("trained.*")), None)
                    location = str(candidate) if candidate else None
            if not location:
                raise ValueError("Map the selected imported model with --model ID=/local/path")
            model["location"] = str(Path(location).resolve())
            if details.get("trainingJobId") and model["backend"] in {"mlx", "transformers"}:
                details.update(
                    {"baseLocation": model["location"], "adapterPath": str(private_model)}
                )
        output = directory / "output"
        output.mkdir(exist_ok=True)
        if lease.get("resumeAvailable"):
            content = client.request(
                f"/worker/jobs/{identifier}/checkpoint?workerId={urllib.parse.quote(worker_id)}"
            )
            _restore(content, output)
        if cancel.is_set():
            raise ValueError("Job cancelled while preparing assets")
        (directory / "request.json").write_text(json.dumps(request))
        (directory / "result.json").unlink(missing_ok=True)
        with (directory / "worker.log").open("wb") as log:
            process = subprocess.Popen(  # noqa: S603 — fixed private worker module
                [
                    sys.executable,
                    "-m",
                    "studio.domain.learning.workspace_runtime.worker",
                    str(directory),
                ],
                cwd=directory,
                env=_environment(directory),
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            started = time.monotonic()
            while process.poll() is None:
                if cancel.is_set() or time.monotonic() - started > request["config"].get(
                    "maxSeconds", 3600
                ):
                    _kill(process)
                    break
                done.wait(1)
        result_path = directory / "result.json"
        result = (
            json.loads(result_path.read_text())
            if result_path.exists()
            else {"ok": False, "error": "Worker cancelled or timed out; checkpoint retained"}
        )
    except Exception as exc:
        result = {"ok": False, "error": f"Worker failed ({type(exc).__name__}): {str(exc)[:200]}"}
    try:
        artifacts = _archive(directory / "output")
        client.upload(identifier, {"workerId": worker_id, "result": result}, artifacts)
        print(json.dumps({"jobId": identifier, "completed": bool(result.get("ok"))}), flush=True)
    finally:
        done.set()
        pulse.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--backends", default="transformers,chemprop")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("STUDIO_WORKER_TOKEN")
    if not token:
        parser.error("Set STUDIO_WORKER_TOKEN to an existing owner session token")
    client = Client(args.api, token)
    worker_id = "worker-" + uuid.uuid4().hex
    models = dict(item.split("=", 1) for item in args.model)
    args.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        while True:
            leased = client.request(
                "/worker/lease", {"workerId": worker_id, "backends": args.backends.split(",")}
            )
            if leased.get("jobId"):
                run_job(client, leased, worker_id, args.work_dir.resolve(), models)
            if args.once:
                return 0
            time.sleep(5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
