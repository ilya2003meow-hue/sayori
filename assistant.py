import re
from datetime import date, datetime, timedelta

from database import PROCEDURES, available_slots, get_db
from translations import PROCEDURE_CONTENT, SETTINGS_CONTENT, merged_ui

INTENT_KEYWORDS = {
    'greeting': {
        'ru': ['привет', 'здравств', 'добрый день', 'доброе утро', 'добрый вечер', 'салют'],
        'kk': ['сәлем', 'сәлеметсіз', 'қайырлы күн', 'қайырлы таң', 'қайырлы кеш'],
        'en': ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening'],
    },
    'thanks': {
        'ru': ['спасибо', 'благодар'],
        'kk': ['рақмет', 'рахмет', 'алғыс'],
        'en': ['thanks', 'thank', 'appreciate'],
    },
    'bye': {
        'ru': ['до свидания', 'пока', 'до встречи'],
        'kk': ['сау бол', 'қош', 'көріскенше'],
        'en': ['bye', 'goodbye', 'see you'],
    },
    'cancel': {
        'ru': ['отмен', 'перенес'],
        'kk': ['болдырмау', 'көшіру', 'кейінге'],
        'en': ['cancel', 'reschedule', 'postpone'],
    },
    'booking': {
        'ru': ['запис', 'забронир', 'бронь', 'как попасть'],
        'kk': ['жазыл', 'жазылу', 'бронь'],
        'en': ['book', 'booking', 'reserve', 'reservation', 'appointment', 'make a booking', 'schedule a'],
    },
    'my_bookings': {
        'ru': ['мои записи', 'моя запись', 'мои брони', 'мой заказ', 'я записан', 'мои визиты'],
        'kk': ['менің жазбаларым', 'менің жазылуым', 'менің бронь'],
        'en': ['my bookings', 'my booking', 'my appointments', 'my appointment', 'my reservation', 'i am booked'],
    },
    'slots': {
        'ru': ['свободное время', 'свободные окна', 'свободные места', 'когда можно', 'есть места', 'ближайшее время', 'ближайшие', 'какие окна', 'свободно'],
        'kk': ['бос уақыт', 'бос орын', 'қашан болады', 'жақын уақыт'],
        'en': ['free slots', 'free slot', 'available', 'availability', 'when is free', 'openings', 'free time', 'earliest'],
    },
    'payment': {
        'ru': ['оплат', 'наличн', 'карт', 'касп', 'kaspi', 'предоплат', 'как платить'],
        'kk': ['төлеу', 'төлем', 'ақша', 'карта', 'каспи'],
        'en': ['pay', 'payment', 'cash', 'card', 'kaspi', 'prepay'],
    },
    'gift': {
        'ru': ['сертификат', 'подарочн', 'в подарок', 'подарок'],
        'kk': ['сертификат', 'сыйлық', 'сыйлык'],
        'en': ['gift', 'certificate', 'voucher', 'present'],
    },
    'masters': {
        'ru': ['мастер', 'специалист', 'персонал', 'кто делает', 'кто будет', 'кто работает'],
        'kk': ['шебер', 'маман', 'қызметкер'],
        'en': ['master', 'specialist', 'staff', 'who will do', 'who does', 'therapist'],
    },
    'hours': {
        'ru': ['часы', 'режим', 'время работы', 'во сколько', 'график', 'открыт', 'работаете'],
        'kk': ['жұмыс уақыты', 'сағат', 'ашық', 'уақытта'],
        'en': ['hours', 'opening', 'open', 'when do you work', 'schedule', 'what time'],
    },
    'address': {
        'ru': ['адрес', 'где находит', 'как добраться', 'как доехать', 'расположен'],
        'kk': ['мекенжай', 'адрес', 'қайда', 'қалай жету', 'қалай бару'],
        'en': ['address', 'where are you', 'where is', 'location', 'how to get', 'directions'],
    },
    'phone': {
        'ru': ['телефон', 'позвонить', 'звонок', 'номер телефона', 'связаться'],
        'kk': ['телефон', 'қоңырау', 'нөмір'],
        'en': ['phone', 'call', 'number', 'contact number', 'ring'],
    },
    'age': {
        'ru': ['возраст', 'сколько лет', 'с какого возраста', 'лет ребёнку', 'лет ребенку', 'малыш'],
        'kk': ['жасы', 'жас', 'неше жас', 'кішкентай'],
        'en': ['age', 'years old', 'how old', 'toddler', 'little kid'],
    },
    'safety': {
        'ru': ['безопасн', 'гипоаллерген', 'стерильн', 'косметика', 'краски'],
        'kk': ['қауіпсіз', 'гипоаллергенді', 'стерильді', 'косметика'],
        'en': ['safe', 'safety', 'hypoallergenic', 'allergic', 'allergy', 'sterile', 'cosmetics'],
    },
    'reviews': {
        'ru': ['отзыв'],
        'kk': ['пікір'],
        'en': ['review', 'reviews', 'rating', 'feedback'],
    },
    'price': {
        'ru': ['цена', 'цены', 'цену', 'ценах', 'стоимость', 'сколько стоит', 'сколько', 'прайс', 'недорого', 'скидк'],
        'kk': ['баға', 'бағасы', 'қанша тұрады', 'қанша', 'құны', 'жеңілдік'],
        'en': ['price', 'prices', 'cost', 'costs', 'how much', 'expensive', 'discount', 'cheap'],
    },
    'procedures': {
        'ru': ['процедур', 'услуг', 'меню', 'каталог', 'что есть', 'что можно', 'какие бывают', 'список'],
        'kk': ['процедур', 'қызмет', 'не бар', 'тізім', 'мәзір'],
        'en': ['procedure', 'procedures', 'treatment', 'treatments', 'service', 'services', 'what do you offer', 'menu', 'options', 'list'],
    },
}

