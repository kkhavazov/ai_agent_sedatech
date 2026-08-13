from repositories.sqlserver_item_repository import SqlServerItemRepository


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.parameters = ()

    def execute(self, query, parameters) -> None:
        self.query = query
        self.parameters = parameters

    def fetchone(self):
        return {"ItemCount": 12}

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self) -> None:
        pass


def make_repository():
    repository = SqlServerItemRepository("server", "user", "password", "database")
    connection = FakeConnection()
    repository._connect = lambda: connection
    return repository, connection.cursor_instance


def test_amd_cpu_search_uses_cpu_manufacturer_and_prefix_match() -> None:
    repository, cursor = make_repository()

    amount = repository.search_inventory(
        category="CP",
        cpu_manufacturer="AMD",
        cpu_generation=9,
        cpu_model="9900X",
    )

    assert amount == 12
    assert cursor.parameters[-2:] == (
        "AMD Ryzen 9 9900X",
        "AMD Ryzen 9 9900X %",
    )
    assert "SUM(LAGERP.Bestand)" in cursor.query


def test_intel_cpu_search_matches_names_with_or_without_description() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(
        category="CP",
        cpu_manufacturer="Intel",
        cpu_generation=9,
        cpu_model="14900K",
    )

    assert cursor.parameters[-4:] == (
        "Intel Core i9-14900K",
        "Intel Core i9-14900K %",
        "Intel Core Ultra 9 14900K",
        "Intel Core Ultra 9 14900K %",
    )


def test_intel_kf_search_without_tier_has_exact_model_boundary() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(
        category="CP",
        cpu_manufacturer="Intel",
        cpu_model="14900KF",
    )

    assert cursor.parameters[-4:] == (
        "Intel Core i%-14900KF",
        "Intel Core i%-14900KF %",
        "Intel Core Ultra % 14900KF",
        "Intel Core Ultra % 14900KF %",
    )


def test_partial_cpu_search_is_filtered() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(category="CP", cpu_manufacturer="AMD")

    assert cursor.parameters[-1] == "AMD Ryzen %"
