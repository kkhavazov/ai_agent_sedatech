from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from repositories.sqlserver_emails_repository import SqlServerEmailsRepository
from tools.registry import ToolDefinition


class GetEmailsArguments(BaseModel):
    platform: Literal["sedatech"] = "sedatech"
    date_from: date | None = Field(
        default=None, description="Inclusive invoice start date (YYYY-MM-DD)."
    )
    date_to: date | None = Field(
        default=None, description="Inclusive invoice end date (YYYY-MM-DD)."
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> GetEmailsArguments:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must be on or before date_to")
        return self


def build_get_emails_tool(repository: SqlServerEmailsRepository) -> ToolDefinition:
    def get_emails(
        platform: Literal["sedatech"] = "sedatech",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        emails = repository.get_emails(
            platform=platform, date_from=date_from, date_to=date_to
        )
        return {"platform": platform, "emails": emails, "count": len(emails)}

    return ToolDefinition(
        name="get_emails",
        description=(
            "List customer email addresses from Sedatech invoices. Only the "
            "sedatech platform is supported. Optionally filter by inclusive "
            "invoice dates using date_from and date_to (YYYY-MM-DD). "
            "For a single day, set both dates to that day. Preserve explicit "
            "years; when omitted, use the current year from the request context. "
            "Omit dates to retrieve all matching emails."
        ),
        arguments_model=GetEmailsArguments,
        handler=get_emails,
    )