PROC_KEYWORDS = {
    1: {
        'ru': ['маникюр', 'ногот', 'ногти', 'лак для ногтей'],
        'kk': ['маникюр', 'тырнақ'],
        'en': ['manicure', 'nails', 'nail', 'polish'],
    },
    2: {
        'ru': ['педикюр', 'ножки', 'пятк', 'пальчики ног'],
        'kk': ['педикюр', 'аяқ'],
        'en': ['pedicure', 'feet', 'foot', 'toes'],
    },
    3: {
        'ru': ['причёск', 'прическ', 'волос', 'косы', 'косичк', 'локоны', 'корона', 'диадем'],
        'kk': ['шаш', 'бұрым', 'шаш үлгісі'],
        'en': ['hair', 'hairstyle', 'hairdo', 'braid', 'curls', 'tiara', 'rapunzel'],
    },
    4: {
        'ru': ['аквагрим', 'грим', 'фейс', 'бабочк', 'единорог'],
        'kk': ['аквагрим', 'бет бояу', 'бояу'],
        'en': ['face painting', 'facepaint', 'butterfly', 'unicorn', 'glitter art'],
    },
    5: {
        'ru': ['спа-уход', 'спа уход', 'уход', 'массаж', 'молочн', 'ванночк', 'расслаб'],
        'kk': ['спа-күтім', 'спа күтім', 'күтім', 'массаж'],
        'en': ['spa care', 'spa treatment', 'massage', 'milk bath', 'relax'],
    },
    6: {
        'ru': ['вечеринк', 'праздник', 'бал принцесс', 'юбилей', 'подружк', 'торжеств'],
        'kk': ['кеш', 'мереке', 'ханшалар балы'],
        'en': ['party', 'celebration', 'spa ball', 'friends over'],
    },
    7: {
        'ru': ['день рождения', 'именин', 'др', 'торт', 'свеч'],
        'kk': ['туған күн', 'туған кун', 'туган кун'],
        'en': ['birthday', 'b-day', 'cake', 'candles'],
    },
    8: {
        'ru': ['выпускн', 'выпускной', 'прощай'],
        'kk': ['бітіру', 'бітіру кеші'],
        'en': ['graduation', 'graduate', 'prom', 'school leavers'],
    },
    9: {
        'ru': ['пижамная вечеринка', 'пижам', 'ночь чудес', 'какао', 'маршмеллоу'],
        'kk': ['пижама', 'пижама кеші'],
        'en': ['pajama party', 'pyjama party', 'pajama', 'pyjama', 'sleepover', 'hot chocolate'],
    },
    10: {
        'ru': ['наурыз', 'весенн', 'баурсак'],
        'kk': ['наурыз', 'көктем', 'бауырсақ'],
        'en': ['nauryz', 'spring holiday', 'baursak'],
    },
}

