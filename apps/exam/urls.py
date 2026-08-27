from django.urls import path

from . import views

app_name = "exam"

urlpatterns = [
    path("book/", views.book, name="book"),
    path("bookings/<uuid:booking_id>/calendar.ics", views.booking_ics, name="booking_ics"),
    path("bookings/<uuid:booking_id>/reschedule/", views.reschedule, name="reschedule"),
    path("myassessments/<str:status>", views.my_assessments, name="myassessment"),
    path("assessment/<uuid:booking_id>", views.explore_assessment, name="explore_assessment"),
    path("bookings/<uuid:booking_id>/cancel/", views.cancel_booking, name="cancel_booking"),
    path("bookings/<uuid:booking_id>/cancelpage/", views.cancel_booking_page, name="cancel_booking_page"),
    path("assign_grading/", views.assign_grading, name="assign_grading"),
    path("subject_center/create_subject/", views.create_subject, name="create_subject"),
    path("subject_center/explore_subjects/", views.explore_subjects, name="explore_subjects"),
    path("subject_center/edit_subject/<int:subject_id>/", views.edit_subject, name="edit_subject"),
    path("exam_center/explore_exams/", views.explore_exams, name="explore_exams"),
    path("exam_center/add_exam/", views.add_exam, name="add_exam"),
    path("exam_center/edit_exam/<int:exam_id>/", views.edit_exam, name="edit_exam"),
    path("question_center/add_question/", views.add_question, name="add_question"),
    path("question_center/question_bank/", views.question_bank, name="question_bank"),
]
