"""Supported user roles.

StrEnum so members compare equal to their string value (Role.STUDENT == "student") and
slot directly into SQLAlchemy string columns and SQL comparisons with no conversion.
Single source of truth for the role vocabulary used across models, seeding, and access.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
