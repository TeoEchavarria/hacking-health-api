"""
Heart Rate Classification Strategies (Adult Resting HR).

Implements the Strategy Pattern to follow the Open-Closed Principle.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class HRClassificationStrategy(ABC):
    """Abstract strategy for heart rate classification."""
    
    def __init__(self, category_id: str, label: str, severity: str):
        self.category_id = category_id
        self.label = label
        self.severity = severity
    
    @abstractmethod
    def applies(self, bpm: int) -> bool:
        """Check if this strategy applies to the given heart rate."""
        pass
    
    def classify(self, bpm: int) -> Dict[str, str]:
        """Return classification result if this strategy applies."""
        return {
            "category": self.category_id,
            "severity": self.severity,
            "label": self.label
        }


class CriticalBradycardiaStrategy(HRClassificationStrategy):
    """Critical Bradycardia: BPM < 40"""
    
    def __init__(self):
        super().__init__(
            category_id="critical_bradycardia",
            label="Critical Bradycardia",
            severity="urgent"
        )
    
    def applies(self, bpm: int) -> bool:
        return bpm < 40


class BradycardiaStrategy(HRClassificationStrategy):
    """Bradycardia: BPM 40-59"""
    
    def __init__(self):
        super().__init__(
            category_id="bradycardia",
            label="Bradycardia",
            severity="moderate"
        )
    
    def applies(self, bpm: int) -> bool:
        return 40 <= bpm < 60


class NormalHRStrategy(HRClassificationStrategy):
    """Normal: BPM 60-100"""
    
    def __init__(self):
        super().__init__(
            category_id="normal",
            label="Normal Heart Rate",
            severity="info"
        )
    
    def applies(self, bpm: int) -> bool:
        return 60 <= bpm <= 100


class TachycardiaStrategy(HRClassificationStrategy):
    """Tachycardia: BPM 101-150"""
    
    def __init__(self):
        super().__init__(
            category_id="tachycardia",
            label="Tachycardia",
            severity="moderate"
        )
    
    def applies(self, bpm: int) -> bool:
        return 101 <= bpm <= 150


class CriticalTachycardiaStrategy(HRClassificationStrategy):
    """Critical Tachycardia: BPM > 150"""
    
    def __init__(self):
        super().__init__(
            category_id="critical_tachycardia",
            label="Critical Tachycardia",
            severity="urgent"
        )
    
    def applies(self, bpm: int) -> bool:
        return bpm > 150


class HRClassifier:
    """
    Heart rate classifier using Chain of Responsibility pattern.
    
    Strategies are evaluated in priority order.
    First matching strategy wins.
    """
    
    def __init__(self, strategies: Optional[List[HRClassificationStrategy]] = None):
        """
        Initialize classifier with strategies.
        
        Args:
            strategies: List of strategies in priority order.
                       If None, uses default strategies.
        """
        if strategies is None:
            # Default strategies in priority order
            strategies = [
                CriticalBradycardiaStrategy(),
                BradycardiaStrategy(),
                NormalHRStrategy(),
                TachycardiaStrategy(),
                CriticalTachycardiaStrategy()
            ]
        self.strategies = strategies
    
    def classify(self, bpm: int) -> Dict[str, str]:
        """
        Classify heart rate reading using configured strategies.
        
        Args:
            bpm: Heart rate in beats per minute
            
        Returns:
            Dict with keys: category, severity, label
            
        Raises:
            ValueError: If no strategy matches (should not happen with complete ruleset)
        """
        for strategy in self.strategies:
            if strategy.applies(bpm):
                return strategy.classify(bpm)
        
        # Fallback to normal if no strategy matched
        return NormalHRStrategy().classify(bpm)


# Module-level singleton for backward compatibility
_default_classifier = HRClassifier()


def classify_heart_rate(bpm: int) -> Dict[str, str]:
    """
    Classify heart rate reading for adult resting heart rate.
    
    This is a convenience function that uses the default classifier.
    For custom strategies, instantiate HRClassifier directly.
    
    Args:
        bpm: Heart rate in beats per minute
        
    Returns:
        Dict with keys: category, severity, label
    """
    return _default_classifier.classify(bpm)
