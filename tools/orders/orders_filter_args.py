from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


DocumentType = Literal["A", "D", "L", "R"]
DocumentStatus = Literal["0", "2"]

LifecycleState = Literal[
    "created_unconfirmed",
    "confirmed_workshop",
    "in_production",
    "ready_or_sent",
]


LIFECYCLE_FILTERS = {
    "created_unconfirmed": ("A", "0"),
    "confirmed_workshop": ("D", "0"),
    "in_production": ("L", "0"),
    "ready_or_sent": ("R", "0"),
}

def resolve_lifecycle_filters(
    *,
    lifecycle_state: LifecycleState | None,
    document_type: DocumentType | None,
    status: DocumentStatus | None,
) -> tuple[DocumentType | None, DocumentStatus | None]:
    if lifecycle_state is not None:
        return LIFECYCLE_FILTERS[lifecycle_state]

    return document_type, status


class OrderFiltersArguments(BaseModel):
    lifecycle_state: LifecycleState | None = Field(
        default=None,
        description=(
            "Current operational lifecycle state. "
            "'created_unconfirmed' maps to A with status 0. "
            "'confirmed_workshop' maps to D with status 0. "
            "'in_production' maps to L with status 0. "
            "'ready_or_sent' maps to R with status 0. "
            "Use this field for questions about the current state."
        ),
    )

    order_number: str | None = Field(
        default=None,
        description=(
            "Full or partial order number, for example AG0950953."
        ),
        min_length=1,
        max_length=50,
    )

    document_type: DocumentType | None = Field(
        default=None,
        description=(
            "Raw database document type. "
            "'A' = created order, "
            "'D' = confirmed Werkstattschein, "
            "'L' = Lieferschein / production stage, "
            "'R' = Rechnung / final stage."
        ),
    )

    status: DocumentStatus | None = Field(
        default=None,
        description=(
            "Raw status of the selected document stage. "
            "For A, D, and L: 0 means active and 2 means completed. "
            "For R, status normally remains 0."
        ),
    )

    customer_name: str | None = Field(
        default=None,
        description="Full or partial customer name.",
        min_length=1,
        max_length=100,
    )

    country: str | None = Field(
        default=None,
        description="Country of orders' customer",
        min_length=1,
        max_length=100,
    )

    address: str | None = Field(
        default=None,
        description="Address of orders' customer",
        min_length=1,
        max_length=100,
    )

    date_from: date | None = Field(
        default=None,
        description=(
            "Earliest document date, inclusive, formatted as YYYY-MM-DD. "
            "Convert European DD.MM.YYYY dates correctly."
        ),
    )

    date_to: date | None = Field(
        default=None,
        description=(
            "Latest document date, inclusive, formatted as YYYY-MM-DD. "
            "Convert European DD.MM.YYYY dates correctly."
        ),
    )

    @model_validator(mode="after")
    def validate_filters(self) -> "OrderFiltersArguments":
        if self.lifecycle_state is not None:
            expected_document_type, expected_status = (
                LIFECYCLE_FILTERS[self.lifecycle_state]
            )

            if (
                self.document_type is not None
                and self.document_type != expected_document_type
            ):
                raise ValueError(
                    f"lifecycle_state={self.lifecycle_state!r} requires "
                    f"document_type={expected_document_type!r}"
                )

            if (
                self.status is not None
                and self.status != expected_status
            ):
                raise ValueError(
                    f"lifecycle_state={self.lifecycle_state!r} requires "
                    f"status={expected_status}"
                )

        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError(
                "date_from must be earlier than or equal to date_to"
            )

        return self


