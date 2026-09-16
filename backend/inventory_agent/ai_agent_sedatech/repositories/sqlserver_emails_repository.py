from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import pymssql

logger = logging.getLogger(__name__)



class SqlServerEmailsRepository:
    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        database: str,
        tds_version: str = "7.0",
        port: str = "1433",
        login_timeout_seconds: int = 10,
        query_timeout_seconds: int = 30,
    ) -> None:
        self.server = server
        self.user = user
        self.password = password
        self.database = database
        self.tds_version = tds_version
        self.port = port
        self.login_timeout_seconds = login_timeout_seconds
        self.query_timeout_seconds = query_timeout_seconds

    def _connect(self) -> pymssql.Connection:
        return pymssql.connect(
            server=self.server,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            tds_version=self.tds_version,
            charset="UTF-8",
            as_dict=True,
            appname="SedatechAIAgent",
            autocommit=True,
            login_timeout=self.login_timeout_seconds,
            timeout=self.query_timeout_seconds,
        )

    def get_emails(
        self,
        platform: Literal["sedatech"] = "sedatech",
        date_from: date | str | None = None,
        date_to: date | str | None = None,
    ) -> list[str]:
        if platform != "sedatech":
            raise ValueError("Only the sedatech platform is supported")
        if isinstance(date_from, str):
            date_from = date.fromisoformat(date_from)
        if isinstance(date_to, str):
            date_to = date.fromisoformat(date_to)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be on or before date_to")

        query = """
        SELECT _EMAIL1 as Email
        FROM BELEG
        WHERE Belegtyp = 'R'
        AND _EMAIL1 IS NOT NULL
        AND Vertreter = 8
"""
        parameters: list[date] = []
        if date_from is not None:
            query += " AND Datum >= %s"
            parameters.append(date_from)
        if date_to is not None:
            query += " AND Datum < DATEADD(day, 1, %s)"
            parameters.append(date_to)
        connection = None
        cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, tuple(parameters))
            main_row = cursor.fetchall()
        except pymssql.Error as exc:
            logger.exception("Customer email search failed")
            raise RuntimeError(
                f"DATABASE_QUERY_ERROR: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
        result = []
        for row in main_row:
            result.append(row["Email"])
        return result
