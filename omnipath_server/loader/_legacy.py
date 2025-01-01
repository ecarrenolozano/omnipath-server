from collections.abc import Generator
import csv
import json
import pathlib as pl

from pypath_common import _misc
from sqlalchemy.orm import decl_api

from .. import _connection
from ..schema import _legacy as _schema

__all__ = [
    'Loader',
    'TableLoader',
]


class Loader:

    _all_tables: list[str] = [
        'interactions',
        'enz_sub',
        'complexes',
        'intercell',
        'annotations',
    ]
    _fname = 'omnipath_webservice_%s.tsv.gz'


    def __init__(
            self,
            path: str | None = None,
            tables: dict[str, dict] | None = None,
            exclude: list[str] | None = None,
            con: _connection.Connection | dict | None = None,
    ):
        """
        Populate the legacy database from TSV files.

        Args:
            config:
                Configuration for loading the database for this service. Under
                "con_param" connection parameters can be provided, and
        """

        self.path = pl.Path(path or '.')
        self.tables = tables
        self.exclude = exclude
        self.con = con


    def create(self):
        """
        Create the tables defined in the legacy schema.
        """

        _schema.Base.metadata.create_all(self.con.engine)


    def load(self):
        """
        Load all tables from TSV files into Postgres.
        """

        for tbl in set(self._all_tables) - _misc.to_set(self.exclude):

            self._load_table(tbl)


    def _load_table(self, tbl: str):
        """
        Load one table from a TSV file into Postgres.

        Args:
            tbl:
                Name of the table to load.
        """

        param = self.tables.get(tbl, {})
        path = self.path / param.get('path', self._fname % tbl)

        if not path.exists():

            return

        schema = getattr(_schema, tbl.capitalize())

        TableLoader(path, schema, self.con).load()


class TableLoader:

    def __init__(
            self,
            path: str,
            table: decl_api.DeclarativeMeta,
            con: _connection.Connection,
    ):
        """
        Load data from a TSV file into a Postgres table.

        Args:
            path:
                Path to a TSV file with the data to be loaded.
            table:
                The SQLAlchemy table where we load the data.
        """

        self.path = path
        self.table = table
        self.con = con


    def load(self) -> None:
        """
        Load data from the TSV file into the table.
        """

        cols = [col.name for col in self.table.columns]
        query = f'INSERT INTO {self.table.name} ({', '.join(cols)}) VALUES %s'

        self.con.execute_values(query, self._read())


    def _read(self) -> Generator[tuple, None, None]:
        """
        Read TSV and process fields according to their types.
        """

        with open(self.path) as fp:

            reader = csv.DictReader(fp, delimiter = '\t')

            for row in reader:

                for col, typ in self.table.columns.items():

                    if typ.type.python_type is dict:  # JSONB

                        row[col] = json.loads(row[col]) if row[col] else None

                    elif typ.type.python_type is list:  # Array

                        row[col] = row[col].split(';') if row[col] else []

                    elif typ.type.python_type is bool:  # Boolean

                        row[col] = row[col].lower() in ('true', '1', 'yes')

                    elif typ.type.python_type in (int, float):  # Numeric

                        row[col] = typ.type.python_type(row[col]) if row[col] else None

                yield tuple(row[column.name] for column in self.table.columns)
