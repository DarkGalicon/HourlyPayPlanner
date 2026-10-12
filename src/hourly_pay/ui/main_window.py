from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.availability_settings import AvailabilitySettingsService
from hourly_pay.application.calculate_teacher import TeacherCalculationService
from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.application.distribution_export import DistributionExportService
from hourly_pay.application.import_workload import ImportWorkloadService
from hourly_pay.application.monthly_planning import MonthlyPlanningService
from hourly_pay.application.schedule_month import ScheduleMonthService
from hourly_pay.application.selection_service import SelectionService
from hourly_pay.application.semester_settings import SemesterSettingsService
from hourly_pay.application.statement_export import StatementExportService
from hourly_pay.application.teacher_settings import TeacherSettingsService
from hourly_pay.ui.pages.availability_page import AvailabilityPage
from hourly_pay.ui.pages.calculation_page import CalculationPage
from hourly_pay.ui.pages.calendar_page import CalendarPage
from hourly_pay.ui.pages.distribution_page import DistributionPage
from hourly_pay.ui.pages.documents_page import DocumentsPage
from hourly_pay.ui.pages.import_page import ImportPage
from hourly_pay.ui.pages.monthly_page import MonthlyPage
from hourly_pay.ui.pages.schedule_page import SchedulePage
from hourly_pay.ui.pages.selection_page import SelectionPage
from hourly_pay.ui.pages.semester_page import SemesterPage
from hourly_pay.ui.pages.teacher_page import TeacherPage
from hourly_pay.ui.theme import apply_workspace_appearance

NAVIGATION_TITLES = (
    "Импорт",
    "Преподаватели",
    "Расчет",
    "План распределения",
    "Расписание месяца",
    "Документы",
    "Настройки",
)
SECTION_DESCRIPTIONS = (
    "Добавьте индивидуальные планы XLSX и проверьте распознанные данные.",
    "Подтвердите ставку и укажите источники для расчёта нагрузки.",
    "Проверьте лимит почасовки и предупреждения импорта.",
    "Выберите занятия и распределите выбранные часы по месяцам.",
    "Задайте доступность, создайте расписание и проверьте занятия.",
    "Сформируйте заявление по сохранённому расписанию месяца.",
    "Настройте календарь и даты допуска практик и лабораторных.",
)
WORKFLOW_STEP_COUNT = 6


