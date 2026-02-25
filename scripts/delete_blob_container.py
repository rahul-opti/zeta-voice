#!/usr/bin/env python3
"""Simple script for deleting blob containers using AzureBlobStorage."""

import typer

from carriage_services.utils.recordings_storage import AzureBlobStorage


def main(
    container_name: str, force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt")
) -> None:
    """Delete a blob container.

    Args:
        container_name: Name of the container to delete
        force: Skip confirmation prompt
    """
    if not force:
        confirmed = typer.confirm(f"Are you sure you want to delete container '{container_name}'?")
        if not confirmed:
            typer.echo("Operation cancelled")
            raise typer.Exit()

    try:
        storage = AzureBlobStorage()
        success = storage.delete_container(container_name)

        if success:
            typer.echo(f"✓ Container '{container_name}' deleted successfully")
        else:
            typer.echo(f"✗ Container '{container_name}' does not exist or could not be deleted")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"✗ Error: {e}")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    typer.run(main)
