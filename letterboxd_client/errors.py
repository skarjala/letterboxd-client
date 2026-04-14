"""Package exceptions."""


class LetterboxdError(Exception):
    """Base package error."""


class AuthenticationError(LetterboxdError):
    """Authentication failed or an authenticated call was required."""


class PermissionDenied(LetterboxdError):
    """The request was refused by the upstream service."""


class PrivateResource(LetterboxdError):
    """The requested content exists but is not publicly available."""


class NotFound(LetterboxdError):
    """The requested content does not exist."""


class RateLimited(LetterboxdError):
    """The service requested that the client slow down."""


class MarkupChanged(LetterboxdError):
    """The upstream HTML shape no longer matches the parser assumptions."""


class UnsupportedFlow(LetterboxdError):
    """The requested action is not supported by the configured transport."""

