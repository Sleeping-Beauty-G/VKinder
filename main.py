"""
VKinder - бот для поиска людей для знакомств в ВКонтакте
Основной файл приложения
"""

import os
import logging
from datetime import datetime
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

from database import Database
from vk_service import VKService
from config import VK_GROUP_TOKEN, VK_USER_TOKEN, DB_CONFIG

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vkinder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class VKinderBot:
    """Главный класс бота VKinder"""

    def __init__(self):
        """Инициализация бота"""
        self.vk_session = vk_api.VkApi(token=VK_GROUP_TOKEN)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkLongPoll(self.vk_session)
        self.db = Database(**DB_CONFIG)

        # Создаём отдельную сессию для поиска (с пользовательским токеном)
        self.user_session = vk_api.VkApi(token=VK_USER_TOKEN)
        self.vk_service = VKService(self.vk_session, self.user_session)

        # Состояния пользователей
        self.user_states = {}

    def get_main_keyboard(self):
        """Создание главной клавиатуры"""
        keyboard = VkKeyboard(one_time=True)
        keyboard.add_button('🔍 Поиск', VkKeyboardColor.PRIMARY)
        keyboard.add_button('❤️ Избранные', VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button('Настройки', VkKeyboardColor.SECONDARY)  # Убрали эмодзи
        keyboard.add_button('ℹ️ Помощь', VkKeyboardColor.SECONDARY)
        return keyboard.get_keyboard()

    def get_search_keyboard(self):
        """Создание клавиатуры для поиска"""
        keyboard = VkKeyboard(one_time=True)
        keyboard.add_button('❤️ В избранное', VkKeyboardColor.POSITIVE)
        keyboard.add_button('👎 В черный список', VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button('▶️ Следующий', VkKeyboardColor.PRIMARY)
        keyboard.add_button('🏠 Главное меню', VkKeyboardColor.SECONDARY)
        return keyboard.get_keyboard()

    def get_settings_keyboard(self):
        """Создание клавиатуры для настроек"""
        keyboard = VkKeyboard(one_time=True)
        keyboard.add_button('🚻 Изменить пол', VkKeyboardColor.PRIMARY)
        keyboard.add_button('🎂 Изменить возраст', VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button('🏙️ Изменить город', VkKeyboardColor.PRIMARY)
        keyboard.add_button('📊 Показать настройки', VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button('🏠 Главное меню', VkKeyboardColor.SECONDARY)
        return keyboard.get_keyboard()

    def get_favorites_keyboard(self):
        """Создание клавиатуры для избранных"""
        keyboard = VkKeyboard(one_time=True)
        keyboard.add_button('📋 Показать избранных', VkKeyboardColor.PRIMARY)
        keyboard.add_button('🗑️ Очистить избранных', VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button('🏠 Главное меню', VkKeyboardColor.SECONDARY)
        return keyboard.get_keyboard()

    def send_message(self, user_id, message, keyboard=None, attachment=None):
        """Отправка сообщения пользователю"""
        try:
            self.vk.messages.send(
                user_id=user_id,
                message=message,
                keyboard=keyboard,
                attachment=attachment,
                random_id=get_random_id()
            )
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

    def handle_start(self, user_id):
        """Обработка команды /start"""
        try:
            # Получаем информацию о пользователе
            user_info = self.vk_service.get_user_info(user_id)
            if not user_info:
                self.send_message(user_id, "❌ Не удалось получить информацию о вашем профиле.")
                return

            # Сохраняем пользователя в БД
            self.db.add_user(user_info)

            welcome_msg = f"""👋 Привет, {user_info['first_name']}!

🤖 Я VKinder - бот для поиска людей для знакомств в ВКонтакте!

✨ Что я умею:
• Искать людей для знакомств по вашим параметрам
• Показывать самые популярные фото профилей
• Сохранять понравившихся людей в избранное
• Добавлять неподходящих в черный список

🚀 Давайте начнем! Выберите действие:"""

            self.send_message(user_id, welcome_msg, self.get_main_keyboard())

        except Exception as e:
            logger.error(f"Ошибка в handle_start для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Произошла ошибка при запуске. Попробуйте позже.")

    def handle_search(self, user_id):
        """Обработка поиска людей"""
        try:
            # Получаем информацию о пользователе из БД (здесь хранятся настройки!)
            user_info = self.db.get_user(user_id)
            if not user_info:
                self.send_message(user_id, "❌ Сначала нужно запустить бота командой /start")
                return

            # Ищем людей для знакомств
            self.send_message(user_id, "🔍 Ищу подходящих людей для знакомства...")

            candidates = self.vk_service.search_people(user_info)
            if not candidates:
                self.send_message(
                    user_id,
                    "😔 К сожалению, не нашел подходящих кандидатов. Попробуйте изменить параметры поиска в настройках.",
                    self.get_main_keyboard()
                )
                return

            # Сохраняем кандидатов в состоянии пользователя
            self.user_states[user_id] = {
                'candidates': candidates,
                'current_index': 0,
                'mode': 'search'
            }

            self.show_next_candidate(user_id)

        except Exception as e:
            logger.error(f"Ошибка в handle_search для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при поиске. Попробуйте позже.")

    def show_next_candidate(self, user_id):
        """Показ следующего кандидата"""
        try:
            if user_id not in self.user_states:
                self.send_message(user_id, "❌ Сначала начните поиск", self.get_main_keyboard())
                return

            state = self.user_states[user_id]
            candidates = state['candidates']
            current_index = state['current_index']

            if current_index >= len(candidates):
                self.send_message(
                    user_id,
                    "🎉 Вы просмотрели всех найденных людей!\n\nХотите начать новый поиск?",
                    self.get_main_keyboard()
                )
                del self.user_states[user_id]
                return

            candidate = candidates[current_index]

            # Получаем фотографии кандидата
            photos = self.vk_service.get_popular_photos(candidate['id'])

            # Формируем сообщение
            message = f"""👤 {candidate['first_name']} {candidate['last_name']}
🎂 {candidate.get('age', 'Не указан')} лет
🏙️ {candidate.get('city', 'Город не указан')}
🔗 https://vk.com/id{candidate['id']}

📸 Популярные фотографии профиля:"""

            # Формируем attachment для фотографий
            attachments = []
            for photo in photos[:3]:  # Максимум 3 фото
                attachments.append(f"photo{photo['owner_id']}_{photo['id']}")

            attachment = ','.join(attachments) if attachments else None

            self.send_message(user_id, message, self.get_search_keyboard(), attachment)

            # Сохраняем текущего кандидата
            state['current_candidate'] = candidate

        except Exception as e:
            logger.error(f"Ошибка в show_next_candidate для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при показе кандидата.")

    def handle_next_candidate(self, user_id):
        """Переход к следующему кандидату"""
        if user_id in self.user_states:
            self.user_states[user_id]['current_index'] += 1
            self.show_next_candidate(user_id)
        else:
            self.send_message(user_id, "❌ Сначала начните поиск", self.get_main_keyboard())

    def handle_add_to_favorites(self, user_id):
        """Добавление в избранное"""
        try:
            if user_id not in self.user_states:
                self.send_message(user_id, "❌ Сначала начните поиск", self.get_main_keyboard())
                return

            state = self.user_states[user_id]
            if 'current_candidate' not in state:
                self.send_message(user_id, "❌ Нет текущего кандидата")
                return

            candidate = state['current_candidate']

            # Добавляем в избранное в БД с именами
            success = self.db.add_to_favorites(
                user_id,
                candidate['id'],
                candidate['first_name'],
                candidate['last_name']
            )

            if success:
                self.send_message(user_id, f"❤️ {candidate['first_name']} добавлен(а) в избранное!")
            else:
                self.send_message(user_id, "❌ Этот человек уже в вашем списке избранных")

            # Автоматически переходим к следующему
            self.handle_next_candidate(user_id)

        except Exception as e:
            logger.error(f"Ошибка в handle_add_to_favorites для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при добавлении в избранное.")

    def handle_add_to_blacklist(self, user_id):
        """Добавление в черный список"""
        try:
            if user_id not in self.user_states:
                self.send_message(user_id, "❌ Сначала начните поиск", self.get_main_keyboard())
                return

            state = self.user_states[user_id]
            if 'current_candidate' not in state:
                self.send_message(user_id, "❌ Нет текущего кандидата")
                return

            candidate = state['current_candidate']

            # Добавляем в черный список в БД
            self.db.add_to_blacklist(user_id, candidate['id'])
            self.send_message(user_id, f"👎 {candidate['first_name']} добавлен(а) в черный список")

            # Автоматически переходим к следующему
            self.handle_next_candidate(user_id)

        except Exception as e:
            logger.error(f"Ошибка в handle_add_to_blacklist для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при добавлении в черный список.")

    def handle_show_favorites(self, user_id):
        """Показ списка избранных"""
        try:
            favorites = self.db.get_favorites(user_id)

            if not favorites:
                self.send_message(
                    user_id,
                    "💔 Ваш список избранных пуст.\n\nНачните поиск, чтобы найти интересных людей!",
                    self.get_main_keyboard()
                )
                return

            message = "❤️ Ваши избранные:\n\n"
            for i, fav in enumerate(favorites[:10], 1):  # Показываем максимум 10
                message += f"{i}. {fav['first_name']} {fav['last_name']}\n"
                message += f"   🔗 https://vk.com/id{fav['candidate_id']}\n\n"

            if len(favorites) > 10:
                message += f"... и еще {len(favorites) - 10} человек(а)"

            self.send_message(user_id, message, self.get_favorites_keyboard())

        except Exception as e:
            logger.error(f"Ошибка в handle_show_favorites для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при получении избранных.")

    def handle_clear_favorites(self, user_id):
        """Очистка списка избранных"""
        try:
            self.db.clear_favorites(user_id)
            self.send_message(
                user_id,
                "🗑️ Список избранных очищен!",
                self.get_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка в handle_clear_favorites для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при очистке избранных.")

    def handle_settings(self, user_id):
        """Показ меню настроек"""
        try:
            # Получаем текущие настройки пользователя
            user_info = self.db.get_user(user_id)
            if not user_info:
                self.send_message(user_id, "❌ Сначала запустите бота командой /start")
                return

            sex_text = "Не указан"
            if user_info.get('sex') == 1:
                sex_text = "Женский"
            elif user_info.get('sex') == 2:
                sex_text = "Мужской"

            settings_text = f"""⚙️ Ваши настройки поиска:

🚻 Пол: {sex_text}
🎂 Возраст: {user_info.get('age', 'Не указан')} лет
🏙️ Город: {user_info.get('city', 'Не указан')}

Выберите, что хотите изменить:"""

            self.send_message(user_id, settings_text, self.get_settings_keyboard())

        except Exception as e:
            logger.error(f"Ошибка в handle_settings для пользователя {user_id}: {e}")
            self.send_message(user_id, "❌ Ошибка при получении настроек.")

    def handle_change_sex(self, user_id):
        """Изменение пола для поиска"""
        try:
            # Сохраняем состояние - ожидаем ввод пола
            self.user_states[user_id] = {'mode': 'waiting_sex'}

            message = """🚻 Укажите ваш пол:

Отправьте:
1 - Женский
2 - Мужской

Это нужно, чтобы подбирать вам подходящих людей."""

            keyboard = VkKeyboard(one_time=True)
            keyboard.add_button('1 - Женский', VkKeyboardColor.POSITIVE)
            keyboard.add_button('2 - Мужской', VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button('❌ Отмена', VkKeyboardColor.NEGATIVE)

            self.send_message(user_id, message, keyboard.get_keyboard())

        except Exception as e:
            logger.error(f"Ошибка в handle_change_sex: {e}")
            self.send_message(user_id, "❌ Ошибка.")

    def handle_change_age(self, user_id):
        """Изменение возраста"""
        try:
            # Сохраняем состояние - ожидаем ввод возраста
            self.user_states[user_id] = {'mode': 'waiting_age'}

            message = """🎂 Укажите ваш возраст:

Отправьте число от 18 до 80.
Например: 25"""

            keyboard = VkKeyboard(one_time=True)
            keyboard.add_button('❌ Отмена', VkKeyboardColor.NEGATIVE)

            self.send_message(user_id, message, keyboard.get_keyboard())

        except Exception as e:
            logger.error(f"Ошибка в handle_change_age: {e}")
            self.send_message(user_id, "❌ Ошибка.")

    def handle_change_city(self, user_id):
        """Изменение города"""
        try:
            # Сохраняем состояние - ожидаем ввод города
            self.user_states[user_id] = {'mode': 'waiting_city'}

            message = """🏙️ Укажите ваш город:

Отправьте название города.
Например: Москва

Доступные города:
• Москва
• Санкт-Петербург
• Новосибирск
• Красноярск"""

            keyboard = VkKeyboard(one_time=True)
            keyboard.add_button('Москва', VkKeyboardColor.PRIMARY)
            keyboard.add_button('Санкт-Петербург', VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button('Новосибирск', VkKeyboardColor.PRIMARY)
            keyboard.add_button('Красноярск', VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button('❌ Отмена', VkKeyboardColor.NEGATIVE)

            self.send_message(user_id, message, keyboard.get_keyboard())

        except Exception as e:
            logger.error(f"Ошибка в handle_change_city: {e}")
            self.send_message(user_id, "❌ Ошибка.")

    def process_settings_input(self, user_id, text):
        """Обработка ввода настроек"""
        try:
            state = self.user_states.get(user_id, {})
            mode = state.get('mode')

            if not mode:
                return False

            # Обработка ввода пола
            if mode == 'waiting_sex':
                if text in ['1', '1 - женский', 'женский', 'ж']:
                    self.db.update_user_sex(user_id, 1)
                    self.send_message(user_id, "✅ Пол изменён на: Женский", self.get_settings_keyboard())
                    del self.user_states[user_id]
                    return True
                elif text in ['2', '2 - мужской', 'мужской', 'м']:
                    self.db.update_user_sex(user_id, 2)
                    self.send_message(user_id, "✅ Пол изменён на: Мужской", self.get_settings_keyboard())
                    del self.user_states[user_id]
                    return True
                else:
                    self.send_message(user_id, "❌ Неверный формат. Отправьте 1 или 2")
                    return True

            # Обработка ввода возраста
            elif mode == 'waiting_age':
                try:
                    age = int(text)
                    if 18 <= age <= 80:
                        self.db.update_user_age(user_id, age)
                        self.send_message(user_id, f"✅ Возраст изменён на: {age} лет", self.get_settings_keyboard())
                        del self.user_states[user_id]
                        return True
                    else:
                        self.send_message(user_id, "❌ Возраст должен быть от 18 до 80 лет")
                        return True
                except ValueError:
                    self.send_message(user_id, "❌ Отправьте число. Например: 25")
                    return True

            # Обработка ввода города
            elif mode == 'waiting_city':
                city = text.strip().lower()  # Приводим к нижнему регистру

                # Проверяем, есть ли такой город в списке
                if city in ['москва', 'санкт-петербург', 'новосибирск', 'пермь', 'казань',
                            'нижний новгород', 'челябинск', 'самара', 'омск', 'ростов-на-дону',
                            'уфа', 'красноярск', 'воронеж', 'волгоград', 'краснодар', 'саратов',
                            'тюмень', 'тольятти', 'ижевск', 'елабуга', 'набережные челны', 'екатеринбург']:

                    self.db.update_user_city(user_id, city)

                    # Проверяем что сохранилось
                    updated_user = self.db.get_user(user_id)
                    logger.info(f"После обновления город в БД: '{updated_user.get('city')}'")

                    self.send_message(user_id, f"✅ Город изменён на: {city.title()}", self.get_settings_keyboard())
                    del self.user_states[user_id]
                    return True
                else:
                    self.send_message(user_id,
                                      f"❌ Город '{city}' не найден в списке. Выберите из доступных или напишите точное название.")
                    return True

            return False

        except Exception as e:
            logger.error(f"Ошибка в process_settings_input: {e}")
            return False

    def handle_help(self, user_id):
        """Показ справки"""
        help_text = """ℹ️ Справка по VKinder:

🔍 Поиск - поиск людей для знакомства
❤️ Избранные - управление списком избранных
⚙️ Настройки - настройки профиля (в разработке)

Во время поиска:
❤️ В избранное - добавить человека в избранные
👎 В черный список - больше не показывать
▶️ Следующий - перейти к следующему человеку

📞 Техподдержка: karalash.anka@yandex.ru"""

        self.send_message(user_id, help_text, self.get_main_keyboard())

    def handle_message(self, event):
        """Обработка входящих сообщений"""
        user_id = event.user_id
        message = event.text.lower().strip()

        try:
            # Сначала проверяем, не ожидаем ли мы ввод настроек
            if self.process_settings_input(user_id, message):
                return

            # Отмена
            if message in ['❌ отмена', 'отмена']:
                if user_id in self.user_states:
                    del self.user_states[user_id]
                self.send_message(user_id, "❌ Отменено", self.get_main_keyboard())
                return

            # Команды и кнопки
            if message in ['/start', 'начать', 'привет', 'старт']:
                self.handle_start(user_id)

            elif message in ['🔍 поиск', 'поиск']:
                self.handle_search(user_id)

            elif message in ['▶️ следующий', 'следующий', 'далее']:
                self.handle_next_candidate(user_id)

            elif message in ['❤️ в избранное', 'в избранное', 'лайк']:
                self.handle_add_to_favorites(user_id)

            elif message in ['👎 в черный список', 'в черный список', 'дизлайк']:
                self.handle_add_to_blacklist(user_id)

            elif message in ['❤️ избранные', 'избранные']:
                self.send_message(user_id, "❤️ Избранные:", self.get_favorites_keyboard())

            elif message in ['📋 показать избранных', 'показать избранных']:
                self.handle_show_favorites(user_id)

            elif message in ['🗑️ очистить избранных', 'очистить избранных']:
                self.handle_clear_favorites(user_id)

            elif message in ['⚙️ настройки', 'настройки', '⚙ настройки', 'настройки⚙️', 'настройка']:
                self.handle_settings(user_id)

            elif message in ['🚻 изменить пол', 'изменить пол', 'пол']:
                self.handle_change_sex(user_id)

            elif message in ['🎂 изменить возраст', 'изменить возраст', 'возраст']:
                self.handle_change_age(user_id)

            elif message in ['🏙️ изменить город', 'изменить город', 'город', '🏙 изменить город']:
                self.handle_change_city(user_id)

            elif message in ['📊 показать настройки', 'показать настройки']:
                self.handle_settings(user_id)

            elif message in ['🏠 главное меню', 'главное меню', 'меню']:
                self.send_message(
                    user_id,
                    "🏠 Главное меню:",
                    self.get_main_keyboard()
                )

            elif message in ['ℹ️ помощь', 'помощь', 'help']:
                self.handle_help(user_id)

            else:
                # Логируем неизвестную команду для отладки
                logger.info(f"Неизвестная команда от {user_id}: '{message}'")

                # Неизвестная команда
                self.send_message(
                    user_id,
                    f"🤔 Не понимаю команду '{event.text}'.\n\nВыберите действие из меню:",
                    self.get_main_keyboard()
                )

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения от {user_id}: {e}")
            self.send_message(
                user_id,
                "❌ Произошла ошибка. Попробуйте позже.",
                self.get_main_keyboard()
            )

    def run(self):
        """Запуск бота"""
        logger.info("VKinder bot запущен!")
        print("🤖 VKinder bot запущен! Нажмите Ctrl+C для остановки.")

        try:
            for event in self.longpoll.listen():
                if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                    self.handle_message(event)

        except KeyboardInterrupt:
            logger.info("VKinder bot остановлен пользователем")
            print("\n🛑 VKinder bot остановлен")

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            print(f"❌ Критическая ошибка: {e}")

        finally:
            self.db.close()


if __name__ == "__main__":
    bot = VKinderBot()
    bot.run()