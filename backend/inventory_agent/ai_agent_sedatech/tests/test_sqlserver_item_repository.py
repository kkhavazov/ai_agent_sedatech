import pytest

from repositories.sqlserver_item_repository import SqlServerItemRepository


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.parameters = ()
        self.executions = []

    def execute(self, query, parameters) -> None:
        self.query = query
        self.parameters = parameters
        self.executions.append((query, parameters))

    def fetchall(self):
        return [
            {
                "Artikelnummer": "CP00001",
                "Bezeichnung": "AMD Ryzen 9 9900X",
                "ItemCount": 12,
                "OrderedAmount": 4,
                "MinimumPrice": 100,
                "MaximumPrice": 300,
                "AveragePrice": 200,
                "EAN": "0012345678905",
                "ProducerEAN": "100-100000662WOF",
            }
        ]

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


@pytest.mark.parametrize(
    "field,column,value",
    [
        ("ean", "ART.EANNummer", "0012345678905"),
        ("producer_ean", "ART.HstArtikelnummer", "100-100000662WOF"),
        ("producer_ean", "ART.HstArtikelnummer", "part%' OR 1=1 --"),
    ],
)
def test_identifier_search_uses_exact_bound_parameters(field, column, value) -> None:
    repository, cursor = make_repository()

    result = repository.search_inventory(**{field: f" {value} "})

    assert cursor.query.count(f"{column} = %s") == 2
    assert cursor.parameters == (value, value)
    assert value not in cursor.query
    assert "Stock.EAN," in cursor.query
    assert "Stock.ProducerEAN," in cursor.query
    assert result[0].ean == "0012345678905"
    assert result[0].producer_ean == "100-100000662WOF"


def test_identifier_filters_combine_with_existing_filters() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(
        ean="0012345678905", producer_ean="100-100000662WOF", category="CP",
    )

    assert "ART.EANNummer = %s AND ART.HstArtikelnummer = %s AND ART.ArtikelGruppe LIKE %s" in cursor.query
    assert cursor.parameters == ("0012345678905", "100-100000662WOF", "%CP%") * 2
    assert cursor.query.count("%s") == len(cursor.parameters)


def test_null_identifiers_remain_unknown() -> None:
    repository, cursor = make_repository()
    row = cursor.fetchall()[0]
    row.update(EAN=None, ProducerEAN=None)
    cursor.fetchall = lambda: [row]

    result = repository.search_inventory(sku="CP00001")

    assert result[0].ean is None
    assert result[0].producer_ean is None


def test_amd_cpu_search_uses_cpu_manufacturer_and_prefix_match() -> None:
    repository, cursor = make_repository()

    result = repository.search_inventory(
        category="CP",
        cpu_manufacturer="AMD",
        cpu_generation=9,
        cpu_model="9900X",
    )

    assert len(result) == 1
    assert result[0].sku == "CP00001"
    assert result[0].name == "AMD Ryzen 9 9900X"
    assert result[0].amount == 12
    assert result[0].ordered == 4
    assert result[0].minimum_price == 100.0
    assert cursor.parameters[-2:] == (
        "AMD Ryzen 9 9900X",
        "AMD Ryzen 9 9900X %",
    )
    assert "SUM(LAGERP.Bestand)" in cursor.executions[0][0]
    assert "SUM(BELEGP.Menge)" in cursor.executions[0][0]
    assert "Orders.Artikelnummer = Stock.Artikelnummer" in cursor.query


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


def test_case_search_matches_exact_name_or_trailing_description() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(
        category="TW",
        case_manufacturer="CoolerMaster",
        case_model="Elite 302",
    )

    assert cursor.parameters[-2:] == (
        "CoolerMaster Elite 302",
        "CoolerMaster Elite 302 %",
    )
    assert "ART.Bezeichnung = %s OR ART.Bezeichnung LIKE %s" in cursor.query


def test_case_manufacturer_search_uses_name_prefix() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(
        category="TW",
        case_manufacturer="CoolerMaster",
    )

    assert cursor.parameters[-1] == "CoolerMaster %"


def test_gpu_search_uses_series_model_and_gigabyte_vram() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(
        category="GC",
        gpu_manufacturer="NVIDIA",
        gpu_series="GeForce",
        gpu_model="RTX5070Ti",
        gpu_vram=16,
    )

    assert cursor.parameters[-6:] == (
        "%GC%",
        "Geforce %",
        "Quadro %",
        "Nvidia %",
        "%RTX5070Ti%",
        "%16GB%",
    )


def test_two_gigabyte_gpu_search_uses_2048_mb() -> None:
    repository, cursor = make_repository()

    repository.search_inventory(category="GC", gpu_vram=2)

    assert cursor.parameters[-1] == "%2048MB%"