TEXTS = {
    'ru': {
        'greeting': 'Здравствуйте! Я фея-помощница Princess Spa. Покажу процедуры и цены, свободное время на сегодня и завтра, а после входа — ваши ближайшие записи. Подскажу, как записаться, отменить визит и связаться с администратором. Выберите вопрос или напишите свой.',
        'thanks': 'Всегда рада помочь! Если появятся ещё вопросы — пишите.',
        'bye': 'До встречи в Princess Spa!',
        'booking_logged': 'Записаться просто:\n1. Выберите процедуру.\n2. Выберите дату и свободное время — запись открыта на 30 дней вперёд.\n3. Укажите имя и возраст ребёнка.\nАдминистратор подтвердит запись. Открыть форму можно кнопкой ниже.',
        'booking_anon': 'Записаться просто:\n1. Выберите процедуру.\n2. Выберите дату и свободное время — запись открыта на 30 дней вперёд.\n3. Укажите имя и возраст ребёнка.\nДля записи нужно войти или зарегистрироваться — это займёт минуту. Администратор подтвердит запись.',
        'cancel': 'Отменить запись можно в личном кабинете в один клик. Чтобы перенести визит — отмените запись и создайте новую, или позвоните нам: {phone}.',
        'hours': 'Работаем {hours}.\nАдрес: {address}',
        'address': 'Мы находимся по адресу: {address}.\nВход со стороны улицы, розовая вывеска с короной — не пропустите.',
        'phone': 'Наш телефон: {phone}.\nРаботаем {hours} — звоните, поможем с записью.',
        'age': 'Ждём принцесс от 3 до 14 лет. Самым маленьким советуем аквагрим и причёски, маникюр — с 5 лет.',
        'safety': 'Безопасность прежде всего: стерильные инструменты, одноразовые расходники для каждой гостьи и только гипоаллергенная детская косметика на водной основе.',
        'reviews': 'Отзывы мам можно прочитать на странице «Отзывы» — там же после визита можно оставить свой.',
        'payment': 'Онлайн-оплаты на сайте нет. Способы оплаты и условия предоплаты уточните у администратора: {phone}.',
        'gift': 'Возможность покупки подарочного сертификата, сумму и срок действия уточните у администратора: {phone}. В чате оформить сертификат нельзя.',
        'masters': 'В каталоге есть маникюр, причёски и аквагрим. Узнать, какой мастер будет на вашем визите, можно у администратора: {phone}.',
        'my_bookings_logged': 'Ваши ближайшие записи:\n{list}\nОтменить или перенести визит можно в личном кабинете.',
        'my_bookings_line': '• {date} в {time} — {name} ({status})',
        'my_bookings_empty': 'Ближайших записей нет. Загляните в меню и выберите удобное время — кнопка ниже.',
        'my_bookings_anon': 'Чтобы посмотреть свои записи, войдите в аккаунт — кнопка ниже.',
        'my_bookings_staff': 'Вы вошли как сотрудник — все записи клиентов видны в панели персонала.',
        'slots_proc': 'Свободное время на «{name}» ({dur} мин):\n{lines}\nЭто ещё не бронь — выберите время в форме записи.',
        'slots_day': '{day}: {slots}',
        'slots_empty_day': 'нет окон',
        'slots_none': 'На сегодня и завтра свободных окон нет. Позвоните нам: {phone} — подберём удобное время.',
        'slots_noproc': 'Подскажу свободные окна — на какую процедуру посмотреть время? Вот меню:\n{menu}',
        'today_label': 'сегодня',
        'tomorrow_label': 'завтра',
        'menu_intro': 'Вот наше сказочное меню:\n{menu}\nКнопка ниже откроет каталог — там можно выбрать время.',
        'price_intro': 'Цены на процедуры:\n{menu}\nСпросите про любую процедуру — расскажу подробнее.',
        'menu_line': '• {name} — {dur} мин, {price}',
        'proc_detail': '{name}\n{cat} · {dur} мин · {price}\n{desc}',
        'fallback': 'Простите, я не совсем поняла вопрос. Я знаю всё о процедурах, ценах, записи, адресе и часах работы — выберите подсказку ниже или позвоните нам: {phone}.',
    },
    'kk': {
        'greeting': 'Сәлеметсіз бе! Мен Princess Spa періште-көмекшісімін. Процедуралар мен бағаларды, бүгін және ертеңгі бос уақытты, ал кіргеннен кейін жақын жазбаларыңызды көрсетемін. Жазылу, жазбаны болдырмау және әкімшімен байланысу жолдарын айтамын. Сұрақты таңдаңыз немесе өзіңіз жазыңыз.',
        'thanks': 'Көмектескеніме қуаныштымын! Тағы сұрағыңыз болса — жазыңыз.',
        'bye': 'Princess Spa-да күтеміз!',
        'booking_logged': 'Жазылу оңай:\n1. Процедураны таңдаңыз.\n2. Күн мен бос уақытты таңдаңыз — жазба 30 күн алға ашық.\n3. Баланың аты мен жасын жазыңыз.\nӘкімші жазбаны растайды. Төмендегі батырма форманы ашады.',
        'booking_anon': 'Жазылу оңай:\n1. Процедураны таңдаңыз.\n2. Күн мен бос уақытты таңдаңыз — жазба 30 күн алға ашық.\n3. Баланың аты мен жасын жазыңыз.\nЖазылу үшін кіріңіз немесе тіркеліңіз — бір минут. Әкімші жазбаны растайды.',
        'cancel': 'Жазбаны жеке кабинетте бір басумен болдырмауға болады. Көшіру үшін — жазбаны болдырмап, жаңасын жасаңыз немесе қоңырау шалыңыз: {phone}.',
        'hours': 'Жұмыс уақытымыз: {hours}.\nМекенжай: {address}',
        'address': 'Мекенжайымыз: {address}.\nКіреберіс көше жағынан — тәжді қызғылт белгі.',
        'phone': 'Телефонымыз: {phone}.\nЖұмыс уақыты: {hours} — қоңырау шалыңыз, жазылуға көмектесеміз.',
        'age': '3-тен 14 жасқа дейінгі ханшаларды күтеміз. Кішкентайларға аквагрим мен шаш үлгілерін ұсынамыз, маникюр — 5 жастан.',
        'safety': 'Қауіпсіздік бірінші орында: стерильді құралдар, әр қонаққа бір реттік материалдар және тек су негізіндегі гипоаллергенді балалар косметикасы.',
        'reviews': 'Аналар пікірлерін «Пікірлер» бетінен оқыңыз — келгеннен кейін өз пікіріңізді қалдыра аласыз.',
        'payment': 'Сайтта онлайн төлем жоқ. Төлем тәсілдері мен алдын ала төлеу шарттарын әкімшіден нақтылаңыз: {phone}.',
        'gift': 'Сыйлық сертификатын сатып алу мүмкіндігін, сомасы мен жарамдылық мерзімін әкімшіден нақтылаңыз: {phone}. Чатта сертификат ресімделмейді.',
        'masters': 'Каталогта маникюр, шаш үлгілері және аквагрим бар. Сізді қай шебер қабылдайтынын әкімшіден сұраңыз: {phone}.',
        'my_bookings_logged': 'Жақын жазбаларыңыз:\n{list}\nЖеке кабинетте болдырмауға немесе көшіруге болады.',
        'my_bookings_line': '• {date} {time} — {name} ({status})',
        'my_bookings_empty': 'Жақын жазба жоқ. Мәзірді қарап, уақыт таңдаңыз — батырма төменде.',
        'my_bookings_anon': 'Жазбаларыңызды көру үшін кіріңіз — батырма төменде.',
        'my_bookings_staff': 'Сіз қызметкер ретінде кірдіңіз — барлық жазба қызметкер панелінде көрінеді.',
        'slots_proc': '«{name}» ({dur} мин) бос уақыты:\n{lines}\nБұл әлі бронь емес — жазылу формасында уақытты таңдаңыз.',
        'slots_day': '{day}: {slots}',
        'slots_empty_day': 'бос орын жоқ',
        'slots_none': 'Бүгін мен ертеңге бос орын жоқ. Қоңырау шалыңыз: {phone} — ыңғайлы уақыт таңдаймыз.',
        'slots_noproc': 'Бос уақытты айтамын — қай процедураға қарайын? Мәзір:\n{menu}',
        'today_label': 'бүгін',
        'tomorrow_label': 'ертең',
        'menu_intro': 'Біздің ертегі мәзіріміз:\n{menu}\nТөмендегі батырма каталогты ашады — уақытты сонда таңдайсыз.',
        'price_intro': 'Процедуралар бағасы:\n{menu}\nКез келген процедура туралы сұрасаңыз, толық айтамын.',
        'menu_line': '• {name} — {dur} мин, {price}',
        'proc_detail': '{name}\n{cat} · {dur} мин · {price}\n{desc}',
        'fallback': 'Кешіріңіз, сұрағыңызды толық түсінбедім. Мен процедуралар, бағалар, жазба, мекенжай және жұмыс уақыты туралы білемін — төмендегі кеңесті таңдаңыз немесе қоңырау шалыңыз: {phone}.',
    },
    'en': {
        'greeting': 'Hello! I am the Princess Spa fairy assistant. I can show treatments, prices, free slots today and tomorrow, and your upcoming bookings after login. I can help you book, cancel a visit or contact the administrator. Pick a question or type your own.',
        'thanks': 'Happy to help! Ask me anything else.',
        'bye': 'See you at Princess Spa!',
        'booking_logged': 'Booking is easy:\n1. Choose a treatment.\n2. Pick a date and a free time slot — booking is open 30 days ahead.\n3. Enter your child\'s name and age.\nThe admin will confirm your booking. The button below opens the form.',
        'booking_anon': 'Booking is easy:\n1. Choose a treatment.\n2. Pick a date and a free time slot — booking is open 30 days ahead.\n3. Enter your child\'s name and age.\nYou need to log in or register to book — it takes a minute. The admin will confirm your booking.',
        'cancel': 'You can cancel a booking in your personal account in one click. To reschedule, cancel and book a new time, or call us: {phone}.',
        'hours': 'We work {hours}.\nAddress: {address}',
        'address': 'We are at: {address}.\nEnter from the street side — look for the pink crown sign.',
        'phone': 'Our phone: {phone}.\nWe work {hours} — call us and we will help you book.',
        'age': 'We welcome princesses aged 3 to 14. For the little ones we suggest face painting and hairstyles; manicures from age 5.',
        'safety': 'Safety first: sterile tools, disposable supplies for every guest and only water-based hypoallergenic kids\' cosmetics.',
        'reviews': 'Read moms\' reviews on the Reviews page — you can leave your own there after a visit.',
        'payment': 'There is no online payment on this website. Ask the administrator about payment methods and any deposit: {phone}.',
        'gift': 'Ask the administrator about gift certificate availability, amounts and validity: {phone}. Certificates cannot be purchased in this chat.',
        'masters': 'The catalog includes manicures, hairstyles and face painting. Ask the administrator which specialist will be at your appointment: {phone}.',
        'my_bookings_logged': 'Your upcoming appointments:\n{list}\nYou can cancel or reschedule in your personal account.',
        'my_bookings_line': '• {date} at {time} — {name} ({status})',
        'my_bookings_empty': 'No upcoming appointments. Browse the menu and pick a time — button below.',
        'my_bookings_anon': 'Log in to see your appointments — button below.',
        'my_bookings_staff': 'You are signed in as staff — all client bookings are visible in the staff panel.',
        'slots_proc': 'Free slots for {name} ({dur} min):\n{lines}\nThese are not reserved — choose a time in the booking form.',
        'slots_day': '{day}: {slots}',
        'slots_empty_day': 'fully booked',
        'slots_none': 'No free slots today or tomorrow. Call us: {phone} — we will find a convenient time.',
        'slots_noproc': 'I can check free slots — which treatment are you interested in? Here is the menu:\n{menu}',
        'today_label': 'today',
        'tomorrow_label': 'tomorrow',
        'menu_intro': 'Here is our fairytale menu:\n{menu}\nThe button below opens the catalog where you can pick a time.',
        'price_intro': 'Our prices:\n{menu}\nAsk me about any treatment and I will tell you more.',
        'menu_line': '• {name} — {dur} min, {price}',
        'proc_detail': '{name}\n{cat} · {dur} min · {price}\n{desc}',
        'fallback': 'Sorry, I did not quite get that. I know everything about treatments, prices, booking, address and hours — pick a suggestion below, or call us: {phone}.',
    },
}

