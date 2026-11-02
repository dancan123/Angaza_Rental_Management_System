from decimal import Decimal, ROUND_HALF_UP

def to_cents(amount) -> int:
    """
    Converts a float, int, str, or Decimal amount to integer minor units (cents).
    e.g., 12000.50 -> 1200050
    """
    if amount is None:
        return 0
    if isinstance(amount, int):
        return amount * 100
    d = Decimal(str(amount))
    return int((d * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def from_cents(cents: int) -> Decimal:
    """
    Converts integer minor units (cents) to Decimal.
    e.g., 1200050 -> Decimal('12000.50')
    """
    if cents is None:
        return Decimal('0.00')
    return (Decimal(cents) / Decimal(100)).quantize(Decimal('0.01'))

def format_currency(cents: int, currency: str = 'KES') -> str:
    """
    Formats integer cents to standard currency display.
    e.g., 1200050 -> "KES 12,000.50"
    """
    amount = from_cents(cents)
    return f"{currency} {amount:,.2f}"

