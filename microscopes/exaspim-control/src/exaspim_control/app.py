"""
CLI Application for exaspim control and testing.
"""

import click


@click.group()
def cli() -> None:
    """
    CLI for controlling and testing ExASPIM.
    """
    pass


@cli.command()
@click.argument("config_path", type=click.Path(exists=True), required=True)
def launch(config_path: str) -> None:
    """
    Launch the ExASPIM application.

    :param config_path: Path to the configuration file
    :type config_path: str
    :param simulated: Flag to launch the simulated ExASPIM application
    :type simulated: bool
    """
    click.echo(f"Exaspim config path: {config_path}")
    click.echo("Not yet implemented.")


if __name__ == "__main__":
    cli()
