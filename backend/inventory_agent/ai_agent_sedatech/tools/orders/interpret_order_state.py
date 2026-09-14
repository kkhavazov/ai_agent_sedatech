def interpret_order_state(
    document_type: str,
    status: int,
) -> dict[str, str | bool]:
    state_map = {
        ("A", 0): {
            "document_type_label": "Created order",
            "document_status_label": "Active",
            "lifecycle_state": "created_unconfirmed",
            "lifecycle_label": "Created but not confirmed",
            "is_current_stage": True,
        },
        ("A", 2): {
            "document_type_label": "Created order",
            "document_status_label": "Completed",
            "lifecycle_state": "created_stage_completed",
            "lifecycle_label": "Initial order stage completed",
            "is_current_stage": False,
        },
        ("D", 0): {
            "document_type_label": "Werkstattschein",
            "document_status_label": "Active",
            "lifecycle_state": "confirmed_workshop",
            "lifecycle_label": "Confirmed and at workshop stage",
            "is_current_stage": True,
        },
        ("D", 2): {
            "document_type_label": "Werkstattschein",
            "document_status_label": "Completed",
            "lifecycle_state": "workshop_stage_completed",
            "lifecycle_label": "Workshop stage completed",
            "is_current_stage": False,
        },
        ("L", 0): {
            "document_type_label": "Lieferschein",
            "document_status_label": "Active",
            "lifecycle_state": "in_production",
            "lifecycle_label": "Currently in production",
            "is_current_stage": True,
        },
        ("L", 2): {
            "document_type_label": "Lieferschein",
            "document_status_label": "Completed",
            "lifecycle_state": "production_completed",
            "lifecycle_label": "Production stage completed",
            "is_current_stage": False,
        },
        ("R", 0): {
            "document_type_label": "Rechnung",
            "document_status_label": "Final stage",
            "lifecycle_state": "ready_or_sent",
            "lifecycle_label": (
                "Ready for shipment, invoiced, or already shipped"
            ),
            "is_current_stage": True,
        },
    }

    return state_map.get(
        (document_type, status),
        {
            "document_type_label": "Unknown document type",
            "document_status_label": "Unknown status",
            "lifecycle_state": "unknown",
            "lifecycle_label": (
                f"Unknown combination: {document_type}/{status}"
            ),
            "is_current_stage": False,
        },
    )