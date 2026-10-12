# 04. Data Model

Все часы и ставки в Python — `Decimal`.

## AcademicYear

```text
id
name                # "2026-2027"
is_active
```

## Teacher

```text
id
full_name
imported_name        # исходное ФИО из XLSX для повторного импорта после правки ФИО
effective_rate      # вручную подтверждаемая ставка для формулы 900 ч/ставку
department           nullable
degree               nullable
title                nullable
position             nullable
birth_date            nullable
address               nullable
passport_series       nullable
passport_number       nullable
passport_issued_by    nullable
passport_issue_date   nullable
snils                 nullable
inn                   nullable
created_at
updated_at
```

Все реквизиты, кроме ФИО, необязательны. Пользователь редактирует их в карточке
преподавателя; приложение хранит их локально для заполнения DOCX.

## WorkloadSource

Один импортированный XLSX.

```text
id
teacher_id
academic_year_id
original_filename
file_sha256
employment_type      # строка из титульного листа
reported_rate         # ставка, указанная в конкретном файле
reported_total_hours
include_in_fact       # пользователь может менять
imported_at
parser_version        # "nagr_xlsx_v1"
```

## WorkloadItem

Нормализованная единица нагрузки.

```text
id
source_id
teacher_id
academic_year_id
study_form            # FULL_TIME / CORRESPONDENCE
semester              # 1 / 2 / null
session_period         # для Zaoch: UST / WINTER / SUMMER / null
source_row_number
group_name
course
stream
student_count
faculty
discipline
work_type              # LECTURE / PRACTICE / LAB / CONTROL / COURSEWORK / ...
control_type            nullable
hours
row_total_hours         nullable
is_idpo
raw_context_json        # минимальный debug snapshot без лишних персональных данных
```

Одна строка Excel может дать несколько `WorkloadItem`, если в ней заполнено несколько видов нагрузки.

## ImportWarning

```text
id
source_id
source_row_number nullable
code
severity             # INFO / WARNING / ERROR
message
raw_value nullable
resolved
```

Рекомендуемые codes:

```text
UNKNOWN_CONTROL_KIND
UNKNOWN_WORK_TYPE
UNEXPLAINED_TOTAL_DIFF
MISSING_GROUP
MISSING_DISCIPLINE
NON_EVEN_AUDITORY_HOURS
UNRECOGNIZED_FORMAT
DUPLICATE_IMPORT
```

## HourlyCalculation

Можно вычислять на лету; отдельная таблица необязательна. Если сохранять snapshot:

```text
teacher_id
academic_year_id
effective_rate
norm_hours
fact_hours
idpo_hours
net_hours
excess_hours
eligible_auditory_hours
hourly_limit
calculated_at
```

## HourlySelection

Ручной выбор пользователя.

```text
id
teacher_id
workload_item_id
selected_hours
prefer_evening        # пожелание вечерних слотов для выбранной строки
```

`selected_hours` должно быть кратно 2 и <= `WorkloadItem.hours`.

`HourlyLimitPermission` хранит `teacher_id`, `academic_year_id` и
`allow_limit_excess` для явного разрешения превышения расчётного лимита.
Максимум 300 часов сохраняется.

## MonthlyAllocation

```text
id
hourly_selection_id
month                 # 1..12
year
hours                  # 0 или кратно 2
```

Сумма allocation по selection = selected_hours.

## TeacherAvailability

Поддержать как минимум три вида правил:

```text
WEEKDAY_ALLOWED_SLOTS
EXCLUDED_DATE
DATE_ALLOWED_SLOTS
```

Можно реализовать нормализованными таблицами или JSON, но бизнес-слой должен работать с типизированными объектами.

## CalendarOverride

Глобальное явное правило для календарной даты, сохраняемое отдельно от базового
календаря праздников `holidays`.

```text
target_date            # уникальная дата
is_working             # true: рабочая вопреки базовому празднику; false: нерабочая
```

Выходные остаются недоступными независимо от `is_working`.

## SemesterPracticeStart

Единая настройка разгона для учебного года и семестра (1 или 2):

```text
academic_year_id       # FK, часть составного PK
semester              # часть составного PK
first_allowed_date    # первая допустимая дата Пр/Лаб
```

Отсутствующая запись означает, что дата не подтверждена; генерация Пр/Лаб
запрещена, лекции не затронуты. Дата должна относиться к месяцам семестра.

## Lesson

Сгенерированная строка будущего заявления.

```text
id
teacher_id
monthly_allocation_id
date
time_slot_id
group_name
discipline
work_type
hours = 2
generation_batch_id
manual_override bool
```

Уникальное ограничение:

```text
UNIQUE(teacher_id, date, time_slot_id)
```

## GenerationBatch

```text
id
teacher_id
year
month
seed nullable
created_at
```

Позволяет перегенерировать расписание и понимать, какие строки относятся к одной генерации.
