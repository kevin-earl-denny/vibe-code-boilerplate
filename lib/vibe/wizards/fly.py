"""Fly.io setup wizard."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import click

from lib.vibe.tools import require_interactive

try:
    import tomli
except ImportError:
    tomli = None  # type: ignore[assignment]

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]


def _detect_fly_command() -> str | None:
    """Detect whether to use 'fly' or 'flyctl' command."""
    for cmd in ["fly", "flyctl"]:
        if shutil.which(cmd):
            return cmd
    return None


def check_fly_cli() -> bool:
    """Check if Fly CLI is installed."""
    return _detect_fly_command() is not None


def check_fly_auth() -> bool:
    """Check if Fly CLI is authenticated."""
    fly_cmd = _detect_fly_command()
    if not fly_cmd:
        return False
    try:
        result = subprocess.run(
            [fly_cmd, "auth", "whoami"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_fly_user() -> str | None:
    """Get the authenticated Fly.io user."""
    fly_cmd = _detect_fly_command()
    if not fly_cmd:
        return None
    try:
        result = subprocess.run(
            [fly_cmd, "auth", "whoami"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def check_fly_toml() -> bool:
    """Check if fly.toml exists."""
    return Path("fly.toml").exists()


def get_app_name() -> str | None:
    """Get app name from fly.toml."""
    fly_toml = Path("fly.toml")
    if not fly_toml.exists():
        return None

    if tomli:
        try:
            content = fly_toml.read_text()
            data = tomli.loads(content)
            app_name: str | None = data.get("app")
            return app_name
        except (OSError, ValueError):
            pass

    # Fallback: simple parsing
    try:
        for line in fly_toml.read_text().split("\n"):
            if line.startswith("app ="):
                return line.split("=")[1].strip().strip("\"'")
    except OSError:
        pass
    return None


def run_fly_wizard(config: dict[str, Any]) -> bool:
    """
    Configure Fly.io deployment.

    Args:
        config: Configuration dict to update

    Returns:
        True if configuration was successful
    """
    # Check prerequisites
    ok, error = require_interactive("Fly.io")
    if not ok:
        click.echo(f"\n{error}")
        return False

    click.echo("\n--- Fly.io Deployment Configuration ---")
    click.echo()

    fly_cmd = _detect_fly_command()

    # Step 1: Check CLI installation
    click.echo("Step 1: Checking Fly CLI...")
    if not check_fly_cli():
        click.echo("  Fly CLI is not installed.")
        click.echo("  Install with:")
        click.echo("    macOS: brew install flyctl")
        click.echo("    Linux: curl -L https://fly.io/install.sh | sh")
        click.echo('    Windows: powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"')
        if not click.confirm("  Continue after installing manually?", default=False):
            return False
        fly_cmd = _detect_fly_command()
        if not fly_cmd:
            click.echo("  Fly CLI still not found. Please install and try again.")
            return False
    click.echo(f"  ✓ Fly CLI is installed ({fly_cmd})")

    # Step 2: Check authentication
    click.echo("\nStep 2: Checking authentication...")
    assert fly_cmd is not None  # Validated above
    if not check_fly_auth():
        click.echo("  Not authenticated with Fly.io.")
        if click.confirm("  Run 'fly auth login' now?", default=True):
            click.echo("  Opening browser for authentication...")
            result = subprocess.run([fly_cmd, "auth", "login"])
            if result.returncode != 0:
                click.echo("  Authentication failed. Run 'fly auth login' manually.")
                return False
            click.echo("  ✓ Authenticated")
        else:
            click.echo("  Authentication required. Run: fly auth login")
            return False
    else:
        user = get_fly_user()
        click.echo(f"  ✓ Authenticated as {user}")

    # Step 3: Check fly.toml
    click.echo("\nStep 3: Checking fly.toml...")
    if not check_fly_toml():
        click.echo("  fly.toml not found.")
        if click.confirm("  Run 'fly launch' to create app and config?", default=True):
            click.echo("  Launching Fly.io setup...")
            result = subprocess.run([fly_cmd, "launch"])
            if result.returncode != 0:
                click.echo("  Launch failed. Run 'fly launch' manually.")
                return False
            click.echo("  ✓ App created")
        else:
            click.echo("  fly.toml is required. Run: fly launch")
            return False
    else:
        app_name = get_app_name()
        click.echo(f"  ✓ fly.toml exists (app: {app_name or 'unknown'})")

    # Step 4: Check Dockerfile
    click.echo("\nStep 4: Checking Dockerfile...")
    dockerfile = Path("Dockerfile")
    if not dockerfile.exists():
        click.echo("  Dockerfile not found.")
        click.echo("  Fly.io can auto-detect some frameworks, but a Dockerfile is recommended.")
        click.echo("  See recipes/deployment/fly-io.md for examples.")
    else:
        click.echo("  ✓ Dockerfile exists")

    # Step 5: Update config
    click.echo("\nStep 5: Updating configuration...")

    app_name = get_app_name()

    # Ensure deployment config exists
    if "deployment" not in config:
        config["deployment"] = {}

    config["deployment"]["fly"] = {
        "enabled": True,
        "app_name": app_name,
    }

    # Add to secrets providers if not already present
    if "secrets" not in config:
        config["secrets"] = {"providers": []}
    if "fly" not in config["secrets"].get("providers", []):
        config["secrets"]["providers"] = config["secrets"].get("providers", []) + ["fly"]

    click.echo("  ✓ Configuration updated")

    # Summary
    click.echo("\n" + "=" * 50)
    click.echo("  Fly.io Configuration Complete!")
    click.echo("=" * 50)
    click.echo()
    click.echo("Your project is ready for Fly.io deployment.")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Deploy: fly deploy")
    click.echo("  2. Set secrets: fly secrets set KEY=value")
    click.echo("  3. View logs: fly logs")
    click.echo("  4. Check status: fly status")
    click.echo()
    if app_name:
        click.echo(f"Your app will be available at: https://{app_name}.fly.dev")
    click.echo()

    return True
