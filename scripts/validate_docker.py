"""Build and validate an isolated synthetic Docker stack; never use local .env."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import uuid

from validate_recovery import validate_recovery


ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-image', type=Path,
                        help='Save the validated runtime image and its .id file for publication.')
    args = parser.parse_args(argv)
    project = "muv-check-" + uuid.uuid4().hex[:12]
    test_image = project + ":test"
    # Do not inherit operational Compose/database configuration.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("COMPOSE_", "DB_", "MUV_"))}
    env.update(DB_HOST="postgres", DB_PORT="5432", DB_NAME="muv_synthetic",
               DB_USER="muv_synthetic", DB_PASSWORD=secrets.token_hex(24),
               MUV_BANK_ACCOUNT_ID="TEST_BANK_ACCOUNT_001")

    def run(args, **kwargs):
        kwargs.setdefault('check', True)
        return subprocess.run(args, cwd=ROOT, env=env, timeout=900, **kwargs)

    run(["docker", "info"], stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix="muv-docker-check-") as directory:
        temporary = Path(directory)
        empty_env = temporary / "empty.env"
        empty_env.write_text("")
        override = temporary / "compose.yaml"
        # No host ports: safe alongside a developer's existing app on port 8501.
        override.write_text("services:\n  app:\n    ports: !reset []\n")
        compose = ["docker", "compose", "--env-file", str(empty_env), "-p", project,
                   "-f", str(ROOT / "compose.yaml"), "-f", str(override)]
        try:
            run(compose + ["config", "--quiet"])
            run(["docker", "build", "--target", "test", "-t", test_image, "."])
            run(["docker", "run", "--rm", "--name", project + "-tests",
                 "--network", "none", test_image])
            run(compose + ["build"])
            run(compose + ["up", "-d", "--wait", "--wait-timeout", "180"])
            app = compose + ["exec", "-T", "app"]
            run(app + ["python", "-m", "container_runtime", "health"])
            run(app + ["python", "-c",
                "from pathlib import Path; import os; "
                "assert os.environ['MUV_BANK_ACCOUNT_ID'] == 'TEST_BANK_ACCOUNT_001'; "
                "Path('/data/synthetic-marker').write_text('synthetic-only')"])
            sql = compose + ["exec", "-T", "postgres", "psql", "-U", "muv_synthetic",
                             "-d", "muv_synthetic", "-v", "ON_ERROR_STOP=1"]
            run(sql + ["-c", "CREATE TABLE synthetic_probe (value text); "
                       "INSERT INTO synthetic_probe VALUES ('synthetic-only');"])
            run(compose + ["up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180"])
            run(app + ["python", "-m", "container_runtime", "health"])
            run(app + ["python", "-c", "from pathlib import Path; "
                       "assert Path('/data/synthetic-marker').read_text() == 'synthetic-only'"])
            result = run(sql + ["-Atc", "SELECT value FROM synthetic_probe"],
                         capture_output=True, text=True)
            if result.stdout.strip() != "synthetic-only":
                raise RuntimeError("Synthetic database persistence check failed.")
            validate_recovery(run=run, compose=compose, project=project,
                              temporary=temporary, root=ROOT, env_file=empty_env)
            if args.export_image:
                target = args.export_image.resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                image = project + '-app:latest'
                run(['docker', 'image', 'save', '--output', str(target), image])
                image_id = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image],
                               capture_output=True, text=True).stdout.strip()
                target.with_suffix(target.suffix + '.id').write_text(image_id + '\n')
                # Verify the archive can be loaded before handing it to publication.
                run(['docker', 'image', 'load', '--input', str(target)], stdout=subprocess.DEVNULL)
            print("PASS: container tests, app/DB health, account config, persistence and recovery.", flush=True)
        finally:
            # Only this invocation's randomly named synthetic resources are removed.
            subprocess.run(["docker", "rm", "-f", project + "-tests"], env=env,
                           check=False, timeout=60, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            run(compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"])
            subprocess.run(["docker", "image", "rm", test_image], cwd=ROOT, env=env,
                           check=False, timeout=60, stdout=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
