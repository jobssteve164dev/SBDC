import json
import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_IMAGE_DIR = PROJECT_ROOT / "infrastructure/docker/runtime-images"
EXPECTED_RUNTIME_WRAPPERS = {
    "grobid": ("grobid.Dockerfile", "grobid/grobid:0.9.0-crf"),
    "minio": ("minio.Dockerfile", "minio/minio:RELEASE.2025-04-22T22-12-26Z"),
    "postgres": ("postgres.Dockerfile", "postgres:16.9-alpine"),
    "redis": ("redis.Dockerfile", "redis:7.4.4-alpine"),
}


def _rendered_services() -> dict[str, dict[str, object]]:
    result = subprocess.run(
        ["docker", "compose", "config", "--no-interpolate", "--format", "json"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["services"]


def test_all_runtime_services_are_build_selectable_for_whole_project_release() -> None:
    services = _rendered_services()

    unbundled = sorted(
        service_name
        for service_name, service in services.items()
        if service.get("build") is None
    )

    assert unbundled == [], (
        "GitOps whole-project selection omits services without build definitions: "
        f"{unbundled}"
    )


def test_all_runtime_services_target_deployment_node_architecture() -> None:
    services = _rendered_services()

    wrong_platform = sorted(
        service_name
        for service_name, service in services.items()
        if service.get("platform") != "linux/amd64"
    )

    assert wrong_platform == [], (
        "Release images must target the amd64 deployment node explicitly: "
        f"{wrong_platform}"
    )


def test_runtime_image_wrappers_are_local_and_digest_pinned() -> None:
    services = _rendered_services()

    for service_name, (dockerfile_name, upstream_image) in EXPECTED_RUNTIME_WRAPPERS.items():
        build = services[service_name]["build"]
        context = Path(build["context"]).resolve()
        assert context == RUNTIME_IMAGE_DIR.resolve()

        dockerfile = (context / build["dockerfile"]).resolve()
        assert dockerfile == (RUNTIME_IMAGE_DIR / dockerfile_name).resolve()
        assert dockerfile.is_file()

        instructions = [
            line.strip()
            for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        assert len(instructions) == 1
        assert re.fullmatch(
            rf"FROM {re.escape(upstream_image)}@sha256:[0-9a-f]{{64}}",
            instructions[0],
        )