class MainWindow(QMainWindow):
    def __init__(
        self,
        import_service: ImportWorkloadService,
        teacher_settings: TeacherSettingsService,
        calculation_service: TeacherCalculationService,
        selection_service: SelectionService,
        monthly_service: MonthlyPlanningService,
        availability_service: AvailabilitySettingsService,
        calendar_service: CalendarSettingsService,
        schedule_service: ScheduleMonthService | None = None,
        semester_service: SemesterSettingsService | None = None,
        statement_service: StatementExportService | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Почасовая нагрузка")
        self.resize(1320, 840)
        self.setMinimumSize(1030, 680)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("mainNavigation")
        self.tabs.tabBar().setObjectName("mainTabBar")
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.import_page = ImportPage(import_service, self)
        self.teacher_page = TeacherPage(teacher_settings, self)
        self.calculation_page = CalculationPage(calculation_service, self)
        self.selection_page = SelectionPage(selection_service, self)
        self.monthly_page = MonthlyPage(monthly_service, self)
        self.availability_page = AvailabilityPage(availability_service, self)
        self.calendar_page = CalendarPage(calendar_service, self)
        self.semester_page = SemesterPage(semester_service, self) if semester_service else None
        self.schedule_page = SchedulePage(schedule_service, self) if schedule_service else None
        self.documents_page = DocumentsPage(statement_service, self) if statement_service else None
        self.distribution_page = DistributionPage(
            DistributionExportService(monthly_service, teacher_settings), self
        )
        self.documents_tabs = QTabWidget(self)
        self.documents_tabs.setObjectName("documentsTabs")
        if self.documents_page is not None:
            self.documents_tabs.addTab(self.documents_page, "Заявление DOCX")
        self.documents_tabs.addTab(self.distribution_page, "Распределение XLSX")
        self.plan_tabs = QTabWidget(self)
        self.plan_tabs.setObjectName("planTabs")
        self.plan_tabs.addTab(self.selection_page, "Выбор нагрузки")
        self.plan_tabs.addTab(self.monthly_page, "По месяцам")
        self.schedule_tabs = QTabWidget(self)
        self.schedule_tabs.setObjectName("scheduleTabs")
        self.schedule_tabs.addTab(self.availability_page, "Доступность")
        self.schedule_tabs.addTab(
            self.schedule_page
            if self.schedule_page is not None
            else QLabel("Генерация занятий будет подключена на следующем этапе.", self),
            "Занятия",
        )
        self.settings_tabs = QTabWidget(self)
        self.settings_tabs.setObjectName("settingsTabs")
        self.settings_tabs.addTab(self.calendar_page, "Календарь")
        if self.semester_page is not None:
            self.settings_tabs.addTab(self.semester_page, "Начало семестра")
        self.import_page.imports_saved.connect(self.teacher_page.refresh)
        self.import_page.imports_saved.connect(self.calculation_page.refresh)
        self.import_page.imports_saved.connect(self.selection_page.refresh)
        self.import_page.imports_saved.connect(self.monthly_page.refresh)
        self.import_page.imports_saved.connect(self.availability_page.refresh)
        if self.semester_page is not None:
            self.import_page.imports_saved.connect(self.semester_page.refresh)
        self.teacher_page.settings_saved.connect(self.calculation_page.refresh)
        self.teacher_page.settings_saved.connect(self.selection_page.refresh)
        self.teacher_page.settings_saved.connect(self.monthly_page.refresh)
        self.teacher_page.settings_saved.connect(self.distribution_page.refresh)
        self.teacher_page.settings_saved.connect(self.availability_page.refresh)
        self.selection_page.selections_saved.connect(self.monthly_page.refresh)
        self.selection_page.selections_saved.connect(self.distribution_page.refresh)
        self.monthly_page.plan_saved.connect(self.distribution_page.refresh)
        self.import_page.imports_saved.connect(self.distribution_page.refresh)
        if self.schedule_page is not None:
            self.import_page.imports_saved.connect(self.schedule_page.refresh)
            self.teacher_page.settings_saved.connect(self.schedule_page.refresh)
            self.monthly_page.plan_saved.connect(self.schedule_page.refresh)
        if self.documents_page is not None:
            self.import_page.imports_saved.connect(self.documents_page.refresh)
            self.teacher_page.settings_saved.connect(self.documents_page.refresh)
            self.monthly_page.plan_saved.connect(self.documents_page.refresh)
            self.tabs.currentChanged.connect(self._refresh_documents)

        for title in NAVIGATION_TITLES:
            if title == "Преподаватели":
                page = self.teacher_page
            elif title == "Импорт":
                page = self.import_page
            elif title == "Расчет":
                page = self.calculation_page
            elif title == "План распределения":
                page = self.plan_tabs
            elif title == "Расписание месяца":
                page = self.schedule_tabs
            elif title == "Настройки":
                page = self.settings_tabs
            elif title == "Документы" and self.documents_page is not None:
                page = self.documents_tabs
            else:
                page = QLabel(f"Раздел «{title}» будет подключен на следующем этапе.")
                page.setObjectName(f"placeholder_{title}")
                page.setMargin(24)
            self.tabs.addTab(page, title)
            self.tabs.setTabToolTip(
                self.tabs.count() - 1, SECTION_DESCRIPTIONS[self.tabs.count() - 1]
            )

        for page in (
            self.import_page,
            self.teacher_page,
            self.calculation_page,
            self.selection_page,
            self.monthly_page,
            self.availability_page,
            self.schedule_page,
            self.documents_page,
            self.distribution_page,
            self.calendar_page,
            self.semester_page,
        ):
            if page is not None and page.layout() is not None:
                page.layout().setContentsMargins(22, 20, 22, 20)
                page.layout().setSpacing(12)

        shell = QWidget(self)
        shell.setObjectName("appShell")
        header = QWidget(shell)
        header.setObjectName("headerCard")
        self.header_eyebrow = QLabel("ПОЧАСОВАЯ НАГРУЗКА  /  ПЛАНИРОВЩИК", header)
        self.header_eyebrow.setObjectName("headerEyebrow")
        self.header_title = QLabel(header)
        self.header_title.setObjectName("headerTitle")
        self.header_description = QLabel(header)
        self.header_description.setObjectName("headerDescription")
        self.header_description.setWordWrap(True)
        self.step_badge = QLabel(header)
        self.step_badge.setObjectName("stepBadge")
        self.step_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_button = QPushButton(header)
        self.next_button.setObjectName("nextStepButton")
        self.next_button.clicked.connect(self._go_next)
        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        header_text.addWidget(self.header_eyebrow)
        header_text.addWidget(self.header_title)
        header_text.addWidget(self.header_description)
        header_actions = QVBoxLayout()
        header_actions.setSpacing(8)
        header_actions.addWidget(self.step_badge)
        header_actions.addWidget(self.next_button)
        header_actions.addStretch()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 17, 22, 17)
        header_layout.addLayout(header_text, 1)
        header_layout.addLayout(header_actions)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(20, 18, 20, 18)
        shell_layout.setSpacing(14)
        shell_layout.addWidget(header)
        shell_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(shell)
        self.tabs.currentChanged.connect(self._update_header)
        self.tabs.setCurrentWidget(self.import_page)
        self._update_header(self.tabs.currentIndex())
        apply_workspace_appearance(self)
        self.import_page.resize_preview_columns()

    def _update_header(self, index: int) -> None:
        if not 0 <= index < len(NAVIGATION_TITLES):
            return
        self.header_title.setText(NAVIGATION_TITLES[index])
        self.header_description.setText(SECTION_DESCRIPTIONS[index])
        is_workflow_step = index < WORKFLOW_STEP_COUNT
        self.step_badge.setText(
            f"ШАГ {index + 1:02d} / {WORKFLOW_STEP_COUNT:02d}"
            if is_workflow_step else "ПАРАМЕТРЫ"
        )
        self.next_button.setVisible(index < WORKFLOW_STEP_COUNT - 1)
        if index < WORKFLOW_STEP_COUNT - 1:
            self.next_button.setText(f"Далее: {NAVIGATION_TITLES[index + 1]}  →")

    def _go_next(self) -> None:
        index = self.tabs.currentIndex()
        if 0 <= index < WORKFLOW_STEP_COUNT - 1:
            self.tabs.setCurrentIndex(index + 1)

    def _refresh_documents(self, index: int) -> None:
        if self.documents_page is not None and self.tabs.widget(index) is self.documents_tabs:
            self.documents_page.refresh()
            self.distribution_page.refresh()
