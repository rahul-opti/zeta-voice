#!/usr/bin/env python3
"""Simple script for creating blob containers using AzureBlobStorage."""

import typer

from carriage_services.utils.recordings_storage import AzureBlobStorage


def main(
    container_name: str,
    set_public_access: bool = typer.Option(
        False, "--public", "-p", help="Set container access level to 'blob' (public read access)"
    ),
) -> None:
    """Create a blob container and optionally set public access.

    Args:
        container_name: Name of the container to create
        set_public_access: Whether to set public access level to 'blob'
    """
    try:
        storage = AzureBlobStorage()
        success = storage.create_container(container_name, public_access=set_public_access)

        if success:
            typer.echo(f"✓ Container '{container_name}' created successfully")
            if set_public_access:
                typer.echo("  (Check logs for public access status)")
        else:
            typer.echo(f"✗ Failed to create container '{container_name}'")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"✗ Error: {e}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    typer.run(main)
