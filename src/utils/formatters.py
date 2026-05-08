"""
Utility functions for formatting data.
"""
from typing import Optional


def format_sleep_duration(minutes: Optional[int]) -> str:
    """Convert minutes to human-readable hours and minutes (Spanish).
    
    Examples:
        400 → "6 horas 40 minutos"
        60 → "1 hora"
        45 → "45 minutos"
        0 → "0 minutos"
        None → "No disponible"
    
    Args:
        minutes: Sleep duration in minutes
        
    Returns:
        Human-readable string in Spanish
    """
    if minutes is None or minutes < 0:
        return "No disponible"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
    if remaining_minutes > 0:
        parts.append(f"{remaining_minutes} minuto{'s' if remaining_minutes != 1 else ''}")
    
    return " ".join(parts) if parts else "0 minutos"
