from django.urls import path

from . import views

app_name = "exam"

urlpatterns = [
    path("book/", views.book, name="book"),
    path("bookings/<uuid:booking_id>/calendar.ics", views.booking_ics, name="booking_ics"),
]
