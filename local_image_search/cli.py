from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from local_image_search.db import Database
from local_image_search.indexer import index_paths


app = typer.Typer(no_args_is_help=True)
console = Console()


DbOption = Annotated[
    Path,
    typer.Option(
        "--db",
        help="Path to the SQLite metadata database.",
    ),
]


@app.command()
def index(
    paths: Annotated[list[Path], typer.Argument(help="Image file or folder paths to index.")],
    db: DbOption = Path("./data/index.sqlite"),
    thumbs: Annotated[
        Path,
        typer.Option("--thumbs", help="Directory where thumbnails are stored."),
    ] = Path("./data/thumbs"),
) -> None:
    """Index image metadata and thumbnails."""
    if not paths:
        raise typer.BadParameter("At least one path is required.")

    missing = [path for path in paths if not path.expanduser().exists()]
    if missing:
        raise typer.BadParameter(f"Path does not exist: {missing[0]}")

    summary = index_paths(paths, db, thumbs)
    table = Table(title="Index Summary")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("Scanned", str(summary.scanned))
    table.add_row("Indexed", str(summary.indexed))
    table.add_row("Skipped", str(summary.skipped))
    table.add_row("Errors", str(summary.errors))
    table.add_row("Marked missing", str(summary.missing_marked))
    console.print(table)


@app.command()
def stats(db: DbOption = Path("./data/index.sqlite")) -> None:
    """Print index statistics."""
    with Database(db) as database:
        stats_ = database.stats()

    table = Table(title="Index Stats")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key in ("total", "active", "missing", "error", "folders"):
        table.add_row(key.replace("_", " ").title(), str(stats_.get(key, 0)))
    console.print(table)


@app.command()
def verify(db: DbOption = Path("./data/index.sqlite")) -> None:
    """Verify active files and thumbnails still exist."""
    with Database(db) as database:
        result = database.verify()

    table = Table(title="Verify Index")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key, value in result.items():
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)


@app.command()
def serve(
    db: DbOption = Path("./data/index.sqlite"),
    host: Annotated[
        str,
        typer.Option("--host", help="Host address to bind."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Port to bind."),
    ] = 8000,
) -> None:
    """Run the local API server."""
    import uvicorn

    from local_image_search.api import create_app

    uvicorn.run(create_app(db), host=host, port=port)


if __name__ == "__main__":
    app()
