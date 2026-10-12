from datetime import time

from hourly_pay.domain.enums import WorkType
from hourly_pay.domain.models import TimeSlot

DEFAULT_DOCX_WORK_TYPE_LABELS = {
    WorkType.LECTURE: "лекционные",
    WorkType.PRACTICE: "практические",
    WorkType.LAB: "лабораторные",
}

DEFAULT_TIME_SLOTS = (
    TimeSlot(1, 1, time(8, 30), time(10, 5), "08:30-10:05"),
    TimeSlot(2, 2, time(10, 15), time(11, 50), "10:15-11:50"),
    TimeSlot(3, 3, time(12, 40), time(14, 15), "12:40-14:15"),
    TimeSlot(4, 4, time(14, 25), time(16, 0), "14:25-16:00"),
    TimeSlot(5, 5, time(16, 10), time(17, 45), "16:10-17:45"),
    TimeSlot(6, 6, time(17, 55), time(19, 30), "17:55-19:30"),
    TimeSlot(7, 7, time(19, 40), time(21, 15), "19:40-21:15"),
)
