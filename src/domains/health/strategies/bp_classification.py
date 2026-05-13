"""
Blood Pressure Classification Strategies (AHA/ACC 2025).

Implements the Strategy Pattern to follow the Open-Closed Principle:
- Open for extension: new categories can be added easily
- Closed for modification: existing strategies don't need changes
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BPClassificationStrategy(ABC):
    """Abstract strategy for blood pressure classification."""
    
    def __init__(self, stage_id: str, label: str, severity: str, guideline: str):
        self.stage_id = stage_id
        self.label = label
        self.severity = severity
        self.guideline = guideline
    
    @abstractmethod
    def applies(self, systolic: int, diastolic: int) -> bool:
        """Check if this strategy applies to the given readings."""
        pass
    
    def classify(self, systolic: int, diastolic: int) -> Dict[str, str]:
        """Return classification result if this strategy applies."""
        return {
            "stage": self.stage_id,
            "severity": self.severity,
            "label": self.label,
            "guideline": self.guideline
        }


class HypertensiveCrisisStrategy(BPClassificationStrategy):
    """Hypertensive Crisis: SBP > 180 OR DBP > 120"""
    
    def __init__(self):
        super().__init__(
            stage_id="hypertensive_crisis",
            label="Hypertensive Crisis",
            severity="urgent",
            guideline="AHA/ACC 2025"
        )
    
    def applies(self, systolic: int, diastolic: int) -> bool:
        return systolic > 180 or diastolic > 120


class Stage2HypertensionStrategy(BPClassificationStrategy):
    """Stage 2 Hypertension: SBP >= 140 OR DBP >= 90"""
    
    def __init__(self):
        super().__init__(
            stage_id="hypertension_stage_2",
            label="Stage 2 Hypertension",
            severity="high",
            guideline="AHA/ACC 2025"
        )
    
    def applies(self, systolic: int, diastolic: int) -> bool:
        return systolic >= 140 or diastolic >= 90


class Stage1HypertensionStrategy(BPClassificationStrategy):
    """Stage 1 Hypertension: SBP 130-139 OR DBP 80-89"""
    
    def __init__(self):
        super().__init__(
            stage_id="hypertension_stage_1",
            label="Stage 1 Hypertension",
            severity="moderate",
            guideline="AHA/ACC 2025"
        )
    
    def applies(self, systolic: int, diastolic: int) -> bool:
        return (130 <= systolic <= 139) or (80 <= diastolic <= 89)


class ElevatedBPStrategy(BPClassificationStrategy):
    """Elevated: SBP 120-129 AND DBP < 80"""
    
    def __init__(self):
        super().__init__(
            stage_id="elevated",
            label="Elevated Blood Pressure",
            severity="info",
            guideline="AHA/ACC 2025"
        )
    
    def applies(self, systolic: int, diastolic: int) -> bool:
        return (120 <= systolic <= 129) and diastolic < 80


class NormalBPStrategy(BPClassificationStrategy):
    """Normal: SBP < 120 AND DBP < 80"""
    
    def __init__(self):
        super().__init__(
            stage_id="normal",
            label="Normal Blood Pressure",
            severity="info",
            guideline="AHA/ACC 2025"
        )
    
    def applies(self, systolic: int, diastolic: int) -> bool:
        return systolic < 120 and diastolic < 80


class BPClassifier:
    """
    Blood pressure classifier using Chain of Responsibility pattern.
    
    Strategies are evaluated in priority order (most urgent first).
    First matching strategy wins.
    """
    
    def __init__(self, strategies: Optional[List[BPClassificationStrategy]] = None):
        """
        Initialize classifier with strategies.
        
        Args:
            strategies: List of strategies in priority order.
                       If None, uses default AHA/ACC 2025 strategies.
        """
        if strategies is None:
            # Default strategies in priority order
            strategies = [
                HypertensiveCrisisStrategy(),
                Stage2HypertensionStrategy(),
                Stage1HypertensionStrategy(),
                ElevatedBPStrategy(),
                NormalBPStrategy()
            ]
        self.strategies = strategies
    
    def classify(self, systolic: int, diastolic: int) -> Dict[str, str]:
        """
        Classify blood pressure reading using configured strategies.
        
        Args:
            systolic: Systolic blood pressure in mmHg
            diastolic: Diastolic blood pressure in mmHg
            
        Returns:
            Dict with keys: stage, severity, label, guideline
            
        Raises:
            ValueError: If no strategy matches (should not happen with complete ruleset)
        """
        for strategy in self.strategies:
            if strategy.applies(systolic, diastolic):
                return strategy.classify(systolic, diastolic)
        
        # Fallback to normal if no strategy matched
        # (should not happen with complete AHA/ACC ruleset)
        return NormalBPStrategy().classify(systolic, diastolic)


# Module-level singleton for backward compatibility
_default_classifier = BPClassifier()


def classify_blood_pressure(systolic: int, diastolic: int) -> Dict[str, str]:
    """
    Classify blood pressure reading according to AHA/ACC 2025 guidelines.
    
    This is a convenience function that uses the default classifier.
    For custom strategies, instantiate BPClassifier directly.
    
    Args:
        systolic: Systolic blood pressure in mmHg
        diastolic: Diastolic blood pressure in mmHg
        
    Returns:
        Dict with keys: stage, severity, label, guideline
    """
    return _default_classifier.classify(systolic, diastolic)
