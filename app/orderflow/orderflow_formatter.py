from app.telegram.message_formatter import format_orderflow_summary_message


def format_orderflow(summary: dict) -> str:
    return format_orderflow_summary_message(summary)
