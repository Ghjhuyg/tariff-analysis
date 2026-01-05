from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class Operator(models.Model):
    """
    Оператор связи (МТС, МегаФон, Билайн и т.д.)
    """
    name = models.CharField('Название оператора', max_length=100, unique=True)
    logo = models.ImageField('Логотип', upload_to='operators/logo/', blank=True, null=True)
    website = models.URLField('Сайт для парсинга', max_length=200)
    color = models.CharField('Брендовый цвет', max_length=7, default='#007bff', 
                            help_text='HEX-код цвета, например, #ff0000 для красного')

    class Meta:
        verbose_name = 'Оператор'
        verbose_name_plural = 'Операторы'
        ordering = ['name']

    def __str__(self):
        return self.name


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
    overage_data_price = models.DecimalField(
        'Цена за дополнительный ГБ',
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    overage_minute_price = models.DecimalField(
        'Цена за дополнительную минуту',
        max_digits=10,
        decimal_places=2,
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

    def calculate_cost_for_user(self, data_gb, minutes):
        """
        Рассчитывает стоимость тарифа для пользователя с заданным потреблением
        """
        base_cost = self.monthly_fee
        extra_data = max(0, data_gb - self.data_volume)
        extra_minutes = max(0, minutes - self.minutes_volume)
        total_cost = base_cost + (extra_data * self.overage_data_price) + (extra_minutes * self.overage_minute_price)
        return total_cost


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