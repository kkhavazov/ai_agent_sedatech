from dataclasses import dataclass
from typing import TypedDict


ORDERED_AMOUNT_DESCRIPTION = (
    "Quantity ordered from suppliers for incoming inventory replenishment. "
    "This is not stock reserved for customers or customer demand. "
    "Do not subtract it from amount or count it as stock already received."
)

EAN_DESCRIPTION = "Item barcode (EAN), stored in ART.EANNummer. Preserve leading zeros."
PRODUCER_EAN_DESCRIPTION = (
    "Manufacturer article/part number (ProducerEAN), stored in ART.HstArtikelnummer. "
    "May be alphanumeric; it is distinct from the EAN barcode and internal SKU."
)


class MissingComponentEntry(TypedDict):
    ID: str
    count: int
    name: str

@dataclass(slots=True)
class MissingComponent:
    order_number: str
    components: list[MissingComponentEntry]

@dataclass(slots=True)
class ItemsSearchResponse:
    sku: str
    name: str
    amount: int
    ordered: int  # Incoming supplier replenishment; see ORDERED_AMOUNT_DESCRIPTION.
    minimum_price: float
    maximum_price: float
    average_price: float
    ean: str | None = None
    producer_ean: str | None = None


@dataclass(slots=True)
class ComponentForecast:
    sku: str
    name: str
    weekly_forecast: float
    stock_coverage: float
