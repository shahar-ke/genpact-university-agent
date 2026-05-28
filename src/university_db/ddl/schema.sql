-- University QA Agent — schema
-- Target: SQLite (portable to Postgres via SQLAlchemy).
-- Foreign keys require `PRAGMA foreign_keys = ON;` per connection (set in engine.py).

-- ---------------------------------------------------------------------------
-- Core entities
-- ---------------------------------------------------------------------------

CREATE TABLE students (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE teachers (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE courses (
    id    INTEGER PRIMARY KEY,
    code  TEXT NOT NULL UNIQUE,           -- e.g. 'CS101'
    title TEXT NOT NULL
);

CREATE TABLE semesters (
    id   INTEGER PRIMARY KEY,
    term TEXT NOT NULL CHECK (term IN ('Fall', 'Spring', 'Summer')),
    year INTEGER NOT NULL,
    UNIQUE (term, year)
);

-- ---------------------------------------------------------------------------
-- Relationships
-- ---------------------------------------------------------------------------

-- A course offered in a specific semester, taught by a specific teacher.
CREATE TABLE course_offerings (
    id          INTEGER PRIMARY KEY,
    course_id   INTEGER NOT NULL REFERENCES courses(id),
    teacher_id  INTEGER NOT NULL REFERENCES teachers(id),
    semester_id INTEGER NOT NULL REFERENCES semesters(id),
    UNIQUE (course_id, semester_id)       -- one offering per course per semester
);

-- A student enrolled in an offering, with an optional grade.
CREATE TABLE enrollments (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id),
    offering_id INTEGER NOT NULL REFERENCES course_offerings(id),
    grade       REAL CHECK (grade >= 0 AND grade <= 100),  -- NULL = not yet graded
    UNIQUE (student_id, offering_id)      -- no double-enrollment in the same offering
);

-- ---------------------------------------------------------------------------
-- Access control
-- ---------------------------------------------------------------------------

-- Maps a system login to exactly one student OR one teacher.
-- Identity is resolved at MCP session start and drives session-scoped views.
CREATE TABLE users (
    id         INTEGER PRIMARY KEY,
    username   TEXT NOT NULL UNIQUE,      -- login identifier, e.g. 'alice'
    role       TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    student_id INTEGER REFERENCES students(id),
    teacher_id INTEGER REFERENCES teachers(id),
    CHECK (
        (role = 'student' AND student_id IS NOT NULL AND teacher_id IS NULL) OR
        (role = 'teacher' AND teacher_id IS NOT NULL AND student_id IS NULL) OR
        (role = 'admin'   AND student_id IS NULL AND teacher_id IS NULL)
    )
);

-- ---------------------------------------------------------------------------
-- Indexes for common join / filter paths
-- ---------------------------------------------------------------------------

CREATE INDEX idx_offerings_course    ON course_offerings(course_id);
CREATE INDEX idx_offerings_teacher   ON course_offerings(teacher_id);
CREATE INDEX idx_offerings_semester  ON course_offerings(semester_id);
CREATE INDEX idx_enrollments_student  ON enrollments(student_id);
CREATE INDEX idx_enrollments_offering ON enrollments(offering_id);
