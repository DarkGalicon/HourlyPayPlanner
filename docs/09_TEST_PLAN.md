# 09. Test Plan

## 1. Unit tests — расчет

Проверить:

- 1 ставка = 900;
- 0.5 ставки = 450;
- отрицательное превышение → 0;
- IDPO вычитается;
- cap 300;
- cap по количеству eligible auditory hours;
- Decimal arithmetic без float drift.

## 2. Unit tests — выбор часов

- selected_hours = 0 допустимо;
- selected_hours кратно 2;
- selected_hours > available запрещено;
- odd selected_hours запрещено;
- сумма выбранного <= hourly limit.

## 3. Unit tests — месяцы

- I семестр не допускает январь–май;
- II семестр не допускает сентябрь–декабрь;
- январь II семестра зависит от флага;
- сумма месяцев совпадает с selected_hours;
- каждая ячейка кратна 2.

## 4. Unit tests — scheduler

Проверить:

- создается `hours/2` занятий;
- только Пн–Пт;
- нет excluded dates;
- нет запрещенных slots;
- нет duplicate `(teacher, date, slot)`;
- gaps между слотами не считаются ошибкой;
- capacity error корректный;
- fixed seed дает одинаковый результат;
- reroll с другим seed меняет результат при наличии альтернатив.
- лекции предпочитают первые две недели, но допустимы позже;
- первый курс заканчивает занятия до 16:00 включительно при генерации и переносе;
- заочная и явно отмеченная очно-заочная строка предпочитают вечер;
- дневные слоты остаются допустимы при нехватке вечерних.

## 5. XLSX importer tests

На приватных fixture-файлах проверить:

- staff / internal part-time / hourly type распознается из титульного;
- ставка распознается;
- academic year распознается;
- AutumnOch → semester 1;
- SpringOch → semester 2;
- Zaoch импортируется отдельно;
- lecture/practice/lab columns mapping;
- control type + hours;
- row total не задваивает часы;
- пустая строка с потоком не создает нулевую нагрузку;
- sample values как strings конвертируются в Decimal;
- отсутствие Zaoch не ломает импорт;
- duplicate SHA detection;
- incompatible workbook → controlled error.

## 6. Anomaly tests

- `row_total != sum(mapped)` → warning;
- unknown control kind → warning;
- known `Эк`, `Зч` → не anomaly сами по себе;
- missing discipline with hours → warning/error;
- IDPO prefix recognized.

## 7. DOCX tests

Автотесты:

- output file создается;
- исходный template не изменяется;
- число строк занятий совпадает с lessons;
- все hours = 2;
- HOURS_SUM корректен;
- FIO вставлено;
- финансовые/паспортные поля не заполняются случайно.

Дополнительно visual/manual smoke test на:

- Windows + Microsoft Word;
- macOS + Microsoft Word или LibreOffice;
- длинные названия дисциплин;
- 1 строка;
- много строк / перенос на вторую страницу.

## 8. GUI tests

Проверить явную единую дату допуска Пр/Лаб: отсутствие настройки блокирует их
генерацию; до даты доступны только лекции; после даты соблюдаются доступность и
ёмкость; сохранённые занятия нельзя сделать невалидными изменением настройки.

Проверить ручной перенос: корректная дата/слот сохраняются с `manual_override`,
праздник, выходной, занятый слот, другая дата месяца и ранняя Пр/Лаб отклоняются
без изменения расписания. Очистка месяца требует подтверждения, удаляет только
занятия, сохраняет помесячный план и допускает повторную генерацию.

pytest-qt для критичных flows:

- import preview;
- calculation card;
- cannot save invalid monthly allocation;
- conflict shown in schedule editor;
- export button disabled пока schedule invalid.

## 9. Cross-platform CI

Рекомендуемый минимум GitHub Actions:

```text
windows-latest: tests + build smoke
macos-latest:   tests + build smoke
```

Секретные реальные fixtures в CI не использовать. Создать synthetic fixtures.
