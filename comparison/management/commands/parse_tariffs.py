from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from comparison.models import Operator, TariffPlan
import requests
from bs4 import BeautifulSoup
import re
from decimal import Decimal
import logging
import html

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Парсит тарифы с сайтов операторов и сохраняет в TariffPlan'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--operator',
            type=str,
            help='Парсить только конкретного оператора (mts, megafon, beeline, t2)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительный парсинг даже если данные свежие',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Тестовый режим без сохранения в БД',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Очистить старые тарифы перед парсингом',
        )
    
    def handle(self, *args, **options):
        # Получаем всех операторов
        operators = Operator.objects.all()
        
        if options['operator']:
            operators = operators.filter(name__icontains=options['operator'])
        
        if options['clear']:
            self.stdout.write('🧹 Очищаем старые тарифы...')
            TariffPlan.objects.all().delete()
        
        self.stdout.write(f'Начинаем парсинг для {operators.count()} операторов...')
        
        total_parsed = 0
        for operator in operators:
            try:
                tariffs_count = self.parse_and_save_operator(operator, options)
                total_parsed += tariffs_count
                
                if options['dry_run']:
                    self.stdout.write(self.style.WARNING(
                        f'🧪 {operator.name}: найдено {tariffs_count} тарифов (режим теста)'
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ {operator.name}: сохранено {tariffs_count} тарифов'
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Ошибка при парсинге {operator.name}: {e}'))
                logger.exception(f"Error parsing {operator.name}")
        
        self.stdout.write(f'\n🎯 ИТОГО: обработано {total_parsed} тарифов')
    
    @transaction.atomic
    def parse_and_save_operator(self, operator, options):
        """Парсит и сохраняет тарифы оператора"""
        tariffs_data = self.parse_operator(operator)
        
        if options['dry_run']:
            return len(tariffs_data)
        
        saved_count = 0
        for tariff_data in tariffs_data:
            try:
                # Создаем или обновляем тариф
                tariff, created = TariffPlan.objects.update_or_create(
                    operator=operator,
                    name=tariff_data['name'],
                    defaults={
                        'description': tariff_data.get('description', ''),
                        'monthly_fee': tariff_data['monthly_fee'],
                        'data_volume': tariff_data.get('data_volume', 0),
                        'minutes_volume': tariff_data.get('minutes_volume', 0),
                        'overage_data_price': tariff_data.get('overage_data_price', 0),
                        'overage_minute_price': tariff_data.get('overage_minute_price', 0),
                        'is_archived': tariff_data.get('is_archived', False),
                    }
                )
                saved_count += 1
                
                if created:
                    self.stdout.write(f'   ➕ Создан: {tariff.name}')
                else:
                    self.stdout.write(f'   🔄 Обновлен: {tariff.name}')
                    
            except Exception as e:
                self.stdout.write(f'   ⚠️ Ошибка сохранения тарифа: {e}')
        
        return saved_count
    
    def parse_operator(self, operator):
        """Парсит сайт оператора и возвращает данные для TariffPlan"""
        tariffs = []
        
        if 'мтс' in operator.name.lower():
            tariffs = self.parse_mts(operator.website)
        elif 'мегафон' in operator.name.lower():
            tariffs = self.parse_megafon(operator.website)
        elif 'билайн' in operator.name.lower():
            tariffs = self.parse_beeline(operator.website)
        elif 'т2' in operator.name.lower() or 'tele2' in operator.name.lower():
            tariffs = self.parse_t2(operator.website)
        
        return tariffs
    
    def remove_tags(text):
        return re.sub(r'<.*?>', '', text)

    def extract_price(text):
        """Извлекает число из текста с ценой"""
        # Ищем числа с десятичными разделителями
        match = re.search(r'(\d+[\s,.]?\d*[\s,.]?\d*)', str(text))
        if match:
            # Заменяем запятые на точки и убираем пробелы
            price_str = match.group(1).replace(',', '.').replace(' ', '')
            try:
                return float(Decimal(price_str))
            except:
                return float(Decimal(0))
        return float(Decimal(0))
    
    def extract_data_gb(text):
        """Извлекает объем данных в ГБ"""
        # Ищем числа с указанием ГБ, GB, Гб
        text_lower = Command.remove_tags(str(text).lower().replace('&nbsp;', ' '))
        
        # Паттерны для поиска
        patterns = [
            r'безлимит гб',
            r'неограничен'
            r'(\d+[\s,.]?\d*)\s*(?:гб|gb|гигабайт)',
            r'(\d+)\s*гб',
            r'(\d+)\s*тб'
        ]
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                if 'тб' in text_lower and 'тб' in pattern:
                    multiplier = 1000
                else:
                    multiplier = 1
                if 'безлимит гб' in text_lower or 'неограничен' in text_lower:
                    return 999999  # Очень большое число для безлимита
                try:
                    return float(match.group(1).replace(',', '.')) * multiplier
                except:
                    continue
        
        return 0.0
    
    def extract_minutes(text):
        """Извлекает количество минут"""
        text_lower = Command.remove_tags(str(text).lower().replace('&nbsp;', ' '))
        
        patterns = [
            r'(\d+)\s*(?:минут|мин|min)',
            r'(\d+)\s*мин',
            r'безлимит минут',
            r'неограничен'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                if 'безлимит минут' in text_lower or 'неограничен' in text_lower:
                    return 999999
                try:
                    return int(match.group(1))
                except:
                    continue
        
        return 0
    
    def parse_mts(self, url):
        """Парсер для МТС"""
        try:
            response = requests.get(url, timeout=10, verify=False)
            soup = BeautifulSoup(response.content, 'html.parser')

            tariffs = []
            
            cards = soup.find_all("div", class_=["card"])
            for card in cards:
                tariff = {}
                tariff['name'] = card.find("a", "card-title__link").contents[0]
                tariff['description'] = str(card.find("div", "card-description card-description__margin card-element_margin-bottom").contents[0]).replace('\xa0', ' ')
                tariff['monthly_fee'] = int(card.find("span", "price-text").contents[0])
                data_and_minutes = str(card.find("ul", "features features__margin features__padding")).replace('&nbsp;', ' ')
                tariff['data_volume'] = Command.extract_data_gb(data_and_minutes)
                tariff['minutes_volume'] = Command.extract_minutes(data_and_minutes)
                tariff['is_archived'] = False

            return tariffs
            
        except Exception as e:
            self.stdout.write(f'Ошибка парсинга МТС: {e}')
            return []
    
    def parse_megafon(self, url):
        """Парсер для Мегафон"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            tariffs = []
            
            # Заглушка с тестовыми данными
            tariffs = [
            {
                'name': 'Мегафон Включайся!',
                'description': 'Тариф с пакетом интернета',
                'monthly_fee': self.extract_price('400 ₽'),
                'data_volume': self.extract_data_gb('15 ГБ'),
                'minutes_volume': self.extract_minutes('500 минут'),
                'overage_data_price': self.extract_price('150 руб/ГБ'),
                'overage_minute_price': self.extract_price('3 руб/мин'),
                'is_archived': False,
            },
            ]
            
            return tariffs
            
        except Exception as e:
            self.stdout.write(f'Ошибка парсинга МегаФон: {e}')
            return []

    
    def parse_beeline(self, url):

        def get_price_and_info(price_block):
                if not price_block:
                    return "0 ₽", ""
        
                p_discount = price_block.get('priceWithDiscount')
                p_full = price_block.get('priceWithoutDiscount')
        
                price_str = "0 ₽"
                if p_discount:
                    price_str = f"{p_discount.get('price')} {p_discount.get('unit')}"
                elif p_full:
                    price_str = f"{p_full.get('price')} {p_full.get('unit')}"
            
                conditions = price_block.get('conditionsText', '')
                conditions = html.unescape(conditions)
        
                return [price_str, conditions]
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            response = requests.get(url, headers=headers, timeout=15)

            soup = BeautifulSoup(response.text, 'html.parser')

            scripts = soup.find_all('script')
            target_script = None
    
            for script in scripts:
                if script.string and 'beeline.externalPages.TariffsCatalogLanding' in script.string:
                    target_script = script.string
                    break
    
            if not target_script:
                return "Скрипт с тарифами не найден"

            # Ищем Json, где формируется тарифы
            match = re.search(r'React\.createElement\(beeline\.externalPages\.TariffsCatalogLanding, ({.*?})\), document', target_script)
    
            if not match:
                return "Не удалось найти JSON"
            json_str = match.group(1)

            try:
                data = json.loads(json_str)
            except:
                return "Ошибка чтения JSON"
        
            parsed_tariffs = []
    
            raw_data = data.get('data', {})
    
            main_tariffs = raw_data.get('tariffsCards', [])
            for card in main_tariffs:
                price_and_info = get_price_and_info(card.get('priceBlock'))
                tariff = {
                    'name': card.get('cardTitle', {}).get('text'),
                    'description': card.get('presetText'),
                    'monthly_fee': Command.extract_price(price_and_info[0]),
                    'data_volume': Command.extract_data_gb(price_and_info[1]),
                    'minutes_volume': Command.extract_minutes(price_and_info[1]),
                    'is_archived': False
                    }
                parsed_tariffs.append(tariff)

            extra_sections = raw_data.get('extraTariffsCards', [])
            for section in extra_sections:
                for card in section.get('tariffs', []):
                    price_and_info = get_price_and_info(card.get('priceBlock'))
                    tariff = {
                    'name': card.get('cardTitle', {}).get('text'),
                    'description': card.get('presetText'),
                    'monthly_fee': Command.extract_price(price_and_info[0]),
                    'data_volume': Command.extract_data_gb(card.get('presetText')),
                    'minutes_volume': Command.extract_minutes(card.get('presetText')),
                    'is_archived': False
                    }
                    parsed_tariffs.append(tariff)

                    return parsed_tariffs
            
        except Exception as e:
            self.stdout.write(f'Ошибка парсинга Билайн: {e}')
            return []
    
    def parse_t2(self, url):
        """Парсер для Т2 (Tele2)"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            tariffs = []
            
            # Заглушка с тестовыми данными
            tariffs = [
            {
                'name': 'Т2 Мой Онлайн',
                'description': 'Популярный тариф Tele2',
                'monthly_fee': self.extract_price('350 ₽'),
                'data_volume': self.extract_data_gb('12 ГБ'),
                'minutes_volume': self.extract_minutes('400 минут'),
                'overage_data_price': self.extract_price('80 руб/ГБ'),
                'overage_minute_price': self.extract_price('2.5 руб/мин'),
                'is_archived': False,
            },
            ]
            
            return tariffs
            
        except Exception as e:
            self.stdout.write(f'Ошибка парсинга Т2: {e}')
            return []