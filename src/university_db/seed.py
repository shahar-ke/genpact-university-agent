"""Deterministic mock-data generator (Faker + fixed seed).

Produces a small but realistic university dataset:
- consistent per-student skill and per-course difficulty, so aggregates are meaningful
- teachers stay within a subject area
- a handful of retakes (same course, a different offering)
- the most recent semester is left ungraded (in progress -> NULL grades)

Reproducible: same seed -> identical data, so tests and demos are stable.
Scale is a parameter (SeedConfig) so tests can generate tiny datasets.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from faker import Faker
from sqlalchemy.orm import Session

from university_db.models import (
    Course,
    CourseOffering,
    Enrollment,
    Semester,
    Student,
    Teacher,
    User,
)
from university_db.roles import Role

RANDOM_SEED = 42
GRADE_BASE_MEAN = 78.0
GRADE_STDDEV = 8.0

# Subject-area code -> human name. Teachers and courses are tied to an area.
SUBJECTS = {
    "CS": "Computer Science",
    "MATH": "Mathematics",
    "PHYS": "Physics",
    "BIO": "Biology",
    "ECON": "Economics",
}
_SUBJECT_CODES = list(SUBJECTS)
_LEVEL_NAMES = {1: "Foundations of", 2: "Intermediate", 3: "Advanced", 4: "Topics in"}


@dataclass(frozen=True)
class SeedConfig:
    """Row counts and per-row ranges controlling dataset scale.

    Ranges are inclusive. Tests override this to generate tiny datasets.
    """

    teachers: int = 10
    students: int = 50
    courses: int = 20
    semesters: int = 6
    offerings_per_course: tuple[int, int] = (2, 3)  # inclusive range
    enrollments_per_student: tuple[int, int] = (8, 12)
    retakes: int = 8
    start_year: int = 2024


def _chronological_semesters(n: int, start_year: int) -> list[tuple[str, int]]:
    """n (term, year) pairs in chronological order; the last is the newest/current."""
    order = ["Spring", "Summer", "Fall"]
    seq: list[tuple[str, int]] = []
    year = start_year
    while len(seq) < n:
        for term in order:
            if len(seq) < n:
                seq.append((term, year))
        year += 1
    return seq


def _seed_semesters(session: Session, config: SeedConfig) -> list[Semester]:
    """Insert semesters in chronological order; the last one is the current/ungraded term."""
    semesters = [
        Semester(term=term, year=year)
        for term, year in _chronological_semesters(config.semesters, config.start_year)
    ]
    session.add_all(semesters)
    session.flush()
    return semesters


def _seed_teachers(session: Session, fake: Faker, config: SeedConfig) -> list[Teacher]:
    """Insert teachers with faked names/emails (draws the teacher name/email faker stream)."""
    teachers = [
        Teacher(name=fake.name(), email=fake.unique.email()) for _ in range(config.teachers)
    ]
    session.add_all(teachers)
    session.flush()
    return teachers


def _teachers_by_subject(teachers: list[Teacher]) -> dict[str, list[int]]:
    """Map each subject code to its teacher ids, assigned round-robin over subject areas."""
    by_subject: dict[str, list[int]] = {}
    for i, teacher in enumerate(teachers):
        subject = _SUBJECT_CODES[i % len(_SUBJECT_CODES)]
        by_subject.setdefault(subject, []).append(teacher.id)
    return by_subject


def _seed_courses(session: Session, config: SeedConfig) -> tuple[list[Course], dict[int, str]]:
    """Insert courses round-robin over subjects; return them plus a course_id -> subject map."""
    courses = []
    course_meta: list[str] = []  # subject per course, parallel to `courses`
    level_counter = dict.fromkeys(_SUBJECT_CODES, 0)
    for i in range(config.courses):
        subject = _SUBJECT_CODES[i % len(_SUBJECT_CODES)]
        level_counter[subject] += 1
        level = level_counter[subject]
        code = f"{subject}{level}01"
        title = f"{_LEVEL_NAMES.get(level, 'Topics in')} {SUBJECTS[subject]}"
        courses.append(Course(code=code, title=title))
        course_meta.append(subject)
    session.add_all(courses)
    session.flush()
    course_subject = dict(zip([c.id for c in courses], course_meta, strict=True))
    return courses, course_subject


def _seed_offerings(
    session: Session,
    rng: random.Random,
    config: SeedConfig,
    courses: list[Course],
    course_subject: dict[int, str],
    teachers: list[Teacher],
    teachers_by_subject: dict[str, list[int]],
    semesters: list[Semester],
) -> list[CourseOffering]:
    """Offer each course in a few random semesters, taught by a same-subject teacher."""
    offerings = []
    lo, hi = config.offerings_per_course
    for course in courses:
        pool = teachers_by_subject.get(course_subject[course.id]) or [t.id for t in teachers]
        k = min(rng.randint(lo, hi), len(semesters))
        for semester in rng.sample(semesters, k):
            offerings.append(
                CourseOffering(
                    course_id=course.id,
                    teacher_id=rng.choice(pool),
                    semester_id=semester.id,
                )
            )
    session.add_all(offerings)
    session.flush()
    return offerings


def _seed_students(session: Session, fake: Faker, config: SeedConfig) -> list[Student]:
    """Insert students with faked names/emails (draws the student name/email faker stream)."""
    students = [
        Student(name=fake.name(), email=fake.unique.email()) for _ in range(config.students)
    ]
    session.add_all(students)
    session.flush()
    return students


def _make_grade_fn(
    rng: random.Random,
    student_skill: dict[int, float],
    course_difficulty: dict[int, float],
    current_semester_id: int,
) -> Callable[[int, CourseOffering], float | None]:
    """Build the grade sampler: NULL for the current term, else a skill/difficulty-biased draw."""

    def grade_for(student_id: int, offering: CourseOffering) -> float | None:
        if offering.semester_id == current_semester_id:
            return None  # in progress
        mean = GRADE_BASE_MEAN + student_skill[student_id] - course_difficulty[offering.course_id]
        return round(min(100.0, max(0.0, rng.gauss(mean, GRADE_STDDEV))), 1)

    return grade_for


def _seed_enrollments(
    session: Session,
    rng: random.Random,
    config: SeedConfig,
    students: list[Student],
    offerings: list[CourseOffering],
    grade_for: Callable[[int, CourseOffering], float | None],
) -> tuple[list[Enrollment], set[tuple[int, int]], dict[int, list[int]]]:
    """Enroll each student in distinct courses (one offering per course, for a clean GPA).

    Returns the enrollments plus bookkeeping the retake step reuses: the set of
    (student_id, offering_id) pairs already used, and each student's enrolled course ids.
    """
    enrollments = []
    enrolled_pairs: set[tuple[int, int]] = set()
    student_courses: dict[int, list[int]] = {}
    elo, ehi = config.enrollments_per_student
    for student in students:
        k = rng.randint(elo, ehi)
        seen_courses: set[int] = set()
        for offering in rng.sample(offerings, min(k * 2, len(offerings))):
            if offering.course_id in seen_courses:
                continue
            seen_courses.add(offering.course_id)
            enrollments.append(
                Enrollment(
                    student_id=student.id,
                    offering_id=offering.id,
                    grade=grade_for(student.id, offering),
                )
            )
            enrolled_pairs.add((student.id, offering.id))
            student_courses.setdefault(student.id, []).append(offering.course_id)
            if len(seen_courses) >= k:
                break
    session.add_all(enrollments)
    session.flush()
    return enrollments, enrolled_pairs, student_courses


def _seed_retakes(
    session: Session,
    rng: random.Random,
    config: SeedConfig,
    students: list[Student],
    offerings: list[CourseOffering],
    current_semester_id: int,
    enrolled_pairs: set[tuple[int, int]],
    student_courses: dict[int, list[int]],
    grade_for: Callable[[int, CourseOffering], float | None],
) -> list[Enrollment]:
    """Add retakes: a second graded offering of a course the student already took.

    Best-effort up to config.retakes, with a bounded number of attempts so a small
    dataset that runs out of valid candidates still terminates.
    """
    graded_by_course: dict[int, list[CourseOffering]] = {}
    for offering in offerings:
        if offering.semester_id != current_semester_id:
            graded_by_course.setdefault(offering.course_id, []).append(offering)

    retakes = []
    student_ids = [s.id for s in students]
    attempts = 0
    while len(retakes) < config.retakes and attempts < config.retakes * 50:
        attempts += 1
        sid = rng.choice(student_ids)
        taken = student_courses.get(sid)
        if not taken:
            continue
        course_id = rng.choice(taken)
        candidates = [
            o for o in graded_by_course.get(course_id, []) if (sid, o.id) not in enrolled_pairs
        ]
        if not candidates:
            continue
        offering = rng.choice(candidates)
        enrolled_pairs.add((sid, offering.id))
        retakes.append(
            Enrollment(student_id=sid, offering_id=offering.id, grade=grade_for(sid, offering))
        )
    session.add_all(retakes)
    session.flush()
    return retakes


def _seed_users(
    session: Session, fake: Faker, students: list[Student], teachers: list[Teacher]
) -> list[User]:
    """Create one login per student then per teacher, plus a single admin login."""
    users = [
        User(username=fake.unique.user_name(), role=Role.STUDENT, student_id=s.id) for s in students
    ]
    users += [
        User(username=fake.unique.user_name(), role=Role.TEACHER, teacher_id=t.id) for t in teachers
    ]
    users.append(User(username="admin", role=Role.ADMIN))
    session.add_all(users)
    session.flush()
    return users


def generate(session: Session, config: SeedConfig | None = None) -> dict[str, int]:
    """Populate all tables with a deterministic dataset; return per-table row counts.

    Runs the seeding steps in dependency order (semesters -> teachers -> courses ->
    offerings -> students -> enrollments -> retakes -> users). The rng and faker are
    seeded once here and threaded through the steps, so the sequence of random draws
    is fixed and the result is reproducible.
    """
    config = config or SeedConfig()
    rng = random.Random(RANDOM_SEED)
    fake = Faker()
    Faker.seed(RANDOM_SEED)

    semesters = _seed_semesters(session, config)
    current_semester_id = semesters[-1].id

    teachers = _seed_teachers(session, fake, config)
    teachers_by_subject = _teachers_by_subject(teachers)

    courses, course_subject = _seed_courses(session, config)
    course_difficulty = {c.id: rng.gauss(0, 6) for c in courses}  # +harder, -easier

    offerings = _seed_offerings(
        session, rng, config, courses, course_subject, teachers, teachers_by_subject, semesters
    )

    students = _seed_students(session, fake, config)
    student_skill = {s.id: rng.gauss(0, 7) for s in students}

    grade_for = _make_grade_fn(rng, student_skill, course_difficulty, current_semester_id)

    enrollments, enrolled_pairs, student_courses = _seed_enrollments(
        session, rng, config, students, offerings, grade_for
    )
    retakes = _seed_retakes(
        session,
        rng,
        config,
        students,
        offerings,
        current_semester_id,
        enrolled_pairs,
        student_courses,
        grade_for,
    )

    users = _seed_users(session, fake, students, teachers)

    return {
        "teachers": len(teachers),
        "students": len(students),
        "courses": len(courses),
        "semesters": len(semesters),
        "course_offerings": len(offerings),
        "enrollments": len(enrollments) + len(retakes),
        "users": len(users),
    }
