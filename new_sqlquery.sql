SELECT current_database();

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;



SELECT * FROM programs;
SELECT * FROM batches;
SELECT * FROM intakes;
SELECT * FROM sections;
SELECT * FROM modules;
SELECT * FROM module_offerings;
SELECT * FROM module_offering_sections;







SELECT
    mos.id,
    m.code AS module_code,
    m.title AS module_title,
    i.code AS intake,
    mo.semester_number AS semester,
    b.name AS batch,
    s.name AS section
FROM module_offering_sections mos
JOIN module_offerings mo
    ON mo.id = mos.module_offering_id
JOIN modules m
    ON m.id = mo.academic_module_id
JOIN intakes i
    ON i.id = mo.intake_id
JOIN batches b
    ON b.id = mo.batch_id
JOIN sections s
    ON s.id = mos.section_id
ORDER BY s.name, m.code;