LINKS = {
    'ru': {'all': 'Все процедуры', 'book': 'Записаться', 'choose': 'Выбрать процедуру', 'contacts': 'Контакты', 'reviews': 'Отзывы', 'login': 'Войти', 'cabinet': 'Мой кабинет', 'panel': 'Панель персонала'},
    'kk': {'all': 'Барлық процедуралар', 'book': 'Жазылу', 'choose': 'Процедура таңдау', 'contacts': 'Байланыс', 'reviews': 'Пікірлер', 'login': 'Кіру', 'cabinet': 'Менің кабинетім', 'panel': 'Қызметкер панелі'},
    'en': {'all': 'All treatments', 'book': 'Book now', 'choose': 'Choose a treatment', 'contacts': 'Contacts', 'reviews': 'Reviews', 'login': 'Log in', 'cabinet': 'My account', 'panel': 'Staff panel'},
}

STATUS_TEXT = {
    'ru': {'new': 'новая', 'confirmed': 'подтверждена', 'completed': 'завершена', 'cancelled': 'отменена'},
    'kk': {'new': 'жаңа', 'confirmed': 'расталған', 'completed': 'аяқталған', 'cancelled': 'болдырылмаған'},
    'en': {'new': 'new', 'confirmed': 'confirmed', 'completed': 'completed', 'cancelled': 'cancelled'},
}

