import json
import re
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "compose.yaml"
RUNTIME_IMAGE_DIR = PROJECT_ROOT / "infrastructure/docker/runtime-images"
EXPECTED_RUNTIME_WRAPPERS = {
    "grobid": ("grobid.Dockerfile", "grobid/grobid:0.9.0-crf"),
    "minio": ("minio.Dockerfile", "minio/minio:RELEASE.2025-04-22T22-12-26Z"),
    "redis": ("redis.Dockerfile", "redis:7.4.4-alpine"),
}
WEB_DOCKERFILE = PROJECT_ROOT / "apps/web/Dockerfile"


def _rendered_services() -> dict[str, dict[str, object]]:
    result = subprocess.run(
        ["docker", "compose", "config", "--no-interpolate", "--format", "json"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["services"]


def _rendered_local_services() -> dict[str, dict[str, object]]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "compose.local.yaml",
            "config",
            "--no-interpolate",
            "--format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["services"]


def test_production_release_excludes_the_local_postgres_service() -> None:
    assert "postgres" not in _rendered_services()


def test_production_database_migration_uses_the_attached_api_service() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    assert compose["x-gitops"]["database_migration"] == {
        "service": "api",
        "command": ["/usr/local/bin/alembic", "upgrade", "head"],
    }
    assert "migrate" not in compose["services"]
    assert "migrate" not in compose["services"]["api"].get("depends_on", {})
    assert "migrate" not in compose["services"]["worker"].get("depends_on", {})


def test_local_compose_restores_postgres_and_orders_schema_migration_after_it() -> None:
    services = _rendered_local_services()

    assert services["postgres"]["image"] == "sbdc-postgres:16.9-alpine"
    assert Path(services["postgres"]["build"]["context"]).resolve() == RUNTIME_IMAGE_DIR.resolve()
    assert services["postgres"]["build"]["dockerfile"] == "postgres.Dockerfile"
    assert {
        "type": "volume",
        "source": "postgres_data",
        "target": "/var/lib/postgresql/data",
        "volume": {},
    } in services["postgres"]["volumes"]
    assert services["migrate"]["depends_on"]["postgres"]["condition"] == "service_healthy"


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


def test_web_build_runs_on_runner_architecture_and_emits_target_architecture() -> None:
    instructions = [
        line.strip()
        for line in WEB_DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert instructions[0] == "FROM --platform=$BUILDPLATFORM node:22-alpine AS deps"
    assert "FROM --platform=$BUILDPLATFORM node:22-alpine AS runtime-deps" in instructions
    assert "ARG TARGETARCH" in instructions
    assert "amd64) npm_cpu=x64 ;; \\" in instructions
    assert "arm64) npm_cpu=arm64 ;; \\" in instructions
    assert (
        'npm ci --omit=dev --ignore-scripts --os=linux --cpu="$npm_cpu" --libc=musl'
        in instructions
    )
    assert "FROM --platform=$BUILDPLATFORM node:22-alpine AS builder" in instructions
    assert "FROM --platform=$TARGETPLATFORM node:22-alpine AS runner" in instructions
    assert "COPY --from=runtime-deps /app/node_modules ./node_modules" in instructions
    assert instructions.index(
        "COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./"
    ) < instructions.index("COPY --from=runtime-deps /app/node_modules ./node_modules")


def test_public_web_port_is_configurable_with_the_audited_unique_default() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert '127.0.0.1:${SBDC_WEB_PORT:-3100}:3000' in compose


def test_web_runtime_provides_the_healthcheck_client_used_by_compose() -> None:
    dockerfile = WEB_DOCKERFILE.read_text(encoding="utf-8")

    assert "RUN apk add --no-cache wget" in dockerfile
    assert dockerfile.index("RUN apk add --no-cache wget") < dockerfile.index("USER nextjs")
