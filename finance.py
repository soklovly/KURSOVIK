import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import yfinance as yf
import asyncio

API_TOKEN = ''

if not API_TOKEN:
    raise ValueError("API_TOKEN не найден. Убедитесь, что он установлен в переменных окружения.")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создаем бота и диспетчер
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def validate_ticker(ticker):

# Проверяет, существует ли тикер. Возвращает True, если тикер существует, иначе False.

    try:
        test_data = yf.Ticker(ticker).history(period="1d")
        return not test_data.empty
    except Exception as e:
        logging.error(f"Ошибка при проверке тикера {ticker}: {e}")
        return False

def analyze_stock(stock_ticker):

# Анализирует акцию по стратегиям и возвращает рейтинг и текущую цену.

    try:
        stock_data = yf.download(stock_ticker, period="6mo", progress=False)

        if stock_data.empty or len(stock_data) < 50:
            return None, None

        stock_data['SMA50'] = stock_data['Close'].rolling(window=50).mean()
        stock_data['SMA200'] = stock_data['Close'].rolling(window=200).mean()
        stock_data['EMA12'] = stock_data['Close'].ewm(span=12).mean()
        stock_data['EMA26'] = stock_data['Close'].ewm(span=26).mean()
        stock_data['MACD'] = stock_data['EMA12'] - stock_data['EMA26']
        stock_data['Signal_Line'] = stock_data['MACD'].ewm(span=9).mean()
        delta = stock_data['Close'].diff(1)
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
        rs = gain / loss
        stock_data['RSI'] = 100 - (100 / (1 + rs))
        stock_data['BB_Lower'] = stock_data['Close'].rolling(window=20).mean() - 2 * stock_data['Close'].rolling(window=20).std()

        strategies = {
            "SMA Crossover": stock_data['SMA50'].iloc[-1] > stock_data['SMA200'].iloc[-1],
            "RSI Oversold": stock_data['RSI'].iloc[-1] < 30,
            "MACD Divergence": stock_data['MACD'].iloc[-1] > stock_data['Signal_Line'].iloc[-1],
            "Momentum": delta.iloc[-1] > 0,
            "Bollinger Bands": stock_data['Close'].iloc[-1] < stock_data['BB_Lower'].iloc[-1],
        }

        score = sum(strategies.values())
        current_price = stock_data['Close'].iloc[-1]
        return int(score), float(current_price)
    except Exception as e:
        logging.error(f"Ошибка при анализе акции {stock_ticker}: {e}")
        return None, None

@dp.message(Command(commands=['start', 'help']))
async def send_welcome(message: types.Message):
    await message.reply(
        "Привет! Я помогу тебе выбрать лучшую акцию для покупки при помощи 5 популярных стратегий.\n"
        "Введите до 10 тикеров акций через запятую, и я проанализирую их."
    )

@dp.message()
async def analyze_stocks(message: types.Message):
    tickers = [ticker.strip().upper() for ticker in message.text.split(",")]

    if len(tickers) > 10:
        await message.reply("Пожалуйста, укажите не более 10 тикеров.")
        return

    invalid_tickers = [ticker for ticker in tickers if not validate_ticker(ticker)]
    if invalid_tickers:
        await message.reply(f"Некорректные тикеры: {', '.join(invalid_tickers)}. Проверьте их.")
        return

    results = {}
    for ticker in tickers:
        try:
            score, price = analyze_stock(ticker)
            if score is not None and price is not None:
                results[ticker] = (score, price)
            else:
                results[ticker] = ("Не удалось получить данные", None)
        except Exception as e:
            logging.error(f"Ошибка при анализе тикера {ticker}: {e}")
            results[ticker] = ("Ошибка анализа", None)

    if not results:
        await message.reply("Не удалось проанализировать указанные акции. Проверьте тикеры.")
        return

    sorted_results = sorted(
        results.items(),
        key=lambda item: (-item[1][0] if isinstance(item[1][0], int) else 0, item[1][1] or float('inf'))
    )

    response = "Результаты анализа:\n\n"
    for ticker, result in sorted_results:
        score, price = result
        if isinstance(score, int):
            response += f"🔹 {ticker}: Удовлетворяется стратегий {score}, Цена ${price:.2f}\n"
        else:
            response += f"🔹 {ticker}: {score}\n"

    best_ticker = sorted_results[0][0]
    best_score = sorted_results[0][1][0]
    best_price = sorted_results[0][1][1]

    if isinstance(best_score, int):
        response += f"\n🌟 Лучшая акция: {best_ticker} (Стратегии: {best_score}, Цена: ${best_price:.2f})"

    await message.reply(response)

async def start_bot():
    await dp.start_polling(bot)