DAY_WORDS = {
    'today': ['сегодня', 'бүгін', 'bugin', 'today'],
    'tomorrow': ['завтра', 'ертең', 'erten', 'tomorrow'],
}

SUGG = {
    'ru': {
        'start': ['Какие есть процедуры?', 'Свободные окна', 'Мои записи', 'Как оплатить?', 'Подарочный сертификат', 'Кто делает процедуры?'],
        'after_proc': ['Как записаться?', 'Мои записи', 'Какие ещё есть процедуры?'],
        'after_info': ['Свободные окна', 'Мои записи', 'Адрес и часы работы'],
        'slot_question': 'Свободное время: {name} {day}',
    },
    'kk': {
        'start': ['Қандай процедуралар бар?', 'Бос уақыт', 'Менің жазбаларым', 'Қалай төлеу керек?', 'Сыйлық сертификаты', 'Шеберлер туралы'],
        'after_proc': ['Қалай жазылуға болады?', 'Менің жазбаларым', 'Тағы қандай процедуралар бар?'],
        'after_info': ['Бос уақыт', 'Менің жазбаларым', 'Мекенжай және жұмыс уақыты'],
        'slot_question': 'Бос уақыт: {name} {day}',
    },
    'en': {
        'start': ['What treatments do you have?', 'Free slots', 'My bookings', 'How can I pay?', 'Gift certificates', 'Who does the treatments?'],
        'after_proc': ['How do I book?', 'My bookings', 'What other treatments?'],
        'after_info': ['Free slots', 'My bookings', 'Address and hours'],
        'slot_question': 'Free slots: {name} {day}',
    },
}


