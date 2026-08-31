from app.modules.operations.email_templates import attendance_alert_email, invitation_email


def test_invitation_email_is_branded_and_keeps_a_plain_text_fallback():
    subject, plain, html = invitation_email(
        student_name="Aayush Karki",
        email="aayush@example.com",
        setup_url="https://example.test/activate?token=secure-token",
        expires_hours=168,
        welcome=True,
        has_account=True,
    )

    assert subject == "Your AntimBench student account is ready"
    assert "Aayush Karki" in plain and "secure-token" in plain
    assert "AntimBench" in html
    assert "Hello <strong>Aayush Karki</strong>" in html
    assert "Complete account setup" in html


def test_attendance_alert_email_includes_module_details_and_report_link():
    subject, plain, html = attendance_alert_email(
        student_name="Aayush Karki",
        module_name="Advanced Database Systems",
        module_code="CT004-3-3",
        class_types=["Lecture"],
        percentage=62.5,
        threshold=75,
        total_classes=8,
    )

    assert subject == "Attendance alert: action needed"
    assert "Advanced Database Systems" in plain and "CT004-3-3" in plain
    assert "62.50%" in html and "75%" in html
    assert "student/reports" in html
