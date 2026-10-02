"""Failures in the decision loop."""


class DecisionError(ValueError):
    """The loop cannot take this step yet."""
