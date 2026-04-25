"""
Timestamp adapters for handling legacy data formats.

The system is migrating from int timestamps (milliseconds since epoch)
to ISO 8601 string format. This module provides adapters to normalize
data on read, allowing seamless handling of both formats during transition.
"""
from datetime import datetime, timezone
from typing import Union, Optional


def normalize_timestamp(value: Union[int, str, None]) -> Optional[str]:
    """
    Normalize a timestamp to ISO 8601 string format.
    
    Handles both legacy int timestamps (milliseconds since epoch)
    and new ISO 8601 string timestamps.
    
    Args:
        value: Timestamp as int (ms), ISO 8601 string, or None
        
    Returns:
        ISO 8601 formatted string (e.g., "2025-04-24T10:30:00Z") or None
        
    Examples:
        >>> normalize_timestamp(1713953400000)
        '2024-04-24T10:30:00Z'
        >>> normalize_timestamp("2025-04-24T10:30:00Z")
        '2025-04-24T10:30:00Z'
        >>> normalize_timestamp(None)
        None
    """
    if value is None:
        return None
    
    if isinstance(value, int):
        # Convert milliseconds to seconds and create datetime
        dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if isinstance(value, str):
        # Validate and normalize the ISO 8601 string
        try:
            # Parse to validate
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            # Return in consistent format
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, AttributeError):
            # If invalid, return as-is (will fail validation elsewhere)
            return value
    
    # Unknown type - convert to string
    return str(value)


def timestamp_to_ms(value: Union[int, str, None]) -> Optional[int]:
    """
    Convert a timestamp to milliseconds since epoch.
    
    Useful for database queries that need numeric comparisons.
    
    Args:
        value: Timestamp as int (ms), ISO 8601 string, or None
        
    Returns:
        Milliseconds since epoch as int, or None
        
    Examples:
        >>> timestamp_to_ms("2025-04-24T10:30:00Z")
        1745492200000
        >>> timestamp_to_ms(1713953400000)
        1713953400000
    """
    if value is None:
        return None
    
    if isinstance(value, int):
        return value
    
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            return None
    
    return None


def extract_date_from_timestamp(value: Union[int, str, None]) -> Optional[str]:
    """
    Extract the date portion (YYYY-MM-DD) from a timestamp.
    
    Used for daily aggregation queries.
    
    Args:
        value: Timestamp as int (ms), ISO 8601 string, or None
        
    Returns:
        Date string in YYYY-MM-DD format, or None
        
    Examples:
        >>> extract_date_from_timestamp("2025-04-24T10:30:00Z")
        '2025-04-24'
        >>> extract_date_from_timestamp(1713953400000)
        '2024-04-24'
    """
    if value is None:
        return None
    
    if isinstance(value, int):
        dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            # Try to extract date directly if it's already YYYY-MM-DD
            if len(value) >= 10 and value[4] == '-' and value[7] == '-':
                return value[:10]
            return None
    
    return None


def now_iso() -> str:
    """
    Get current UTC time as ISO 8601 string.
    
    Returns:
        Current time in ISO 8601 format (e.g., "2025-04-24T10:30:00Z")
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ms() -> int:
    """
    Get current UTC time as milliseconds since epoch.
    
    Returns:
        Current time as milliseconds since epoch
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def parse_iso_timestamp(value: str) -> datetime:
    """
    Parse an ISO 8601 timestamp string to datetime.
    
    Args:
        value: ISO 8601 timestamp string
        
    Returns:
        datetime object in UTC
        
    Raises:
        ValueError: If the string is not valid ISO 8601
    """
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def days_ago_iso(days: int) -> str:
    """
    Get ISO 8601 timestamp for N days ago from now.
    
    Args:
        days: Number of days ago
        
    Returns:
        ISO 8601 timestamp string
    """
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def days_ago_ms(days: int) -> int:
    """
    Get milliseconds timestamp for N days ago from now.
    
    Args:
        days: Number of days ago
        
    Returns:
        Milliseconds since epoch
    """
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return int(dt.timestamp() * 1000)
