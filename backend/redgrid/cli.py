"""Command-line tools:
  flask --app redgrid init-db          create the database (schema + RedGrid seed)
  flask --app redgrid load-data        check prepared files against the contract and load them
  flask --app redgrid check-data       only check, load nothing
  flask --app redgrid make-demo-data   write SYNTHETIC prepared data (labelled DEMONSTRATION_DATA) and load it
"""
from __future__ import annotations

import click

from . import db


def register(app):
    @app.cli.command("init-db")
    def init_db_cmd():
        db.init_db(app.config["DATABASE"])
        click.echo(f"Database created: {app.config['DATABASE']}")

    @app.cli.command("check-data")
    def check_data_cmd():
        from .loader import check_prepared
        problems = check_prepared(app.config["DATA_DIR"])
        if problems:
            for p in problems:
                click.echo(f"  - {p}")
            raise SystemExit(1)
        click.echo("Prepared data meets the contract.")

    @app.cli.command("load-data")
    def load_data_cmd():
        from .loader import load_prepared
        with app.app_context():
            report = load_prepared(app.config["DATA_DIR"])
        for line in report:
            click.echo(line)

    @app.cli.command("make-demo-data")
    @click.option("--seed", default=7, help="Random seed for the synthetic terrain")
    def make_demo_cmd(seed):
        from .demo_data import make_demo
        from .loader import load_prepared
        make_demo(app.config["DATA_DIR"], seed=seed)
        with app.app_context():
            for line in load_prepared(app.config["DATA_DIR"], demonstration=True):
                click.echo(line)
        click.echo("Synthetic demonstration data loaded (every layer is labelled DEMONSTRATION_DATA).")
