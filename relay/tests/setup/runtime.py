"""Container runtime bootstrap for the `pg` test layer.

Rootless podman does not populate DOCKER_HOST or run a ryuk-compatible reaper the way a
Docker daemon does. This makes testcontainers work against it with no per-developer shell
setup, and fails loudly with the exact fix command when no runtime is reachable at all -- a
test layer that needs containers must never silently skip for their absence.

Ryuk being disabled here is not a degraded version of cleanup -- it is none. A process that
exits normally already tears its own containers down via its fixtures' own context managers,
Ryuk or not; without it, a *killed* run's containers simply sit there, indistinguishable from
a legitimately long-running stack by age alone -- `owner_labels`/`sweep_orphaned_containers`
identify them by whether the specific process that started them is still alive instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PODMAN_SOCKET_ENV = "XDG_RUNTIME_DIR"

#: Every container this project's test tooling starts carries these, via
#: `DockerContainer.with_kwargs(labels=owner_labels())`.
LABEL_ROLE = "lios-relay.role"
LABEL_OWNER_PID = "lios-relay.owner-pid"
LABEL_OWNER_FINGERPRINT = "lios-relay.owner-fingerprint"
ROLE_TEST = "test"

_DOCKER_DEFAULT_SOCKET = Path("/var/run/docker.sock")


class ContainerRuntimeError(Exception):
    """Raised when no usable container runtime is found."""


def bootstrap_container_runtime() -> None:
    """Ensure a container runtime is reachable before any testcontainers fixture starts,
    then sweep whatever a previous, now-dead process left behind.

    Three cases, in order: `DOCKER_HOST` already set (an explicit setting always wins) --
    the standard Docker socket exists (a real daemon, or a DinD CI runner; testcontainers
    finds it unaided) -- neither, so probe the rootless podman socket location and point
    testcontainers at it explicitly, since podman does not populate `DOCKER_HOST` itself.

    Raises:
        ContainerRuntimeError: none of the three apply.
    """
    if os.environ.get("DOCKER_HOST"):
        _sweep_and_report()
        return

    if _DOCKER_DEFAULT_SOCKET.exists():
        _sweep_and_report()
        return

    runtime_dir = os.environ.get(_PODMAN_SOCKET_ENV)
    if runtime_dir:
        socket_path = Path(runtime_dir) / "podman" / "podman.sock"
        if socket_path.exists():
            os.environ["DOCKER_HOST"] = f"unix://{socket_path}"
            os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
            _sweep_and_report()
            return

    raise ContainerRuntimeError(
        "No container runtime found. This test layer requires one -- set DOCKER_HOST "
        "explicitly, or enable the rootless podman socket:\n\n"
        "    systemctl --user enable --now podman.socket\n"
    )


def _sweep_and_report() -> None:
    removed = sweep_orphaned_containers()
    if removed:
        print(
            f"Removed {len(removed)} container(s) orphaned by a dead process: "
            f"{', '.join(removed)}",
            file=sys.stderr,
        )


def process_fingerprint(pid: int) -> str | None:
    """A cheap fingerprint for whichever process currently holds `pid`.

    `/proc/<pid>`'s own ctime marks when the kernel allocated that PID to the process
    presently holding it -- a later, unrelated process the OS hands the same PID to gets a
    different one, so a fingerprint recorded at container-creation time that no longer
    matches means the original owner is provably gone. None if nothing holds `pid` right now.
    """
    try:
        return str(os.stat(f"/proc/{pid}").st_ctime)
    except (FileNotFoundError, ProcessLookupError, NotADirectoryError, PermissionError):
        return None


def owner_labels() -> dict[str, str]:
    """Labels every container this process starts should carry, keyed on this process's own
    fingerprint -- whether the process that requested a container is still alive is the only
    question `sweep_orphaned_containers` asks; age alone cannot distinguish an orphan from a
    legitimately long-running stack."""
    pid = os.getpid()
    fingerprint = process_fingerprint(pid)
    assert fingerprint is not None, "a live process always has a /proc entry for its own pid"
    return {
        LABEL_ROLE: ROLE_TEST,
        LABEL_OWNER_PID: str(pid),
        LABEL_OWNER_FINGERPRINT: fingerprint,
    }


def sweep_orphaned_containers() -> list[str]:
    """Remove every container carrying this project's test-role label whose owning process
    is confirmed dead, and return the names of whatever was removed.

    "Confirmed dead" means `process_fingerprint(owner_pid)` no longer matches what was
    recorded at creation time -- never an age threshold. A container whose owner labels are
    missing or unparseable is left alone rather than guessed at.
    """
    import docker
    from docker.errors import NotFound

    client = docker.from_env()
    removed = []
    containers = client.containers.list(all=True, filters={"label": f"{LABEL_ROLE}={ROLE_TEST}"})
    for container in containers:
        owner_pid = container.labels.get(LABEL_OWNER_PID)
        owner_fingerprint = container.labels.get(LABEL_OWNER_FINGERPRINT)
        if owner_pid is None or owner_fingerprint is None:
            continue
        try:
            pid = int(owner_pid)
        except ValueError:
            continue
        if process_fingerprint(pid) == owner_fingerprint:
            continue  # the process that started this container is still alive

        name = container.name
        try:
            container.remove(force=True)
        except NotFound:
            continue
        removed.append(name)
    return removed
