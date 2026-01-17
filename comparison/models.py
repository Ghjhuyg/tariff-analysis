from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class Operator(models.Model):
    """
    Оператор связи (МТС, МегаФон, Билайн и т.д.)
    """
    name = models.CharField('Название оператора', max_length=100, unique=True)
    logo = models.CharField('Путь до логотипа', max_length=100, blank=True)
    website = models.URLField('Сайт для парсинга', max_length=200)
    color = models.CharField('Брендовый цвет', max_length=7, default='#007bff', 
                            help_text='HEX-код цвета, например, #ff0000 для красного')

    class Meta:
        verbose_name = 'Оператор'
        verbose_name_plural = 'Операторы'
        ordering = ['name']

    def __str__(self):
        return self.name
    
    @property
    def logo_url(self):
        """Генерируем URL до логотипа"""
        if self.logo:
            return f'/static/comparison/operators_logo/{self.logo}'
        return None
    
    @property
    def logo_path(self):
        """Полный путь к файлу"""
        import os
        from django.conf import settings
        if self.logo:
            return os.path.join(
                settings.BASE_DIR,
                'comparison',
                'static',
                'comparison',
                'operators_logo',
                self.logo
            )
        return None


class TariffPlan(models.Model):
    """
    Тарифный план оператора
    """
    name = models.CharField('Название тарифа', max_length=200)
    operator = models.ForeignKey(
        Operator,
        on_delete=models.CASCADE,
        related_name='tariffs',
        verbose_name='Оператор'
    )
    description = models.TextField('Описание условий', blank=True)
    monthly_fee = models.DecimalField(
        'Абонентская плата',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    data_volume = models.FloatField(
        'Включено ГБ',
        default=0,
        validators=[MinValueValidator(0)]
    )
    minutes_volume = models.IntegerField(
        'Включено минут',
        default=0,
        validators=[MinValueValidator(0)]
    )
    is_archived = models.BooleanField(
        'Архивный тариф',
        default=False,
        help_text='Не отображается в основном поиске'
    )

    class Meta:
        verbose_name = 'Тарифный план'
        verbose_name_plural = 'Тарифные планы'
        ordering = ['operator', 'monthly_fee']
        unique_together = ['operator', 'name']

    def __str__(self):
        return f'{self.operator.name} - {self.name}'


class UserProfile(models.Model):
    """
    Профиль пользователя с плановыми потребностями
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    avg_monthly_data = models.FloatField(
        'Плановый расход ГБ/мес',
        default=5,
        validators=[MinValueValidator(0)]
    )
    avg_monthly_minutes = models.IntegerField(
        'Плановый расход минут/мес',
        default=200,
        validators=[MinValueValidator(0)]
    )
    current_tariff = models.ForeignKey(
        TariffPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscribers',
        verbose_name='Текущий тариф'
    )

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        return f'Профиль {self.user.username}'


class MonthlyConsumption(models.Model):
    """
    Журнал фактического потребления (ручной ввод пользователя)
    """
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='consumption_history'
    )
    year = models.IntegerField('Год', validators=[MinValueValidator(2020)])
    month = models.IntegerField('Месяц', validators=[MinValueValidator(1), MaxValueValidator(12)])
    actual_data_used = models.FloatField(
        'Фактический расход ГБ',
        validators=[MinValueValidator(0)]
    )
    actual_minutes_used = models.IntegerField(
        'Фактический расход минут',
        validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = 'Запись о потреблении'
        verbose_name_plural = 'Журнал потребления'
        ordering = ['-year', '-month']
        unique_together = ['user_profile', 'year', 'month']

    def __str__(self):
        return f'{self.user_profile.user.username} - {self.year}-{self.month:02d}'


class TariffComparison(models.Model):
    """
    История сравнений и рекомендаций тарифов
    """
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='comparisons'
    )
    tariff_plan = models.ForeignKey(
        TariffPlan,
        on_delete=models.CASCADE,
        related_name='comparisons'
    )
    calculated_monthly_cost = models.DecimalField(
        'Рассчитанная стоимость',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    user_data_input = models.FloatField(
        'Введённые ГБ',
        validators=[MinValueValidator(0)]
    )
    user_minutes_input = models.IntegerField(
        'Введённые минуты',
        validators=[MinValueValidator(0)]
    )
    is_recommended = models.BooleanField(
        'Рекомендовано',
        default=False
    )
    comparison_date = models.DateTimeField(
        'Дата сравнения',
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Результат сравнения'
        verbose_name_plural = 'История сравнений'
        ordering = ['-comparison_date']

    def __str__(self):
        status = "Рек." if self.is_recommended else "Срав."
        return f'{self.user_profile.user.username} - {self.tariff_plan.name} ({status})'