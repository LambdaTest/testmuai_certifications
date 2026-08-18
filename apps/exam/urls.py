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
]
