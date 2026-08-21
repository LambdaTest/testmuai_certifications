"""
Access control for views.

One gate, written once. A view decorated with these can assume that by the
time its body runs, the caller is signed in and holds the right role — so the
view goes back to doing only its own job.

Keep gating out of the views themselves. The same two lines repeated across
every admin page is how a check gets forgotten on the fifteenth one, and how
the same bug appears in two places at once.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404


def role_required(*roles):
    """
    Restricts a view to the given roles.

        @role_required(User.Role.ADMIN)
        def subject_center(request): ...

        @role_required(User.Role.ADMIN, User.Role.EXAMINER)
        def support_tickets(request): ...

    Raises 404 rather than 403, matching the ownership checks elsewhere — we
    don't confirm a page exists to someone who has no business reaching it.

    ``login_required`` is applied inside, so it runs *before* the role check.
    That order matters: ``AnonymousUser`` has no ``role``, so an anonymous
    visitor must be redirected to login before that attribute is read.
    """

    def decorator(view):
        # @wraps keeps the view's real name for tracebacks, logging and
        # Django's technical 404 page — without it every gated view would
        # report itself as "wrapped".
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if getattr(request.user, "role", None) not in roles:
                raise Http404("No such page.")
            # Everything passes through untouched, including URL kwargs, so
            # this works on any view signature.
            return view(request, *args, **kwargs)

        return wrapped

    return decorator