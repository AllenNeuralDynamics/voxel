"""
CLI Application for exaspim control and testing.
"""

import click


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--simulated", "-s", is_flag=True, help="Launch the simulated ExASPIM application.")
def cli(ctx: click.Context, simulated: bool) -> None:
    """
    CLI for controlling and testing ExASPIM.

    :param ctx: Click context
    :type ctx: click.Context
    :param simulated: Flag to launch the simulated ExASPIM application
    :type simulated: bool
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(launch, simulated=simulated)


@cli.command()
@click.argument("config_path", type=click.Path(exists=True), required=False)
@click.option("--simulated", "-s", is_flag=True, help="Launch the simulated ExASPIM application.")
def launch(config_path: str, simulated: bool) -> None:
    """
    Launch the ExASPIM application.

    :param config_path: Path to the configuration file
    :type config_path: str
    :param simulated: Flag to launch the simulated ExASPIM application
    :type simulated: bool
    """

    def launch_simulated() -> None:
        """
        Launch the simulated ExASPIM application.
        """
        from exaspim_control.simulated.main import launch_simulated_exaspim

        launch_simulated_exaspim()

    if simulated:
        launch_simulated()
    else:
        click.echo(f"Exaspim config path: {config_path}")
        click.echo("Not yet implemented.")
        click.echo("Launching simulated ExASPIM instead.")
        launch_simulated()


if __name__ == "__main__":
    cli()
