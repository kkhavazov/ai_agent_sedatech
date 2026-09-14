from __future__ import annotations

import os
import re

import pymssql

from models.item import MissingComponent, MissingComponentEntry
from repositories.missing_repository import MissingRepository



from collections import defaultdict

def get_group(item_id: str) -> str:
  # Extracts the alphabetical prefix (e.g., 'ME' from 'ME0001')
  match = re.match(r"^([A-Za-z]+)", item_id)
  return match.group(1) if match else item_id

def compare_dict_lists(
    list_1: list[dict],
    list_2: list[dict],
    id_key: str = "ID",
    count_key: str = "count",
) -> list[MissingComponentEntry]:
    dict_1 = defaultdict(int)
    dict_2 = defaultdict(int)
    original_ids = {}  # Keeps track of an original ID for each group

    # Aggregate list 1 and store a representative original ID
    for item in list_1:
        orig_id = item[id_key]
        group = get_group(orig_id)
        dict_1[group] += item[count_key]
        if group not in original_ids:
            original_ids[group] = orig_id

    # Aggregate list 2 and store a representative original ID if not already tracked
    for item in list_2:
        orig_id = item[id_key]
        group = get_group(orig_id)
        dict_2[group] += item[count_key]
        if group not in original_ids:
            original_ids[group] = orig_id

    result: list[MissingComponentEntry] = []
    #all_groups = set(dict_1.keys()).union(set(dict_2.keys()))

    # Compare counts for every unique group
    for group, c2 in dict_2.items():
        c1 = dict_1[group]  # Gibt 0 zurück, wenn die Gruppe in list_1 nicht existiert

        # Nur Elemente aufnehmen, die in list_2 mehr/neu vorhanden sind
        if c2 > c1:
            diff = c2 - c1
            rep_id = original_ids[group]
            result.append({id_key: rep_id, count_key: diff})

    return result

class SqlServerMissingRepository(MissingRepository):
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

    def find_missing_components(
        self,
        order_number: str,
    ) -> MissingComponent | None:
        query_werstatt = """
            SELECT LieferBelegNr, Belegnummer
            FROM BELEG
            WHERE Belegnummer = %s
        """
        query_auge = """
            SELECT Artikelnummer AS ID, Menge AS count
            FROM BELEGP t1
            INNER JOIN BELEG AS t2 ON t1.Belegnummer = t2.Belegnummer
            WHERE t1.Belegnummer = %s
        """
        query_order = """
            SELECT Artikelnummer AS ID, Menge AS count
            FROM BELEGP
            WHERE Belegnummer = %s
            """
        connection = None
        cursor = None

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query_werstatt, (order_number,))
            werstatt_rows = cursor.fetchone()
            if not werstatt_rows or not werstatt_rows.get("LieferBelegNr"):
                return None

            cursor.execute(query_werstatt, (werstatt_rows.get("LieferBelegNr"),))
            more_rows = cursor.fetchone()
            if not more_rows or not more_rows.get("LieferBelegNr"):
                return None

            cursor.execute(query_auge, (more_rows.get("LieferBelegNr"),))
            original_comps = cursor.fetchall()
            cursor.execute(query_order, (order_number,))
            current_comps = cursor.fetchall()
            

        except pymssql.Error as exc:
            raise RuntimeError(f"SQL Server query failed: {exc}") from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        comparison = compare_dict_lists(current_comps, original_comps)
        if not comparison:
            return None
        result = MissingComponent(order_number=order_number, components=comparison)
        return result


    def find_missing_components_for_open_orders(
        self,
    ) -> list[MissingComponent] | None:
        query_open_orders = """
            SELECT Belegnummer
            FROM BELEG
            WHERE Adressnummer <> 'K10000' AND Adressnummer <> 'DE00000' AND Adressnummer <> 'K000000' AND Vorlage = '' 
            AND Belegtyp = 'L'
            AND Status = '0'
        """
        connection = None
        cursor = None
        missing_components_list: list[MissingComponent] = []

        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query_open_orders)
            open_orders_rows = cursor.fetchall()

            for row in open_orders_rows:
                order_number = row.get("Belegnummer")
                if order_number:
                    missing_components = self.find_missing_components(order_number)
                    if missing_components:
                        missing_components_list.append(missing_components)

        except pymssql.Error as exc:
            raise RuntimeError(f"SQL Server query failed: {exc}") from exc

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()

        return missing_components_list or None

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sqlserver_server = os.environ.get("SQLSERVER_SERVER") or None
    sqlserver_user = os.environ.get("SQLSERVER_USER") or None
    sqlserver_password = os.environ.get("SQLSERVER_PASSWORD") or None
    sqlserver_database = os.environ.get("SQLSERVER_DATABASE") or None
    sqlserver_tds_version: str = os.getenv(
        "SQLSERVER_TDS_VERSION",
        "7.0",
    )
    sqlserver_port: str = os.getenv(
        "SQLSERVER_PORT",
        "1433",
    )
    required_settings = {
        "SQLSERVER_SERVER": sqlserver_server,
        "SQLSERVER_USER": sqlserver_user,
        "SQLSERVER_PASSWORD": sqlserver_password,
        "SQLSERVER_DATABASE": sqlserver_database,
    }
    missing_settings = [
        name for name, value in required_settings.items() if not value
    ]
    if missing_settings:
        raise RuntimeError(
            "Missing SQL Server environment variables: "
            + ", ".join(missing_settings)
        )

    repository = SqlServerMissingRepository(
        server=sqlserver_server or "",
        user=sqlserver_user or "",
        password=sqlserver_password or "",
        database=sqlserver_database or "",
        tds_version=sqlserver_tds_version,
        port=sqlserver_port,
    )
    order_number = "LS164077"

    # list_1 = [("ME0001", 1), ("HD0001", 1)]
    # list_2 = [("ME0001", 2), ("HD0001", 1), ("ME0002", 1)]

    # print(compare_lists(list_1, list_2))
    missing_components_order = repository.find_missing_components(order_number)
    print(missing_components_order)
    missing_components = repository.find_missing_components_for_open_orders()
    print(missing_components)
    
