from __future__ import annotations


def normalize_compatability_skus(skus: list[str]) -> list[str]:
    if not isinstance(skus, list) or not skus:
        raise ValueError("skus must be a non-empty list")
    if any(not isinstance(sku, str) or not sku.strip() for sku in skus):
        raise ValueError("Each SKU must be a non-empty string")
    return list(dict.fromkeys(sku.strip() for sku in skus))


def build_sku_conditions(skus: list[str]) -> tuple[str, tuple[str, ...]]:
    """Return a parenthesized IN placeholder list and deduplicated bound SKUs."""
    values = tuple(normalize_compatability_skus(skus))
    placeholders = "(" + ", ".join("%s" for _ in values) + ")"
    return placeholders, values


class SqlServerItemsCompatabilityRepository:
    def __init__(
        self, server: str, user: str, password: str, database: str,
        tds_version: str = "7.0", port: str = "1433",
        login_timeout_seconds: int = 10, query_timeout_seconds: int = 30,
    ) -> None:
        self.server = server
        self.user = user
        self.password = password
        self.database = database
        self.tds_version = tds_version
        self.port = port
        self.login_timeout_seconds = login_timeout_seconds
        self.query_timeout_seconds = query_timeout_seconds

    def _connect(self):
        import pymssql

        return pymssql.connect(
            server=self.server, user=self.user, password=self.password,
            database=self.database, port=self.port, tds_version=self.tds_version,
            charset="UTF-8", as_dict=True, appname="SedatechAIAgent",
            autocommit=True, login_timeout=self.login_timeout_seconds,
            timeout=self.query_timeout_seconds,
        )

    def _build_query(self, sku_conditions: str) -> str:
        query = f"""
SELECT
    Belegnummer AS order_number
FROM (
    SELECT a.Belegnummer
    FROM BELEGP AS a
    INNER JOIN BELEG AS t1 ON a.Belegnummer = t1.Belegnummer
    WHERE a.Artikelnummer IN {sku_conditions}
    AND t1.Vertreter NOT IN ('23', '0', '28') AND t1.PLZ != '10997' AND t1.Vertrag NOT IN (-1) AND t1.Lager = 100 AND t1.Belegtyp = 'R'
    GROUP BY a.Belegnummer
    HAVING COUNT(DISTINCT a.Artikelnummer) = %s
) x;
"""
        return query

    def items_compatability(self, skus: list[str], sample_limit: int = 20) -> dict:
        if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or not 0 <= sample_limit <= 100:
            raise ValueError("sample_limit must be an integer from 0 to 100")
        conditions, normalized_skus = build_sku_conditions(skus)
        parameters = (*normalized_skus, len(normalized_skus))
        query = self._build_query(conditions)
        if not query or not query.strip():
            raise NotImplementedError(
                "ITEMS_COMPATABILITY_QUERY_NOT_CONFIGURED: fill in _build_query in "
                "sqlserver_items_compatability_repository.py"
            )
        connection = None
        cursor = None
        seen: set[str] = set()
        sample: list[str] = []
        try:
            connection = self._connect()
            cursor = connection.cursor()
            cursor.execute(query, parameters)
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                for row in rows:
                    if "order_number" not in row or row["order_number"] is None:
                        raise ValueError("Compatibility query must return a non-null order_number column")
                    number = str(row["order_number"]).strip()
                    if not number:
                        raise ValueError("Compatibility query returned an empty order_number")
                    if number not in seen:
                        seen.add(number)
                        if len(sample) < sample_limit:
                            sample.append(number)
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                if connection is not None:
                    connection.close()
        return {
            "skus": list(normalized_skus),
            "matching_order_count": len(seen),
            "sample_order_numbers": sample,
            "order_numbers_truncated": len(seen) > len(sample),
        }
