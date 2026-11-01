from functools import wraps

from django.core.exceptions import PermissionDenied


def require(capability):
    """Lässt eine View nur zu, wenn `request.user.<capability>` wahr ist.

    Die Anmeldung selbst erzwingt bereits LoginRequiredMiddleware.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not getattr(request.user, capability, False):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
