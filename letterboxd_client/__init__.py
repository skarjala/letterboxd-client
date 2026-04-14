"""High-level Letterboxd client package."""

from .client import LetterboxdClient
from .errors import (
    AuthenticationError,
    LetterboxdError,
    MarkupChanged,
    NotFound,
    PermissionDenied,
    PrivateResource,
    RateLimited,
    UnsupportedFlow,
)
from .models import (
    Activity,
    Comment,
    DiaryDetails,
    Film,
    FilmRelationship,
    ListEntry,
    ListResource,
    LogEntry,
    Member,
    MemberRelationship,
    Page,
    Review,
    SearchResult,
)

__all__ = [
    "Activity",
    "AuthenticationError",
    "Comment",
    "DiaryDetails",
    "Film",
    "FilmRelationship",
    "LetterboxdClient",
    "LetterboxdError",
    "ListEntry",
    "ListResource",
    "LogEntry",
    "MarkupChanged",
    "Member",
    "MemberRelationship",
    "NotFound",
    "Page",
    "PermissionDenied",
    "PrivateResource",
    "RateLimited",
    "Review",
    "SearchResult",
    "UnsupportedFlow",
]
