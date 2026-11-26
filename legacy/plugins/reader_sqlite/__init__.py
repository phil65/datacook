from __future__ import annotations

import contextlib
import logging
import sqlite3

import pandas as pd

from processanalyzer.constants import iconnames
from processanalyzer.core import dataset
from processanalyzer.plugintypes import filereaderplugin

logger = logging.getLogger(__name__)


class SQLiteReader(filereaderplugin.FileReaderPlugin):
    menu_label = "SqLite database"
    extensions = {"SqLite files": [".sqlite", ".db"]}
    plugin_id = "reader.sqlite"
    icon = iconnames.DATASET

    def read_file(self, path):
        with contextlib.closing(sqlite3.connect(str(path))) as db:
            with db:
                cursor = db.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                for i, table_name in enumerate(tables):
                    table_name = table_name[0]
                    df = pd.concat([df for df in self._yield_chunks(table_name, db)])
                    ds = dataset.DataSet(data=df, name=table_name)
                    keyword_args = dict(sql=f"SELECT * from {table_name}")
                    ds.log(
                        "with contextlib.closing(sqlite3.connect(|ORIGIN|)) as db:",
                        "    with db:",
                        "        |ds| = pandas.read_sql_query(|KWARGS|, con=db)",
                        imports=["contextlib", "sqlite3", "pandas"],
                        operation="import",
                        description="Import from SQLite",
                        origin=path,
                        kwargs=keyword_args,
                    )
                    yield ds

    def _yield_chunks(self, table_name, db):
        """
        Read an SQLite database table
        """
        chunk_gen = pd.read_sql_query(
            f"SELECT * from {table_name}", db, chunksize=1_000_000
        )
        numlines = 0
        for rows in chunk_gen:
            numlines += len(rows)
            logger.info(f"imported {numlines} rows...")
            yield rows
