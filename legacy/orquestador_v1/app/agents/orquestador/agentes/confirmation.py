from app.application.quotes import interpret_quote_decision


def parse_confirmation(message: str) -> bool | None:
    decision = interpret_quote_decision(message)
    if decision == "ACCEPT":
        return True
    if decision == "REJECT":
        return False
    return None
