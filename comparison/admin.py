from django.contrib import admin
from .models import Operator, TariffPlan, UserProfile, MonthlyConsumption, TariffComparison

@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ('name', 'website')
    search_fields = ('name',)

@admin.register(TariffPlan)
class TariffPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'operator', 'monthly_fee', 'data_volume', 'minutes_volume', 'is_archived')
    list_filter = ('operator', 'is_archived')
    search_fields = ('name', 'operator__name')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'avg_monthly_data', 'avg_monthly_minutes', 'current_tariff')
    search_fields = ('user__username',)

@admin.register(MonthlyConsumption)
class MonthlyConsumptionAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'year', 'month', 'actual_data_used', 'actual_minutes_used')
    list_filter = ('year', 'month')

@admin.register(TariffComparison)
class TariffComparisonAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'tariff_plan', 'calculated_monthly_cost', 'is_recommended', 'comparison_date')
    list_filter = ('is_recommended', 'comparison_date')