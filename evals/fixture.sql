BEGIN TRANSACTION;
CREATE TABLE course_offerings (
    id          INTEGER PRIMARY KEY,
    course_id   INTEGER NOT NULL REFERENCES courses(id),
    teacher_id  INTEGER NOT NULL REFERENCES teachers(id),
    semester_id INTEGER NOT NULL REFERENCES semesters(id),
    UNIQUE (course_id, semester_id)       -- one offering per course per semester
);
INSERT INTO "course_offerings" VALUES(1,1,1,3);
INSERT INTO "course_offerings" VALUES(2,1,1,2);
INSERT INTO "course_offerings" VALUES(3,2,2,1);
INSERT INTO "course_offerings" VALUES(4,2,2,3);
INSERT INTO "course_offerings" VALUES(5,3,3,1);
INSERT INTO "course_offerings" VALUES(6,3,3,2);
INSERT INTO "course_offerings" VALUES(7,3,3,3);
INSERT INTO "course_offerings" VALUES(8,4,2,2);
INSERT INTO "course_offerings" VALUES(9,4,1,1);
INSERT INTO "course_offerings" VALUES(10,4,1,3);
INSERT INTO "course_offerings" VALUES(11,5,3,1);
INSERT INTO "course_offerings" VALUES(12,5,2,2);
INSERT INTO "course_offerings" VALUES(13,5,1,3);
INSERT INTO "course_offerings" VALUES(14,6,1,3);
INSERT INTO "course_offerings" VALUES(15,6,1,1);
INSERT INTO "course_offerings" VALUES(16,6,1,2);
CREATE TABLE courses (
    id    INTEGER PRIMARY KEY,
    code  TEXT NOT NULL UNIQUE,           -- e.g. 'CS101'
    title TEXT NOT NULL
);
INSERT INTO "courses" VALUES(1,'CS101','Foundations of Computer Science');
INSERT INTO "courses" VALUES(2,'MATH101','Foundations of Mathematics');
INSERT INTO "courses" VALUES(3,'PHYS101','Foundations of Physics');
INSERT INTO "courses" VALUES(4,'BIO101','Foundations of Biology');
INSERT INTO "courses" VALUES(5,'ECON101','Foundations of Economics');
INSERT INTO "courses" VALUES(6,'CS201','Intermediate Computer Science');
CREATE TABLE enrollments (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id),
    offering_id INTEGER NOT NULL REFERENCES course_offerings(id),
    grade       REAL CHECK (grade >= 0 AND grade <= 100),  -- NULL = not yet graded
    UNIQUE (student_id, offering_id)      -- no double-enrollment in the same offering
);
INSERT INTO "enrollments" VALUES(1,1,15,71.2);
INSERT INTO "enrollments" VALUES(2,1,11,70.6);
INSERT INTO "enrollments" VALUES(3,1,6,79.9);
INSERT INTO "enrollments" VALUES(4,1,3,63.9);
INSERT INTO "enrollments" VALUES(5,1,10,NULL);
INSERT INTO "enrollments" VALUES(6,1,1,NULL);
INSERT INTO "enrollments" VALUES(7,2,11,82.3);
INSERT INTO "enrollments" VALUES(8,2,14,NULL);
INSERT INTO "enrollments" VALUES(9,2,1,NULL);
INSERT INTO "enrollments" VALUES(10,2,4,NULL);
INSERT INTO "enrollments" VALUES(11,2,6,66.0);
INSERT INTO "enrollments" VALUES(12,2,10,NULL);
INSERT INTO "enrollments" VALUES(13,3,9,81.3);
INSERT INTO "enrollments" VALUES(14,3,3,87.7);
INSERT INTO "enrollments" VALUES(15,3,12,79.0);
INSERT INTO "enrollments" VALUES(16,3,16,82.0);
INSERT INTO "enrollments" VALUES(17,3,5,75.4);
INSERT INTO "enrollments" VALUES(18,3,2,90.8);
INSERT INTO "enrollments" VALUES(19,4,9,88.6);
INSERT INTO "enrollments" VALUES(20,4,16,86.0);
INSERT INTO "enrollments" VALUES(21,4,1,NULL);
INSERT INTO "enrollments" VALUES(22,4,11,76.4);
INSERT INTO "enrollments" VALUES(23,4,5,79.9);
INSERT INTO "enrollments" VALUES(24,4,3,69.6);
INSERT INTO "enrollments" VALUES(25,5,7,NULL);
INSERT INTO "enrollments" VALUES(26,5,3,67.5);
INSERT INTO "enrollments" VALUES(27,5,13,NULL);
INSERT INTO "enrollments" VALUES(28,5,15,86.9);
INSERT INTO "enrollments" VALUES(29,5,9,83.4);
INSERT INTO "enrollments" VALUES(30,5,1,NULL);
INSERT INTO "enrollments" VALUES(31,6,3,72.2);
INSERT INTO "enrollments" VALUES(32,6,12,88.6);
INSERT INTO "enrollments" VALUES(33,6,8,64.5);
INSERT INTO "enrollments" VALUES(34,6,2,93.9);
INSERT INTO "enrollments" VALUES(35,6,16,84.0);
INSERT INTO "enrollments" VALUES(36,6,5,83.2);
INSERT INTO "enrollments" VALUES(37,7,11,84.4);
INSERT INTO "enrollments" VALUES(38,7,1,NULL);
INSERT INTO "enrollments" VALUES(39,7,10,NULL);
INSERT INTO "enrollments" VALUES(40,7,4,NULL);
INSERT INTO "enrollments" VALUES(41,7,14,NULL);
INSERT INTO "enrollments" VALUES(42,7,6,81.6);
INSERT INTO "enrollments" VALUES(43,8,7,NULL);
INSERT INTO "enrollments" VALUES(44,8,9,69.0);
INSERT INTO "enrollments" VALUES(45,8,3,86.4);
INSERT INTO "enrollments" VALUES(46,8,12,80.4);
INSERT INTO "enrollments" VALUES(47,8,16,78.3);
INSERT INTO "enrollments" VALUES(48,8,2,85.7);
INSERT INTO "enrollments" VALUES(49,7,5,78.7);
INSERT INTO "enrollments" VALUES(50,2,15,85.1);
CREATE TABLE semesters (
    id   INTEGER PRIMARY KEY,
    term TEXT NOT NULL CHECK (term IN ('Fall', 'Spring', 'Summer')),
    year INTEGER NOT NULL,
    UNIQUE (term, year)
);
INSERT INTO "semesters" VALUES(1,'Spring',2024);
INSERT INTO "semesters" VALUES(2,'Summer',2024);
INSERT INTO "semesters" VALUES(3,'Fall',2024);
CREATE TABLE students (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
INSERT INTO "students" VALUES(1,'Abigail Shaffer','jpeterson@example.org');
INSERT INTO "students" VALUES(2,'Gabrielle Davis','howardmaurice@example.com');
INSERT INTO "students" VALUES(3,'Monica Herrera','smiller@example.net');
INSERT INTO "students" VALUES(4,'Shannon Ray','williamsjeremy@example.com');
INSERT INTO "students" VALUES(5,'Dr. Sharon James','xreid@example.org');
INSERT INTO "students" VALUES(6,'Daniel Adams','lynchgeorge@example.net');
INSERT INTO "students" VALUES(7,'Joel Nelson','gabriellecameron@example.org');
INSERT INTO "students" VALUES(8,'Andrew Stewart','carl95@example.org');
CREATE TABLE teachers (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
INSERT INTO "teachers" VALUES(1,'Allison Hill','donaldgarcia@example.net');
INSERT INTO "teachers" VALUES(2,'Angie Henderson','davisjesse@example.net');
INSERT INTO "teachers" VALUES(3,'Cristian Santos','lrobinson@example.com');
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
INSERT INTO "users" VALUES(1,'pfoster','student',1,NULL);
INSERT INTO "users" VALUES(2,'ithomas','student',2,NULL);
INSERT INTO "users" VALUES(3,'julieryan','student',3,NULL);
INSERT INTO "users" VALUES(4,'zhurst','student',4,NULL);
INSERT INTO "users" VALUES(5,'jeffrey28','student',5,NULL);
INSERT INTO "users" VALUES(6,'ddavis','student',6,NULL);
INSERT INTO "users" VALUES(7,'hernandezernest','student',7,NULL);
INSERT INTO "users" VALUES(8,'ycarlson','student',8,NULL);
INSERT INTO "users" VALUES(9,'dcarlson','teacher',NULL,1);
INSERT INTO "users" VALUES(10,'tasha01','teacher',NULL,2);
INSERT INTO "users" VALUES(11,'kayla51','teacher',NULL,3);
INSERT INTO "users" VALUES(12,'admin','admin',NULL,NULL);
CREATE INDEX idx_offerings_course    ON course_offerings(course_id);
CREATE INDEX idx_offerings_teacher   ON course_offerings(teacher_id);
CREATE INDEX idx_offerings_semester  ON course_offerings(semester_id);
CREATE INDEX idx_enrollments_student  ON enrollments(student_id);
CREATE INDEX idx_enrollments_offering ON enrollments(offering_id);
COMMIT;