def _norm(s):
    s = s.lower().replace('ё', 'е')
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s-]', ' ', s)).strip()


def _prep(source):
    return {key: list(dict.fromkeys(_norm(k) for kws in per_lang.values() for k in kws))
            for key, per_lang in source.items()}


_INTENT_KW = _prep(INTENT_KEYWORDS)
_PROC_KW = _prep(PROC_KEYWORDS)


def _hits(msg, keywords):
    score = 0
    for k in keywords:
        if len(k) <= 3:
            if re.search(r'\b' + re.escape(k) + r'\b', msg):
                score += len(k)
        elif k in msg:
            score += len(k)
    return score


def _ranked(kw_map, msg):
    return sorted(((k, _hits(msg, kws)) for k, kws in kw_map.items()), key=lambda x: -x[1])


def _fmt_price(v):
    return f'{int(v):,}'.replace(',', ' ') + ' ₸'


def _load(lang):
    conn = get_db()
    procs = []
    for row in conn.execute('SELECT id, name, description, category, duration_min, price FROM procedures WHERE active=1 AND published=1 ORDER BY id'):
        p = dict(row)
        p['source_name'] = p['name']
        overlay = PROCEDURE_CONTENT.get(p['id'], {}).get(lang)
        if overlay and 1 <= p['id'] <= len(PROCEDURES) and (p['name'], p['description']) == PROCEDURES[p['id'] - 1][:2]:
            p.update(overlay)
        p['cat_loc'] = merged_ui(lang)['cats'].get(p['category'], p['category'])
        procs.append(p)
    st = {}
    for k in ('phone', 'address', 'hours'):
        row = conn.execute('SELECT value FROM settings WHERE key=?', (k,)).fetchone()
        st[k] = row['value'] if row else ''
    overlay = SETTINGS_CONTENT.get(lang, {})
    st.update({k: v for k, v in overlay.items() if k in st})
    conn.close()
    return procs, st


