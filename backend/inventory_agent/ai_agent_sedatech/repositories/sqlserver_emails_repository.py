from __future__ import annotations

import logging
import os
from datetime import date
from typing import Literal, TypedDict
from urllib.parse import quote

import pymssql
import requests

logger = logging.getLogger(__name__)


class CustomerEmail(TypedDict):
    email: str
    customer_service: bool


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
        tickets_api_url: str | None = None,
    ) -> None:
        self.server = server
        self.user = user
        self.password = password
        self.database = database
        self.tds_version = tds_version
        self.port = port
        self.login_timeout_seconds = login_timeout_seconds
        self.query_timeout_seconds = query_timeout_seconds
        self.tickets_api_url = (
            tickets_api_url
            or os.getenv("BACKEND_TICKETS_URL", "http://localhost:8000/tickets")
        ).rstrip("/")

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
    ) -> list[CustomerEmail]:
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
        WHERE Belegtyp = 'R' AND PLZ != '10997' AND Vertrag NOT IN (-1) AND Lager = 100 AND Netto != 0
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
        result: list[CustomerEmail] = []
        if not main_row:
            return result
        with requests.Session() as session:
            for row in main_row:
                email = row["Email"]
                try:
                    response = session.get(
                        f"{self.tickets_api_url}/emails/{quote(email, safe='')}",
                        timeout=(5, 30),
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                        raise ValueError("Expected a data list from the tickets endpoint")
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else response.status_code
                    hint = (
                        " Verify BACKEND_TICKETS_URL and rebuild the backend so the email endpoint is available."
                        if status == 404 else ""
                    )
                    raise RuntimeError(
                        f"TICKET_LOOKUP_ERROR: Tickets endpoint returned HTTP {status}.{hint}"
                    ) from exc
                except requests.Timeout as exc:
                    raise RuntimeError("TICKET_LOOKUP_ERROR: Tickets endpoint timed out.") from exc
                except requests.RequestException as exc:
                    raise RuntimeError(
                        "TICKET_LOOKUP_ERROR: Could not connect to the tickets endpoint. "
                        "Verify BACKEND_TICKETS_URL and that the backend is running."
                    ) from exc
                except ValueError as exc:
                    raise RuntimeError(
                        "TICKET_LOOKUP_ERROR: Tickets endpoint must return JSON with a data list."
                    ) from exc
                result.append({"email": email, "customer_service": bool(payload["data"])})
        return result
