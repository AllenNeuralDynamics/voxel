from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from voicecoil import VoiceCoilDevice

PORT = 'COM3'

console = Console()


def print_help():
    table = Table(title='VoiceCoil REPL Commands', box=box.ROUNDED)
    table.add_column('Command', style='cyan', no_wrap=True)
    table.add_column('Description', style='magenta')
    table.add_row('info', 'Get device info')
    table.add_row('enable', 'Enable the device')
    table.add_row('disable', 'Disable the device')
    table.add_row('test', 'Send TEST command')
    table.add_row('send <raw>', 'Send a raw command string (e.g. N, k1, d0)')
    table.add_row('help', 'Show this help message')
    table.add_row('exit', 'Exit the REPL')
    console.print(table)


def main():  # noqa: PLR0912
    device = VoiceCoilDevice(port=PORT)
    console.print(Panel('[bold green]VoiceCoil Device Interactive REPL[/bold green]', expand=False))
    print_help()
    try:
        while True:
            cmd = Prompt.ask('[bold blue]voicecoil>[/bold blue]').strip()
            if not cmd:
                continue
            if cmd.lower() in ('exit', 'quit'):
                console.print('[yellow]Exiting...[/yellow]')
                break
            if cmd.lower() == 'help':
                print_help()
            elif cmd.lower() == 'info':
                resp = device.get_info()
                console.print(f'[green]INFO:[/green] {resp}')
            elif cmd.lower() == 'enable':
                resp = device.enable()
                console.print(f'[green]ENABLED:[/green] {resp}')
            elif cmd.lower() == 'disable':
                resp = device.disable()
                console.print(f'[red]DISABLED:[/red] {resp}')
            elif cmd.lower() == 'test':
                resp = device.test()
                console.print(f'[cyan]TEST:[/cyan] {resp}')
            elif cmd.lower().startswith('send '):
                raw = cmd[5:].strip()
                if raw:
                    resp = device._send_bytes(raw.encode('ascii') + b'\r')  # noqa: SLF001
                    console.print(f'[blue]RESPONSE:[/blue] {resp}')
                else:
                    console.print('[red]Usage: send <raw_command>[/red]')
            else:
                console.print(f'[red]Unknown command:[/red] {cmd}')
    except KeyboardInterrupt:
        console.print('\n[yellow]Interrupted by user.[/yellow]')
    finally:
        device.close()
        console.print('[green]Device connection closed.[/green]')


if __name__ == '__main__':
    main()
