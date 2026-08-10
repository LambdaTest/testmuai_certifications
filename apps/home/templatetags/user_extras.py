from django import template

register = template.Library()


@register.filter
def initials(value, count=2):
    """'Imad Alam' -> 'IA'. Used for the avatar in the header."""
    parts = [p for p in str(value or "").split() if p]
    if not parts:
        return "?"
    return "".join(p[0] for p in parts[:count]).upper()
