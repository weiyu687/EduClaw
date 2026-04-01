"""
设置启动卡片

Author: Gongmin Wei
Date: 2026-03-31
"""
import os
import sys
import platform
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


ui_console = Console(stderr=True)

# EduClaw
BANNER = """
[bold white] ______  _____   _    _ [/bold white][bold blue]  _____  _           _ _          __[/bold blue]
[bold white]|  ____||  __ \ | |  | |[/bold white][bold blue] / ____|| |         / \ \        / /[/bold blue]
[bold white]| |__   | |  | || |  | |[/bold white][bold blue]| |     | |        / _ \ \  /\  / / [/bold blue]
[bold white]|  __|  | |  | || |  | |[/bold white][bold blue]| |     | |       / ___ \ \/  \/ /  [/bold blue]
[bold white]| |____ | |__| || |__| |[/bold white][bold blue]| |____ | |____  / /   \ \  /\  /   [/bold blue]
[bold white]|______||_____/  \____/ [/bold white][bold blue] \_____||______|/_/     \_\/  \/    [/bold blue]

[dim white]:: EduClaw Framework :: (v0.1.0)[/dim white]
"""

def print_startup_info():
    """打印启动卡片"""
    ui_console.print(BANNER)

    table = Table(show_header=False, border_style="dim white", box=None)
    table.add_column("Key", style="dim white", width=15)
    table.add_column("Value", style="white")

    table.add_row("OS Platform", f"{platform.system()} {platform.release()}")
    table.add_row("Python Ver", sys.version.split()[0])
    table.add_row("Working Dir", os.getcwd())
    table.add_row("Log File", "logs\educlaw.log")
    table.add_row("MCP Status", "[bold green]READY[/bold green]")

    ui_console.print(Panel(
        table,
        title="[bold white]System Context[/bold white]",
        border_style="blue",
        expand=False,
        padding=(1, 2)
    ))