def _upcoming_bookings(user_id, lang):
    now = datetime.now()
    conn = get_db()
    rows = conn.execute(
        'SELECT b.date, b.time, b.status, b.procedure_id, p.name FROM bookings b '
        'JOIN procedures p ON p.id=b.procedure_id '
        "WHERE b.client_id=? AND (b.date>? OR (b.date=? AND b.time>=?)) AND b.status IN ('new','confirmed') "
        'ORDER BY b.date, b.time LIMIT 3',
        (user_id, now.date().isoformat(), now.date().isoformat(), now.strftime('%H:%M'))).fetchall()
    conn.close()
    result = []
    for row in rows:
        r = dict(row)
        pid = r['procedure_id']
        overlay = PROCEDURE_CONTENT.get(pid, {}).get(lang)
        if overlay and 1 <= pid <= len(PROCEDURES) and r['name'] == PROCEDURES[pid - 1][0]:
            r['name'] = overlay['name']
        result.append(r)
    return result


def _free_slots(procedure, day):
    conn = get_db()
    try:
        return available_slots(conn, procedure, day)
    finally:
        conn.close()


def answer(message, lang, user):
    if lang not in TEXTS:
        lang = 'ru'
    msg = _norm(message or '')
    procs, st = _load(lang)
    t = TEXTS[lang]
    links = LINKS[lang]
    sugg = SUGG[lang]

    if not msg:
        return {'reply': t['greeting'], 'suggestions': sugg['start'], 'link': None}

    ranked = _ranked(_INTENT_KW, msg)
    intent, score = ranked[0]
    if intent == 'greeting' and ranked[1][1] > 0:
        intent, score = ranked[1]
    if score == 0:
        intent = None
    if intent not in ('cancel', 'thanks', 'bye'):
        for specific in ('my_bookings', 'slots', 'gift', 'payment', 'masters'):
            if _hits(msg, _INTENT_KW[specific]):
                intent = specific
                break
    proc_words = {}
    for p in procs:
        pid = p['id']
        keywords = [_norm(p['name']), _norm(p['source_name'])]
        if 1 <= pid <= len(PROCEDURES) and p['source_name'] == PROCEDURES[pid - 1][0]:
            keywords.extend(_PROC_KW.get(pid, []))
        proc_words[pid] = keywords
    proc_ranked = _ranked(proc_words, msg)
    proc = proc_ranked[0][0] if proc_ranked and proc_ranked[0][1] else None
    procs_by_id = {p['id']: p for p in procs}

    def proc_block(p):
        return t['proc_detail'].format(name=p['name'], cat=p['cat_loc'], dur=p['duration_min'],
                                       price=_fmt_price(p['price']), desc=p['description'])

    def menu():
        return '\n'.join(t['menu_line'].format(name=p['name'], dur=p['duration_min'], price=_fmt_price(p['price'])) for p in procs)

    reply, link, sg = None, None, sugg['after_info']

    if intent == 'thanks':
        reply = t['thanks']
    elif intent == 'bye':
        reply = t['bye']
    elif intent == 'greeting':
        reply = t['greeting']
        sg = sugg['start']
    elif intent == 'cancel':
        reply = t['cancel'].format(phone=st['phone'])
    elif intent == 'my_bookings':
        if not user:
            reply = t['my_bookings_anon']
            link = {'url': '/login', 'label': links['login']}
        elif user.get('role') in ('admin', 'owner'):
            reply = t['my_bookings_staff']
            link = {'url': '/staff', 'label': links['panel']}
        else:
            rows = _upcoming_bookings(user['id'], lang)
            if rows:
                statuses = STATUS_TEXT.get(lang, STATUS_TEXT['ru'])
                lines = '\n'.join(
                    t['my_bookings_line'].format(
                        date=r['date'], time=r['time'],
                        name=r['name'],
                        status=statuses.get(r['status'], r['status']))
                    for r in rows)
                reply = t['my_bookings_logged'].format(list=lines)
                link = {'url': '/cabinet', 'label': links['cabinet']}
            else:
                reply = t['my_bookings_empty']
                link = {'url': '/procedures', 'label': links['all']}
    elif intent == 'slots':
        if proc in procs_by_id:
            p = procs_by_id[proc]
            today_hit = any(re.search(r'\b' + re.escape(w) + r'\b', msg) for w in DAY_WORDS['today'])
            tomorrow_hit = any(re.search(r'\b' + re.escape(w) + r'\b', msg) for w in DAY_WORDS['tomorrow'])
            if today_hit and not tomorrow_hit:
                days = [(t['today_label'], date.today())]
            elif tomorrow_hit and not today_hit:
                days = [(t['tomorrow_label'], date.today() + timedelta(days=1))]
            else:
                days = [(t['today_label'], date.today()),
                        (t['tomorrow_label'], date.today() + timedelta(days=1))]
            lines = []
            for label, day in days:
                free = _free_slots(p, day)
                lines.append(t['slots_day'].format(day=label, slots=', '.join(free) if free else t['slots_empty_day']))
            reply = t['slots_proc'].format(name=p['name'], dur=p['duration_min'], lines='\n'.join(lines))
            link = {'url': f'/booking/{p["id"]}', 'label': links['book']}
            sg = sugg['after_proc']
        else:
            reply = t['slots_noproc'].format(menu=menu())
            link = {'url': '/procedures', 'label': links['all']}
    elif intent in ('payment', 'gift', 'masters'):
        reply = t[intent].format(phone=st['phone'])
        link = {'url': '/contacts', 'label': links['contacts']}
    elif intent == 'booking':
        reply = t['booking_logged'] if user else t['booking_anon']
        if proc in procs_by_id:
            link = {'url': f'/booking/{proc}', 'label': links['book']}
        else:
            link = {'url': '/procedures', 'label': links['choose']}
        sg = sugg['after_proc']
    elif intent == 'hours':
        reply = t['hours'].format(hours=st['hours'], address=st['address'])
    elif intent == 'address':
        reply = t['address'].format(address=st['address'])
        link = {'url': '/contacts', 'label': links['contacts']}
    elif intent == 'phone':
        reply = t['phone'].format(phone=st['phone'], hours=st['hours'])
        link = {'url': '/contacts', 'label': links['contacts']}
    elif intent == 'age':
        reply = t['age']
    elif intent == 'safety':
        reply = t['safety']
    elif intent == 'reviews':
        reply = t['reviews']
        link = {'url': '/reviews', 'label': links['reviews']}
    elif intent in ('price', 'procedures') or proc in procs_by_id:
        if proc in procs_by_id:
            p = procs_by_id[proc]
            reply = proc_block(p)
            link = {'url': f'/booking/{p["id"]}', 'label': links['book']}
            sg = sugg['after_proc']
        elif intent == 'price':
            reply = t['price_intro'].format(menu=menu())
            link = {'url': '/procedures', 'label': links['all']}
        else:
            reply = t['menu_intro'].format(menu=menu())
            link = {'url': '/procedures', 'label': links['all']}
    else:
        reply = t['fallback'].format(phone=st['phone'])
        sg = sugg['start']

    if intent == 'slots' and proc not in procs_by_id:
        sg = [sugg['slot_question'].format(name=p['name'], day=t['tomorrow_label']) for p in procs]
    elif proc in procs_by_id and intent in ('slots', 'booking', 'price', 'procedures', None):
        sg = [sugg['slot_question'].format(name=procs_by_id[proc]['name'], day=t[label])
              for label in ('today_label', 'tomorrow_label')] + sugg['after_proc'][:1]
    return {'reply': reply, 'suggestions': sg, 'link': link}
